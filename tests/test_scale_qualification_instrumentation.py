import json

from scripts.qualify_scale_workload import safe_performance


def test_safe_performance_retains_boundary_totals_without_file_paths():
    snapshot = {
        "schema": "projecttrace-performance-v1",
        "clock": "WALL_PERF_COUNTER",
        "stage_seconds": {"ANALYZING": 12.5},
        "components": {
            "SANDBOX_BOUNDARY_LANGUAGES": {"count": 4, "seconds": 3.25, "max_seconds": 1.2},
            "CONTAINED_NATIVE": {"count": 2, "seconds": 6.5, "max_seconds": 4.0},
        },
        "counters": {"parser_cache_misses": 40},
        "helper_concurrency_max": 2,
        "source_cache_bytes_max": 2_000_000,
        "timing_scope": "aggregate-only",
        "slowest_file_operations": [{"path": "customer/private/source.py", "seconds": 9.0}],
        "secret_payload": "must not appear in the receipt",
    }
    filtered = safe_performance(snapshot)

    assert filtered["components"]["SANDBOX_BOUNDARY_LANGUAGES"]["count"] == 4
    assert filtered["components"]["CONTAINED_NATIVE"]["seconds"] == 6.5
    encoded = json.dumps(filtered)
    assert "slowest_file_operations" not in encoded
    assert "customer/private/source.py" not in encoded
    assert "secret_payload" not in encoded


def test_safe_performance_rejects_non_mapping_snapshots():
    assert safe_performance(None) == {}
    assert safe_performance(["not", "a", "mapping"]) == {}
