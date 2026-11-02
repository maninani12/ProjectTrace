"""Expiry maintenance respects authoritative worker ownership and fences stale leases."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend import analysis_checkpoints, publication_units, queue
from backend.db import AnalysisCheckpoint, AnalysisCheckpointPart, AnalysisInput, PublicationUnit, QueueEntry
from backend.domain import add
from tests.test_repository_store import storage  # noqa: F401


@pytest.fixture
def retained(storage):  # noqa: F811 - imported shared fixture
    db, user, repo = storage
    job = add(
        db, user.organization_id, repo.id, "job", {"state": "VERIFYING", "source": "INVENTORY", "user_id": user.id}
    )
    expiry = datetime.now(timezone.utc) + timedelta(hours=72)
    db.add(
        AnalysisInput(
            job_id=job.id,
            organization_id=user.organization_id,
            repository_id=repo.id,
            ciphertext=queue.cipher().encrypt(json.dumps({"files": {}}).encode()).decode(),
            expires_at=expiry.isoformat(),
        )
    )
    db.commit()
    analysis_checkpoints.save(
        db, job.id, user.organization_id, repo.id, "a" * 64, {"rows": ["complete owned recovery value"]}, lambda: None
    )
    drafts = publication_units.Drafts(db, job.id, user.organization_id, repo.id, "a" * 64, lambda: None)
    drafts.save("MANIFEST", "", {"owned": "complete draft"})
    return db, job, expiry


@pytest.mark.parametrize("resource", ["input", "checkpoint", "draft"])
@pytest.mark.parametrize("owner", ["active", "cancel_requested", "expired", "queued", "terminal", "foreign", "legacy"])
def test_expiry_preserves_live_worker_and_reclaims_only_unowned_data(retained, monkeypatch, resource, owner):
    db, job, expiry = retained
    if owner != "legacy":
        entry = QueueEntry(
            job_id=job.id,
            organization_id="other" if owner == "foreign" else job.organization_id,
            repository_id=job.repository_id,
            state="QUEUED" if owner == "queued" else "FAILED" if owner == "terminal" else "RUNNING",
            worker_token="owned-worker-token",
            cancel_requested=owner == "cancel_requested",
            lease_expires_at=(expiry + timedelta(minutes=5) if owner != "expired" else expiry).isoformat(),
        )
        if owner == "foreign":
            # A corrupt legacy row cannot be created through the protected ORM.
            # Inject it only in this disposable DB to verify cleanup scoping.
            db.execute(
                QueueEntry.__table__.insert().values(
                    job_id=job.id,
                    organization_id="other",
                    repository_id=job.repository_id,
                    state="RUNNING",
                    worker_token="owned-worker-token",
                    cancel_requested=False,
                    lease_expires_at=entry.lease_expires_at,
                )
            )
        else:
            db.add(entry)
        db.commit()
    before = {
        model.__name__: db.scalar(select(func.count()).select_from(model))
        for model in (AnalysisInput, AnalysisCheckpoint, AnalysisCheckpointPart, PublicationUnit)
    }
    active = owner in {"active", "cancel_requested"}
    with monkeypatch.context() as clock:
        instant = (expiry + timedelta(seconds=30)).isoformat()
        for module in (analysis_checkpoints, publication_units, queue):
            clock.setattr(module, "now", lambda: instant)
        if resource == "input":
            count = queue.purge_expired_inputs(db)
            assert count == (0 if active else 1)
        elif resource == "checkpoint":
            analysis_checkpoints.purge_expired(db)
        else:
            publication_units.purge_expired(db)
        if active:
            # Keeping encrypted bytes for an owner does not extend readability.
            assert analysis_checkpoints.load(db, job.id, job.organization_id, job.repository_id, "a" * 64) is None
            assert (
                publication_units.Drafts(
                    db, job.id, job.organization_id, job.repository_id, "a" * 64, lambda: None
                ).load("MANIFEST")
                is None
            )
        db.commit()
    db.expire_all()
    if active:
        for model in (AnalysisInput, AnalysisCheckpoint, AnalysisCheckpointPart, PublicationUnit):
            assert db.scalar(select(func.count()).select_from(model)) == before[model.__name__]
        assert job.data["state"] == "VERIFYING"
        restored = analysis_checkpoints.load(db, job.id, job.organization_id, job.repository_id, "a" * 64)
        assert list(restored["rows"]) == ["complete owned recovery value"]
        restored["rows"].close()
        assert publication_units.Drafts(
            db, job.id, job.organization_id, job.repository_id, "a" * 64, lambda: None
        ).load("MANIFEST") == {"owned": "complete draft"}
    else:
        removed = {"input": AnalysisInput, "checkpoint": AnalysisCheckpoint, "draft": PublicationUnit}[resource]
        assert db.scalar(select(func.count()).select_from(removed)) == 0
        if resource == "input":
            assert job.data["state"] == "FAILED"
            if owner != "legacy" and owner != "foreign":
                entry = db.get(QueueEntry, job.id)
                assert entry.state == "FAILED" and entry.worker_token is None and entry.lease_expires_at is None


def test_renewal_between_candidate_scan_and_ownership_lock_wins(retained, monkeypatch):
    from backend.retention import ExpiryGuard

    db, job, expiry = retained
    db.add(
        QueueEntry(
            job_id=job.id,
            organization_id=job.organization_id,
            repository_id=job.repository_id,
            state="RUNNING",
            worker_token="owned-token",
            lease_expires_at=expiry.isoformat(),
        )
    )
    db.commit()
    allow, renewed = ExpiryGuard.allows, []
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)

    def renew_then_check(guard, job_id, organization_id, repository_id):
        if not renewed:
            with factory() as owner:
                owner.execute(
                    update(QueueEntry)
                    .where(QueueEntry.job_id == job_id)
                    .values(lease_expires_at=(expiry + timedelta(minutes=5)).isoformat())
                )
                owner.commit()
            renewed.append(True)
        return allow(guard, job_id, organization_id, repository_id)

    monkeypatch.setattr(ExpiryGuard, "allows", renew_then_check)
    instant = (expiry + timedelta(seconds=30)).isoformat()
    for module in (analysis_checkpoints, publication_units, queue):
        monkeypatch.setattr(module, "now", lambda: instant)
    assert queue.purge_expired_inputs(db) == 0
    assert renewed and db.get(AnalysisInput, job.id) is not None
    assert db.get(AnalysisCheckpoint, job.id) is not None
    assert job.data["state"] == "VERIFYING"


def test_cleanup_lock_blocks_late_renewal_and_fences_expired_owner(retained, monkeypatch):
    from backend.retention import ExpiryGuard
    from backend.scheduling import JobCancelled, ensure_current

    db, job, expiry = retained
    job.data = {**job.data, "worker_token": "owned-token"}
    db.add(
        QueueEntry(
            job_id=job.id,
            organization_id=job.organization_id,
            repository_id=job.repository_id,
            state="RUNNING",
            worker_token="owned-token",
            lease_expires_at=expiry.isoformat(),
        )
    )
    db.commit()
    allow, blocked = ExpiryGuard.allows, []
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)

    def check_then_renew(guard, *scope):
        allowed = allow(guard, *scope)
        if allowed and not blocked:
            with factory() as owner:
                owner.connection().exec_driver_sql("PRAGMA busy_timeout=50")
                with pytest.raises(OperationalError, match="locked"):
                    owner.execute(
                        update(QueueEntry)
                        .where(QueueEntry.job_id == job.id)
                        .values(lease_expires_at=(expiry + timedelta(minutes=5)).isoformat())
                    )
                owner.rollback()
            blocked.append(True)
        return allowed

    monkeypatch.setattr(ExpiryGuard, "allows", check_then_renew)
    instant = (expiry + timedelta(seconds=30)).isoformat()
    for module in (analysis_checkpoints, publication_units, queue):
        monkeypatch.setattr(module, "now", lambda: instant)
    assert queue.purge_expired_inputs(db) == 1 and blocked
    with pytest.raises(JobCancelled):
        ensure_current(db, job, renew_seconds=120)


def test_reaper_selects_metadata_not_ciphertext_batches(retained, monkeypatch):
    db, _, expiry = retained
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("SELECT"):
            statements.append(statement)

    instant = (expiry + timedelta(seconds=30)).isoformat()
    for module in (analysis_checkpoints, publication_units, queue):
        monkeypatch.setattr(module, "now", lambda: instant)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        assert queue.purge_expired_inputs(db) == 1
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert statements
    assert all("ciphertext" not in statement.partition("FROM")[0] for statement in statements)


def test_generation_page_expiry_retains_receipt_identity_and_publication_state(storage, monkeypatch):  # noqa: F811
    from backend import generations
    from backend.generation_models import GenerationContextPart, GenerationReceipt, PublishedGeneration
    from tests.test_generation_context import context

    generation, state = context(storage)
    generation.save("SNAPSHOT", state)
    db = generation.db
    receipt = db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT"))
    identity = receipt.digest, receipt.dependency_digest, receipt.format_version, receipt.completed_at
    expiry = datetime.fromisoformat(generation.row.expires_at)
    row = QueueEntry(
        job_id=generation.row.job_id,
        organization_id=generation.row.organization_id,
        repository_id=generation.row.repository_id,
        state="RUNNING",
        worker_token="owned-token",
        lease_expires_at=(expiry + timedelta(minutes=5)).isoformat(),
    )
    db.add(row)
    db.commit()
    count = db.scalar(select(func.count()).select_from(GenerationContextPart))
    monkeypatch.setattr(generations, "now", lambda: (expiry + timedelta(seconds=30)).isoformat())
    assert generations.purge_expired_chunks(db, limit=2) == 0
    assert db.scalar(select(func.count()).select_from(GenerationContextPart)) == count
    row.lease_expires_at = expiry.isoformat()
    db.commit()
    while generations.purge_expired_chunks(db, limit=2):
        db.commit()
    db.commit()
    assert db.scalar(select(func.count()).select_from(GenerationContextPart)) == 0
    assert (receipt.digest, receipt.dependency_digest, receipt.format_version, receipt.completed_at) == identity
    assert generation.row.state == "ABANDONED"
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0


def test_expiry_preserves_terminal_job_history_and_reconciles_stale_queue(retained, monkeypatch):
    db, job, expiry = retained
    history = {
        **job.data,
        "state": "COMPLETED",
        "snapshot_id": "historical-snapshot-reference",
        "finished_at": "2026-01-01",
        "errors": [],
    }
    job.data = history
    db.add(
        QueueEntry(
            job_id=job.id,
            organization_id=job.organization_id,
            repository_id=job.repository_id,
            state="RUNNING",
            worker_token="owned-old-token",
            lease_expires_at=expiry.isoformat(),
        )
    )
    db.commit()
    instant = (expiry + timedelta(seconds=30)).isoformat()
    for module in (analysis_checkpoints, publication_units, queue):
        monkeypatch.setattr(module, "now", lambda: instant)
    assert queue.purge_expired_inputs(db) == 1
    assert job.data == history
    entry = db.get(QueueEntry, job.id)
    assert entry.state == "COMPLETED" and entry.worker_token is None and entry.lease_expires_at is None


def test_cleanup_failure_rolls_back_private_deletes_and_job_transition(retained, monkeypatch):
    from backend.retention import ExpiryGuard

    db, job, expiry = retained
    before = {
        model: db.scalar(select(func.count()).select_from(model))
        for model in (AnalysisInput, AnalysisCheckpoint, AnalysisCheckpointPart, PublicationUnit)
    }

    def fail(_self, _job):
        raise RuntimeError("Owned expiry transaction interruption")

    monkeypatch.setattr(ExpiryGuard, "finish", fail)
    instant = (expiry + timedelta(seconds=30)).isoformat()
    for module in (analysis_checkpoints, publication_units, queue):
        monkeypatch.setattr(module, "now", lambda: instant)
    with pytest.raises(RuntimeError, match="Owned expiry"):
        queue.purge_expired_inputs(db)
    db.rollback()
    assert job.data["state"] == "VERIFYING"
    for model, count in before.items():
        assert db.scalar(select(func.count()).select_from(model)) == count


def test_live_job_orphan_pages_do_not_starve_other_expired_jobs(retained):
    db, job, expiry = retained
    other = add(db, job.organization_id, job.repository_id, "job", {"state": "FAILED"})
    db.add(
        QueueEntry(
            job_id=job.id,
            organization_id=job.organization_id,
            repository_id=job.repository_id,
            state="RUNNING",
            worker_token="owned-token",
            lease_expires_at=expiry.isoformat(),
        )
    )
    db.commit()
    values = [
        dict(
            job_id=job.id,
            attempt="owned-old-staging",
            ordinal=index,
            organization_id=job.organization_id,
            repository_id=job.repository_id,
            ciphertext="owned opaque expired orphan",
            digest="0" * 64,
            expires_at="2000-01-01",
        )
        for index in range(1000)
    ]
    values.append({**values[0], "job_id": other.id})
    db.execute(AnalysisCheckpointPart.__table__.insert(), values)
    db.commit()
    analysis_checkpoints.purge_expired(db)
    db.commit()
    assert (
        db.scalar(
            select(func.count()).select_from(AnalysisCheckpointPart).where(AnalysisCheckpointPart.job_id == other.id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AnalysisCheckpointPart)
            .where(AnalysisCheckpointPart.job_id == job.id, AnalysisCheckpointPart.attempt == "owned-old-staging")
        )
        == 1000
    )
