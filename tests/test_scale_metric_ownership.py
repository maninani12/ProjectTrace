import copy

import pytest

from analyzers.code_quality.core import build
from analyzers.engine import analyze, native_observations


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


def test_engine_rejects_implicit_cache_ownership_transfer():
    with pytest.raises(ValueError, match="explicit observations"):
        analyze({"a.py": "pass"}, consume_metrics=True)


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
