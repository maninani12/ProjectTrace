"""Owned cgroup denial probe, distinct from application recovery qualification."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.scale_linux_resources import memory


def main():
    before = memory()
    if before.get("memory.max") != 768_000_000 or before.get("memory.swap.max") != 0:
        raise RuntimeError("Actual required cgroup limit is absent.")
    code = "import time; allocated=bytearray(600_000_000); time.sleep(3)"
    children = [subprocess.Popen([sys.executable, "-I", "-B", "-c", code], env={"LANG": "C.UTF-8"},
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(2)]
    try:
        statuses = [child.wait(timeout=45) for child in children]
        after = memory()
        enforced = -9 in statuses and after["memory.events"]["oom_kill"] > before["memory.events"]["oom_kill"]
        Path("/evidence/resource-probe.json").write_text(json.dumps({
            "schema": "projecttrace-cgroup-owned-child-probe-v1", "enforced": enforced,
            "children": [child.pid for child in children], "child_exit_statuses": statuses,
            "allocation_bytes_each": 600_000_000, "before": before, "after": after,
            "scope": "Kernel shared-envelope enforcement only; no application job/publication/recovery exercised"}, indent=2))
        if not enforced:
            raise RuntimeError("Expected real child OOM denial was not observed.")
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


if __name__ == "__main__":
    main()
