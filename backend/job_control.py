"""Shared fenced job transitions; caller owns authorization, transaction and dispatch."""
import os
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.db import Repository
from backend.domain import audit


def transition_job(db,user,job,action):
    if action == "cancel":
        if job.data.get("state") in {"COMPLETED", "COMPLETED_NO_FINDINGS", "CANCELLED"}:
            raise HTTPException(409, "This job has already finished.")
        from backend.db import AnalysisInput

        retained = db.get(AnalysisInput, job.id)
        from backend.scheduling import cancel
        result = cancel(db, job)
        if retained and result == "CANCELLED":
            db.delete(retained)
        audit(db, user, "JOB_CANCELLED", job.id, {}, job.repository_id)
        if result == "CANCELLATION_REQUESTED":
            return {"cancellation_requested": True}
    else:
        from backend.governance import job_principal
        from backend.queue import check_capacity
        original_actor=job_principal(db,job)
        check_capacity(db,original_actor,db.get(Repository,job.repository_id),source=job.data.get("source"),existing_job=job)
        if os.getenv("JOB_MODE") not in {"celery", "local"}:
            raise HTTPException(503, "Start the local development runner or a configured Celery worker before retrying.")
        if job.data.get("source") == "GITHUB" and not os.getenv("REDIS_URL"):
            raise HTTPException(503, "Private GitHub jobs require the configured SCM Celery worker.")
        lease = job.data.get("lease_expires_at")
        stale = (
            job.data.get("state") not in {"COMPLETED", "COMPLETED_NO_FINDINGS", "CANCELLED"}
            and lease
            and datetime.fromisoformat(lease) <= datetime.now(timezone.utc)
        )
        if job.data.get("state") not in {"FAILED", "PARTIAL", "QUEUED"} and not stale:
            raise HTTPException(409, "This job cannot be retried in its current state.")
        from backend.db import AnalysisInput

        if job.data.get("source") in {"ZIP", "FILES", "INVENTORY"} and not db.get(AnalysisInput, job.id):
            raise HTTPException(409, "Retained input is unavailable; upload a fresh snapshot.")

        repair_revision = "safe-intake-2026-10-08"
        repair_retry = (job.data.get("source") == "GITHUB" and job.data.get("retry_count", 0) == 2
            and job.data.get("error_type") in {"TransportError", "TimeoutError"}
            and not job.data.get("repair_retry_revision"))
        # One further attempt is tied to the verified writer-collision and
        # transport fixes. This finite migration never resets prior counts.
        if (job.data.get("source") == "GITHUB" and job.data.get("retry_count") == 3
            and job.data.get("repair_retry_revision") == repair_revision
            and job.data.get("error_code") == "SCM_TRANSPORT"):
            repair_revision, repair_retry = "serialized-transport-2026-10-08", True
        if job.data.get("retry_count", 0) >= 2 and not repair_retry:
            raise HTTPException(409, "Retry limit reached. Review the precise failure before importing a fresh snapshot.")
        previous_attempt = {key: job.data.get(key) for key in ("state", "stage", "error_type", "error_code", "error_detail", "started_at", "finished_at", "duration_ms", "snapshot_id", "stages", "performance", "completed_analysis", "retry_count", "repair_retry_revision")}
        job.data = {
            **job.data,
            "state": "QUEUED",
            "stage": "QUEUED",
            "finished_at": None,
            "retry_count": job.data.get("retry_count", 0) + 1,
            "attempt_history": [*job.data.get("attempt_history", []), previous_attempt],
            "repair_retry_revision": repair_revision if repair_retry else job.data.get("repair_retry_revision"),
            "errors": [], "error_detail": None, "error_code": None,
            "duration_ms": None, "performance": {}, "completed_analysis": None,
        }
        audit(db, user, "JOB_RETRIED", job.id, {"retry_count": job.data["retry_count"]}, job.repository_id)
        from backend.scheduling import register
        register(db, job)
    return {}
