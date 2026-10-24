"""Recovery reconciles committed outcomes and respects the current lease owner."""

import copy
from datetime import datetime, timedelta, timezone

import pytest

from backend import main
from backend.db import QueueEntry, Record
from backend.scheduling import claim, recover_expired
from tests.test_fair_scheduling import factory, queued  # noqa: F401
from tests.test_queue import queued as api_queued


@pytest.mark.parametrize("state", ["COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL", "FAILED", "CANCELLED"])
def test_recovery_cannot_reopen_a_committed_terminal_job(factory, state):  # noqa: F811
    with factory() as db:
        job = queued(db, "a", "a1")
        claim(db, job, 120)
        job.data = {**job.data, "state": state, "finished_at": "retained-outcome", "recovery_attempts": 1}
        entry = db.get(QueueEntry, job.id)
        entry.lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
        before = copy.deepcopy(job.data)
        assert recover_expired(db) == []
        db.refresh(job)
        assert job.data == before
        assert entry.state == state
        assert entry.worker_token is None and entry.lease_expires_at is None
        assert recover_expired(db) == []


def test_legacy_recovery_does_not_override_a_renewed_scheduler_lease(client, monkeypatch):
    tasks, sent = api_queued(client, monkeypatch)
    job_id = client.post("/api/import", json={"name": "Renewed", "files": {"app.py": "pass\n"}}).json()["job_id"]
    with main.Session() as db:
        job = db.get(Record, job_id)
        token = claim(db, job, 120)["token"]
        job.data = {**job.data, "state": "ANALYZING", "lease_expires_at": "2000-01-01T00:00:00+00:00"}
        db.commit()
        before = copy.deepcopy(job.data)
    assert tasks.recover_jobs.run() == {"recovered_jobs": 0}
    with main.Session() as db:
        assert db.get(Record, job_id).data == before
        assert db.get(QueueEntry, job_id).worker_token == token
        assert db.get(QueueEntry, job_id).state == "RUNNING"
    assert len(sent) == 1


def test_celery_maintenance_does_not_recover_local_runner_jobs(factory, monkeypatch):  # noqa: F811
    from workers import tasks

    monkeypatch.setattr(tasks, "Session", factory)
    with factory() as db:
        job = queued(db, "a", "a1", execution="LOCAL")
        claim(db, job, 120)
        db.get(QueueEntry, job.id).lease_expires_at = "2000-01-01T00:00:00+00:00"
        db.commit()
        before = copy.deepcopy(job.data)
        job_id = job.id
    assert tasks.recover_jobs.run() == {"recovered_jobs": 0}
    with factory() as db:
        assert db.get(Record, job_id).data == before
        assert db.get(QueueEntry, job_id).state == "RUNNING"


def test_legacy_job_without_a_scheduler_entry_remains_recoverable(client, monkeypatch):
    tasks, sent = api_queued(client, monkeypatch)
    job_id = client.post("/api/import", json={"name": "Legacy", "files": {"app.py": "pass\n"}}).json()["job_id"]
    with main.Session() as db:
        db.delete(db.get(QueueEntry, job_id))
        job = db.get(Record, job_id)
        job.data = {**job.data, "state": "FETCHING", "lease_expires_at": "2000-01-01T00:00:00+00:00"}
        db.commit()
    assert tasks.recover_jobs.run() == {"recovered_jobs": 1}
    with main.Session() as db:
        assert db.get(Record, job_id).data["recovery_attempts"] == 1
        assert db.get(QueueEntry, job_id).state == "QUEUED"
    assert len(sent) == 2


def test_repeated_worker_loss_exhausts_two_recoveries_without_touching_another_tenant(factory):  # noqa: F811
    with factory() as db:
        job = queued(db, "a", "a1")
        other = queued(db, "b", "b1")
        other_data = copy.deepcopy(other.data)
        for attempt in range(3):
            # Fair selection gives tenant b its turn after a. Complete b's
            # independent work rather than bypassing scheduler admission.
            if attempt == 1:
                claim(db, other, 120)
                other.data = {**other.data, "state": "COMPLETED"}
                from backend.scheduling import release
                release(db, other)
                db.commit()
                other_data = copy.deepcopy(other.data)
            assert claim(db, job, 120)["state"] == "CLAIMED"
            db.get(QueueEntry, job.id).lease_expires_at = "2000-01-01T00:00:00+00:00"
            db.commit()
            assert recover_expired(db) == ([job.id] if attempt < 2 else [])
            db.refresh(job)
            assert job.data["recovery_attempts"] == attempt + 1
            assert other.data == other_data
        assert job.data["state"] == "FAILED"
        assert job.data["error_code"] == "WORKER_RECOVERY_EXHAUSTED"
        assert job.data["errors"]
        assert len(job.data["attempt_history"]) == 3
        assert claim(db, job, 120)["state"] == "STOPPED"


def test_expired_worker_without_retained_source_has_an_actionable_failure(factory):  # noqa: F811
    with factory() as db:
        job = queued(db, "a", "a1", source="FILES")
        claim(db, job, 120)
        db.get(QueueEntry, job.id).lease_expires_at = "2000-01-01T00:00:00+00:00"
        db.commit()
        assert recover_expired(db) == []
        assert job.data["state"] == "FAILED"
        assert job.data["error_code"] == "RETAINED_INPUT_UNAVAILABLE"
        assert job.data["errors"]
