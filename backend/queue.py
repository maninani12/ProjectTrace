"""Durable Celery dispatch with tenant quotas and encrypted, expiring input."""

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy import select

from analyzers.engine import MAX_TOTAL_BYTES
from backend.db import AnalysisInput, Record, now
from backend.domain import add, audit
from backend.jobs import TERMINAL


def cipher():
    value = os.getenv("ANALYSIS_INPUT_KEY")
    if not value:
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("Production queued input requires ANALYSIS_INPUT_KEY.")
        path = Path(os.getenv("ANALYSIS_KEY_FILE", "data/analysis-input.key"))
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            try:
                with path.open("xb") as stream:
                    stream.write(Fernet.generate_key())
                path.chmod(0o600)
            except FileExistsError:
                pass
        value = path.read_bytes().strip()
    current = Fernet(value.encode() if isinstance(value, str) else value)
    previous = json.loads(os.getenv("ANALYSIS_PREVIOUS_KEYS", "[]"))
    if not isinstance(previous, list) or len(previous) > 3 or any(not isinstance(key, str) for key in previous):
        raise ValueError("Previous analysis keys must be a bounded operator-owned list.")
    return MultiFernet([current, *[Fernet(key.encode()) for key in previous]]) if previous else current


def dispatch(db, job):
    from fastapi import HTTPException

    from backend.governance import job_principal
    from backend.scheduling import register
    from workers.tasks import celery

    if job.data.get("state") == "QUEUED":
        try:
            job_principal(db,job)
        except HTTPException:
            # Retain encrypted source, inventory and every completed checkpoint.
            # A blocked dispatch is never reported as completed analysis.
            from backend.db import QueueEntry
            job.data={**job.data,"state":"FAILED","dispatch":"POLICY_BLOCKED","finished_at":now(),
                "error_code":"JOB_AUTHORIZATION_REVOKED","errors":["Job access policy changed or its authorized identity is unavailable. An administrator must review access before retry."]}
            entry=db.get(QueueEntry,job.id)
            if entry:
                entry.state="FAILED"
            db.commit()
            return
        register(db, job)
        db.commit()

    if job.data.get("execution") == "LOCAL":
        from backend.local_jobs import notify
        try:
            notify()
        except RuntimeError:
            db.refresh(job)
            job.data = {**job.data, "dispatch": "PENDING_RETRY", "warnings": ["Local runner unavailable; restart ProjectTrace."]}
            db.commit()
        # The fenced claim records SENT. Never race the awakened worker with an
        # API-side write of a stale version of its stage/token/input metadata.
        return

    if job.data.get("type") == "ADVISORIES":
        task = "projecttrace.advisories"
    elif job.data.get("source") == "INVENTORY":
        task = "projecttrace.analyze_inventory"
    elif job.data.get("source") in {"ZIP", "FILES"}:
        task = "projecttrace.analyze"
    elif job.data.get("source") == "PUBLIC_GITHUB":
        task = "projecttrace.public_github"
    else:
        task = "projecttrace.github_delivery"
    try:
        celery.send_task(task, args=[job.id], task_id=job.id, retry=False)
        status, warning = "SENT", None
    except Exception:
        status, warning = "PENDING_RETRY", "Queue dispatch unavailable; retry this retained job."
    from sqlalchemy.orm.exc import StaleDataError
    for _ in range(3):
        db.refresh(job)
        job.data = {**job.data, "dispatch": status, "last_dispatched_at": now(),
                    **({"warnings": [warning]} if warning else {})}
        try:
            db.commit()
            return
        except StaleDataError:
            db.rollback()
    # Delivery already happened; do not resend or overwrite a newer worker.
    db.refresh(job)


def check_capacity(db, user, repo, *, source=None, existing_job=None):
    from backend.admin_quotas import enforce_quotas
    from backend.governance import authorize_job
    from backend.scheduling import check_capacity as admit
    user=authorize_job(db,user,repo,source)
    from backend.db import QueueEntry
    entry=db.get(QueueEntry,existing_job.id) if existing_job else None
    if entry and entry.state in {"QUEUED","RUNNING"}:
        from backend.scheduling import lock
        lock(db)
    else:
        admit(db, user.organization_id, repo.id)
    enforce_quotas(db,user,repo,existing_job=existing_job)


def enqueue_analysis(db, user, repo, content, *, source="FILES", request_id=None, import_receipt=None, **options):
    check_capacity(db, user, repo, source=source)
    if source == "INVENTORY":
        from backend.repository_store import RepositoryFiles

        if not isinstance(content, RepositoryFiles) or (content.organization_id, content.repository_id) != (
            user.organization_id,
            repo.id,
        ):
            raise ValueError("Inventory queue input scope is invalid.")
        value = {"inventory_id": content.inventory_id}
    elif source == "ZIP":
        if len(content) > MAX_TOTAL_BYTES:
            raise ValueError("Archive exceeds the bounded input size.")
        value = {"archive": base64.b64encode(content).decode()}
    else:
        from analyzers.engine import validate_files

        clean = validate_files(content, keep_excluded=True)
        value = {"files": clean, "intake": getattr(clean, "intake", [])}
    job = add(
        db,
        user.organization_id,
        repo.id,
        "job",
        {
            "state": "QUEUED",
            "stage": "QUEUED",
            "queued_at": now(),
            "started_at": None,
            "finished_at": None,
            "user_id": user.id,
            "request_id": request_id,
            "source": source,
            "execution": "LOCAL" if os.getenv("JOB_MODE") == "local" else "CELERY",
            "options": options,
            "warnings": [],
            "errors": [],
            "stages": [],
            "dispatch": "PENDING",
        },
    )
    db.add(
        AnalysisInput(
            job_id=job.id,
            organization_id=user.organization_id,
            repository_id=repo.id,
            ciphertext=cipher().encrypt(json.dumps(value).encode()).decode(),
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
        )
    )
    audit(db, user, "ANALYSIS_QUEUED", job.id, {"source": source}, repo.id)
    from backend.scheduling import register
    register(db, job)
    if import_receipt:
        import_receipt.data = {**import_receipt.data, "state": "QUEUED", "job_id": job.id}
    db.commit()
    dispatch(db, job)
    return job


def load_input(db, job):
    value = db.get(AnalysisInput, job.id)
    if not value or value.organization_id != job.organization_id or value.repository_id != job.repository_id:
        raise ValueError("Worker input scope is invalid or unavailable.")
    if datetime.fromisoformat(value.expires_at) <= datetime.now(timezone.utc):
        db.delete(value)
        db.commit()
        raise ValueError("Retained input has expired; upload a fresh snapshot.")
    content = json.loads(cipher().decrypt(value.ciphertext.encode()))
    if job.data.get("source") == "INVENTORY":
        from backend.repository_store import RepositoryFiles

        return RepositoryFiles(db, job.organization_id, job.repository_id, content["inventory_id"])
    if job.data.get("source") == "ZIP":
        from analyzers.engine import read_zip

        return read_zip(base64.b64decode(content["archive"], validate=True), keep_excluded=True)
    from analyzers.source_input import SourceFiles

    return SourceFiles(content["files"], intake=content.get("intake", []))


def purge_expired_inputs(db):
    expired = list(db.scalars(select(AnalysisInput).where(AnalysisInput.expires_at <= now())))
    for retained in expired:
        job = db.get(Record, retained.job_id)
        if job and job.data.get("state") not in TERMINAL:
            job.data = {
                **job.data,
                "state": "FAILED",
                "finished_at": now(),
                "errors": ["Retained input expired; upload a fresh snapshot."],
            }
        db.delete(retained)
    db.commit()
    return len(expired)
