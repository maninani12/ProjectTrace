"""Reproducible, bounded native quality benchmark. Imported source never executes.

python -m scripts.benchmark_quality --output quality-benchmark.json [--real-zip repository.zip]
"""

import argparse
import ctypes
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from analyzers.code_quality.classification import classify
from analyzers.engine import PARSER_SIGNATURE, analyze, read_zip, validate_files
from tests.test_code_quality import RULE_CASES


def memory():
    scope = "entire benchmark Python process including accumulated results; excludes native child parser RSS"
    if sys.platform == "win32":

        class Memory(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        m = Memory()
        m.cb = ctypes.sizeof(m)
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(ctypes.windll.kernel32.GetCurrentProcess()), ctypes.byref(m), m.cb
        )
        return {
            "peak_working_set_bytes": m.PeakWorkingSetSize if ok else None,
            "working_set_bytes": m.WorkingSetSize if ok else None,
            "scope": scope,
        }
    import resource

    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "peak_working_set_bytes": maximum if sys.platform == "darwin" else maximum * 1024,
        "working_set_bytes": None,
        "scope": scope,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--real-zip", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    measures = []
    for count in [10, 100, 1000]:
        files = {f"src/function{i}.py": f"def function{i}(value):\n    return value + {i}\n" for i in range(count)}
        timings = []
        first = None
        for repeat in range(12):
            start = time.perf_counter()
            result = analyze(files)
            timings.append((time.perf_counter() - start) * 1000)
            first = result
        warm = []
        for repeat in range(20):
            start = time.perf_counter()
            cached = analyze(files, first["analysis_cache"])
            warm.append((time.perf_counter() - start) * 1000)

        def stats(values):
            values = sorted(values)
            return {
                "samples": len(values),
                "p50_ms": round(values[math.ceil(len(values) * 0.5) - 1], 2),
                "p95_ms": round(values[math.ceil(len(values) * 0.95) - 1], 2),
                "p99_ms": round(values[math.ceil(len(values) * 0.99) - 1], 2),
                "maximum_ms": round(max(values), 2),
                "method": "nearest rank; p99 with this sample size equals observed max, not production tail proof",
            }

        measures.append(
            {
                "files": count,
                "functions": len(first["quality_metrics"]),
                "cold": stats(timings),
                "cached": stats(warm),
                "reused_files": cached["reused_files"],
                "quality_state": cached["code_quality"]["state"],
                "cache_json_bytes": len(json.dumps(first["analysis_cache"]).encode()),
            }
        )
        print(json.dumps(measures[-1]), flush=True)
    limits = []
    for n in [10000, 50000]:
        files = {f"app{i}.py": "x=1" for i in range(n)}
        start = time.perf_counter()
        try:
            validate_files(files)
            state = "UNEXPECTED_ACCEPT"
        except ValueError:
            state = "REJECTED_BY_1000_FILE_INTAKE_LIMIT"
        limits.append({"files": n, "full_analysis": state, "intake_ms": round((time.perf_counter() - start) * 1000, 2)})
        start = time.perf_counter()
        rows = classify(files)
        limits[-1].update(
            scope_classifier_component_ms=round((time.perf_counter() - start) * 1000, 2),
            classified=len(rows),
            component_only=True,
        )
    corpus = []
    for rule, path, positive, negative in RULE_CASES:
        key = "PT-QUALITY-" + rule
        hits = analyze({path: positive})
        clear = analyze({path: negative})
        corpus.append(
            {
                "rule": key,
                "positive_detected": any(f["rule"] == key for f in hits["findings"]),
                "negative_clear": not any(f["rule"] == key for f in clear["findings"]),
            }
        )
    real = analyze(read_zip(args.real_zip.read_bytes(), keep_excluded=True)) if args.real_zip else None
    report = {
        "version": "1.5.0",
        "timings": measures,
        "scale_limits": limits,
        "rule_corpus": corpus,
        "corpus_scope": "12 manually labeled positives + 12 negatives; generated exclusions tested separately. Not population precision/recall proof.",
        "user_repository": (
            {
                "input": args.real_zip.name,
                "executed": False,
                "scope_counts": real["code_quality"]["scope_counts"],
                "state": real["code_quality"]["state"],
                "functions": len(real["quality_metrics"]),
                "quality_findings": sum(f["category"] == "QUALITY" for f in real["findings"]),
                "duplication_groups": len(real["code_quality"]["duplication"]["groups"]),
                "parser_partial_files": sum(r["parser_state"] == "PARTIAL" for r in real["code_quality"]["inventory"]),
                "coverage": real["code_quality"]["coverage"]["state"],
                "native_sast_findings": sum(f["category"] == "SAST" for f in real["findings"]),
            }
            if real
            else None
        ),
    }
    report["process_memory"] = memory()
    report["environment"] = {
        "python": sys.version,
        "platform": platform.platform(),
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "parser_signature": PARSER_SIGNATURE,
    }
    report["sarif_schema_sha256"] = hashlib.sha256(
        (Path(__file__).resolve().parents[1] / "tests/schemas/sarif-2.1.0.json").read_bytes()
    ).hexdigest()
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["user_repository"]), flush=True)


if __name__ == "__main__":
    main()
