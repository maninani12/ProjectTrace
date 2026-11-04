"""Deterministic file findings retain publication, replay and BASE history."""
import copy

import pytest
from sqlalchemy import func, select

from backend.db import NativeProfile, QualityAnalysis, Record
from backend.generation_models import AnalysisGeneration, PublishedGeneration
from backend.generations import Generation
from backend.jobs import execute_analysis
from backend.repository_store import RepositoryFiles
from tests.test_repository_store import captured, storage  # noqa: F401


def file_sources():
    return {path: "VALUE = 1\n" * 24 for path in ("nested/z.py", "a.py", "nested/deeper/m.py")}


def file_rows(snapshot):
    return [f for f in snapshot.data["findings"] if f["rule"] == "PT-QUALITY-013"]


def configure(db, user, repo):
    db.add(NativeProfile(id="owned-file-order", organization_id=user.organization_id, repository_id=repo.id,
                         scope_key=repo.id, data={"quality": {"rules": {"PT-QUALITY-013": {"threshold": 10}}}}))
    db.commit()


@pytest.mark.parametrize("stage", ["FINDINGS", "HISTORY", "FINAL_OUTPUT"])
def test_file_order_survives_generation_replay_and_duplicate_delivery(storage, monkeypatch, stage):  # noqa: F811
    db, user, repo = storage
    configure(db, user, repo)
    sources = file_sources()
    base, _ = execute_analysis(db, user, repo, captured(storage, sources), git_commit="a" * 40)
    db.refresh(base)
    original_base = copy.deepcopy(base.data)
    assert [f["path"] for f in file_rows(base)] == sorted(sources)
    base_ids = {f["path"]: (f["fingerprint"], f.get("identity_id")) for f in file_rows(base)}
    head_sources = {**sources, "added.py": "VALUE = 2\n" * 30, "a.py": "VALUE = 1\n"}
    files = captured(storage, head_sources)
    inventory_id = files.inventory_id
    save = Generation.save

    def interrupt(self, name, state):
        save(self, name, state)
        if name == stage:
            raise RuntimeError("Owned file-order interruption")

    monkeypatch.setattr(Generation, "save", interrupt)
    with pytest.raises(RuntimeError, match="Owned file-order interruption"):
        execute_analysis(db, user, repo, files, base_id=base.id, git_commit="b" * 40)
    pending = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.state == "STAGING"))
    assert pending is not None
    pointer = db.get(PublishedGeneration, (user.organization_id, repo.id, "main"))
    assert db.get(AnalysisGeneration, pointer.generation_id).snapshot_id == base.id
    db.refresh(base)
    assert base.data == original_base
    monkeypatch.setattr(Generation, "save", save)
    head, job = execute_analysis(db, user, repo,
        RepositoryFiles(db, user.organization_id, repo.id, inventory_id), job=db.get(Record, pending.job_id),
        base_id=base.id, git_commit="b" * 40)
    assert job.data["generation_receipts_reused"] > 0
    rows = file_rows(head)
    assert [f["path"] for f in rows] == sorted(p for p in head_sources if p != "a.py")
    for finding in rows:
        if finding["path"] in base_ids:
            assert (finding["fingerprint"], finding.get("identity_id")) == base_ids[finding["path"]]
            assert finding["delta"] == "EXISTING"
    assert next(f for f in rows if f["path"] == "added.py")["delta"] == "NEW"
    quality = db.get(QualityAnalysis, head.id).data
    assert any(f["path"] == "a.py" for f in quality["resolved"])
    assert quality["summary"]["total"] == len(rows)
    before_count = db.scalar(select(func.count()).select_from(AnalysisGeneration))
    duplicate, _ = execute_analysis(db, user, repo,
        RepositoryFiles(db, user.organization_id, repo.id, inventory_id), base_id=base.id, git_commit="b" * 40)
    assert duplicate.id == head.id
    assert file_rows(duplicate) == rows
    assert db.scalar(select(func.count()).select_from(AnalysisGeneration)) == before_count
    db.refresh(base)
    assert base.data == original_base
