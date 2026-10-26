import copy
import json
import time

import pytest

from analyzers import engine
from analyzers.code_quality import core
from scripts.scale_operation_probe import operation_probe


def events(path):
    return [json.loads(row) for row in path.read_text().splitlines()]


def test_operation_probe_preserves_nested_return_identity_and_restores_functions(tmp_path, monkeypatch):
    payload = {"source": "PRIVATE-INPUT-SENTINEL"}
    monkeypatch.setattr(core, "classify", lambda *_a: payload)
    def build(*a, **kw):
        return core.classify(*a)
    monkeypatch.setattr(engine, "quality_build", build)
    path = tmp_path / "operations.jsonl"
    stage = ["ANALYZING"]
    with operation_probe(stage, path, time.monotonic(), sample=lambda: {"available": False}, scenario=["owned"]):
        assert engine.quality_build(payload) is payload
        assert events(path) == []
        stage[0] = "VERIFYING"
        assert engine.quality_build(payload) is payload
        rows = events(path)  # Already flushed before the context is closed.
    assert engine.quality_build is build
    assert [(r["operation"], r["event"]) for r in rows] == [
        ("QUALITY_BUILD", "START"), ("QUALITY_INVENTORY", "START"),
        ("QUALITY_INVENTORY", "END"), ("QUALITY_BUILD", "END")]
    assert rows[1]["parent"] == rows[0]["call"] == rows[2]["parent"]
    assert all(r["scenario"] == "owned" for r in rows)
    assert "PRIVATE-INPUT-SENTINEL" not in path.read_text()


def test_operation_probe_preserves_original_exception_without_exporting_its_message(tmp_path, monkeypatch):
    error = RuntimeError("PRIVATE-EXCEPTION-SENTINEL")
    def fail(*_a, **_k):
        raise error
    monkeypatch.setattr(engine, "verify_claim", fail)
    path = tmp_path / "operations.jsonl"
    with pytest.raises(RuntimeError) as raised:
        with operation_probe(["VERIFYING"], path, time.monotonic(), sample=lambda: {"available": False}):
            engine.verify_claim("PRIVATE-INPUT-SENTINEL")
    assert raised.value is error and engine.verify_claim is fail
    assert [r["event"] for r in events(path)] == ["START", "ERROR"]
    assert "PRIVATE-" not in path.read_text()


def test_owned_quality_phase_observer_retains_complete_output_and_input(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    files = {"owned.py": "def owned(value):\n    return value + 1\n"}
    observed = engine.native_observations(files)
    saved = copy.deepcopy(observed[4])
    expected = core.build(files, observed[4], observed[1], observed[0], observed[2])
    expected[1].pop("performance")
    phases = []
    path = tmp_path / "operations.jsonl"
    with operation_probe(["VERIFYING"], path, time.monotonic(), sample=lambda: {"available": False}):
        actual = core.build(files, observed[4], observed[1], observed[0], observed[2],
                            observe=lambda *event: phases.append(event))
    actual[1].pop("performance")
    assert actual == expected and observed[4] == saved
    assert phases == [(name, event) for name in ("METRIC_PROJECTION", "METRIC_OWNER_INDEX",
        "PRODUCTION_METRIC_SELECTION", "QUALITY_SYMBOLS", "QUALITY_RULES") for event in ("START", "END")]
    assert {r["operation"] for r in events(path)} >= {name for name, _ in phases}


def test_quality_phase_observer_failure_is_not_silently_ignored(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    failure = RuntimeError("owned observer failure")
    def fail(*_a):
        raise failure
    with pytest.raises(RuntimeError) as raised:
        core.build({}, [], [], [], [], observe=fail)
    assert raised.value is failure
