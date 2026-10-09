"""Seekable upload spool: only bounded, authenticated ciphertext reaches disk."""

import bisect
import io
import os
import tempfile
from pathlib import Path

from backend.intake_errors import IntakeError
from backend.queue import cipher


class EncryptedArchive(io.RawIOBase):
    chunk_bytes = 512_000
    max_read = 64_000_000

    def __init__(self, maximum):
        super().__init__()
        root = Path(os.getenv("SOURCE_UPLOAD_DIR", "data/source-uploads")).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="archive-", dir=root)
        self.root = Path(self.directory.name).resolve()
        if self.root.parent != root:
            raise ValueError("Encrypted upload directory escaped its configured root.")
        self.encryption, self.maximum = cipher(), maximum
        self.starts, self.paths, self.length, self.position = [], [], 0, 0
        self.cached_index, self.cached_chunk = None, b""

    def append(self, data):
        if self.length + len(data) > self.maximum:
            raise IntakeError("ARCHIVE_COMPRESSED_BYTES", "Archive exceeds its configured compressed byte quota.",
                              budget="REPOSITORY_MAX_ARCHIVE_BYTES", actual=self.length + len(data), maximum=self.maximum,
                              remediation="Upload a smaller source archive; omit build outputs and vendored dependencies.")
        for offset in range(0, len(data), self.chunk_bytes):
            block = data[offset : offset + self.chunk_bytes]
            target = self.root / (str(len(self.paths)) + ".enc")
            target.write_bytes(self.encryption.encrypt(block))
            target.chmod(0o600)
            self.starts.append(self.length)
            self.paths.append(target)
            self.length += len(block)

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        position = offset + (
            0
            if whence == io.SEEK_SET
            else self.position
            if whence == io.SEEK_CUR
            else self.length
            if whence == io.SEEK_END
            else -1
        )
        if whence not in {io.SEEK_SET, io.SEEK_CUR, io.SEEK_END} or position < 0:
            raise ValueError("Invalid encrypted upload seek.")
        self.position = position
        return position

    def read(self, size=-1):
        remaining = max(0, self.length - self.position)
        amount = remaining if size < 0 else min(size, remaining)
        if amount > self.max_read:
            raise IntakeError("ARCHIVE_METADATA_BYTES", "Archive read exceeds its metadata budget.",
                              budget="ARCHIVE_METADATA_BYTES", actual=amount, maximum=self.max_read)
        result = bytearray()
        while len(result) < amount:
            index = bisect.bisect_right(self.starts, self.position) - 1
            if index != self.cached_index:
                self.cached_chunk = self.encryption.decrypt(self.paths[index].read_bytes())
                self.cached_index = index
            raw = self.cached_chunk
            offset = self.position - self.starts[index]
            taken = min(len(raw) - offset, amount - len(result))
            if taken <= 0:
                raise ValueError("Encrypted upload chunk is inconsistent.")
            result.extend(raw[offset : offset + taken])
            self.position += taken
        return bytes(result)

    def close(self):
        self.cached_index, self.cached_chunk = None, b""
        if not self.closed:
            # Every path was created here; validate containment before cleanup.
            for target in self.paths:
                if target.resolve().parent != self.root:
                    raise ValueError("Upload cleanup target escaped its owned directory.")
            self.directory.cleanup()
        super().close()
