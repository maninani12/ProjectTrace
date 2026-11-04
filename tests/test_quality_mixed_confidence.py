"""Lifecycle observations and trusted new-code attribution have distinct contracts."""
from collections import Counter

import pytest
from sqlalchemy import func, select

from backend.db import FindingOccurrence, QualityAnalysis, QualityOccurrence, Record
from backend.generation_models import AnalysisGeneration
from tests.test_public_snapshot_continuity import public_snapshot
from tests.test_repository_store import storage  # noqa: F401

GOOD = "def work(items=None):\n    return items\n"
BAD = "def work(items=[]):\n    return items\n"
AMBIGUOUS = BAD + "\n" + BAD


def quality_finding(snapshot, path="app.py"):
    return next(f for f in snapshot.data["findings"] if f.get("rule") == "PT-QUALITY-011" and f["path"] == path)


def verify_projection(db, snapshot):
    quality = db.get(QualityAnalysis, snapshot.id).data
    findings = [f for f in snapshot.data["findings"] if f.get("category") == "QUALITY"]
    assert quality["summary"]["total"] == len(findings)
    assert quality["summary"]["new"] == sum(bool(f.get("new_code")) for f in findings)
    assert quality["deltas"] == dict(Counter(f["delta"] for f in findings))
    assert db.scalar(select(func.count()).select_from(QualityOccurrence).where(QualityOccurrence.snapshot_id == snapshot.id)) == len(findings)
    return quality


@pytest.mark.parametrize("case", ["verified", "unknown_predecessor", "existing", "resolved", "ambiguous", "partial", "mixed", "confidence_change", "added_deleted"])
def test_lifecycle_attribution_and_counters(storage, monkeypatch, case):  # noqa: F811
    from analyzers import finding_identity
    db, _, _ = storage
    before, after = {"app.py": GOOD}, {"app.py": BAD}
    if case in {"unknown_predecessor", "existing", "confidence_change"}:
        before = {"app.py": BAD}
    if case in {"unknown_predecessor", "existing"}:
        after = before
    if case == "unknown_predecessor":
        monkeypatch.setattr(finding_identity, "VERSION", "owned-unsupported-schema")
    if case == "resolved":
        before, after = {"app.py": BAD}, {"app.py": GOOD}
    if case == "ambiguous":
        before = after = {"ambiguous.py": AMBIGUOUS}
    if case == "partial":
        before["workflow.yml"] = after["workflow.yml"] = "jobs:\n  job: ${{ inputs.job }}\n"
    if case == "mixed":
        before["ambiguous.py"] = after["ambiguous.py"] = AMBIGUOUS
    if case == "confidence_change":
        before = {"ambiguous.py": AMBIGUOUS}
        after = {"ambiguous.py": BAD}
    if case == "added_deleted":
        before = {"deleted.py": "def old(items=[]):\n    return items\n", "unchanged.py": GOOD}
        after = {"added.py": "def added(options={}):\n    return options\n", "unchanged.py": GOOD}
    base = public_snapshot(storage, before, "a" * 40, legacy=True)
    db.refresh(base)  # Compare persisted JSON, including JSON array representation.
    monkeypatch.setattr(finding_identity, "VERSION", "structural-v2")
    original = dict(base.data)
    head = public_snapshot(storage, after, "b" * 40, base=base.id)
    quality = verify_projection(db, head)
    history = list(db.scalars(select(FindingOccurrence).where(FindingOccurrence.snapshot_id == head.id)))
    if case in {"verified", "partial", "added_deleted"}:
        f = quality_finding(head, "added.py" if case == "added_deleted" else "app.py")
        assert f["delta"] == "NEW" and f["new_code"] is True
        assert any(h.finding_id == f["id"] and h.status == "INTRODUCED" for h in history)
    if case == "existing":
        f, prior = quality_finding(head), quality_finding(base, "repo-" + "a" * 40 + "/app.py")
        assert f["identity_id"] == prior["identity_id"] and f["previous_version_id"] == prior["id"]
        assert f["delta"] == "EXISTING" and not f["new_code"]
        assert {h.status for h in history} == {"SEEN"}
    if case in {"resolved", "added_deleted"}:
        assert any(h.status == "RESOLVED" for h in history)
        assert len(quality["resolved"]) == 1
    if case in {"unknown_predecessor", "ambiguous", "mixed", "confidence_change"}:
        assert quality["comparison_identity_unresolved"] and not quality["summary"]["new"]
        assert quality["gate"]["status"] == "REVIEW_REQUIRED"
        assert not quality["resolved"] and not any(h.status == "RESOLVED" for h in history)
        assert any(h.status == "NOT_OBSERVED" for h in history)
    if case == "mixed":
        f = quality_finding(head)
        assert f["identity_confidence"] == "HIGH" and f["delta"] == "ANALYZER_BASELINE" and not f["new_code"]
        assert any(h.finding_id == f["id"] and h.status == "INTRODUCED" for h in history)
    if case == "partial":
        assert head.data["status"] == "PARTIAL" and head.data["gate"]["overall"] != "PASS"
    if case == "added_deleted":
        assert head.data["changed_files"] == ["added.py", "deleted.py"]
    db.refresh(base)
    assert base.data == original


def test_mixed_counter_replay_and_duplicate_delivery(storage, monkeypatch):  # noqa: F811
    from backend.generations import Generation
    from backend.jobs import execute_analysis
    from backend.repository_store import RepositoryFiles
    db, actor, repo = storage
    base = public_snapshot(storage, {"app.py": GOOD, "ambiguous.py": AMBIGUOUS}, "a" * 40)
    save = Generation.save

    def interrupt(self, name, state):
        save(self, name, state)
        if name == "POLICY":
            raise RuntimeError("Owned mixed-confidence interruption")

    monkeypatch.setattr(Generation, "save", interrupt)
    with pytest.raises(RuntimeError, match="Owned mixed-confidence interruption"):
        public_snapshot(storage, {"app.py": BAD, "ambiguous.py": AMBIGUOUS}, "b" * 40, base=base.id)
    pending = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.state == "STAGING"))
    monkeypatch.setattr(Generation, "save", save)
    files = RepositoryFiles(db, actor.organization_id, repo.id, pending.inventory_id)
    head, _ = execute_analysis(db, actor, repo, files, job=db.get(Record, pending.job_id), branch="main", git_commit="b" * 40, base_id=base.id)
    quality = verify_projection(db, head)
    assert quality["comparison_identity_unresolved"] and quality["summary"]["new"] == 0
    original = dict(head.data)
    count = db.scalar(select(func.count()).select_from(AnalysisGeneration))
    again, _ = execute_analysis(db, actor, repo, files, branch="main", git_commit="b" * 40, base_id=base.id)
    assert again.id == head.id and again.data == original
    assert db.scalar(select(func.count()).select_from(AnalysisGeneration)) == count


def test_mixed_history_api_does_not_upgrade_attribution_or_gate(storage, client, monkeypatch):  # noqa: F811
    from sqlalchemy.orm import sessionmaker

    from backend import main
    from backend.security import passwords
    db, actor, repo = storage
    base = public_snapshot(storage, {"app.py": GOOD, "ambiguous.py": AMBIGUOUS}, "a" * 40)
    head = public_snapshot(storage, {"app.py": BAD, "ambiguous.py": AMBIGUOUS}, "b" * 40, base=base.id)
    actor.password_hash = passwords.hash("Strong-owned-fixture-password-123!")
    db.commit()
    monkeypatch.setattr(main, "Session", sessionmaker(db.get_bind(), expire_on_commit=False))
    assert client.post("/api/auth/login", json={"email": actor.email, "password": "Strong-owned-fixture-password-123!"}).status_code == 200
    finding = quality_finding(head)
    overview = client.get(f"/api/code-quality/{repo.id}/overview?snapshot_id={head.id}").json()
    assert overview["comparison_identity_unresolved"] and overview["gate"]["status"] == "REVIEW_REQUIRED"
    assert overview["summary"]["new"] == 0 and overview["summary"]["total"] == 3
    record = client.get(f"/api/record/{finding['id']}").json()
    assert record["delta"] == "ANALYZER_BASELINE" and record["new_code"] is False
    history = client.get(f"/api/findings/{finding['id']}/history").json()
    assert {e["status"] for e in history["items"]} == {"INTRODUCED"}
    filtered = client.get(f"/api/code-quality/{repo.id}/findings?snapshot_id={head.id}&new_code=true").json()
    assert filtered["total"] == 0 and filtered["items"] == []


def test_claim_changes_keep_predecessors_and_explicit_unknowns(storage):  # noqa: F811
    db, _, _ = storage
    base = public_snapshot(storage, {
        "changed.md": "The API exposes GET /old.\n", "deleted.md": "Testing uses pytest.\n",
        "unchanged.md": "Backend uses Flask.\n",
    }, "a" * 40, legacy=True)
    head = public_snapshot(storage, {
        "changed.md": "The API exposes GET /new.\n", "added.md": "Backend uses FastAPI.\n",
        "unchanged.md": "Backend uses Flask.\n",
    }, "b" * 40, base=base.id)
    old = {c["path"].split("/", 1)[1]: c for c in base.data["claims"]}
    current = {c["path"]: c for c in head.data["claims"]}
    assert current["unchanged.md"]["previous_version_id"] == old["unchanged.md"]["id"]
    assert current["unchanged.md"]["identity_id"] == old["unchanged.md"]["identity_id"]
    assert current["unchanged.md"]["status"] == "UNVERIFIED"
    assert current["added.md"]["previous_version_id"] is None
    removed = [d for d in head.data["drifts"] if d["type"] == "CLAIM_REMOVED"]
    assert {d["previous_version_id"] for d in removed} == {old["changed.md"]["id"], old["deleted.md"]["id"]}
    # Unverified claims remain visible; an advisory configured gate is not a
    # claim verifier and does not turn an unsupported assertion into VERIFIED.
    assert all(c["status"] == "UNVERIFIED" for c in current.values())
