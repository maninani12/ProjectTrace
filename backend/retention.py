"""Transaction-local expiry ownership, shared with scheduler admission/fencing."""

from sqlalchemy import exists, select

from backend.db import QueueEntry


class ExpiryGuard:
    """Bounded caller batches own the guard until commit; never a global cache.

    Scheduler admission is serialized before queue-row locks. SQLite's writer
    lock also excludes renewal; PostgreSQL skips renewal-locked rows and holds
    acquired row locks until the caller commits. Retention never renews a lease,
    extends an expiry timestamp, or makes expired data readable.
    """

    def __init__(self, db, instant):
        self.db, self.instant = db, instant
        self.locked, self.rows, self.decisions = False, {}, {}

    def active(self, model):
        return exists(
            select(QueueEntry.job_id).where(
                QueueEntry.job_id == model.job_id,
                QueueEntry.organization_id == model.organization_id,
                QueueEntry.repository_id == model.repository_id,
                QueueEntry.state == "RUNNING",
                QueueEntry.lease_expires_at > self.instant,
            )
        ).correlate(model)

    def allows(self, job_id, organization_id, repository_id):
        key = job_id, organization_id, repository_id
        if key in self.decisions:
            return self.decisions[key]
        if not self.locked:
            from backend.scheduling import lock

            lock(self.db)
            self.locked = True
        scope = (
            QueueEntry.job_id == job_id,
            QueueEntry.organization_id == organization_id,
            QueueEntry.repository_id == repository_id,
        )
        row = self.db.scalar(
            select(QueueEntry).where(*scope).with_for_update(skip_locked=True).execution_options(populate_existing=True)
        )
        self.rows[key] = row
        # No returned row can mean a concurrent PostgreSQL renewal holds it.
        busy = row is None and self.db.scalar(select(QueueEntry.job_id).where(*scope)) is not None
        allowed = not busy and not (
            row and row.state == "RUNNING" and row.lease_expires_at and row.lease_expires_at > self.instant
        )
        self.decisions[key] = bool(allowed)
        return bool(allowed)

    def finish(self, job):
        row = self.rows.get((job.id, job.organization_id, job.repository_id))
        if row is not None:
            row.state = job.data["state"]
            row.worker_token = row.lease_expires_at = None
