from scripts.qualify_scale_workload import aggregate_performance
from scripts.scale_linux_resources import cgroup_diagnostics


def test_cgroup_diagnostics_separates_file_charge_and_reclaim_without_fabricating_zero(tmp_path):
    (tmp_path / "memory.stat").write_text("anon 100\nfile 200\nfile_dirty 20\nfile_writeback 10\n")
    (tmp_path / "cpu.stat").write_text("usage_usec 400\nthrottled_usec 50\n")
    (tmp_path / "memory.pressure").write_text("some avg10=1.00 avg60=0.50 avg300=0.10 total=123\n")
    result = cgroup_diagnostics(tmp_path)
    assert result["memory.stat"] == {"anon": 100, "file": 200, "file_dirty": 20, "file_writeback": 10}
    assert result["cpu.stat"]["throttled_usec"] == 50
    assert "total=123" in result["memory.pressure"]
    assert result["io.stat"] == "UNAVAILABLE"
    (tmp_path / "memory.stat").write_text("anon malformed\n")
    assert cgroup_diagnostics(tmp_path)["memory.stat"] == "UNAVAILABLE"


def test_failure_performance_keeps_aggregate_costs_without_exporting_file_details():
    captured = {"stage_seconds": {"ANALYZING": 1800},
                "components": {"OBSERVATION_SPILL": {"seconds": 40, "count": 10}},
                "counters": {"native_metric_rows": 11097},
                "slowest_file_operations": [{"path": "PRIVATE-SOURCE-SENTINEL"}],
                "future_private_field": "PRIVATE-SOURCE-SENTINEL"}
    result = aggregate_performance(captured)
    assert result["components"]["OBSERVATION_SPILL"]["seconds"] == 40
    assert result["counters"]["native_metric_rows"] == 11097
    assert "PRIVATE-SOURCE-SENTINEL" not in str(result)
    assert aggregate_performance({}) == {"stage_seconds": {}, "components": {}, "counters": {}}


def test_post_exit_job_performance_recovers_committed_aggregates_without_source_details():
    import json
    import sqlite3

    from scripts.run_scale_cgroup import durable_job_performance

    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE records(kind TEXT,data TEXT)")
        db.execute("INSERT INTO records VALUES ('job',?)", (json.dumps({"state": "EXTRACTING_CLAIMS",
            "stage": "EXTRACTING_CLAIMS", "files": "PRIVATE-SOURCE-SENTINEL", "performance": {
                "components": {"OPENAPI_CONTRACT_BATCH": {"seconds": 0.5, "count": 1}},
                "slowest_file_operations": [{"path": "PRIVATE-SOURCE-SENTINEL"}]}}),))
        result = durable_job_performance(db)
    assert result[0]["state"] == "EXTRACTING_CLAIMS"
    assert result[0]["performance"]["components"]["OPENAPI_CONTRACT_BATCH"]["count"] == 1
    assert "PRIVATE-SOURCE-SENTINEL" not in str(result)
