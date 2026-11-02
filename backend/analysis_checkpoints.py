"""Encrypted completed-computation receipts; publication remains a separate transaction."""
import hashlib
import json
import os

from backend.db import AnalysisCheckpoint, Record, now


def scope(db, job_id, organization_id, repository_id):
    job = db.get(Record, job_id)
    if not job or (job.kind, job.organization_id, job.repository_id) != ("job", organization_id, repository_id):
        raise ValueError("Analysis checkpoint job scope is invalid.")
    return job


def load(db, job_id, organization_id, repository_id, signature, *, checkpoint=lambda: None, own=None):
    from backend.checkpoint_pages import SCHEMA
    from backend.checkpoint_pages import load as load_pages
    from backend.queue import cipher
    job = scope(db, job_id, organization_id, repository_id)
    maximum = budget()
    from sqlalchemy import func, select
    size = db.scalar(select(func.length(AnalysisCheckpoint.ciphertext)).where(AnalysisCheckpoint.job_id == job_id))
    if size is not None and size > (maximum * 4 // 3) + 4096:
        raise ValueError("Analysis checkpoint exceeds its bounded storage envelope.")
    row = db.get(AnalysisCheckpoint, job_id, populate_existing=True)
    if row is None:
        return None
    if (row.organization_id, row.repository_id) != (organization_id, repository_id):
        raise ValueError("Analysis checkpoint scope is invalid.")
    if row.expires_at <= now():
        return None
    if row.signature != signature:
        return None
    raw = cipher().decrypt(row.ciphertext.encode())
    if len(raw) > maximum:
        raise ValueError("Analysis checkpoint manifest exceeds its byte budget.")
    if hashlib.sha256(raw).hexdigest() != row.result_digest:
        raise ValueError("Analysis checkpoint digest is invalid.")
    envelope = json.loads(raw)
    if envelope.get("schema") == SCHEMA:
        if row.format_version != 2:
            raise ValueError("Analysis checkpoint format identity is invalid.")
        if envelope.get("expires_at") != row.expires_at:
            raise ValueError("Analysis checkpoint retention identity is invalid.")
        return load_pages(db, job, signature, envelope, maximum, checkpoint, own, row.result_digest)
    if row.format_version != 1:
        raise ValueError("Analysis checkpoint format identity is invalid.")
    if (envelope.get("schema"), envelope.get("job_id"), envelope.get("organization_id"),
        envelope.get("repository_id"), envelope.get("signature")) != (
            "projecttrace-analysis-checkpoint-v1", job_id, organization_id, repository_id, signature):
        raise ValueError("Analysis checkpoint envelope is invalid.")
    return envelope["result"]


def budget():
    maximum = int(os.getenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "64000000"))
    if not 1_000_000 <= maximum <= 256_000_000:
        raise ValueError("Analysis checkpoint size configuration is outside its bounded range.")
    return maximum


def save(db, job_id, organization_id, repository_id, signature, result, checkpoint, *, check=None):
    from backend.checkpoint_pages import save as save_pages
    job = scope(db, job_id, organization_id, repository_id)
    return save_pages(db, job, signature, result, budget(), checkpoint, check or checkpoint)


def discard(db, job):
    from sqlalchemy import delete

    from backend.checkpoint_pages import discard as discard_pages
    discard_pages(db, job)
    db.execute(delete(AnalysisCheckpoint).where(AnalysisCheckpoint.job_id == job.id,
        AnalysisCheckpoint.organization_id == job.organization_id,
        AnalysisCheckpoint.repository_id == job.repository_id))


def purge_expired(db, *, _guard=None):
    from sqlalchemy import delete, select, tuple_

    from backend.db import AnalysisCheckpointPart
    from backend.retention import ExpiryGuard
    guard = _guard or ExpiryGuard(db, now())
    # Select metadata only, never up to 1,000 manifest/page ciphertexts.
    rows = db.execute(select(AnalysisCheckpoint.job_id, AnalysisCheckpoint.organization_id,
        AnalysisCheckpoint.repository_id).where(AnalysisCheckpoint.expires_at <= guard.instant,
        ~guard.active(AnalysisCheckpoint)).limit(1000)).all()
    for job_id, organization_id, repository_id in rows:
        if guard.allows(job_id, organization_id, repository_id):
            db.execute(delete(AnalysisCheckpoint).where(AnalysisCheckpoint.job_id == job_id,
                AnalysisCheckpoint.organization_id == organization_id, AnalysisCheckpoint.repository_id == repository_id,
                AnalysisCheckpoint.expires_at <= guard.instant))
    rows = db.execute(select(AnalysisCheckpointPart.job_id, AnalysisCheckpointPart.attempt,
        AnalysisCheckpointPart.ordinal, AnalysisCheckpointPart.organization_id, AnalysisCheckpointPart.repository_id)
        .where(AnalysisCheckpointPart.expires_at <= guard.instant, ~guard.active(AnalysisCheckpointPart)).limit(1000)).all()
    expired = [(job_id, attempt, ordinal) for job_id, attempt, ordinal, org, repo in rows
               if guard.allows(job_id, org, repo)]
    if expired:
        db.execute(delete(AnalysisCheckpointPart).where(tuple_(AnalysisCheckpointPart.job_id,
            AnalysisCheckpointPart.attempt, AnalysisCheckpointPart.ordinal).in_(expired)))
