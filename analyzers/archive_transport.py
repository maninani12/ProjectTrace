"""Bounded duplex archive IPC: only selected byte ranges cross the boundary.

The coordinator decrypts an authorized stream but never interprets ZIP/zlib.
No paths, inherited descriptors, keys or plaintext disk files reach the parser.
"""

import base64
import hashlib
import json
import os
import selectors
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

from analyzers import sandbox
from backend.intake_errors import IntakeError

CHUNK = 512_000
PACKET = 1_000_000


class Wire:
    def __init__(self, process, seconds):
        self.process, self.buffer = process, bytearray()
        self.deadline = time.monotonic() + seconds
        for stream in (process.stdin, process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)

    def wait(self, stream, event):
        with selectors.DefaultSelector() as selector:
            selector.register(stream, event)
            selector.register(self.process.stderr, selectors.EVENT_READ)
            while time.monotonic() < self.deadline:
                for key, _ in selector.select(min(0.1, max(0, self.deadline - time.monotonic()))):
                    if key.fileobj is stream:
                        return
                    # Drain bounded chunks; raw source/exception text is never exported.
                    if not os.read(key.fd, 65536):
                        selector.unregister(key.fileobj)
            raise sandbox.SandboxFailure("ARCHIVE_HELPER_TIMEOUT")

    def write(self, value):
        offset = 0
        while offset < len(value):
            self.wait(self.process.stdin, selectors.EVENT_WRITE)
            try:
                offset += os.write(self.process.stdin.fileno(), value[offset:offset + 65536])
            except BrokenPipeError:
                raise sandbox.SandboxFailure("ARCHIVE_HELPER_CRASH") from None

    def line(self, maximum=PACKET):
        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                if newline > maximum:
                    raise sandbox.SandboxFailure("ARCHIVE_PACKET_BUDGET")
                value = bytes(self.buffer[:newline])
                del self.buffer[:newline + 1]
                return value
            if len(self.buffer) > maximum:
                raise sandbox.SandboxFailure("ARCHIVE_PACKET_BUDGET")
            self.wait(self.process.stdout, selectors.EVENT_READ)
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise sandbox.SandboxFailure("ARCHIVE_HELPER_CRASH")
            self.buffer.extend(data)


def archive_items(stream, policy, *, validate_only=False, seconds=150, sort_paths=False, manifest_only=False):
    from analyzers.engine import safe_path

    # Seeking/decryption are coordinator primitives, not archive interpretation.
    position = stream.tell()
    length = stream.seek(0, 2)
    stream.seek(position)
    if length > policy["archive_bytes"]:
        raise IntakeError("ARCHIVE_COMPRESSED_BYTES", "Archive exceeds its compressed byte quota.",
                          budget="REPOSITORY_MAX_ARCHIVE_BYTES", actual=length, maximum=policy["archive_bytes"])
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).with_name("isolated_worker.py")), "archive_stream"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/", close_fds=True,
            start_new_session=True,
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PROJECTTRACE_PARSER_ISOLATION": "required"},
        )
    except OSError:
        raise sandbox.SandboxFailure("ISOLATION_STARTUP") from None
    wire = Wire(process, seconds)
    read_bytes, total, path_bytes, seen = 0, 0, 0, set()
    try:
        sandbox.validate_proof(wire.line(4096))
        wire.write(json.dumps({"length": length, "policy": policy, "validate_only": validate_only,
                               "sort_paths": sort_paths, "manifest_only": manifest_only}).encode() + b"\n")
        while True:
            packet = sandbox.decode_packet(wire.line())
            if not isinstance(packet, dict):
                raise sandbox.SandboxFailure("ARCHIVE_PROTOCOL")
            if set(packet) == {"read"}:
                request = packet["read"]
                if (not isinstance(request, list) or len(request) != 2
                        or any(type(n) is not int for n in request)):
                    raise sandbox.SandboxFailure("ARCHIVE_READ_SCOPE")
                offset, size = request
                if not 0 <= offset <= length or not 0 <= size <= min(CHUNK, length - offset):
                    raise sandbox.SandboxFailure("ARCHIVE_READ_SCOPE")
                read_bytes += size
                if read_bytes > max(64_000_000, length * 4):
                    raise sandbox.SandboxFailure("ARCHIVE_READ_BUDGET")
                stream.seek(offset)
                raw = stream.read(size)
                if len(raw) != size:
                    raise sandbox.SandboxFailure("ARCHIVE_SOURCE_TRUNCATED")
                wire.write(struct.pack("!I", len(raw)) + raw)
            elif set(packet) == {"entry"} and not validate_only:
                entry = packet["entry"]
                if not isinstance(entry, dict) or set(entry) not in ({"path", "raw", "hash"}, {"path", "metadata"}):
                    raise sandbox.SandboxFailure("ARCHIVE_ENTRY_PROTOCOL")
                path = str(safe_path(entry["path"]))
                encoded_path = len(path.encode())
                path_bytes += encoded_path
                if encoded_path > 65535 or path_bytes > 64_000_000:
                    raise sandbox.SandboxFailure("ARCHIVE_METADATA_BUDGET")
                if path != entry["path"] or path in seen or len(seen) >= policy["files"]:
                    raise sandbox.SandboxFailure("ARCHIVE_ENTRY_SCOPE")
                seen.add(path)
                if "raw" in entry:
                    value = base64.b64decode(entry["raw"], validate=True)
                    size = len(value)
                    if size > policy["file_bytes"] or hashlib.sha256(value).hexdigest() != entry["hash"]:
                        raise sandbox.SandboxFailure("ARCHIVE_ENTRY_INTEGRITY")
                else:
                    value = entry["metadata"]
                    if manifest_only:
                        if (not isinstance(value, dict) or set(value) != {"bytes", "sha256", "kind"}
                                or type(value["bytes"]) is not int or value["bytes"] < 0
                                or value["kind"] not in {"FILE", "SYMLINK"}
                                or not isinstance(value["sha256"], str) or len(value["sha256"]) != 64
                                or any(c not in "0123456789abcdef" for c in value["sha256"])):
                            raise sandbox.SandboxFailure("ARCHIVE_MANIFEST_PROTOCOL")
                    elif (not isinstance(value, dict) or set(value) - {"bytes", "state", "source_kind"}
                            or value.get("state") not in {"UNSUPPORTED", "SKIPPED_SIZE_LIMIT"}
                            or type(value.get("bytes")) is not int or value["bytes"] < 0
                            or value.get("source_kind") not in {None, "SYMLINK", "ZIP_COMPRESSION_METHOD"}):
                        raise sandbox.SandboxFailure("ARCHIVE_ENTRY_PROTOCOL")
                    size = value["bytes"]
                total += size
                if total > policy["bytes"]:
                    raise sandbox.SandboxFailure("ARCHIVE_OUTPUT_BUDGET")
                yield path, value
            elif set(packet) == {"error"}:
                detail = packet["error"]
                # Diagnostics never accept arbitrary helper strings/source text.
                if not isinstance(detail, dict) or detail.get("code") not in {
                    "ARCHIVE_INVALID", "ARCHIVE_METADATA_BYTES", "ARCHIVE_ENTRY_COUNT", "ARCHIVE_MULTIDISK",
                    "ARCHIVE_UNSAFE_PATH", "DUPLICATE_PATH", "ARCHIVE_ENCRYPTED_ENTRY", "ARCHIVE_SPECIAL_ENTRY",
                    "REPOSITORY_UNCOMPRESSED_BYTES", "ARCHIVE_COMPRESSION_RATIO", "ARCHIVE_ENTRY_CORRUPT", "ARCHIVE_ENTRY_SIZE",
                }:
                    raise sandbox.SandboxFailure("ARCHIVE_ERROR_PROTOCOL")
                budget = detail.get("budget")
                counters = {}
                if budget in {"ARCHIVE_METADATA_BYTES", "REPOSITORY_MAX_FILES", "REPOSITORY_MAX_BYTES",
                              "ARCHIVE_MAX_COMPRESSION_RATIO"}:
                    if any(type(detail.get(key)) not in {int, float} or not 0 <= detail[key] <= 10**12
                           for key in ("actual", "maximum")):
                        raise sandbox.SandboxFailure("ARCHIVE_ERROR_PROTOCOL")
                    counters = {"budget": budget, "actual": detail["actual"], "maximum": detail["maximum"]}
                raise IntakeError(detail["code"], "Archive failed its isolated integrity or intake-policy check.", **counters)
            elif packet == {"done": True}:
                process.stdin.close()
                remaining = max(0.01, wire.deadline - time.monotonic())
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    raise sandbox.SandboxFailure("ARCHIVE_HELPER_TIMEOUT") from None
                if process.returncode or wire.buffer or os.read(process.stdout.fileno(), 1):
                    raise sandbox.SandboxFailure("ARCHIVE_HELPER_CRASH")
                return
            else:
                raise sandbox.SandboxFailure("ARCHIVE_PROTOCOL")
    except (OSError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, (sandbox.SandboxFailure, IntakeError)):
            raise
        raise sandbox.SandboxFailure("ARCHIVE_PROTOCOL") from None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if not pipe.closed:
                pipe.close()


class RemoteArchive:
    """Worker-only seekable view of one authorized stream, without filesystem IO."""
    def __init__(self, length):
        self.length, self.position = length, 0

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        base = 0 if whence == 0 else self.position if whence == 1 else self.length if whence == 2 else None
        if base is None or base + offset < 0:
            raise ValueError("Invalid archive seek")
        self.position = base + offset
        return self.position

    def read(self, size=-1):
        amount = max(0, self.length - self.position)
        if size >= 0:
            amount = min(amount, size)
        if amount > 64_000_000:
            raise IntakeError("ARCHIVE_METADATA_BYTES", "Archive metadata read budget exceeded.")
        result = bytearray()
        while len(result) < amount:
            requested = min(CHUNK, amount - len(result))
            sys.stdout.buffer.write(json.dumps({"read": [self.position, requested]}).encode() + b"\n")
            sys.stdout.buffer.flush()
            header = sys.stdin.buffer.read(4)
            if len(header) != 4 or struct.unpack("!I", header)[0] != requested:
                raise ValueError("Invalid archive byte-range reply")
            data = sys.stdin.buffer.read(requested)
            if len(data) != requested:
                raise ValueError("Truncated archive byte-range reply")
            result.extend(data)
            self.position += requested
        return bytes(result)
