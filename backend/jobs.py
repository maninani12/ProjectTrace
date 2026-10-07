"""Durable local analysis lifecycle. No raw source or exception text is logged."""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from backend.db import Record, now
from backend.domain import add, audit, persist_analysis

STATES = {
    "NO_REPOSITORY",
    "READY",
    "QUEUED",
    "FETCHING",
    "VALIDATING",
    "PARSING",
    "ANALYZING",
    "BUILDING_EVIDENCE",
    "EXTRACTING_CLAIMS",
    "VERIFYING",
    "CORRELATING",
    "FINALIZING",
    "COMPLETED",
    "COMPLETED_NO_FINDINGS",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
}
TERMINAL = {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL", "FAILED", "CANCELLED"}
log = logging.getLogger("projecttrace.pipeline")


def inventory_time_budget():
    seconds = int(os.getenv("REPOSITORY_ANALYSIS_SECONDS", "900"))
    if not 120 <= seconds <= 3600:
        raise ValueError("Repository analysis time budget must be between 120 and 3600 seconds.")
    return seconds


def job_time_budget(job):
    return inventory_time_budget() if job.data.get("source") in {"INVENTORY", "GITHUB"} else 120


def execute_analysis(db, user, repo, files, *, request_id=None, job=None, _elapsed_clock=None, **options):
    from backend.repository_store import RepositoryFiles

    inventory_input = isinstance(files, RepositoryFiles)
    job = job or add(
        db,
        user.organization_id,
        repo.id,
        "job",
        {
            "state": "QUEUED",
            "stage": "QUEUED",
            "started_at": now(),
            "finished_at": None,
            "user_id": user.id,
            "request_id": request_id,
            "branch": options.get("branch", "main"),
            "warnings": [],
            "errors": [],
            "stages": [],
            "execution": "PARTITIONED_SYNCHRONOUS" if inventory_input else "BOUNDED_SYNCHRONOUS",
            "source": "INVENTORY" if inventory_input else "FILES",
        },
    )
    db.commit()  # Repository + job survive a failed analysis; snapshot output remains atomic.
    job_id, organization_id, repository_id = job.id, user.organization_id, repo.id
    owned_token = job.data.get("worker_token")
    clock = _elapsed_clock or time.perf_counter
    stages, started = [], clock()
    output_started = False
    job.data = {
        **job.data,
        "started_at": now(),
        "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=job_time_budget(job) + 30)).isoformat(),
    }

    def stage(state):
        nonlocal output_started
        from backend.scheduling import ensure_current
        ensure_current(db, job, renew_seconds=job_time_budget(job))
        elapsed = round((clock() - started) * 1000, 2)
        if elapsed > job_time_budget(job) * 1000:
            raise TimeoutError("Analysis exceeded its configured execution time budget.")
        stages.append({"stage": state, "at": now(), "elapsed_ms": elapsed})
        job.data = {
            **job.data,
            "state": state,
            "stage": state,
            "stages": stages[:],
            "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=job_time_budget(job) + 30)).isoformat(),
        }
        # Publish native stages durably without committing partial graph output.
        if not output_started:
            db.commit()
        if state == "BUILDING_EVIDENCE":
            output_started = True
        log.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "job_id": job_id,
                    "organization_id": organization_id,
                    "repository_id": repository_id,
                    "snapshot_id": job.data.get("snapshot_id"),
                    "analyzer": "ProjectTrace native",
                    "duration_ms": elapsed,
                    "status": state,
                }
            )
        )

    try:
        stage("VALIDATING")
        content = files() if callable(files) else files
        snapshot = persist_analysis(db, user, repo, content, progress=stage, job_id=job.id, **options)
        state = snapshot.data["status"]
        output_started = True
        stage("FINALIZING")
        stage(state)
        job.data = {
            **job.data,
            "snapshot_id": snapshot.id,
            "state": state,
            "stage": state,
            "finished_at": now(),
            "duration_ms": round((clock() - started) * 1000, 2),
            "warnings": snapshot.data.get("warnings", []),
            "errors": [],
            "analyzer_results": snapshot.data.get("analyzer_results", {}),
            "engines": snapshot.data.get("engines", {}),
            "claim_extraction": snapshot.data.get("claim_extraction", {}),
        }
        db.commit()
        return snapshot, job
    except Exception as error:
        from backend.scheduling import JobCancelled, owns
        db.rollback()
        if not owns(db, job_id, owned_token):
            raise JobCancelled("Worker lease was replaced; this attempt cannot modify the job.") from None
        job = db.get(Record, job_id)
        job.data = {
            **{k: v for k, v in job.data.items() if k != "files"},
            "state": "CANCELLED" if isinstance(error, JobCancelled) else "FAILED",
            "stage": stages[-1]["stage"] if stages else "PARSING",
            "stages": stages,
            "finished_at": now(),
            "error_type": type(error).__name__,
            "errors": [
                "Analysis failed. Check archive validity and supported input limits; consult the request/job IDs for diagnostics."
            ],
            "duration_ms": round((clock() - started) * 1000, 2),
        }
        audit(
            db, user, "ANALYSIS_FAILED", job.id, {"error_type": type(error).__name__, "request_id": request_id}, repo.id
        )
        db.commit()
        log.error(
            json.dumps(
                {
                    "request_id": request_id,
                    "job_id": job_id,
                    "organization_id": organization_id,
                    "repository_id": repository_id,
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                }
            )
        )
        raise
