from types import SimpleNamespace

from scripts.benchmark_repository_analysis import unix_process_stats
from scripts.process_telemetry import MemoryWindow, proc_memory
from scripts.scale_linux_resources import namespace_rss


def test_proc_labels_current_rss_and_address_space_high_water_mark(tmp_path):
    (tmp_path / "status").write_text("Pid: 123\nVmRSS: 4096 kB\nVmHWM: 8192 kB\n")
    sample = proc_memory(tmp_path)
    assert sample["rss_bytes"] == 4_194_304
    assert sample["peak_rss_bytes"] == 8_388_608
    assert sample["rss_source"] == "proc/status:VmRSS"
    assert sample["peak_scope"] == "CURRENT_ADDRESS_SPACE_SINCE_EXEC"
    assert sample["memory_available"]
    assert sample["observed_monotonic"] > 0


def test_missing_memory_is_unavailable_not_zero(tmp_path):
    sample = proc_memory(tmp_path)
    assert not sample["memory_available"]
    assert sample["rss_bytes"] is sample["peak_rss_bytes"] is None
    (tmp_path / "status").write_text("Pid: 123\nVmRSS: 17 MB\nVmHWM: invalid kB\n")
    sample = proc_memory(tmp_path)
    assert not sample["memory_available"]
    assert sample["rss_bytes"] is sample["peak_rss_bytes"] is None


def test_valid_zero_is_distinct_from_absent_counter(tmp_path):
    (tmp_path / "status").write_text("VmRSS: 0 kB\nVmHWM: 0 kB\n")
    sample = proc_memory(tmp_path)
    assert sample["memory_available"]
    assert sample["rss_bytes"] == sample["peak_rss_bytes"] == 0


def test_window_tracks_real_reader_values_without_manufacturing_zero():
    values = iter([{"rss_bytes": 11}, {"rss_bytes": None}, {"rss_bytes": 29}, {}])
    window = MemoryWindow(lambda: next(values))
    for _ in range(4):
        window.observe()
    assert (window.samples, window.missing, window.peak) == (4, 2, 29)
    missing = MemoryWindow(lambda: None)
    missing.observe()
    assert missing.peak is None and missing.missing == 1


def test_namespace_memory_distinguishes_owner_children_and_missing_counters(tmp_path):
    for pid, text in [(10, "VmRSS: 12 kB"), (20, "VmRSS: 5 kB")]:
        target = tmp_path / str(pid)
        target.mkdir()
        (target / "status").write_text(text)
    sample = namespace_rss(tmp_path, 10)
    assert sample["namespace_rss_complete"]
    assert sample["coordinator_rss_bytes"] == 12 * 1024
    assert sample["child_rss_bytes"] == 5 * 1024
    assert sample["namespace_rss_bytes"] == 17 * 1024
    (tmp_path / "20/status").write_text("Pid: 20")
    sample = namespace_rss(tmp_path, 10)
    assert not sample["namespace_rss_complete"]
    assert sample["namespace_rss_bytes"] is sample["child_rss_bytes"] is None
    assert sample["namespace_rss_lower_bound_bytes"] == 12 * 1024
    assert sample["missing_process_samples"] == 1


def test_resource_peak_is_not_relabelled_as_current_or_address_space_rss(tmp_path):
    (tmp_path / "status").write_text("VmRSS: 4096 kB\nVmHWM: 8192 kB\n")
    row = SimpleNamespace(ru_utime=1.25, ru_stime=0.5, ru_maxrss=405_740)
    sample = unix_process_stats(row, tmp_path, "linux")
    assert sample["cpu_seconds"] == 1.75
    assert sample["resource_peak_rss_bytes"] == 415_477_760
    assert sample["rss_bytes"] == 4_194_304
    assert sample["peak_rss_bytes"] == 8_388_608
    assert "GETRUSAGE" in sample["resource_peak_scope"]


def test_platform_resource_units_and_absent_proc_do_not_invent_rss(tmp_path):
    row = SimpleNamespace(ru_utime=0, ru_stime=0, ru_maxrss=1024)
    sample = unix_process_stats(row, tmp_path, "darwin")
    assert sample["resource_peak_rss_bytes"] == 1024
    assert not sample["memory_available"]
    assert sample["rss_bytes"] is sample["peak_rss_bytes"] is None
