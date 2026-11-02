"""Exact, payload-free measurement of the v1 analysis checkpoint envelope."""

from __future__ import annotations

import json

import pytest

from backend.checkpoint_diagnostics import SCHEMA, count_v1_envelope_bytes, v1_size_diagnostic


def _reference_v1_bytes(result, *, job_id="job", organization_id="tenant", repository_id="repo", signature="sig"):
    normalized = {**result, "files": list(result["files"])} if "files" in result else result
    envelope = {
        "schema": "projecttrace-analysis-checkpoint-v1",
        "job_id": job_id,
        "organization_id": organization_id,
        "repository_id": repository_id,
        "signature": signature,
        "result": normalized,
    }
    payload = "".join(json.JSONEncoder(sort_keys=True).iterencode(envelope))
    return len(payload.encode("utf-8"))


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"findings": [], "claims": [], "files": []},
        {
            "nested": {"unicode": "café 雪", "escaped": 'quote " slash \\ tab\t newline\n'},
            "numbers": [0, -3, 1.25, True, None, float("nan"), float("inf"), -float("inf")],
            "numeric_keys": {1: "one", 2: "two", 3.5: "three-point-five"},
            "files": [{"path": f"src/f{i}.py", "metrics": [i, i + 1]} for i in range(3)],
        },
        {
            "files": [{"metric": "private-metric-a"}, {"metric": "private-metric-b"}],
            "metrics": [{"symbol": f"symbol-{i}", "value": i} for i in range(12)],
            "code_quality": {"metrics": [{"rule": "quality", "count": 3}], "summary": {"score": 0.75}},
            "claims": [{"text": "private-claim", "evidence": ["a.py:1", "b.py:2"]}],
        },
    ],
)
def test_count_matches_published_v1_serializer(result):
    assert count_v1_envelope_bytes(
        result, job_id="job", organization_id="tenant", repository_id="repo", signature="sig"
    ) == _reference_v1_bytes(result)


def test_files_iterable_is_normalized_once_with_v1_order_and_values():
    class OnePass:
        def __init__(self, rows):
            self.rows = rows
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            assert self.iterations == 1
            return iter(self.rows)

    rows = [{"path": f"src/file-{i}.py", "metrics": [i, i * 2]} for i in range(10)]
    one_pass = OnePass(rows)
    result = {"files": one_pass, "metrics": rows}
    actual = count_v1_envelope_bytes(
        result, job_id="job", organization_id="tenant", repository_id="repo", signature="sig"
    )
    assert actual == _reference_v1_bytes({"files": rows, "metrics": rows})
    assert one_pass.iterations == 1


def test_safe_diagnostic_is_allowlisted_and_does_not_expose_values():
    secret = "SYNTHETIC_SOURCE_VALUE_DO_NOT_LEAK"
    receipt = v1_size_diagnostic(
        {"private": secret, "files": [{"observation": secret}]},
        job_id="job",
        organization_id="tenant",
        repository_id="repo",
        signature="sig",
        limit_bytes=100_000,
    )
    assert set(receipt) == {"schema", "actual_bytes", "limit_bytes", "over_budget"}
    assert receipt["schema"] == SCHEMA
    assert receipt["actual_bytes"] == _reference_v1_bytes(
        {"private": secret, "files": [{"observation": secret}]}
    )
    assert secret not in json.dumps(receipt)


def test_counter_rejects_encoder_default_drift(monkeypatch):
    import backend.checkpoint_diagnostics as diagnostics

    original_encoder = json.JSONEncoder

    class ChangedEncoder(original_encoder):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.ensure_ascii = False

    monkeypatch.setattr(diagnostics.json, "JSONEncoder", ChangedEncoder)
    with pytest.raises(RuntimeError, match="encoder configuration changed"):
        diagnostics.count_v1_envelope_bytes(
            {"files": []}, job_id="job", organization_id="tenant", repository_id="repo", signature="sig"
        )


def test_budget_boundary_uses_small_monkeypatched_limit(monkeypatch):
    import backend.analysis_checkpoints as checkpoints

    result = {"files": [{"path": "a.py"}], "metrics": [{"count": 1}]}
    actual = _reference_v1_bytes(result)
    monkeypatch.setattr(checkpoints, "budget", lambda: actual + 1)
    below = v1_size_diagnostic(result, job_id="job", organization_id="tenant", repository_id="repo", signature="sig")
    monkeypatch.setattr(checkpoints, "budget", lambda: actual)
    exact = v1_size_diagnostic(result, job_id="job", organization_id="tenant", repository_id="repo", signature="sig")
    monkeypatch.setattr(checkpoints, "budget", lambda: actual - 1)
    above = v1_size_diagnostic(result, job_id="job", organization_id="tenant", repository_id="repo", signature="sig")
    assert (below["actual_bytes"], below["over_budget"]) == (actual, False)
    assert (exact["actual_bytes"], exact["over_budget"]) == (actual, False)
    assert (above["actual_bytes"], above["over_budget"]) == (actual, True)


def test_counter_checkpoint_callback_failure_returns_no_partial_measurement():
    def cancelled():
        raise RuntimeError("stop diagnostic")

    with pytest.raises(RuntimeError, match="stop diagnostic"):
        count_v1_envelope_bytes(
            {"files": [{"path": "a.py"}]},
            job_id="job",
            organization_id="tenant",
            repository_id="repo",
            signature="sig",
            checkpoint=cancelled,
        )
