import copy

import pytest

from analyzers.code_quality.core import build
from analyzers.engine import analyze, native_observations
from analyzers.observation_store import EncryptedRows


def test_owned_metric_transfer_preserves_complete_results_and_cached_tokens(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    files = {"a.py": "def f(x):\n    return x + 1\n"}
    observation = native_observations(files)
    metrics = observation[4]
    original = copy.deepcopy(metrics)
    expected_findings, expected = build(files, metrics, observation[1], observation[0], observation[2])
    assert metrics == original
    transferred = copy.deepcopy(metrics)
    findings, actual = build(files, transferred, observation[1], observation[0], observation[2], consume_metrics=True)
    expected.pop("performance")
    actual.pop("performance")
    assert (findings, actual) == (expected_findings, expected)
    assert actual["metrics"][0] is transferred[0]
    assert all("duplicate_tokens" not in row for row in transferred)
    assert metrics == original
    assert observation[6]["a.py"]["quality_metrics"] == original


@pytest.mark.parametrize("observations", [None, (), []])
def test_engine_rejects_implicit_cache_ownership_transfer(observations):
    with pytest.raises(ValueError, match="explicit observations"):
        analyze({"a.py": "pass"}, observations=observations, consume_metrics=True)


def test_owned_transfer_runs_duplication_before_releasing_tokens(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    body = "def work(x):\n" + "".join(f"    value{i} = x + {i}\n" for i in range(15)) + "    return value0\n"
    files = {"a.py": body, "b.py": body}
    observation = native_observations(files)
    baseline = build(files, observation[4], observation[1], observation[0], [])
    owned = build(files, copy.deepcopy(observation[4]), observation[1], observation[0], [], consume_metrics=True)
    for _, quality in (baseline, owned):
        quality.pop("performance")
    assert owned == baseline
    assert owned[1]["duplication"]["groups"]


def test_spooled_quality_selection_avoids_a_second_metric_decode_pass(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    body = "def work(x):\n" + "".join(f"    value{i} = x + {i}\n" for i in range(15)) + "    return value0\n"
    files = {"a.py": body, "b.py": body}
    observation = native_observations(files)
    expected_findings, expected = build(
        files, observation[4], observation[1], observation[0], observation[2]
    )
    rows = EncryptedRows(
        ("org-1", "repo-1", "inventory-1"),
        maximum_bytes=16_000_000,
        row_bytes=2_000_000,
    )
    rows.label = "NATIVE_METRICS"
    try:
        rows.extend(copy.deepcopy(observation[4]))

        def reject_full_rescan(*_args, **_kwargs):
            pytest.fail("quality aggregation performed a redundant predicate scan of encrypted metrics")

        monkeypatch.setattr(rows, "select", reject_full_rescan)
        actual_findings, actual = build(
            files, rows, observation[1], observation[0], observation[2]
        )
        expected.pop("performance")
        actual.pop("performance")
        assert (actual_findings, actual) == (expected_findings, expected)
    finally:
        rows.close()

def test_native_observations_reuses_source_iac_classification(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    import analyzers.engine as engine

    original = engine.is_iac_source
    seen = []

    def count_classification(path, source):
        seen.append(path)
        return original(path, source)

    monkeypatch.setattr(engine, "is_iac_source", count_classification)
    files = {
        "a.py": "def f(x):\n    return x + 1\n",
        "b.py": "def g(y):\n    return y * 2\n",
        "README.md": "Notes about a small project.\n",
    }
    engine.native_observations(files)
    assert sorted(seen) == sorted(files)
