"""Durable Celery dispatch with tenant quotas and encrypted, expiring input."""

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select

from analyzers.engine import MAX_TOTAL_BYTES
from backend.db import AnalysisInput, Organization, Record, now
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
    return Fernet(value.encode() if isinstance(value, str) else value)


def dispatch(db, job):
    from workers.tasks import celery

    task = "projecttrace.advisories" if job.data.get("type") == "ADVISORIES" else (
        "projecttrace.analyze" if job.data.get("source") in {"ZIP", "FILES"} else "projecttrace.github_delivery"
    )
    try:
        celery.send_task(task, args=[job.id], task_id=job.id, retry=False)
        job.data = {**job.data, "dispatch": "SENT"}
    except Exception:
        job.data = {**job.data, "dispatch": "PENDING_RETRY", "warnings": ["Queue dispatch unavailable; retry this retained job."]}
    db.commit()


def check_capacity(db, user, repo):
    # PostgreSQL serializes admission within a tenant. SQLite is the local adapter.
    db.scalar(select(Organization).where(Organization.id == user.organization_id).with_for_update())
    jobs = list(db.scalars(select(Record).where(Record.organization_id == user.organization_id, Record.kind == "job")))
    active = [j for j in jobs if j.data.get("state") not in TERMINAL]
    if len(active) >= 10 or sum(j.repository_id == repo.id for j in active) >= 2:
        raise ValueError("Analysis queue quota reached; finish or cancel existing jobs before submitting more input.")


def enqueue_analysis(db, user, repo, content, *, source="FILES", request_id=None, **options):
    check_capacity(db, user, repo)
    if source == "ZIP":
        if len(content) > MAX_TOTAL_BYTES:
            raise ValueError("Archive exceeds the bounded input size.")
        value = {"archive": base64.b64encode(content).decode()}
    else:
        from analyzers.engine import validate_files

        value = {"files": validate_files(content)}
    job = add(db, user.organization_id, repo.id, "job", {
        "state": "QUEUED", "stage": "QUEUED", "queued_at": now(), "started_at": None,
        "finished_at": None, "user_id": user.id, "request_id": request_id,
        "source": source, "execution": "CELERY", "options": options,
        "warnings": [], "errors": [], "stages": [], "dispatch": "PENDING",
    })
    db.add(AnalysisInput(
        job_id=job.id, organization_id=user.organization_id, repository_id=repo.id,
        ciphertext=cipher().encrypt(json.dumps(value).encode()).decode(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
    ))
    audit(db, user, "ANALYSIS_QUEUED", job.id, {"source": source}, repo.id)
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
    if job.data.get("source") == "ZIP":
        from analyzers.engine import read_zip

        return read_zip(base64.b64decode(content["archive"], validate=True))
    return content["files"]


def purge_expired_inputs(db):
    expired = list(db.scalars(select(AnalysisInput).where(AnalysisInput.expires_at <= now())))
    for retained in expired:
        job = db.get(Record, retained.job_id)
        if job and job.data.get("state") not in TERMINAL:
            job.data = {**job.data, "state": "FAILED", "finished_at": now(),
                        "errors": ["Retained input expired; upload a fresh snapshot."]}
        db.delete(retained)
    db.commit()
    return len(expired)
