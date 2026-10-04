import os
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import select

from backend.db import AnalysisInput, Record, Repository, Session, User, now
from backend.jobs import TERMINAL, execute_analysis

celery = Celery("projecttrace", broker=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
celery.conf.update(
    imports=["workers.github", "workers.advisories"],
    task_serializer="json", accept_content=["json"], result_serializer="json",
    task_acks_late=True, worker_prefetch_multiplier=1, task_time_limit=120,
    task_soft_time_limit=100, task_reject_on_worker_lost=True,
    broker_connection_timeout=3, broker_connection_retry_on_startup=True,
    beat_schedule={"expire-analysis-inputs": {"task": "projecttrace.expire_inputs", "schedule": 3600}},
)


@celery.task(name="projecttrace.analyze", bind=True, max_retries=2)
def analyze_job(self, job_id):
    with Session() as db:
        job = db.scalar(select(Record).where(Record.id == job_id).with_for_update())
        if not job or job.kind != "job" or job.data.get("state") in {"COMPLETED", "COMPLETED_NO_FINDINGS", "CANCELLED"}:
            return
        if job.data.get("state") not in TERMINAL | {"QUEUED"}:
            lease = job.data.get("lease_expires_at")
            if not lease or datetime.fromisoformat(lease) > datetime.now(timezone.utc):
                return
        try:
            user = db.get(User, job.data["user_id"])
            repo = db.get(Repository, job.repository_id)
            if not user or not repo or user.organization_id != job.organization_id or repo.organization_id != job.organization_id:
                raise ValueError("Worker tenant scope is invalid.")
            from backend.main import local_advisories
            from backend.queue import load_input
            from backend.security import require_repo

            require_repo(db, user, repo.id)
            queued_at = job.data.get("queued_at", now())
            job.data = {**job.data, "queue_wait_ms": round((datetime.now(timezone.utc) - datetime.fromisoformat(queued_at)).total_seconds() * 1000, 2)}
            # Legacy operator-created fixtures are supported; API never puts raw input in records.
            loader = (lambda: job.data["files"]) if "files" in job.data else (lambda: load_input(db, job))
            snapshot, job = execute_analysis(db, user, repo, loader, job=job,
                request_id=job.data.get("request_id"), advisory_cache=local_advisories(), **job.data.get("options", {}))
            retained = db.get(AnalysisInput, job.id)
            if retained:
                db.delete(retained)
            job.data = {k: v for k, v in job.data.items() if k != "files"}
            db.commit()
        except Exception as error:
            db.rollback()
            job = db.get(Record, job_id)
            job.data = {k: v for k, v in job.data.items() if k != "files"} | {
                "state": "FAILED", "error_type": type(error).__name__, "finished_at": now(),
                "errors": ["Static analysis failed; retry retained input or upload a fresh snapshot."],
            }
            db.commit()
            raise
        if os.getenv("OSV_ENABLED") == "1":
            from backend.advisories import enqueue_advisories

            try:
                enqueue_advisories(db, user, repo, snapshot)
            except Exception as error:
                db.rollback()
                job = db.get(Record, job_id)
                job.data = {**job.data, "state": "PARTIAL", "warnings": ["Native snapshot completed; advisory queue submission failed."],
                    "engines": {**job.data.get("engines", {}), "OSV": {"state": "FAILED", "error_type": type(error).__name__}}}
                db.commit()


@celery.task(name="projecttrace.expire_inputs")
def expire_inputs():
    from backend.queue import purge_expired_inputs

    with Session() as db:
        return {"expired_inputs": purge_expired_inputs(db)}
