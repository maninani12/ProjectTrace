"""Measured local static-analysis workloads. No source fixture is executed."""

import json
import statistics
import time
from pathlib import Path

from analyzers.engine import analyze


def timed(fn, runs):
    durations = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        durations.append((time.perf_counter() - start) * 1000)
    ordered = sorted(durations)
    return {
        "runs": runs,
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "p99_ms": round(ordered[-1], 3),
    }


if __name__ == "__main__":
    fixture = json.loads(Path("samples/demo.json").read_text())["identity"]
    large = {
        f"component{i}/app.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef health(): return {"status":"ok"}\n'
        for i in range(500)
    }
    large["README.md"] = "Backend uses FastAPI. The API exposes /health."
    baseline = analyze(large)
    report = {
        "environment": "Local Windows / Python 3.14; serial static analysis; no network, queue or production load",
        "identity_head": timed(lambda: analyze(fixture["head"]), 50),
        "500_file_repository": timed(lambda: analyze(large), 20),
        "unchanged_500_file_incremental": timed(lambda: analyze(large, baseline["analysis_cache"]), 20),
    }
    print(json.dumps(report, indent=2))
