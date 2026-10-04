import os

from celery import Celery

from backend.db import Record, Repository, Session, User
from backend.domain import persist_analysis

celery = Celery("projecttrace", broker=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
celery.conf.update(
    imports=["workers.github"],
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=120,
    task_soft_time_limit=100,
    task_reject_on_worker_lost=True,
)


@celery.task(name="projecttrace.analyze", bind=True, max_retries=2)
def analyze_job(self, job_id):
    with Session() as db:
        job = db.get(Record, job_id)
        if not job or job.kind != "job" or job.data.get("state") in {"COMPLETED", "CANCELLED"}:
            return
        if "files" not in job.data:
            job.data = {
                **job.data,
                "state": "PARTIAL",
                "reason": "Provider fetching is not configured. Signed delivery was retained.",
            }
            db.commit()
            return
        user = db.get(User, job.data["user_id"])
        repo = db.get(Repository, job.repository_id)
        if (
            not user
            or not repo
            or user.organization_id != job.organization_id
            or repo.organization_id != job.organization_id
        ):
            raise ValueError("Worker tenant scope is invalid.")
        from backend.security import require_repo

        require_repo(db, user, repo.id)
        try:
            job.data = {**job.data, "state": "ANALYZING"}
            db.commit()
            snapshot = persist_analysis(db, user, repo, job.data["files"])
            job.data = {k: v for k, v in job.data.items() if k != "files"} | {
                "state": "COMPLETED",
                "snapshot_id": snapshot.id,
            }
            db.commit()
        except ValueError:
            db.rollback()
            job = db.get(Record, job_id)
            job.data = {"state": "FAILED", "reason": "Static input validation failed."}
            db.commit()
            raise
