"""Linux qualification counters; RSS and cgroup charge are separate metrics."""
import os
from pathlib import Path


def cgroup_diagnostics(root):
    """Distinguish resident payloads, charged file pages and reclaim stalls.

    Missing counters are unavailable, never reported as zero or a pass.
    These fixed kernel files contain no source, credentials or environment.
    """
    result = {}
    for name in ("memory.stat", "cpu.stat"):
        try:
            result[name] = {key: int(value) for key, value in
                            (line.split() for line in (root / name).read_text().splitlines())}
        except (OSError, ValueError):
            result[name] = "UNAVAILABLE"
    for name in ("memory.pressure", "cpu.pressure", "io.pressure", "io.stat"):
        try:
            result[name] = (root / name).read_text().strip()
        except OSError:
            result[name] = "UNAVAILABLE"
    return result


def namespace_rss(proc_root, coordinator_pid):
    result = {"coordinator_rss_bytes": None, "namespace_rss_bytes": None, "processes": 0,
              "missing_process_samples": 0, "rss_scope": "VISIBLE_PID_NAMESPACE_SUM; SHARED_PAGES_MAY_REPEAT"}
    total = 0
    for path in proc_root.glob("[0-9]*/status"):
        try:
            fields = {k: v.strip() for k, v in (line.split(":", 1) for line in path.read_text().splitlines())}
            pieces = fields["VmRSS"].split()
            if len(pieces) != 2 or pieces[1] != "kB" or int(pieces[0]) < 0:
                raise ValueError("Unavailable RSS counter")
            rss = int(pieces[0]) * 1024
            total += rss
            result["processes"] += 1
            if path.parent.name == str(coordinator_pid):
                result["coordinator_rss_bytes"] = rss
        except (OSError, ValueError, KeyError):
            result["missing_process_samples"] += 1
            continue
    complete = result["missing_process_samples"] == 0 and result["coordinator_rss_bytes"] is not None
    result["namespace_rss_complete"] = complete
    result["namespace_rss_lower_bound_bytes"] = total if result["processes"] else None
    result["namespace_rss_bytes"] = total if complete else None
    result["child_rss_bytes"] = total - result["coordinator_rss_bytes"] if complete else None
    return result


def memory():
    if os.name != "posix" or not Path("/proc/self/status").is_file():
        return {"available": False}
    result = {"available": True, **namespace_rss(Path("/proc"), os.getpid())}
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
    result.update(cgroup_diagnostics(cgroup))
    return result
