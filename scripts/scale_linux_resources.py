"""Linux qualification counters; RSS and cgroup charge are separate metrics."""
import os
from pathlib import Path


def memory():
    if os.name != "posix" or not Path("/proc/self/status").is_file():
        return {"available": False}
    result = {"available": True, "coordinator_rss_bytes": 0, "namespace_rss_bytes": 0, "processes": 0}
    for path in Path("/proc").glob("[0-9]*/status"):
        try:
            fields = {k: v.strip() for k, v in (line.split(":", 1) for line in path.read_text().splitlines())}
            rss = int(fields.get("VmRSS", "0 kB").split()[0]) * 1024
            result["namespace_rss_bytes"] += rss
            result["processes"] += 1
            if path.parent.name == str(os.getpid()):
                result["coordinator_rss_bytes"] = rss
        except (OSError, ValueError):
            continue
    result["child_rss_bytes"] = result["namespace_rss_bytes"] - result["coordinator_rss_bytes"]
    cgroup = Path("/sys/fs/cgroup")
    for name in ("memory.current", "memory.peak", "memory.max", "memory.swap.max", "memory.swap.current"):
        try:
            value = (cgroup / name).read_text().strip()
            result[name] = int(value) if value != "max" else "max"
        except (OSError, ValueError):
            result[name] = "UNAVAILABLE"
    try:
        result["memory.events"] = {key: int(value) for key, value in
                                   (line.split() for line in (cgroup / "memory.events").read_text().splitlines())}
    except (OSError, ValueError):
        result["memory.events"] = "UNAVAILABLE"
    return result
