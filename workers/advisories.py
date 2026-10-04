from backend.db import Record, Repository, Session, User, now
from backend.security import require_repo
from workers.tasks import celery


@celery.task(name="projecttrace.advisories", bind=True, max_retries=2)
def advisory_job(self, job_id):
    with Session() as db:
        job = db.get(Record, job_id)
        if not job or job.kind != "job" or job.data.get("type") != "ADVISORIES" or job.data.get("state") in {"COMPLETED", "CANCELLED"}:
            return
        try:
            user, repo = db.get(User, job.data.get("user_id")), db.get(Repository, job.repository_id)
            snapshot = db.get(Record, job.data.get("snapshot_id"))
            if not user or not repo or not snapshot or user.organization_id != job.organization_id or repo.organization_id != job.organization_id or snapshot.organization_id != job.organization_id or snapshot.repository_id != repo.id or snapshot.kind != "snapshot":
                raise ValueError("Advisory worker tenant scope is invalid.")
            require_repo(db, user, repo.id)
            from backend.advisories import run_checks
            from integrations.osv import query

            run_checks(db, user, repo, snapshot, job, query)
        except Exception as error:
            db.rollback()
            job = db.get(Record, job_id)
            job.data = {**job.data, "state": "FAILED", "finished_at": now(), "error_type": type(error).__name__,
                "errors": ["Advisory checking failed; native findings remain available."]}
            db.commit()
            raise
