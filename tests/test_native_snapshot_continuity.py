"""Owned public snapshots exercise native identities, not synthetic finding IDs."""
import copy

import pytest
from sqlalchemy import select, text

from backend.db import FindingOccurrence, QualityAnalysis, Record
from tests.test_public_snapshot_continuity import public_snapshot
from tests.test_repository_store import storage  # noqa: F401

FAMILIES = [
    ("app.py", "def work(items=[]):\n    return items\n", "PT-QUALITY-011"),
    ("app.js", "function work(value) { eval(value); }\n", "PT-SAST-005"),
    ("app.py", "import subprocess\ndef work(command):\n    subprocess.run(command, shell=True)\n", "PT-SAST-002"),
    ("compose.yaml", "services:\n  app:\n    privileged: true\n", "PT-IAC-001"),
    ("Dockerfile", "FROM ubuntu:latest\nUSER root\n", "PT-IAC-002"),
    ("app.ts", "function work(value: string) { eval(value); }\n", "PT-SAST-005"),
    ("App.java", "class App { void work() { try { run(); } catch(Exception error) {} } }\n", "PT-QUALITY-006"),
    ("app.py", "api_key = 'owned-fixture-credential-123456789012345'\n", "PT-SECRET-001"),
]


@pytest.mark.parametrize("legacy_first", [True, False])
@pytest.mark.parametrize("filename,source,rule", FAMILIES)
def test_unchanged_native_findings_in_distinct_nested_files(storage, legacy_first, filename, source, rule):  # noqa: F811
    db, _, _ = storage
    files = {"one/" + filename: source, "two/" + filename: source}
    base = public_snapshot(storage, files, "a" * 40, legacy=legacy_first)
    db.refresh(base)
    original = copy.deepcopy(base.data)
    before = [f for f in base.data["findings"] if f["rule"] == rule]
    assert len(before) == 2
    head = public_snapshot(storage, files, "b" * 40, legacy=not legacy_first, base=base.id)
    after = [f for f in head.data["findings"] if f["rule"] == rule]
    assert len(after) == 2
    assert {f["identity_id"] for f in after} == {f["identity_id"] for f in before}
    assert {f["previous_version_id"] for f in after} == {f["id"] for f in before}
    assert all(f["delta"] == "EXISTING" and not f["new_code"] for f in after)
    history = list(db.scalars(select(FindingOccurrence).where(FindingOccurrence.snapshot_id == head.id)))
    assert not any(e.status in {"INTRODUCED", "RESOLVED", "CONTEXT_CHANGED", "MOVED"} for e in history)
    if rule.startswith("PT-QUALITY"):
        quality = db.get(QualityAnalysis, head.id).data
        assert not quality["resolved"]
        assert not any(m["new_code"] for m in quality["metrics"])
    db.refresh(base)
    assert base.data == original
    assert db.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    assert not db.execute(text("PRAGMA foreign_key_check")).all()


@pytest.mark.parametrize("legacy_first", [True, False])
def test_actual_metric_regression_is_visible_across_layout_change(storage, legacy_first):  # noqa: F811
    db, _, _ = storage
    before = "def work(items=[]):\n    if items:\n        return items\n    return []\n"
    after = before.replace("    return []", "    if items is None:\n        return []\n    return []")
    base = public_snapshot(storage, {"app.py": before}, "a" * 40, legacy=legacy_first)
    head = public_snapshot(storage, {"app.py": after}, "b" * 40, legacy=not legacy_first, base=base.id)
    change = db.scalar(select(Record).where(Record.kind == "engineering_change",
        Record.data["head_snapshot_id"].as_string() == head.id))
    assert any(c["category"] == "QUALITY_REGRESSION" and "cyclomatic" in c["label"] for c in change.data["changes"])
    prior = next(f for f in base.data["findings"] if f["rule"] == "PT-QUALITY-011")
    current = next(f for f in head.data["findings"] if f["rule"] == "PT-QUALITY-011")
    assert current["identity_id"] == prior["identity_id"]
    assert current["review_identity_id"] != prior["review_identity_id"]


@pytest.mark.parametrize("legacy_first", [True, False])
def test_quality_resolution_introduction_context_and_reopening(storage, legacy_first):  # noqa: F811
    db, _, _ = storage
    bad = "def work(items=[]):\n    return items\n"
    fixed = "def work(items=None):\n    return items\n"
    base_files = {"one/app.py": bad, "two/app.py": bad}
    base = public_snapshot(storage, base_files, "a" * 40, legacy=legacy_first)
    prior = {f["path"].split("/", 1)[-1] if legacy_first else f["path"]: f
             for f in base.data["findings"] if f["rule"] == "PT-QUALITY-011"}
    files = {"one/app.py": fixed, "two/app.py": bad.replace("    return items", "    items.append(1)\n    return items"),
             "new/app.py": bad}
    head = public_snapshot(storage, files, "b" * 40, legacy=not legacy_first, base=base.id)
    events = list(db.scalars(select(FindingOccurrence).where(FindingOccurrence.snapshot_id == head.id)))
    assert {e.status for e in events} >= {"RESOLVED", "INTRODUCED", "CONTEXT_CHANGED"}
    assert any(e.identity_id == prior["one/app.py"]["identity_id"] and e.status == "RESOLVED" for e in events)
    quality = db.get(QualityAnalysis, head.id).data
    assert len([f for f in quality["resolved"] if f["rule"] == "PT-QUALITY-011"]) == 1
    reopened = public_snapshot(storage, {**files, "one/app.py": bad}, "c" * 40, base=head.id)
    finding = next(f for f in reopened.data["findings"] if f["rule"] == "PT-QUALITY-011" and f["path"] == "one/app.py")
    assert finding["identity_id"] == prior["one/app.py"]["identity_id"]
    assert finding["delta"] == "REOPENED" and finding["reopened_count"] == 1
    assert db.get(QualityAnalysis, reopened.id).data["deltas"]["REOPENED"] >= 1


def test_unresolved_provenance_does_not_establish_introduction_or_resolution(storage):  # noqa: F811
    db, _, _ = storage
    source = {"app.py": "def work(items=[]):\n    return items\n"}
    base = public_snapshot(storage, source, "a" * 40, legacy=True, provenance_commit="invalid")
    head = public_snapshot(storage, source, "b" * 40, base=base.id)
    assert head.data["status"] == "PARTIAL"
    events = list(db.scalars(select(FindingOccurrence).where(FindingOccurrence.snapshot_id == head.id)))
    assert events and all(e.status == "NOT_OBSERVED" for e in events)
    quality = db.get(QualityAnalysis, head.id).data
    assert not quality["resolved"] and not quality["deltas"].get("NEW", 0)
    assert quality["comparison_identity_unresolved"]
    assert quality["gate"]["status"] != "PASS"


def test_severity_profile_change_keeps_concept_and_invalidates_review_context(storage):  # noqa: F811
    from backend.db import NativeProfile
    db, actor, repo = storage
    source = {"app.py": "def work(items=[]):\n    return items\n"}
    base = public_snapshot(storage, source, "a" * 40, legacy=True)
    db.add(NativeProfile(id="owned-severity", organization_id=actor.organization_id, repository_id=repo.id,
        scope_key=repo.id, data={"quality": {"rules": {"PT-QUALITY-011": {"severity": "CRITICAL"}}}}))
    db.commit()
    head = public_snapshot(storage, source, "b" * 40, base=base.id)
    prior = next(f for f in base.data["findings"] if f["rule"] == "PT-QUALITY-011")
    current = next(f for f in head.data["findings"] if f["rule"] == "PT-QUALITY-011")
    assert current["severity"] == "CRITICAL" and current["identity_id"] == prior["identity_id"]
    assert current["review_identity_id"] != prior["review_identity_id"]


@pytest.mark.parametrize("unknown_schema", [False, True])
def test_ambiguous_and_unsupported_native_identities_are_not_verified_transitions(storage, monkeypatch, unknown_schema):  # noqa: F811
    from analyzers import finding_identity
    db, _, _ = storage
    source = ("def work(items=[]):\n    return items\n" if unknown_schema else
              "import subprocess\ndef work(command):\n    subprocess.run(command, shell=True)\n    subprocess.run(command, shell=True)\n")
    if unknown_schema:
        monkeypatch.setattr(finding_identity, "VERSION", "unsupported-owned-schema")
    base = public_snapshot(storage, {"app.py": source}, "a" * 40, legacy=True)
    if unknown_schema:
        assert any(f.get("identity_version") == "unsupported-owned-schema" for f in base.data["findings"])
        monkeypatch.setattr(finding_identity, "VERSION", "structural-v2")
    head = public_snapshot(storage, {"app.py": source}, "b" * 40, base=base.id)
    assert head.data["status"] == "PARTIAL"
    events = list(db.scalars(select(FindingOccurrence).where(FindingOccurrence.snapshot_id == head.id)))
    assert events and all(e.status == "NOT_OBSERVED" for e in events)
    assert all(f.get("identity_resolution") == "UNRESOLVED" for f in head.data["findings"])
    quality = db.get(QualityAnalysis, head.id).data
    assert not quality["resolved"] and not quality["deltas"].get("NEW", 0)


def test_real_history_and_quality_api_keep_old_paths_and_tenant_scope(storage, client, monkeypatch):  # noqa: F811
    from sqlalchemy.orm import sessionmaker

    from backend import main
    from backend.security import passwords
    db, actor, repo = storage
    source = {"nested/app.py": "def work(items=[]):\n    return items\n"}
    base = public_snapshot(storage, source, "a" * 40, legacy=True)
    head = public_snapshot(storage, source, "b" * 40, base=base.id)
    actor.password_hash = passwords.hash("Strong-owned-password-123!")
    db.commit()
    monkeypatch.setattr(main, "Session", sessionmaker(db.get_bind(), expire_on_commit=False))
    login = client.post("/api/auth/login", json={"email": actor.email, "password": "Strong-owned-password-123!"})
    assert login.status_code == 200
    client.headers["x-csrf-token"] = login.json()["csrf"]
    finding = next(f for f in head.data["findings"] if f["rule"] == "PT-QUALITY-011")
    history = client.get(f"/api/findings/{finding['id']}/history")
    assert history.status_code == 200
    assert {e["status"] for e in history.json()["items"]} == {"INTRODUCED", "SEEN"}
    assert any(e["path"].startswith("repo-" + "a" * 40) for e in history.json()["items"])
    evidence_id = finding["evidence_ids"][0]
    evidence = client.get(f"/api/record/{evidence_id}")
    assert evidence.status_code == 200
    assert evidence.json()["path"] == "nested/app.py" and "def work(items=[])" in evidence.json()["source"]
    response = client.get(f"/api/code-quality/{repo.id}/overview?snapshot_id={head.id}")
    assert response.status_code == 200 and response.json()["summary"]["resolved"] == 0
    metrics = client.get(f"/api/code-quality/{repo.id}/metrics?snapshot_id={head.id}").json()
    assert all(not m["new_code"] for m in metrics["items"])
    other = client.post("/api/auth/register", json={"email": "other-history@example.com",
        "password": "Strong-owned-password-123!", "organization": "Other history tenant"})
    assert other.status_code == 200
    assert client.get(f"/api/findings/{finding['id']}/history").status_code == 404
    assert client.get(f"/api/record/{evidence_id}").status_code == 404
    assert client.get(f"/api/code-quality/{repo.id}/overview?snapshot_id={base.id}").status_code == 404


@pytest.mark.parametrize("stage", ["CORRELATION", "POLICY"])
def test_native_history_private_replay_and_duplicate_delivery(storage, monkeypatch, stage):  # noqa: F811
    from backend.generation_models import AnalysisGeneration
    from backend.generations import Generation
    from backend.jobs import execute_analysis
    from backend.repository_store import RepositoryFiles
    db, actor, repo = storage
    files = {"one/app.py": "def work(items=[]):\n    return items\n",
             "two/app.py": "def work(items=[]):\n    return items\n"}
    base = public_snapshot(storage, files, "a" * 40, legacy=True)
    save = Generation.save

    def interrupt(self, name, state):
        save(self, name, state)
        if name == stage:
            raise RuntimeError("Owned native history interruption")

    monkeypatch.setattr(Generation, "save", interrupt)
    with pytest.raises(RuntimeError, match="Owned native history"):
        public_snapshot(storage, files, "b" * 40, base=base.id)
    generation = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.state == "STAGING"))
    assert list(db.scalars(select(Record.id).where(Record.kind == "snapshot"))) == [base.id]
    monkeypatch.setattr(Generation, "save", save)
    job = db.get(Record, generation.job_id)
    captured = RepositoryFiles(db, actor.organization_id, repo.id, generation.inventory_id)
    head, _ = execute_analysis(db, actor, repo, captured, job=job,
        branch="main", git_commit="b" * 40, base_id=base.id)
    assert {f["identity_id"] for f in head.data["findings"]} == {f["identity_id"] for f in base.data["findings"]}
    events = list(db.scalars(select(FindingOccurrence.id).where(FindingOccurrence.snapshot_id == head.id)))
    duplicate, _ = execute_analysis(db, actor, repo, captured, job=job,
        branch="main", git_commit="b" * 40, base_id=base.id)
    assert duplicate.id == head.id and duplicate.data["base_id"] == base.id
    assert list(db.scalars(select(FindingOccurrence.id).where(FindingOccurrence.snapshot_id == head.id))) == events
