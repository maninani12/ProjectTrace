"""Durable local analysis lifecycle. No raw source or exception text is logged."""

import json
import logging
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


def execute_analysis(db, user, repo, files, *, request_id=None, job=None, **options):
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
            "execution": "BOUNDED_SYNCHRONOUS",
        },
    )
    db.commit()  # Repository + job survive a failed analysis; snapshot output remains atomic.
    job_id, organization_id, repository_id = job.id, user.organization_id, repo.id
    stages, started = [], time.perf_counter()
    output_started = False
    job.data = {**job.data, "started_at": now(), "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=125)).isoformat()}

    def stage(state):
        nonlocal output_started
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        stages.append({"stage": state, "at": now(), "elapsed_ms": elapsed})
        job.data = {**job.data, "state": state, "stage": state, "stages": stages[:]}
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
        snapshot = persist_analysis(db, user, repo, content, progress=stage, **options)
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
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "warnings": snapshot.data.get("warnings", []),
            "errors": [],
            "analyzer_results": snapshot.data.get("analyzer_results", {}),
            "engines": snapshot.data.get("engines", {}),
            "claim_extraction": snapshot.data.get("claim_extraction", {}),
        }
        snapshot.data = {**snapshot.data, "job_id": job.id}
        db.commit()
        return snapshot, job
    except Exception as error:
        db.rollback()
        job = db.get(Record, job_id)
        job.data = {
            **{k: v for k, v in job.data.items() if k != "files"},
            "state": "FAILED",
            "stage": stages[-1]["stage"] if stages else "PARSING",
            "stages": stages,
            "finished_at": now(),
            "error_type": type(error).__name__,
            "errors": [
                "Analysis failed. Check archive validity and supported input limits; consult the request/job IDs for diagnostics."
            ],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
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
