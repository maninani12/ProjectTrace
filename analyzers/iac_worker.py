"""Owned parser helper. Imported project text is never a Python module or command."""

import json
import os
import sys
import time
from pathlib import Path


def main():
    if os.name == "posix":
        import resource

        for kind, limit in (
            (resource.RLIMIT_CPU, 10),
            (resource.RLIMIT_AS, 384 * 1024 * 1024),
            (resource.RLIMIT_FSIZE, 0),
            (resource.RLIMIT_NOFILE, 32),
        ):
            resource.setrlimit(kind, (limit, limit))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if os.name == "nt":
        from backend.process_limits import self_limits
        self_limits(384 * 1024 * 1024, 10)
    from analyzers.infrastructure import _structured_iac
    from analyzers.parser_protocol import emit_packet

    payload = sys.stdin.buffer.read(13_000_001)
    if len(payload) > 13_000_000:
        raise ValueError("Input transport budget exceeded")
    value = json.loads(payload)
    if "files" in value:
        files = value["files"]
        if not isinstance(files, dict) or not 1 <= len(files) <= 100 or sum(len(s.encode()) for s in files.values()) > 2_000_000:
            raise ValueError("Infrastructure partition budget exceeded")
        output_bytes = 0
        for path, source in files.items():
            if not isinstance(source, str) or len(source.encode()) > 512_000:
                raise ValueError("Per-file input budget exceeded")
            started = time.perf_counter()
            result = _structured_iac(path, source,
                                         lambda rule, path, line, detail: {"rule": rule, "path": path, "line": line, "explanation": detail},
                                         value.get("settings"))
            output_bytes = emit_packet(path, result, time.perf_counter() - started,
                                       "PARTIAL" if result[2] else "COMPLETED", maximum=8*1024*1024, total=output_bytes)
        return
    if len(value["source"].encode()) > 512000:
        raise ValueError("Input budget exceeded")
    result = _structured_iac(
        value["path"],
        value["source"],
        lambda rule, path, line, detail: {"rule": rule, "path": path, "line": line, "explanation": detail},
        value.get("settings"),
    )
    output = json.dumps(result, ensure_ascii=True).encode()
    if len(output) > 8 * 1024 * 1024:
        raise ValueError("Output budget exceeded")
    sys.stdout.buffer.write(output)


if __name__ == "__main__":
    main()
