from backend.db import Record, Repository, Session, User, now
from workers.tasks import celery


@celery.task(name="projecttrace.advisories", bind=True, max_retries=2)
def advisory_job(self, job_id):
    from backend.jobs import TERMINAL
    from backend.scheduling import JobCancelled, claim, owns, release

    with Session() as db:
        job = db.get(Record, job_id)
        if not job or job.kind != "job" or job.data.get("type") != "ADVISORIES" or job.data.get("state") in TERMINAL:
            return
        claimed = claim(db, job, 120)
        if claimed["state"] == "DEFERRED":
            raise self.retry(countdown=2, max_retries=None)
        if claimed["state"] != "CLAIMED":
            return claimed
        try:
            user, repo = db.get(User, job.data.get("user_id")), db.get(Repository, job.repository_id)
            snapshot = db.get(Record, job.data.get("snapshot_id"))
            if (
                not user
                or not user.enabled
                or not repo
                or not snapshot
                or repo.organization_id != job.organization_id
                or snapshot.organization_id != job.organization_id
                or snapshot.repository_id != repo.id
                or snapshot.kind != "snapshot"
            ):
                raise ValueError("Advisory worker tenant scope is invalid.")
            from backend.governance import job_principal
            user=job_principal(db,job)
            from backend.trust import require_egress

            require_egress(db, user.organization_id, "OSV")
            from backend.advisories import run_checks
            from integrations.osv import query

            run_checks(db, user, repo, snapshot, job, query)
        except Exception as error:
            db.rollback()
            if not owns(db, job_id, claimed["token"]):
                return {"state": "STALE_WORKER"}
            job = db.get(Record, job_id)
            job.data = {
                **job.data,
                "state": "CANCELLED" if isinstance(error, JobCancelled) else "FAILED",
                "finished_at": now(),
                "error_type": type(error).__name__,
                "errors": ["Advisory checking failed; native findings remain available."],
            }
            db.commit()
            if not isinstance(error, JobCancelled):
                raise
        finally:
            current = db.get(Record, job_id)
            if current:
                release(db, current, token=claimed["token"])
                db.commit()
