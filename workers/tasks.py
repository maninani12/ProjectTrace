import os
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import select

from backend.db import AnalysisInput, Record, Repository, Session, User, now
from backend.jobs import TERMINAL, execute_analysis

celery = Celery("projecttrace", broker=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
celery.conf.update(
    imports=["workers.github", "workers.advisories"],
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=120,
    task_soft_time_limit=100,
    task_reject_on_worker_lost=True,
    broker_connection_timeout=3,
    broker_connection_retry_on_startup=True,
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=262144,
    broker_transport_options={"visibility_timeout": 180},
    beat_schedule={"expire-analysis-inputs": {"task": "projecttrace.expire_inputs", "schedule": 3600}},
)
celery.conf.beat_schedule["recover-stale-analysis"] = {"task": "projecttrace.recover_jobs", "schedule": 60}


@celery.task(name="projecttrace.analyze", bind=True, max_retries=2)
def analyze_job(self, job_id):
    with Session() as db:
        job = db.scalar(select(Record).where(Record.id == job_id).with_for_update())
        if not job or job.kind != "job" or job.data.get("state") in TERMINAL:
            return
        if job.data.get("state") not in TERMINAL | {"QUEUED"}:
            lease = job.data.get("lease_expires_at")
            if not lease or datetime.fromisoformat(lease) > datetime.now(timezone.utc):
                return
        try:
            user = db.get(User, job.data["user_id"])
            repo = db.get(Repository, job.repository_id)
            if (
                not user
                or not repo
                or user.organization_id != job.organization_id
                or repo.organization_id != job.organization_id
            ):
                raise ValueError("Worker tenant scope is invalid.")
            from backend.main import local_advisories
            from backend.queue import load_input
            from backend.security import require_repo

            require_repo(db, user, repo.id)
            queued_at = job.data.get("queued_at", now())
            from datetime import timedelta

            job.data = {
                **job.data,
                "state": "FETCHING",
                "stage": "FETCHING",
                "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=125)).isoformat(),
                "queue_wait_ms": round(
                    (datetime.now(timezone.utc) - datetime.fromisoformat(queued_at)).total_seconds() * 1000, 2
                ),
            }
            # Claim under the PostgreSQL row lock before publishing any stages.
            # The committed lease prevents duplicate deliveries during later commits.
            db.commit()
            # Legacy operator-created fixtures are supported; API never puts raw input in records.
            loader = (lambda: job.data["files"]) if "files" in job.data else (lambda: load_input(db, job))
            snapshot, job = execute_analysis(
                db,
                user,
                repo,
                loader,
                job=job,
                request_id=job.data.get("request_id"),
                advisory_cache=local_advisories(),
                **job.data.get("options", {}),
            )
            retained = db.get(AnalysisInput, job.id)
            if retained:
                db.delete(retained)
            job.data = {k: v for k, v in job.data.items() if k != "files"}
            db.commit()
        except Exception as error:
            db.rollback()
            job = db.get(Record, job_id)
            job.data = {k: v for k, v in job.data.items() if k != "files"} | {
                "state": "FAILED",
                "error_type": type(error).__name__,
                "finished_at": now(),
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
                job.data = {
                    **job.data,
                    "state": "PARTIAL",
                    "warnings": ["Native snapshot completed; advisory queue submission failed."],
                    "engines": {
                        **job.data.get("engines", {}),
                        "OSV": {"state": "FAILED", "error_type": type(error).__name__},
                    },
                }
                db.commit()


@celery.task(name="projecttrace.expire_inputs")
def expire_inputs():
    from backend.queue import purge_expired_inputs

    with Session() as db:
        return {"expired_inputs": purge_expired_inputs(db)}


@celery.task(name="projecttrace.recover_jobs")
def recover_jobs():
    """Recover expired worker leases under database row locks, at most twice."""
    from backend.queue import dispatch

    recovered = 0
    for _ in range(100):
        with Session() as db:
            job = db.scalar(
                select(Record)
                .where(
                    Record.kind == "job",
                    Record.data["source"].as_string().in_(["ZIP", "FILES"]),
                    Record.data["state"].as_string().not_in(list(TERMINAL | {"QUEUED"})),
                    Record.data["lease_expires_at"].as_string() <= now(),
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not job:
                break
            retained = db.get(AnalysisInput, job.id)
            attempts = job.data.get("recovery_attempts", 0)
            if (
                not retained
                or retained.organization_id != job.organization_id
                or retained.repository_id != job.repository_id
                or retained.expires_at <= now()
                or attempts >= 2
            ):
                job.data = {
                    **job.data,
                    "state": "FAILED",
                    "finished_at": now(),
                    "errors": ["Worker recovery exhausted or retained input unavailable; upload a fresh snapshot."],
                }
                db.commit()
                continue
            job.data = {
                **job.data,
                "state": "QUEUED",
                "stage": "QUEUED",
                "queued_at": now(),
                "recovery_attempts": attempts + 1,
                "warnings": ["An expired worker lease was recovered; previous snapshot output remains atomic."],
            }
            db.commit()
            dispatch(db, job)
            recovered += 1
    return {"recovered_jobs": recovered}
