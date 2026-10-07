"""Database-serialized tenant round robin with bounded admission and fenced leases."""

import os
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from backend.db import PRHead, QueueCursor, QueueEntry, Record, now


class JobCancelled(ValueError):
    pass


def limits():
    values = {
        "global": (4, 1, 64),
        "tenant": (2, 1, 32),
        "repository": (1, 1, 16),
        "pending_global": (10000, 100, 50000),
        "pending_tenant": (1000, 100, 10000),
        "pending_repository": (200, 100, 1000),
    }
    result = {}
    for key, (default, low, high) in values.items():
        value = int(os.getenv("QUEUE_" + key.upper(), str(default)))
        if not low <= value <= high:
            raise ValueError("Queue quota configuration is outside its bounded range.")
        result[key] = value
    return result


def lock(db):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError("Fair scheduling requires a supported SQL adapter.")
    # This write serializes SQLite too; PostgreSQL holds the singleton row lock
    # until the caller commits. Admission/claims use this same short transaction.
    db.execute(insert(QueueCursor).values(id="native", last_tenant="", revision=0).on_conflict_do_nothing())
    db.execute(update(QueueCursor).where(QueueCursor.id == "native").values(revision=QueueCursor.revision + 1))
    return db.scalar(select(QueueCursor).where(QueueCursor.id == "native").execution_options(populate_existing=True))


def check_capacity(db, organization_id, repository_id):
    lock(db)
    quota = limits()
    pending = QueueEntry.state.in_(["QUEUED", "RUNNING"])
    for field, condition in (
        ("pending_global", True),
        ("pending_tenant", QueueEntry.organization_id == organization_id),
        (
            "pending_repository",
            (QueueEntry.organization_id == organization_id) & (QueueEntry.repository_id == repository_id),
        ),
    ):
        count = db.scalar(select(func.count()).select_from(QueueEntry).where(pending, condition))
        if count >= quota[field]:
            raise ValueError("Analysis queue admission quota reached; retry after pending work drains.")


def register(db, job, *, pr_key=None, head_sha=None):
    from backend.jobs import TERMINAL

    lock(db)
    row = db.get(QueueEntry, job.id)
    if not row:
        row = QueueEntry(
            job_id=job.id,
            organization_id=job.organization_id,
            repository_id=job.repository_id,
            state="QUEUED",
            created_at=job.created_at or now(),
            pr_key=pr_key,
            head_sha=head_sha,
        )
        db.add(row)
    elif job.data.get("state") == "QUEUED" and row.state in TERMINAL:
        row.state, row.cancel_requested, row.worker_token, row.lease_expires_at = "QUEUED", False, None, None
    if pr_key and head_sha:
        key = (job.organization_id, job.repository_id, pr_key)
        current = db.get(PRHead, key)
        if current:
            current.job_id, current.head_sha = job.id, head_sha
        else:
            db.add(
                PRHead(
                    organization_id=job.organization_id,
                    repository_id=job.repository_id,
                    pr_key=pr_key,
                    job_id=job.id,
                    head_sha=head_sha,
                )
            )
        for previous in db.scalars(
            select(QueueEntry).where(
                QueueEntry.organization_id == job.organization_id,
                QueueEntry.repository_id == job.repository_id,
                QueueEntry.pr_key == pr_key,
                QueueEntry.job_id != job.id,
                QueueEntry.state.in_(["QUEUED", "RUNNING"]),
            )
        ):
            previous.cancel_requested = True
            if previous.state == "QUEUED":
                previous.state = "CANCELLED"
                obsolete = db.get(Record, previous.job_id)
                obsolete.data = {
                    **obsolete.data,
                    "state": "CANCELLED",
                    "stage": "CANCELLED",
                    "finished_at": now(),
                    "superseded_by": job.id,
                }
    return row


def enqueue_scm(db, repository, details, *, event, delivery_id, connection_id=None, actor=None):
    """Retain every receipt while suppressing duplicate work for the same scoped head."""
    import hashlib

    from backend.domain import add

    lock(db)
    pr_key = (
        ("pr:" + str(details["pr_number"]))
        if details.get("pr_number")
        else "branch:" + str(details.get("branch", "main"))[:120]
    )
    head = details.get("head_sha")
    identity = hashlib.sha256(str((connection_id, repository.id, pr_key, head or delivery_id)).encode()).hexdigest()
    natural_key = "scm-head:" + identity
    latest = db.get(PRHead, (repository.organization_id, repository.id, pr_key))
    if latest and latest.head_sha == head:
        return db.get(Record, latest.job_id)
    previous = db.scalar(
        select(Record).where(
            Record.organization_id == repository.organization_id,
            Record.kind == "job",
            Record.natural_key == natural_key,
        )
    )
    if previous and not latest:
        return previous
    if previous:
        natural_key += ":" + secrets.token_hex(8)
    check_capacity(db, repository.organization_id, repository.id)
    job = add(
        db,
        repository.organization_id,
        repository.id,
        "job",
        {
            "state": "QUEUED",
            "stage": "QUEUED",
            "event": event,
            "delivery_id": delivery_id,
            "repository_id": repository.id,
            "connection_id": connection_id,
            "provider_fetch": "PENDING_CONFIGURATION",
            "source": "GITHUB",
            "execution": "CELERY",
            "user_id": actor.id if actor else None,
            "queued_at": now(),
            "warnings": [],
            "errors": [],
            "stages": [],
            **details,
        },
        natural_key,
    )
    register(db, job, pr_key=pr_key if head else None, head_sha=head)
    return job


def eligible(db):
    quota = limits()
    running = list(
        db.execute(
            select(QueueEntry.organization_id, QueueEntry.repository_id).where(
                QueueEntry.state == "RUNNING", QueueEntry.lease_expires_at > now()
            )
        )
    )
    if len(running) >= quota["global"]:
        return []
    tenants, repos = Counter(r[0] for r in running), Counter((r[0], r[1]) for r in running)
    queued = db.scalars(
        select(QueueEntry)
        .where(QueueEntry.state == "QUEUED", QueueEntry.cancel_requested.is_(False))
        .order_by(QueueEntry.created_at, QueueEntry.job_id)
        .limit(quota["pending_global"])
    )
    result, seen = [], set()
    for row in queued:
        if (
            row.organization_id not in seen
            and tenants[row.organization_id] < quota["tenant"]
            and repos[(row.organization_id, row.repository_id)] < quota["repository"]
        ):
            seen.add(row.organization_id)
            result.append(row)
    return sorted(result, key=lambda row: row.organization_id)


def claim(db, job, seconds):
    cursor = lock(db)
    row = db.get(QueueEntry, job.id)
    if not row:
        row = register(db, job)
        db.flush()
    if row.cancel_requested or row.state not in {"QUEUED", "RUNNING"}:
        db.commit()
        return {"state": "STOPPED"}
    if row.state == "RUNNING":
        if row.lease_expires_at and row.lease_expires_at > now():
            db.commit()
            return {"state": "ALREADY_RUNNING"}
        row.state = "QUEUED"
        db.flush()
    candidates = eligible(db)
    selected = next(
        (item for item in candidates if item.organization_id > cursor.last_tenant),
        candidates[0] if candidates else None,
    )
    if not selected or selected.job_id != job.id:
        db.commit()
        return {"state": "DEFERRED"}
    token = secrets.token_hex(24)
    row.state, row.worker_token = "RUNNING", token
    row.lease_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds + 30)).isoformat()
    cursor.last_tenant = row.organization_id
    job.data = {
        **job.data,
        "worker_token": token,
        "lease_expires_at": row.lease_expires_at,
        "queue_wait_ms": round(
            (
                datetime.now(timezone.utc) - datetime.fromisoformat(job.data.get("queued_at", row.created_at))
            ).total_seconds()
            * 1000,
            3,
        ),
    }
    db.commit()
    return {"state": "CLAIMED", "token": token}


def ensure_current(db, job, *, renew_seconds=None):
    row = db.execute(
        select(QueueEntry.state, QueueEntry.worker_token, QueueEntry.cancel_requested, QueueEntry.pr_key).where(
            QueueEntry.job_id == job.id,
            QueueEntry.organization_id == job.organization_id,
            QueueEntry.repository_id == job.repository_id,
        )
    ).first()
    if not row:
        return  # Legacy synchronous jobs have no scheduler claim.
    if row.state != "RUNNING" or row.cancel_requested or row.worker_token != job.data.get("worker_token"):
        raise JobCancelled("Analysis was cancelled, superseded, or its worker lease was replaced.")
    if row.pr_key:
        latest = db.scalar(
            select(PRHead.job_id).where(
                PRHead.organization_id == job.organization_id,
                PRHead.repository_id == job.repository_id,
                PRHead.pr_key == row.pr_key,
            )
        )
        if latest != job.id:
            raise JobCancelled("A newer PR head superseded this analysis.")
    if renew_seconds:
        db.execute(
            update(QueueEntry)
            .where(QueueEntry.job_id == job.id, QueueEntry.worker_token == row.worker_token)
            .values(lease_expires_at=(datetime.now(timezone.utc) + timedelta(seconds=renew_seconds + 30)).isoformat())
        )


def owns(db, job_id, token):
    if not token:
        return True
    return db.scalar(select(QueueEntry.worker_token).where(QueueEntry.job_id == job_id)) == token


def recover_expired(db):
    from backend.db import AnalysisInput

    lock(db)
    recovered = []
    for entry in db.scalars(
        select(QueueEntry).where(QueueEntry.state == "RUNNING", QueueEntry.lease_expires_at <= now()).limit(100)
    ):
        job = db.get(Record, entry.job_id)
        attempts = job.data.get("recovery_attempts", 0)
        retained = db.get(AnalysisInput, job.id) if job.data.get("source") in {"FILES", "ZIP", "INVENTORY"} else None
        failed = attempts >= 2 or (
            job.data.get("source") in {"FILES", "ZIP", "INVENTORY"} and (not retained or retained.expires_at <= now())
        )
        state = "CANCELLED" if entry.cancel_requested else "FAILED" if failed else "QUEUED"
        entry.state, entry.worker_token, entry.lease_expires_at = state, None, None
        job.data = {
            **job.data,
            "state": state,
            "stage": state,
            "worker_token": None,
            "recovery_attempts": attempts + 1,
            "finished_at": None if state == "QUEUED" else now(),
            "warnings": ["Expired worker lease recovered; stale workers cannot publish output."],
        }
        if state == "QUEUED":
            recovered.append(job.id)
    db.commit()
    return recovered


def release(db, job, *, token=None):
    # A stale worker cannot release another attempt's newer lease.
    token = token or job.data.get("worker_token")
    if token:
        db.execute(
            update(QueueEntry)
            .where(QueueEntry.job_id == job.id, QueueEntry.worker_token == token)
            .values(state=job.data.get("state", "FAILED"), lease_expires_at=None, worker_token=None)
        )


def cancel(db, job):
    lock(db)
    row = db.get(QueueEntry, job.id)
    if row:
        row.cancel_requested = True
        if row.state == "RUNNING":
            return "CANCELLATION_REQUESTED"
        row.state = "CANCELLED"
    job.data = {**job.data, "state": "CANCELLED", "stage": "CANCELLED", "finished_at": now()}
    return "CANCELLED"
