from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import sessionmaker

from backend.db import Base, Organization, PRHead, QueueEntry, Record, Repository, make_engine
from backend.domain import add
from backend.scheduling import (
    JobCancelled,
    cancel,
    check_capacity,
    claim,
    enqueue_scm,
    ensure_current,
    owns,
    recover_expired,
    register,
    release,
)


@pytest.fixture
def factory(tmp_path):
    engine = make_engine("sqlite:///" + str(tmp_path / "scheduler.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([Organization(id=org, name=org) for org in ("a", "b")])
        db.flush()
        db.add_all(
            [
                Repository(
                    id=org + str(n),
                    organization_id=org,
                    name="owned/repo",
                    system="Owned",
                    component="Owned",
                    owner="Owned",
                )
                for org in ("a", "b")
                for n in (1, 2)
            ]
        )
        db.commit()
    yield factory
    engine.dispose()


def queued(db, org, repo, **details):
    job = add(db, org, repo, "job", {"state": "QUEUED", "execution": "CELERY", "source": "GITHUB", **details})
    register(db, job)
    db.commit()
    return job


def test_round_robin_and_repository_running_limit(factory):
    with factory() as db:
        a1, a2, a3 = queued(db, "a", "a1"), queued(db, "a", "a1"), queued(db, "a", "a2")
        b = queued(db, "b", "b1")
        assert claim(db, a1, 120)["state"] == "CLAIMED"
        assert claim(db, a2, 120)["state"] == "DEFERRED"
        assert claim(db, a3, 120)["state"] == "DEFERRED"  # tenant b has its turn
        assert claim(db, b, 120)["state"] == "DEFERRED"  # SQLite serializes its single writer.
        assert claim(db, a1, 120)["state"] == "ALREADY_RUNNING"
        token = a1.data["worker_token"]
        a1.data = {**a1.data, "state": "COMPLETED"}
        release(db, a1, token=token)
        db.commit()
        assert claim(db, a3, 120)["state"] == "DEFERRED"  # b still gets the next tenant turn.
        assert claim(db, b, 120)["state"] == "CLAIMED"
        assert claim(db, a3, 120)["state"] == "DEFERRED"


def test_100_pending_is_separate_from_one_running_and_bounded(factory, monkeypatch):
    monkeypatch.setenv("QUEUE_PENDING_REPOSITORY", "100")
    with factory() as db:
        for _ in range(100):
            check_capacity(db, "a", "a1")
            queued(db, "a", "a1")
        with pytest.raises(ValueError):
            check_capacity(db, "a", "a1")
        db.rollback()
        jobs = list(db.scalars(select(Record).where(Record.repository_id == "a1").order_by(Record.created_at)))
        assert claim(db, jobs[0], 120)["state"] == "CLAIMED"
        assert claim(db, jobs[1], 120)["state"] == "DEFERRED"


def test_scoped_sha_dedup_supersession_and_running_cancellation(factory):
    with factory() as db:
        repo = db.get(Repository, "a1")
        old = enqueue_scm(db, repo, {"head_sha": "a" * 40, "pr_number": 7}, event="pull_request", delivery_id="first")
        db.commit()
        duplicate = enqueue_scm(
            db, repo, {"head_sha": "a" * 40, "pr_number": 7}, event="pull_request", delivery_id="second"
        )
        assert duplicate.id == old.id
        db.commit()
        claimed = claim(db, old, 120)
        new = enqueue_scm(db, repo, {"head_sha": "b" * 40, "pr_number": 7}, event="pull_request", delivery_id="third")
        db.commit()
        with pytest.raises(JobCancelled):
            ensure_current(db, old)
        assert db.get(PRHead, ("a", "a1", "pr:7")).job_id == new.id
        old.data = {**old.data, "state": "CANCELLED"}
        release(db, old, token=claimed["token"])
        db.commit()
        assert claim(db, new, 120)["state"] == "CLAIMED"
        assert cancel(db, new) == "CANCELLATION_REQUESTED"
        db.commit()
        with pytest.raises(JobCancelled):
            ensure_current(db, new)


def test_expired_lease_is_recovered_and_stale_worker_is_fenced(factory):
    with factory() as db:
        job = queued(db, "a", "a1")
        first = claim(db, job, 120)
        job.data = {**job.data, "stage": "BUILDING_EVIDENCE", "performance": {"cache_hits": 14},
                    "completed_analysis": {"publication_state": "UNPUBLISHED"}}
        db.get(QueueEntry, job.id).lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
        assert recover_expired(db) == [job.id]
        db.refresh(job)
        assert job.data["attempt_history"][-1]["stage"] == "BUILDING_EVIDENCE"
        assert job.data["attempt_history"][-1]["performance"] == {"cache_hits": 14}
        assert job.data["attempt_history"][-1]["completed_analysis"]["publication_state"] == "UNPUBLISHED"
        second = claim(db, job, 120)
        assert second["state"] == "CLAIMED" and second["token"] != first["token"]
        assert not owns(db, job.id, first["token"])
        release(db, job, token=first["token"])
        db.commit()
        assert db.get(QueueEntry, job.id).state == "RUNNING"
        assert owns(db, job.id, second["token"])


def test_idle_recovery_is_read_only_while_another_connection_holds_writer(factory):
    engine = factory.kw["bind"]
    writes = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    with engine.connect() as writer:
        writer.execute(text("INSERT INTO queue_cursor VALUES ('native', '', 0)"))
        event.listen(engine, "before_cursor_execute", capture)
        try:
            with factory() as db:
                db.execute(text("PRAGMA busy_timeout=50"))
                assert recover_expired(db, execution="LOCAL") == []
            assert writes == []
        finally:
            event.remove(engine, "before_cursor_execute", capture)
            writer.rollback()


def test_local_recovery_does_not_lock_for_expired_celery_work(factory):
    with factory() as db:
        job = queued(db, "a", "a1")
        claim(db, job, 120)
        db.get(QueueEntry, job.id).lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
    with factory.kw["bind"].connect() as writer:
        writer.execute(text("UPDATE queue_cursor SET revision=revision+1 WHERE id='native'"))
        with factory() as db:
            db.execute(text("PRAGMA busy_timeout=50"))
            assert recover_expired(db, execution="LOCAL") == []
        writer.rollback()
    with factory() as db:
        assert recover_expired(db) == [job.id]


def test_concurrent_duplicate_deliveries_claim_one_attempt(factory):
    with factory() as db:
        job_id = queued(db, "a", "a1").id

    def attempt(_):
        with factory() as db:
            return claim(db, db.get(Record, job_id), 120)["state"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        states = list(pool.map(attempt, range(4)))
    assert states.count("CLAIMED") == 1
    assert states.count("ALREADY_RUNNING") == 3
