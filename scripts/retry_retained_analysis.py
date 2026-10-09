"""Explicit local operator retry; no account/session impersonation or provider I/O.

An operator with filesystem access may requeue an existing retained ZIP inventory.
The ordinary worker rechecks the original submitting user's tenant/grant/lease.
Private SCM/public provider jobs and production are outside this command's scope.
"""

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def retry(db, job_id):
    from backend.db import AnalysisInput, Record, Repository, User, now
    from backend.domain import audit
    from backend.queue import load_input
    from backend.repository_store import RepositoryFiles
    from backend.scheduling import register
    from backend.security import require_repo

    job = db.get(Record, job_id)
    if not job or job.kind != "job" or job.data.get("source") != "INVENTORY" or job.data.get("execution") != "LOCAL":
        raise ValueError("Only existing local retained inventory jobs can be retried.")
    if job.data.get("state") not in {"FAILED", "PARTIAL"} or job.data.get("retry_count", 0) >= 2:
        raise ValueError("Job is not retryable or its bounded retry limit was reached.")
    actor, repo, retained = db.get(User, job.data["user_id"]), db.get(Repository, job.repository_id), db.get(AnalysisInput, job.id)
    if not actor or not actor.enabled or not repo or actor.organization_id != job.organization_id or repo.organization_id != job.organization_id:
        raise ValueError("Original submitting account/repository authorization is unavailable.")
    require_repo(db, actor, repo.id)
    if not retained or (retained.organization_id, retained.repository_id) != (job.organization_id, job.repository_id):
        raise ValueError("Retained input scope is unavailable.")
    files = load_input(db, job)
    if not isinstance(files, RepositoryFiles):
        raise ValueError("Retained source is not a complete inventory.")
    previous = {k: job.data.get(k) for k in ("state", "stage", "started_at", "finished_at", "duration_ms",
                                           "snapshot_id", "error_type", "error_code", "error_detail", "stages", "performance", "completed_analysis")}
    register(db, job)
    job.data = {**job.data, "state": "QUEUED", "stage": "QUEUED", "started_at": None, "finished_at": None,
                "duration_ms": None, "snapshot_id": None, "error_type": None, "error_code": None, "error_detail": None,
                "stages": [], "performance": {}, "completed_analysis": None, "errors": [], "warnings": [], "queued_at": now(), "dispatch": "PENDING",
                "retry_count": job.data.get("retry_count", 0) + 1,
                "attempt_history": [*job.data.get("attempt_history", []), previous]}
    register(db, job)
    audit(db, SimpleNamespace(organization_id=actor.organization_id, email="LOCAL_FILESYSTEM_OPERATOR"),
          "OPERATOR_RETRIED_RETAINED_ANALYSIS", job.id,
          {"retained_inventory_id": files.inventory_id, "original_submitter_id": actor.id,
           "retry_count": job.data["retry_count"], "provider_refetched": False}, repo.id)
    db.commit()
    return {"job_id": job.id, "inventory_id": files.inventory_id, "state": "QUEUED", "retry_count": job.data["retry_count"]}


def main():
    if os.getenv("APP_ENV") == "production" or os.getenv("JOB_MODE") != "local":
        raise ValueError("This command requires an explicitly configured installed local runtime.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    import json

    from backend.db import Session
    with Session() as db:
        print(json.dumps(retry(db, args.job_id)))


if __name__ == "__main__":
    main()
