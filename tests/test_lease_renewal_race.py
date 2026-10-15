"""Fence renewal must reject changes after the initial lease read."""
import pytest
from sqlalchemy import delete, update
from sqlalchemy.sql.dml import Update

from backend.db import QueueEntry
from backend.scheduling import JobCancelled, claim, ensure_current
from tests.test_fair_scheduling import factory, queued  # noqa: F401


@pytest.mark.parametrize('changed', [
    {'worker_token': 'replacement-attempt'},
    {'cancel_requested': True},
    {'state': 'CANCELLED'},
])
def test_renewal_rejects_lease_changes_after_read(factory, monkeypatch, changed):  # noqa: F811 -- shared fixture
    with factory() as db:
        job = queued(db, 'a', 'a1')
        claim(db, job, 120)
        original = db.execute
        injected = False

        def execute(statement, *args, **kwargs):
            nonlocal injected
            if isinstance(statement, Update) and statement.table.name == 'queue_entries' and not injected:
                injected = True
                original(update(QueueEntry).where(QueueEntry.job_id == job.id).values(**changed))
            return original(statement, *args, **kwargs)

        monkeypatch.setattr(db, 'execute', execute)
        with pytest.raises(JobCancelled):
            ensure_current(db, job, renew_seconds=120)
        assert injected


def test_claimed_worker_cannot_fall_back_to_synchronous_without_queue_entry(factory):  # noqa: F811
    with factory() as db:
        job = queued(db, 'a', 'a1')
        claim(db, job, 120)
        db.execute(delete(QueueEntry).where(QueueEntry.job_id == job.id))
        db.commit()
        with pytest.raises(JobCancelled):
            ensure_current(db, job, renew_seconds=120)

