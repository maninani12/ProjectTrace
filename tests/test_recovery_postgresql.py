"""A renewing worker's row lock must win over a stale recovery observation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from backend.db import QueueEntry, Record
from backend.scheduling import claim, recover_expired
from tests.test_postgresql_integration import initialize, postgres, queued  # noqa: F401


def test_recovery_skips_a_locked_lease_renewal(postgres):  # noqa: F811
    engine, _ = postgres
    factory = initialize(postgres)
    with factory() as db:
        job = queued(db, "a", "a1")
        token = claim(db, job, 120)["token"]
        job.data = {**job.data, "state": "ANALYZING"}
        identifier = job.id
        db.get(QueueEntry, identifier).lease_expires_at = "2000-01-01T00:00:00+00:00"
        db.commit()

    def recover():
        with factory() as db:
            return recover_expired(db, execution="CELERY")

    with engine.connect() as controller:
        transaction = controller.begin()
        controller.execute(select(QueueEntry.job_id).where(QueueEntry.job_id == identifier).with_for_update())
        controller.execute(update(QueueEntry).where(QueueEntry.job_id == identifier).values(
            lease_expires_at=(datetime.now(timezone.utc) + timedelta(seconds=150)).isoformat()))
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(recover)
        try:
            assert future.result(timeout=5) == []
            transaction.commit()
        finally:
            if transaction.is_active:
                transaction.rollback()
            pool.shutdown(wait=True)
    with factory() as db:
        assert db.get(Record, identifier).data["state"] == "ANALYZING"
        assert db.get(QueueEntry, identifier).worker_token == token
