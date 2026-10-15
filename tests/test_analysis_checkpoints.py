"""Private computation survives rollback and a new database session."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.analysis_checkpoints import load, save
from backend.db import AnalysisCheckpoint, Record, Repository, User
from backend.domain import add
from backend.jobs import execute_analysis
from backend.repository_store import RepositoryFiles
from tests.test_repository_store import captured, storage  # noqa: F401


def test_publication_retry_reuses_global_analysis_after_session_restart(storage, monkeypatch):  # noqa: F811
    db, user, repo = storage
    files = captured(storage, {"README.md": "Backend uses FastAPI.", "app.py": "from fastapi import FastAPI\napp=FastAPI()\n"})
    inventory_id, actor_id, repo_id = files.inventory_id, user.id, repo.id
    from backend import workspace_read
    original = workspace_read.project_snapshot

    def crash(*args):
        raise RuntimeError("Simulated crash after graph construction before publication")

    monkeypatch.setattr(workspace_read, "project_snapshot", crash)
    with pytest.raises(RuntimeError):
        execute_analysis(db, user, repo, files)
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    checkpoint = db.scalar(select(AnalysisCheckpoint))
    assert checkpoint is not None and 'FastAPI' not in checkpoint.ciphertext
    job_id = checkpoint.job_id
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    db.close()
    monkeypatch.setattr(workspace_read, "project_snapshot", original)

    def unexpected(*args, **kwargs):
        raise AssertionError("Global analysis must not rerun for the same checkpoint inputs")

    monkeypatch.setattr("backend.partitioned_analysis.analyze_inventory", unexpected)
    with factory() as resumed:
        job = resumed.get(Record, job_id)
        actor, repository = resumed.get(User, actor_id), resumed.get(Repository, repo_id)
        content = RepositoryFiles(resumed, actor.organization_id, repo_id, inventory_id)
        snapshot, _ = execute_analysis(resumed, actor, repository, content, job=job)
        assert snapshot.data["claims"]
        assert resumed.get(AnalysisCheckpoint, job_id) is None
        assert resumed.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 1
        assert snapshot.data["source_storage"]["inventory_id"] == inventory_id


def test_checkpoint_scope_signature_digest_and_envelope(storage):  # noqa: F811
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {"state": "ANALYZING"})
    db.commit()
    result = {"inert": "private source observation"}
    assert save(db, job.id, user.organization_id, repo.id, "a" * 64, result, lambda: None)
    assert load(db, job.id, user.organization_id, repo.id, "a" * 64) == result
    assert load(db, job.id, user.organization_id, repo.id, "b" * 64) is None
    with pytest.raises(ValueError):
        load(db, job.id, "other", repo.id, "a" * 64)
    row = db.get(AnalysisCheckpoint, job.id)
    row.result_digest = "0" * 64
    db.commit()
    with pytest.raises(ValueError, match="digest"):
        load(db, job.id, user.organization_id, repo.id, "a" * 64)


def test_oversized_checkpoint_is_not_truncated_or_committed(storage, monkeypatch):  # noqa: F811
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {})
    db.commit()
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "1000000")
    assert not save(db, job.id, user.organization_id, repo.id, "a" * 64, {"value": "x" * 1000001}, lambda: None)
    assert db.get(AnalysisCheckpoint, job.id) is None


def test_stale_checkpoint_writer_is_rejected(storage):  # noqa: F811
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {})
    db.commit()

    def fenced():
        raise ValueError("Attempt replaced")

    with pytest.raises(ValueError, match="Attempt replaced"):
        save(db, job.id, user.organization_id, repo.id, "a" * 64, {"value": 1}, fenced)
    db.rollback()
    assert db.get(AnalysisCheckpoint, job.id) is None


def test_checkpoint_foreign_key_rejects_direct_sql_tenant_substitution(storage):  # noqa: F811
    from sqlalchemy.exc import IntegrityError
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {})
    db.commit()
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        db.execute(AnalysisCheckpoint.__table__.insert().values(job_id=job.id, organization_id="other",
                   repository_id=repo.id, signature="a" * 64, result_digest="b" * 64,
                   ciphertext="inert", expires_at="2099-01-01"))
    db.rollback()
    assert db.get(AnalysisCheckpoint, job.id) is None


def test_expired_checkpoint_is_not_reused_and_is_purged(storage):  # noqa: F811
    from backend.queue import purge_expired_inputs
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {})
    db.commit()
    save(db, job.id, user.organization_id, repo.id, "a" * 64, {"value": 1}, lambda: None)
    db.get(AnalysisCheckpoint, job.id).expires_at = "2000-01-01"
    db.commit()
    assert load(db, job.id, user.organization_id, repo.id, "a" * 64) is None
    purge_expired_inputs(db)
    assert db.get(AnalysisCheckpoint, job.id) is None


def test_failed_new_publication_preserves_existing_snapshot_and_claims(storage, monkeypatch):  # noqa: F811
    import copy

    from backend import workspace_read
    db, user, repo = storage
    first = captured(storage, {"README.md": "Backend uses FastAPI.", "app.py": "from fastapi import FastAPI\napp=FastAPI()"})
    snapshot, _ = execute_analysis(db, user, repo, first)
    db.refresh(snapshot)  # Compare persisted JSON, including tuple-to-array normalization.
    old_id, old_data = snapshot.id, copy.deepcopy(snapshot.data)
    old_claims = {r.id: copy.deepcopy(r.data) for r in db.scalars(select(Record).where(Record.kind == "claim"))}
    second = captured(storage, {"README.md": "Backend uses Flask.", "app.py": "from flask import Flask\napp=Flask(__name__)"})
    original = workspace_read.project_snapshot

    def crash(*args):
        raise RuntimeError("Controlled history interruption")

    monkeypatch.setattr(workspace_read, "project_snapshot", crash)
    with pytest.raises(RuntimeError):
        execute_analysis(db, user, repo, second, base_id=old_id)
    db.expire_all()
    assert db.get(Record, old_id).data == old_data
    assert {r.id: r.data for r in db.scalars(select(Record).where(Record.kind == "claim"))} == old_claims
    receipt = db.scalar(select(AnalysisCheckpoint))
    assert receipt is not None
    monkeypatch.setattr(workspace_read, "project_snapshot", original)
    new_snapshot, _ = execute_analysis(db, user, repo, second, base_id=old_id, job=db.get(Record, receipt.job_id))
    assert new_snapshot.id != old_id
    assert db.get(Record, old_id).data == old_data
