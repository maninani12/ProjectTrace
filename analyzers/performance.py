"""Bounded timing metadata. Never retains source text, credentials or parser output."""

import threading
import time
from collections import defaultdict
from contextlib import contextmanager


class Performance:
    def __init__(self):
        self.lock = threading.Lock()
        self.components = defaultdict(lambda: {"count": 0, "seconds": 0.0, "max_seconds": 0.0})
        self.counters, self.slowest = defaultdict(int), []
        self.stage, self.stage_at = None, time.perf_counter()
        self.stages = defaultdict(float)

    def record(self, component, seconds, path=None, *, state="MEASURED"):
        with self.lock:
            row = self.components[component]
            row["count"] += 1
            row["seconds"] += seconds
            row["max_seconds"] = max(row["max_seconds"], seconds)
            if path:
                self.slowest.append({"path": path, "component": component, "seconds": round(seconds, 6), "state": state})
                self.slowest.sort(key=lambda r: r["seconds"], reverse=True)
                del self.slowest[40:]

    def count(self, name, value=1):
        with self.lock:
            self.counters[name] += value

    @contextmanager
    def measure(self, component, path=None):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(component, time.perf_counter() - started, path)

    def switch(self, stage):
        current = time.perf_counter()
        with self.lock:
            if self.stage:
                self.stages[self.stage] += current - self.stage_at
            self.stage, self.stage_at = stage, current

    def snapshot(self):
        with self.lock:
            stages = dict(self.stages)
            if self.stage:
                stages[self.stage] = stages.get(self.stage, 0) + time.perf_counter() - self.stage_at
            return {"schema": "projecttrace-performance-v1", "clock": "WALL_PERF_COUNTER",
                    "stage_seconds": {k: round(v, 6) for k, v in stages.items()},
                    "components": {k: {n: round(v, 6) if isinstance(v, float) else v for n, v in r.items()}
                                   for k, r in self.components.items()},
                    "counters": dict(self.counters), "slowest_file_operations": list(self.slowest),
                    "helper_concurrency_max": 2, "source_cache_bytes_max": 2_000_000,
                    "timing_scope": "Current attempt; component/helper time overlaps and is not summed as wall runtime."}
