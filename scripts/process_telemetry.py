"""Read-only process memory counters, with explicit units and unavailable values."""
import os
import threading
import time
from pathlib import Path


def proc_memory(root=Path("/proc/self")):
    result = {"rss_bytes": None, "peak_rss_bytes": None,
              "rss_source": "proc/status:VmRSS", "peak_rss_source": "proc/status:VmHWM",
              "peak_scope": "CURRENT_ADDRESS_SPACE_SINCE_EXEC", "pid": os.getpid(),
              "observed_monotonic": time.perf_counter(), "memory_units": "bytes"}
    try:
        fields = dict(line.split(":", 1) for line in (root / "status").read_text().splitlines() if ":" in line)
        for key, name in [("rss_bytes", "VmRSS"), ("peak_rss_bytes", "VmHWM")]:
            pieces = fields.get(name, "").split()
            if len(pieces) == 2 and pieces[1] == "kB" and int(pieces[0]) >= 0:
                result[key] = int(pieces[0]) * 1024
    except (OSError, ValueError):
        pass
    result["memory_available"] = all(result[name] is not None for name in ("rss_bytes", "peak_rss_bytes"))
    try:
        result["io_counters"] = dict((key, int(value)) for key, value in
                                     (line.split(":", 1) for line in (root / "io").read_text().splitlines()))
        result["io_source"] = "proc/io; read_bytes/write_bytes physical I/O, rchar/wchar include cached I/O"
    except (OSError, ValueError):
        result["io_counters"] = None
    return result


class MemoryWindow:
    """Bounded samples of one owning process; not a cgroup or process-tree peak."""
    def __init__(self, reader, interval=0.01):
        self.reader, self.interval = reader, interval
        self.samples, self.missing, self.peak = 0, 0, None
        self.stop = threading.Event()

    def observe(self):
        row = self.reader() or {}
        self.samples += 1
        value = row.get("rss_bytes")
        if value is None:
            self.missing += 1
        else:
            self.peak = max(self.peak or 0, value)

    def __enter__(self):
        self.started = time.perf_counter()
        self.observe()

        def sample():
            while not self.stop.wait(self.interval):
                self.observe()

        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()
        self.observe()
        self.result = {"scope": "OWNER_PROCESS_ONLY", "interval_seconds": self.interval,
                       "samples": self.samples, "missing_samples": self.missing,
                       "sampled_peak_rss_bytes": self.peak,
                       "duration_seconds": time.perf_counter() - self.started,
                       "short_lived_spikes_may_be_missed": True}
