import json
from collections import Counter

import pytest

from analyzers import engine, isolated_analysis, sandbox
from analyzers.isolated_worker import dispatch
from analyzers.performance import Performance
from tests.test_repository_store import storage  # noqa: F401 -- owned fixture


def local_batch(monkeypatch):
    calls = []

    def call(operation, value):
        assert operation == "openapi_batch"
        calls.append(value["files"])
        return dispatch(operation, value, engine, sandbox)

    monkeypatch.setattr(sandbox, "call", call)
    return calls


def force_batches(monkeypatch, *, cancel=False):
    original = isolated_analysis.OpenAPIContracts

    def factory(*args, **kwargs):
        if cancel:
            checkpoint = kwargs.get("checkpoint")

            def stop():
                if checkpoint:
                    checkpoint()
                raise TimeoutError("Owned batch deadline")

            kwargs["checkpoint"] = stop
        reader = original(*args, **kwargs)
        reader.contained = True  # Owned portable dispatch; no Linux enforcement claim.
        return reader

    monkeypatch.setattr(isolated_analysis, "OpenAPIContracts", factory)


def test_unrelated_json_is_parsed_in_bounded_batches_and_sources_are_read_once(monkeypatch):
    class Counted(dict):
        reads = Counter()

        def __getitem__(self, path):
            self.reads[path] += 1
            return super().__getitem__(path)

    files = Counted({f"owned-{i}.json": json.dumps({"entity": i, "private": "OWNED-PRIVATE-SENTINEL"})
                     for i in range(225)})
    calls = local_batch(monkeypatch)
    performance = Performance()
    reader = isolated_analysis.OpenAPIContracts(files, performance=performance)
    reader.contained = True
    for path in files:
        assert reader.read(path) == (None, False, False)
        assert len(reader.pending) < 100
    assert len(calls) == 3 and not reader.pending
    assert files.reads == Counter({path: 1 for path in files})
    assert performance.snapshot()["counters"]["openapi_consumed_files"] == 225
    assert all(len(batch) <= 100 and sum(len(s.encode()) for s in batch.values()) <= 512_000 for batch in calls)
    # No irrelevant JSON object or private field crosses the helper response.
    value = dispatch("openapi_batch", {"files": {"owned.json": files["owned-0.json"]}}, engine, sandbox)
    assert "OWNED-PRIVATE-SENTINEL" not in json.dumps(value)


def test_byte_ceiling_is_independent_of_file_count_and_deadline_is_checked(monkeypatch):
    files = {f"owned-{i}.json": json.dumps({"blob": "x" * 200_000}) for i in range(5)}
    calls = local_batch(monkeypatch)
    checked = []
    reader = isolated_analysis.OpenAPIContracts(files, checkpoint=lambda: checked.append(True))
    reader.contained = True
    assert all(reader.read(path) == (None, False, False) for path in files)
    assert [len(batch) for batch in calls] == [2, 2, 1]
    assert len(checked) == 3


@pytest.mark.parametrize("change", ["path", "hash", "invalid", "mentions", "contract", "missing-field"])
def test_parent_rejects_response_substitution_and_malformed_contracts(monkeypatch, change):
    files = {"owned.json": '{"openapi":"3.0.0","paths":{}}'}
    response = dispatch("openapi_batch", {"files": files}, engine, sandbox)
    if change == "path":
        response["foreign.json"] = response.pop("owned.json")
    elif change == "hash":
        response["owned.json"]["source_hash"] = "wrong"
    elif change == "invalid":
        response["owned.json"]["invalid"] = "false"
    elif change == "mentions":
        response["owned.json"]["mentions_openapi"] = False
    elif change == "contract":
        response["owned.json"]["contract"] = {"unrelated": True}
    else:
        response["owned.json"].pop("contract")
    monkeypatch.setattr(sandbox, "call", lambda *_a, **_k: response)
    reader = isolated_analysis.OpenAPIContracts(files)
    reader.contained = True
    with pytest.raises(sandbox.SandboxFailure, match="HELPER_OPENAPI_"):
        reader.read("owned.json")


def normalized(value):
    if isinstance(value, list):
        return [normalized(row) for row in value]
    if isinstance(value, dict):
        return {key: normalized(row) for key, row in value.items()
                if not (key == "performance" and isinstance(row, dict) and set(row) == {"quality_ms"})}
    return value


def test_complete_analysis_matches_single_file_contract_reads_including_escaped_keys_and_warnings(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    files = {
        "README.md": "The API exposes GET /health.\n",
        "app.py": "from flask import Flask\napp=Flask(__name__)\n@app.route('/health')\ndef health(): return True\n",
        "unrelated.json": '{"description":"The word openapi is only data"}',
        "contract.json": '{"openapi":"3.0.0","paths":{"/health":{"get":{}},"/missing":{"post":{}}}}',
        "escaped.json": '{"open\\u0061pi":"3.0.0","paths":{"/escaped":{"head":{}}}}',
        "invalid.json": '{"openapi":',
        "invalid-unrelated.json": '{',
        "invalid-paths.json": '{"openapi":"3.0.0","paths":null}',
        "partial-methods.json": '{"openapi":"3.0.0","paths":{"/partial":["get","post",7]}}',
    }
    expected = engine.analyze(files)
    calls = local_batch(monkeypatch)
    force_batches(monkeypatch)
    actual = engine.analyze(files)
    assert normalized(actual) == normalized(expected)
    assert len(calls) == 1
    claims = {row["expected"]: row for row in actual["claims"] if row["origin"] == "DOCUMENTATION"}
    assert claims["GET /health"]["status"] == "VERIFIED"
    assert "HEAD /escaped" in claims and "POST /partial" in claims
    assert {r["path"] for r in actual["warnings"] if r["analyzer"] == "API"} == {
        "invalid.json", "invalid-paths.json", "partial-methods.json"}


@pytest.mark.parametrize("trailing", [False, True])
def test_candidate_budget_order_and_diagnostics_match_legacy(monkeypatch, trailing):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    files = {"contract.json": json.dumps({"openapi": "3.0.0", "paths": {
        f"/owned-{i}": {"get": {}} for i in range(1502)}})}
    if trailing:
        files["trailing.txt"] = "owned inert data"
    expected = engine.analyze(files)
    local_batch(monkeypatch)
    force_batches(monkeypatch)
    actual = engine.analyze(files)
    assert normalized(actual) == normalized(expected)
    claims = [r for r in actual["claims"] if r.get("assertion_family") == "api_contract"]
    # The unchanged final declaration cap follows the candidate cap.
    assert len(claims) == 1500 and claims[0]["expected"] == "GET /owned-0"
    assert claims[-1]["expected"] == "GET /owned-1499"


def test_claim_batch_deadline_fails_without_publication_and_preserves_parser_cache(storage, monkeypatch):  # noqa: F811
    from sqlalchemy import func, select

    from backend.db import ParserArtifact, Record
    from backend.generation_models import PublishedGeneration
    from backend.jobs import execute_analysis
    from tests.test_repository_store import captured

    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    db, user, repo = storage
    files = captured(storage, {f"owned-{i}.json": '{"entity":"owned"}' for i in range(110)})
    calls = local_batch(monkeypatch)
    force_batches(monkeypatch, cancel=True)
    with pytest.raises(TimeoutError, match="Owned batch deadline"):
        execute_analysis(db, user, repo, files)
    assert len(calls) == 1
    assert db.scalar(select(func.count()).select_from(ParserArtifact)) > 0
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    job = db.scalar(select(Record).where(Record.kind == "job"))
    assert job.data["state"] == "FAILED" and job.data["error_code"] == "ANALYSIS_TIME_BUDGET"


def test_helper_rejects_out_of_scope_sources_and_over_budget_batches():
    with pytest.raises(ValueError, match="budget"):
        dispatch("openapi_batch", {"files": {f"owned-{i}.json": "{}" for i in range(101)}}, engine, sandbox)
    with pytest.raises(ValueError, match="budget"):
        dispatch("openapi_batch", {"files": {"owned.json": "x" * 512_001}}, engine, sandbox)
    with pytest.raises(ValueError, match="scope"):
        dispatch("openapi_batch", {"files": {"owned.txt": "{}"}}, engine, sandbox)


@pytest.mark.parametrize("depth", [97, 99])
def test_batch_wrapper_preserves_original_per_source_protocol_depth_guard(monkeypatch, depth):
    source = '{"openapi":"3","paths":{},"nested":' + '[' * depth + '0' + ']' * depth + '}'
    files = {"owned.json": source}
    calls, checkpoints = [], []

    def invoke(operation, value, **limits):
        calls.append(operation)
        response = dispatch(operation, value, engine, sandbox)
        return json.dumps({"ok": True, "result": response}).encode(), None

    monkeypatch.setattr(sandbox, "invoke", invoke)
    monkeypatch.setattr(sandbox, "required", lambda: True)
    reader = isolated_analysis.OpenAPIContracts(files, checkpoint=lambda: checkpoints.append(True))
    if depth == 97:
        actual, mentions, invalid = reader.read("owned.json")
        assert actual == json.loads(source) and mentions and not invalid
        assert len(checkpoints) == 2
    else:
        with pytest.raises(sandbox.SandboxFailure, match="HELPER_PROTOCOL"):
            reader.read("owned.json")
    assert calls == ["openapi_batch", "json"]
