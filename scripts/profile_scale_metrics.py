"""Owned synthetic quality-stage probe; never a whole-repository qualification."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import tracemalloc


def worker(count, owned):
    import resource

    from analyzers.code_quality.core import build

    # This worker has no children. RLIMIT_AS is not a general process-tree or
    # Windows committed-memory limit; report that distinction explicitly.
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
    tracemalloc.start()
    stages = {}
    def sample(name):
        stages[name] = {"python_current_bytes": tracemalloc.get_traced_memory()[0],
                        "python_peak_bytes": tracemalloc.get_traced_memory()[1],
                        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
    sample("imports")
    files = {"owned.py": "pass\n" * 100}
    metrics = [{"path": "owned.py", "name": f"f{i}", "qualified_name": f"f{i}", "language": "Python",
                "line": 1, "end_line": 2, "body_hash": str(i), "token_count": 0,
                "complexity": 1, "parameters": 0, "nesting": 0, "length": 2,
                "duplicate_tokens": [], **{f"contributor_{k}": k for k in range(20)}} for i in range(count)]
    sample("input")
    started = time.perf_counter()
    findings, quality = build(files, metrics, [{"type": "quality_file", "path": "owned.py"}], [], [],
                              consume_metrics=owned)
    sample("quality")
    quality.pop("performance")
    digest, size = hashlib.sha256(), 0
    for chunk in json.JSONEncoder(sort_keys=True).iterencode([findings, quality]):
        encoded = chunk.encode()
        digest.update(encoded)
        size += len(encoded)
    sample("serialized")
    print(json.dumps({"scope": "SYNTHETIC_QUALITY_STAGE_ONLY", "python": platform.python_version(),
                      "mode": "owned" if owned else "copied", "input_id": f"owned-metrics-v1:{count}",
                      "source_files": 1, "parser_artifacts": 0, "metrics": len(quality["metrics"]),
                      "symbols": len(quality["symbols"]), "findings": len(findings),
                      "output_sha256": digest.hexdigest(), "output_bytes": size,
                      "seconds": time.perf_counter() - started, "stages": stages,
                      "limit": "768 MiB RLIMIT_AS; single worker; not general tree containment",
                      "publication": "NOT_EXERCISED"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--worker", choices=["copied", "owned"])
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("This probe measures Linux single-process RLIMIT_AS, not Windows Job Objects.")
    if not 1 <= args.count <= 100000:
        parser.error("count must be 1..100000")
    if args.worker:
        worker(args.count, args.worker == "owned")
        return
    rows = []
    for mode in ("copied", "owned", "owned"):
        result = subprocess.run([sys.executable, "-m", "scripts.profile_scale_metrics", "--count", str(args.count),
                                 "--worker", mode], capture_output=True, text=True, timeout=600,
                                env={**os.environ, "APP_ENV": "demo", "PROJECTTRACE_PARSER_ISOLATION": "development"})
        if result.returncode:
            raise RuntimeError(f"Owned probe failed: {mode}, exit {result.returncode}; no qualification")
        rows.append(json.loads(result.stdout))
    assert len({r["output_sha256"] for r in rows}) == 1
    print(json.dumps({"runs": rows, "deterministic_output": True, "scale_001": "NOT_QUALIFIED"}))


if __name__ == "__main__":
    main()
