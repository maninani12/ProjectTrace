"""Owned original-index CPU attribution. No candidate compiler/index/schema changes."""

import argparse
import cProfile
import json
import pstats
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tests import snapshot_materialization_probe as original


def group(filename, function):
    filename = filename.replace("\\", "/")
    if "sqlite3" in function and any(word in function for word in ("execute", "fetch")):
        return "SQLITE_EXECUTE_OR_FETCH"
    if "/json/" in filename or filename.endswith("/backend/json_export.py"):
        return "PYTHON_JSON"
    if filename.endswith("/sql/compiler.py"):
        return "SQLALCHEMY_COMPILATION"
    if function in {"_init_compiled", "construct_params", "_execute_context", "_execute_clauseelement"}:
        return "SQLALCHEMY_PARAMETERS_AND_EXECUTION"
    if "/orm/loading.py" in filename or filename.endswith("/backend/generation_context.py"):
        return "ORM_OR_TYPED_HYDRATION"
    if filename.endswith("/backend/generations.py") and function == "encoded":
        return "TYPED_CALLBACK"
    if "/cryptography/" in filename:
        return "CRYPTOGRAPHY"
    return "OTHER"


def run(root, cpu_only=False):
    profile = cProfile.Profile()

    class Recorder(original.Recorder):
        def sample(self):
            if cpu_only:
                self.stop.wait()
            else:
                super().sample()

        @contextmanager
        def span(self, name, **attributes):
            with super().span(name, **attributes) as item:
                if name == "COMPLETE_ANALYSIS":
                    profile.enable()
                try:
                    yield item
                finally:
                    if name == "COMPLETE_ANALYSIS":
                        profile.disable()

    with patch.object(original, "Recorder", Recorder):
        result = original.run(root, phases=("cold",))
    if cpu_only:
        result["sample_interval_seconds"] = None
        result["resource_sampling"] = (
            "BACKGROUND_DISABLED_FOR_CPU_ATTRIBUTION; Win32 cumulative process peak at span boundaries"
        )
    rows = [
        {
            "file": filename,
            "line": line,
            "function": name,
            "primitive_calls": primitive,
            "calls": calls,
            "self_seconds": own,
            "cumulative_seconds": cumulative,
            "group": group(filename, name),
        }
        for (filename, line, name), (primitive, calls, own, cumulative, _) in pstats.Stats(profile).stats.items()
    ]
    grouped = {}
    for row in rows:
        item = grouped.setdefault(row["group"], {"self_seconds": 0, "functions": 0, "calls": 0})
        item["self_seconds"] += row["self_seconds"]
        item["functions"] += 1
        item["calls"] += row["calls"]
    receipt = {
        "scope": "OWNED_WINDOWS_ORIGINAL_INDEX_147_METRIC_CPU_PROFILE_ONLY",
        "profiling_overhead": True,
        "function_cumulative_times_overlap": True,
        "groups_sum_exclusive_self_time_only": grouped,
        "functions": sorted(rows, key=lambda item: item["cumulative_seconds"], reverse=True),
        "pipeline": result,
    }
    (root / "cpu-attribution.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"states": result["states"], "process": result["final_process"], "groups": grouped}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--cpu-only", action="store_true")
    args = parser.parse_args()
    run(args.root, args.cpu_only)
