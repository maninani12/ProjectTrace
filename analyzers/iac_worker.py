"""Owned parser helper. Imported project text is never a Python module or command."""

import json
import os
import sys
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

    value = json.loads(sys.stdin.buffer.read(3_200_001))
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
