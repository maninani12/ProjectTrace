"""Real static input -> immutable claims -> BASE/HEAD projection, no target execution."""
import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from analyzers.engine import analyze
from analyzers.verifiers import verify_claim
from backend import main
from backend.db import Record, Repository, User
from backend.generation_models import AnalysisGeneration
from backend.generations import Generation
from backend.jobs import execute_analysis
from backend.repository_store import RepositoryFiles
from tests.test_code_quality import import_repo
from tests.test_engineering_changes import advance
from tests.test_repository_store import captured, storage  # noqa: F401

FIXTURE = json.loads(Path("samples/auth-drift.json").read_text())


def jwt_claim(result):
    return next(c for c in result["claims"] if c.get("origin") == "DOCUMENTATION" and c.get("expected") == "jwt")


@pytest.mark.parametrize(("source", "status"), [
    ("import jwt\njwt.encode(payload, key)", "VERIFIED"),
    ("app.add_middleware(SessionMiddleware, secret_key=settings.key)", "CONTRADICTED"),
    ("import jwt", "INFERRED"),
    ("# jwt.encode(payload, key)\nmessage = 'SessionMiddleware'", "UNVERIFIED"),
    ("def broken(:", "UNVERIFIED"),
    ("", "UNVERIFIED"),
    ("jwt.encode(payload, key)\napp.add_middleware(SessionMiddleware)", "VERIFIED"),
])
def test_authentication_classification_uses_positive_syntax(source, status):
    claim = jwt_claim(analyze({"README.md": "Authentication uses JWT.", "app.py": source}))
    assert claim["status"] == status
    assert bool(claim["signals"]) == (status != "UNVERIFIED")


def test_verdict_and_evidence_order_are_deterministic_and_cache_includes_absence():
    claim = {"category": "AUTHENTICATION", "expected": "jwt"}
    signals = [{"type": "auth", "value": "session", "path": p, "line": 4} for p in ("b.py", "a.py")]
    original, _ = verify_claim(claim, signals, [])
    reordered, reused = verify_claim(claim, list(reversed(signals)), [])
    assert original == reordered and not reused
    cached, reused = verify_claim(claim, signals, [], original)
    assert cached == original and reused
    missing, reused = verify_claim(claim, [], [], original)
    assert missing["status"] == "UNVERIFIED" and not reused


def test_captured_auth_drift_has_original_claim_both_sources_and_tenant_boundaries(signed, tmp_path):
    sentinel = tmp_path / "imported-code-executed"
    base_files = {**FIXTURE["base"], "never_run.py": f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"}
    repo, baseline = import_repo(signed, base_files)
    with main.Session() as db:
        original = copy.deepcopy(db.get(Record, baseline).data)
    head = advance(signed, repo, baseline, {**FIXTURE["head"], "never_run.py": base_files["never_run.py"]})
    listing = signed.get(f"/api/engineering-changes?repository_id={repo}").json()
    change = signed.get("/api/engineering-changes/" + listing["items"][0]["id"]).json()
    assert change["base_snapshot_id"] == baseline and change["head_snapshot_id"] == head
    comparison = next(c for c in change["claim_comparisons"] if c["text"] == "Authentication uses JWT.")
    assert comparison["before"]["status"] == "VERIFIED"
    assert comparison["after"]["status"] == "CONTRADICTED"
    assert not comparison["before"]["evidence_truncated"] and not comparison["after"]["evidence_truncated"]
    before, after = (c["evidence"][0] for c in (comparison["before"], comparison["after"]))
    assert before["path"] == after["path"] == "app.py" and before["hash"] != after["hash"]
    assert "jwt.encode" in signed.get("/api/record/" + before["id"]).json()["source"]
    assert "SessionMiddleware" in signed.get("/api/record/" + after["id"]).json()["source"]
    assert "Authentication uses JWT." in signed.get("/api/record/" + comparison["document"]["id"]).json()["source"]
    claim = signed.get("/api/record/" + comparison["after"]["claim_id"]).json()
    assert [h["status"] for h in claim["history"]] == ["VERIFIED", "STALE", "CONTRADICTED"]
    with main.Session() as db:
        assert db.get(Record, baseline).data == original
        drifts = list(db.scalars(select(Record).where(Record.repository_id == repo, Record.kind == "drift")))
        assert drifts and all(d.data["base_id"] == baseline for d in drifts)
    assert not sentinel.exists()  # Imported source was parsed as data, never run.
    login = signed.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"})
    assert login.status_code == 200
    for identifier in (change["id"],):
        assert signed.get("/api/engineering-changes/" + identifier).status_code == 404
    for identifier in (baseline, head, before["id"], after["id"], comparison["document"]["id"], claim["id"]):
        assert signed.get("/api/record/" + identifier).status_code == 404
    assert signed.get(f"/api/engineering-changes?repository_id={repo}").status_code == 404


def test_auth_drift_recovery_publishes_comparison_once_after_restart(storage, monkeypatch):  # noqa: F811
    db, actor, repo = storage
    baseline, _ = execute_analysis(db, actor, repo, captured(storage, FIXTURE["base"]))
    baseline_id = baseline.id
    db.refresh(baseline)  # Compare the persisted JSON representation across Sessions.
    original = copy.deepcopy(baseline.data)
    files = captured(storage, FIXTURE["head"])
    inventory_id = files.inventory_id
    save = Generation.save

    def stop(self, stage, state):
        save(self, stage, state)
        if stage == "FINAL_OUTPUT":
            raise RuntimeError("Controlled auth drift interruption")

    monkeypatch.setattr(Generation, "save", stop)
    with pytest.raises(RuntimeError, match="Controlled auth drift"):
        execute_analysis(db, actor, repo, files, base_id=baseline_id)
    private = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.state == "STAGING"))
    job_id = private.job_id
    assert not list(db.scalars(select(Record).where(Record.kind == "engineering_change")))
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    db.close()
    monkeypatch.setattr(Generation, "save", save)
    with factory() as resumed:
        actor, repo = resumed.get(User, "user"), resumed.get(Repository, "repo")
        snapshot, _ = execute_analysis(resumed, actor, repo, RepositoryFiles(resumed, "tenant", "repo", inventory_id),
                                       job=resumed.get(Record, job_id), base_id=baseline_id)
        changes = list(resumed.scalars(select(Record).where(Record.kind == "engineering_change")))
        assert len(changes) == 1 and changes[0].data["head_snapshot_id"] == snapshot.id
        comparison = changes[0].data["claim_comparisons"][0]
        assert comparison["before"]["status"] == "VERIFIED" and comparison["after"]["status"] == "CONTRADICTED"
        assert resumed.get(Record, baseline_id).data == original
