"""Real renewal-lock regression, opt-in through the existing unique-schema fixture."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from backend.db import AnalysisCheckpoint, AnalysisInput, QueueEntry, Record
from backend.queue import purge_expired_inputs
from backend.scheduling import claim
from tests.test_postgresql_integration import initialize, postgres, queued  # noqa: F401


def test_expiry_skips_locked_renewal_without_deleting_recovery_input(postgres):  # noqa: F811
    engine, _ = postgres
    factory = initialize(postgres)
    with factory() as db:
        job = queued(db, "a", "a1")
        token = claim(db, job, 120)["token"]
        job.data = {**job.data, "state": "ANALYZING"}
        identifier = job.id
        db.get(QueueEntry, identifier).lease_expires_at = "2000-01-01T00:00:00+00:00"
        db.add(
            AnalysisInput(
                job_id=identifier,
                organization_id="a",
                repository_id="a1",
                ciphertext="owned opaque expired input",
                expires_at="2000-01-01",
            )
        )
        db.add(
            AnalysisCheckpoint(
                job_id=identifier,
                organization_id="a",
                repository_id="a1",
                signature="a" * 64,
                result_digest="b" * 64,
                ciphertext="owned opaque checkpoint",
                expires_at="2000-01-01",
            )
        )
        db.commit()

    def expire():
        with factory() as db:
            return purge_expired_inputs(db)

    with engine.connect() as owner:
        transaction = owner.begin()
        owner.execute(select(QueueEntry.job_id).where(QueueEntry.job_id == identifier).with_for_update())
        owner.execute(
            update(QueueEntry)
            .where(QueueEntry.job_id == identifier)
            .values(lease_expires_at=(datetime.now(timezone.utc) + timedelta(seconds=150)).isoformat())
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(expire)
            try:
                assert future.result(timeout=5) == 0
                transaction.commit()
            finally:
                if transaction.is_active:
                    transaction.rollback()
    with factory() as db:
        assert db.get(Record, identifier).data["state"] == "ANALYZING"
        assert db.get(QueueEntry, identifier).worker_token == token
        assert db.get(AnalysisInput, identifier).ciphertext == "owned opaque expired input"
        assert db.get(AnalysisCheckpoint, identifier).ciphertext == "owned opaque checkpoint"
