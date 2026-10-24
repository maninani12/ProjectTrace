"""Owned image qualification. A successful build alone never establishes isolation."""

import json
import os
from pathlib import Path

from analyzers import sandbox


def main():
    assert sandbox.mode() == "required"
    sentinel = os.getenv("PROJECTTRACE_PROBE_SENTINEL", "/etc/passwd")
    assert Path(sentinel).read_bytes()  # Application can read what its child must not.
    assert sandbox.require_runtime()["enforced"]
    result = sandbox.call("probe_denials", {"sentinel": sentinel, "write_path": "/app/data/sec002-escape"})
    assert all(result[key] is True for key in ("read", "write", "proc", "metadata", "opath", "exec", "fork"))
    assert all(result["network"].values()) and result["nnp"] == 1 and result["seccomp"] == 2
    assert not {"DATABASE_URL", "ANALYSIS_INPUT_KEY"} & set(result["environment"])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
