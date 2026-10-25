"""Trusted bootstrap; no untrusted packet is read before Linux controls/probes.

Only installed ProjectTrace operations are selected; repository text is never
imported, evaluated, or used as a command/module/filesystem allowlist.
"""

import ast
import base64
import codecs
import ctypes
import errno
import json
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyzers.sandbox import SandboxFailure  # noqa: E402 -- owned absolute import root

STREAMED = object()
SOURCE_INVALID = object()
DENIAL_RESULTS = []


def prepare(operation):
    # Preload trusted code and lazy parser resources before the deny-by-default
    # syscall filter. Installed runtime code must be immutable and contain no secrets.
    import hcl2
    import tree_sitter
    import tree_sitter_java
    import tree_sitter_javascript
    import tree_sitter_typescript
    import yaml

    import analyzers.performance  # noqa: F401 -- preload before the syscall boundary
    from analyzers import engine, languages, sandbox
    from analyzers.code_quality import coverage
    from backend.process_limits import self_limits

    if operation.startswith("lexical_"):
        import analyzers.lexical_worker  # noqa: F401 -- fixed trusted module before enforcement

    if operation.startswith("archive_") or operation == "legacy_zip":
        import analyzers.archive_parser  # noqa: F401 -- preload pure archive adapter
        import analyzers.archive_transport  # noqa: F401
        codecs.lookup("cp437")

    # Distribution discovery stats site-packages and reads dist-info. Resolve
    # these immutable installed versions before filesystem metadata is denied.
    versions = {name: languages.version(name) for name in
                ("tree-sitter", "tree-sitter-java", "tree-sitter-javascript", "tree-sitter-typescript")}
    languages.version = versions.__getitem__

    if operation == "iac":
        # hcl2's default Lark cache uses pickle and writes in site-packages.
        # Build the identical trusted grammar without a filesystem cache.
        import hcl2.api
        import hcl2.parser
        from hcl2.postlexer import PostLexer
        from lark import Lark
        grammar = Lark.open("hcl2.lark", parser="lalr", cache=False, rel_to=hcl2.parser.__file__,
                            propagate_positions=True, postlex=PostLexer())
        hcl2.api.parser = lambda: grammar
        hcl2.loads('variable "sec002_probe" { default = 1 }')
    yaml.safe_load("{}")
    ast.parse("")
    coverage.ET.fromstring("<probe/>")
    # Hold the handle: dlopen cannot load a new library after Landlock.
    seccomp = ctypes.CDLL("libseccomp.so.2")
    read_paths = {str(Path(__file__).resolve().parent)}
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and os.path.isfile(path):
            read_paths.add(os.path.realpath(path))
    for package in (hcl2, yaml, tree_sitter, tree_sitter_java, tree_sitter_javascript, tree_sitter_typescript):
        read_paths.add(str(Path(package.__file__).resolve().parent))
    import lark
    read_paths.add(str(Path(lark.__file__).resolve().parent))
    with open("/proc/self/maps") as stream:
        for line in stream:
            path = line.split()[-1]
            if path.startswith("/") and os.path.isfile(path):
                read_paths.add(os.path.realpath(path))
    if any(name in sys.modules for name in ("backend.db", "backend.main", "workers.tasks")):
        raise RuntimeError("Parser bootstrap unexpectedly imported application services")
    return engine, sandbox, self_limits, read_paths, seccomp


def denied(operation, *, expected=(errno.EPERM, errno.EACCES)):
    try:
        operation()
    except OSError as error:
        DENIAL_RESULTS.append(error.errno)
        return error.errno in expected
    DENIAL_RESULTS.append(0)
    return False


def main():
    operation = sys.argv[1]
    engine, sandbox, self_limits, read_paths, _library = prepare(operation)
    memory, cpu = (384 * 1024 * 1024, 10) if operation.startswith("iac") else (512 * 1024 * 1024, 25)
    if operation == "archive_stream":
        cpu = 120
    if operation == "probe_cpu":
        cpu = int(time.process_time()) + 2
    self_limits(memory, cpu)
    abi = sandbox.install(read_paths)
    checks = [
        denied(lambda: open("/etc/passwd", "rb")),
        denied(lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM), expected=(errno.EPERM,)),
        denied(lambda: os.execve("/SEC002-NOT-PRESENT", ["probe"], {}), expected=(errno.EPERM,)),
        denied(lambda: os.stat("/etc/passwd"), expected=(errno.EPERM,)),
        denied(lambda: os.open("/etc/passwd", os.O_PATH), expected=(errno.EPERM,)),
    ]
    if not all(checks):
        raise RuntimeError("Parser isolation denial probe failed")
    sandbox.ACTIVE = True
    proof = {"policy": sandbox.POLICY, "enforced": True, "landlock_abi": abi,
             "denials": ["filesystem", "network", "exec", "metadata"]}
    sys.stdout.buffer.write(json.dumps(proof).encode() + b"\n")
    sys.stdout.buffer.flush()
    if operation.startswith("archive_"):
        configuration = sys.stdin.buffer.readline(8193)
        if len(configuration) > 8192:
            raise ValueError("Archive configuration budget")
        if operation == "archive_probe_crash":
            os._exit(73)
        if operation == "archive_probe_timeout":
            while True:
                pass
        if operation == "archive_probe_malformed":
            sys.stdout.buffer.write(b"{not json}\n")
            sys.stdout.buffer.flush()
            os._exit(0)
        if operation != "archive_stream":
            raise ValueError("Unknown installed archive operation")
        archive_stream(json.loads(configuration))
        return
    raw = sys.stdin.buffer.read(32_000_001)
    if len(raw) > 32_000_000:
        raise ValueError("Owned parser input budget exceeded")
    packet = json.loads(raw)
    if packet["operation"] != operation:
        raise ValueError("Owned parser operation mismatch")
    value = packet["value"]
    try:
        result = dispatch(operation, value, engine, sandbox)
    except SandboxFailure as error:
        sys.stdout.buffer.write(json.dumps({"ok": False, "code": error.code}).encode())
        return
    if result is STREAMED:
        return
    if result is SOURCE_INVALID:
        sys.stdout.buffer.write(b'{"ok": false, "code": "SOURCE_SYNTAX_FAILED"}')
        return
    output = json.dumps({"ok": True, "result": result}, ensure_ascii=True).encode()
    if len(output) > (32_000_000 if operation == "legacy_zip" else 16_000_000):
        raise ValueError("Owned parser output budget exceeded")
    sys.stdout.buffer.write(output)


def dispatch(operation, value, engine, sandbox):
    from analyzers.parser_protocol import emit_packet

    if operation.startswith("lexical_"):
        import hashlib

        from analyzers import lexical_worker
        if operation == "lexical_probe_metadata":
            return {"nested": [{"value": "ghp_owned_fixture_abcdefghijklmnopqrstuvwxyz"}],
                    "credentials": {"encoded_shape": ["owned-private-value"]},
                    "dsn": "postgresql://owned:owned-private-password@localhost/owned"}
        if operation == "lexical_probe_wrong_description":
            rows = lexical_worker.describe(value["rows"])
            rows[0]["path"] = "other-tenant.py"
            return rows
        if operation == "lexical_describe":
            return lexical_worker.describe(value["rows"])
        if operation == "lexical_classify":
            return lexical_worker.classify(value)
        if operation == "lexical_ownership":
            return lexical_worker.ownership(value)
        if operation == "lexical_diff":
            return lexical_worker.changed_ranges(value)
        if operation == "lexical_sections":
            if "files" in value:
                return {p: {"hash": hashlib.sha256(s.encode()).hexdigest(),
                            "sections": lexical_worker.sections({"path": p, "source": s,
                                "hash": hashlib.sha256(s.encode()).hexdigest()})["sections"]}
                        for p, s in value["files"].items()}
            return lexical_worker.sections(value)
        if operation == "lexical_storage":
            return {"hashes": {p: hashlib.sha256(s.encode()).hexdigest() for p, s in value["files"].items()},
                    "claims": lexical_worker.storage_claims(value["files"], value["assets"])}
        if operation == "lexical_matches":
            from analyzers.code_quality.classification import matches
            return matches(value["path"], value["patterns"])
        raise ValueError("Unknown installed lexical operation")

    if operation == "probe":
        return {"enforced": True, "policy": sandbox.POLICY}
    if operation == "legacy_zip":
        import zipfile
        try:
            files = engine.read_zip(base64.b64decode(value["archive"], validate=True), keep_excluded=value["keep_excluded"])
            return {"files": {path: base64.b64encode(source.encode()).decode() for path, source in files.items()},
                    "intake": files.intake}
        except (ValueError, zipfile.BadZipFile):
            return {"invalid_archive": True}
    if operation == "probe_denials":
        libc = ctypes.CDLL(None, use_errno=True)
        network = {}
        for address in ("8.8.8.8", "127.0.0.1", "169.254.169.254"):
            def attempt(address=address):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
                    connection.connect((address, 80))
            network[address] = denied(attempt, expected=(errno.EPERM,))
        return {"read": denied(lambda: open(value["sentinel"], "rb")),
                "write": denied(lambda: open(value["write_path"], "wb")),
                "proc": denied(lambda: open("/proc/self/environ", "rb")),
                "metadata": denied(lambda: os.stat(value["sentinel"])), "network": network,
                "opath": denied(lambda: os.open(value["sentinel"], os.O_PATH), expected=(errno.EPERM,)),
                "exec": denied(lambda: os.execve("/bin/echo", ["echo", "SEC002"], {}), expected=(errno.EPERM,)),
                "fork": denied(os.fork, expected=(errno.EPERM,)),
                "environment": sorted(os.environ), "nnp": libc.prctl(39, 0, 0, 0, 0),
                "seccomp": libc.prctl(21, 0, 0, 0, 0), "nonce": value.get("nonce"),
                "denial_errno": list(DENIAL_RESULTS)}
    if operation in {"probe_timeout", "probe_cpu"}:
        while True:
            pass
    if operation == "probe_memory":
        try:
            bytearray(640 * 1024 * 1024)
        except MemoryError:
            return {"contained": True}
        return {"contained": False}
    if operation == "probe_crash":
        os._exit(73)
    if operation == "probe_malformed":
        sys.stdout.buffer.write(b"not a valid packet")
        sys.stdout.buffer.flush()
        os._exit(0)
    if operation == "probe_output":
        while True:
            os.write(1, b"x" * 65536)
    if operation == "json":
        try:
            return json.loads(value["source"])
        except ValueError:
            return SOURCE_INVALID
    if operation == "python":
        return engine.python_analysis(value["path"], value["source"])
    if operation == "identity":
        from analyzers.finding_identity import annotate
        return annotate(value["files"], value["findings"], value["metrics"])
    if operation == "inventory":
        from analyzers.baseline import inventory
        return inventory(value["files"])
    if operation == "documentation":
        from analyzers.verifiers import extract_documentation
        messages = []
        result = extract_documentation(value["files"], diagnostics=messages, limit=value["limit"])
        return result, messages
    if operation == "coverage":
        from analyzers.code_quality.coverage import import_report
        return import_report(value["text"], dict.fromkeys(value["line_counts"]),
                             _line_counts=value["line_counts"], **value["options"])
    if operation == "metrics":
        from analyzers.quality import metrics
        return metrics(value["path"], value["source"])
    if operation == "structure":
        from analyzers.quality import structure
        return structure(value["path"], value["source"], ast.parse(value["source"]))
    if operation == "flows":
        from analyzers.flows import python_flows
        return python_flows(value["path"], value["source"], engine.finding)
    if operation in {"languages", "probe_language_prefix_crash"}:
        from analyzers.languages import _analyze_language
        files = value["files"]
        if len(files) > 1000 or sum(len(s.encode()) for s in files.values()) > 10_000_000:
            raise ValueError("Language batch budget")
        total, metric_count = 0, 0
        for path, source in files.items():
            if len(source.encode()) > 512_000:
                raise ValueError("Per-file source budget")
            started = time.perf_counter()
            try:
                result = _analyze_language(path, source, engine.finding)
                metric_count += len(result[2])
                if metric_count > 10_000:
                    raise ValueError("Native syntax metric budget exceeded")
            except Exception as error:
                result = {"error": "Native syntax parsing failed", "code": "PARSER_FAILED"}
                if isinstance(error, ValueError) and str(error) in {"Syntax node budget exceeded", "Syntax token budget exceeded"}:
                    result.update(code="SYNTAX_NODE_BUDGET", budget="SYNTAX_NODES_OR_TOKENS", actual=40001, maximum=40000)
            total = emit_packet(path, result, time.perf_counter() - started,
                                "PARTIAL" if isinstance(result, dict) else "COMPLETED", maximum=16_000_000, total=total)
            if operation == "probe_language_prefix_crash":
                sys.stdout.buffer.flush()
                os._exit(73)
        return STREAMED
    if operation == "iac":
        from analyzers.infrastructure import _structured_iac
        files = value["files"]
        if len(files) > 100 or sum(len(s.encode()) for s in files.values()) > 2_000_000:
            raise ValueError("Infrastructure batch budget")
        total = 0
        for path, source in files.items():
            if len(source.encode()) > 512_000:
                raise ValueError("Per-file source budget")
            started = time.perf_counter()
            result = _structured_iac(path, source,
                lambda rule, path, line, detail: {"rule": rule, "path": path, "line": line, "explanation": detail}, value["settings"])
            total = emit_packet(path, result, time.perf_counter() - started,
                                "PARTIAL" if result[2] else "COMPLETED", maximum=8*1024*1024, total=total)
        return STREAMED
    if operation == "native":
        files = value["files"]
        if len(files) > 100 or sum(len(s.encode()) for s in files.values()) > 2_000_000:
            raise ValueError("Native batch budget")
        total = 0
        for path, source in files.items():
            started = time.perf_counter()
            from analyzers.performance import Performance
            performance = Performance()
            result = list(engine._native_observations({path: source}, value["cache"], value["settings"], performance, None,
                                                       parsed_inputs=value["parsed"]))
            result[5] = sorted(result[5])
            result.append(performance.snapshot())
            total = emit_packet(path, result, time.perf_counter() - started,
                                "PARTIAL" if result[2] else "COMPLETED", maximum=16_000_000, total=total)
        return STREAMED
    raise ValueError("Unknown installed parser operation")


def archive_stream(configuration):
    import hashlib
    import zipfile
    import zlib

    from analyzers.archive_parser import archive_items
    from analyzers.archive_transport import RemoteArchive
    from backend.intake_errors import IntakeError

    def emit(value):
        raw = json.dumps(value, ensure_ascii=True).encode()
        if len(raw) > 1_000_000:
            raise ValueError("Archive output packet budget")
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()
    try:
        for path, value in archive_items(RemoteArchive(configuration["length"]), configuration["policy"],
                                        validate_only=configuration["validate_only"], sort_paths=configuration["sort_paths"]):
            entry = {"path": path, "metadata": value} if isinstance(value, dict) else {
                "path": path, "raw": base64.b64encode(value).decode(), "hash": hashlib.sha256(value).hexdigest()}
            emit({"entry": entry})
    except IntakeError as error:
        emit({"error": error.detail()})
        return
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError, zlib.error, ValueError):
        emit({"error": {"code": "ARCHIVE_INVALID"}})
        return
    emit({"done": True})


if __name__ == "__main__":
    try:
        main()
        sys.stdout.buffer.flush()
        os._exit(0)
    except SandboxFailure as error:
        sys.stdout.buffer.write(json.dumps({"failure": error.code}).encode() + b"\n")
        sys.stdout.buffer.flush()
        os._exit(70)
    except Exception:
        # Parent reports a sanitized code. Never print input, environment or raw errors.
        os._exit(70)
