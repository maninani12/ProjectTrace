"""Encrypted completed-computation receipts; publication remains a separate transaction."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from backend.db import AnalysisCheckpoint, AnalysisInput, Record, now


def scope(db, job_id, organization_id, repository_id):
    job = db.get(Record, job_id)
    if not job or (job.kind, job.organization_id, job.repository_id) != ("job", organization_id, repository_id):
        raise ValueError("Analysis checkpoint job scope is invalid.")
    return job


def load(db, job_id, organization_id, repository_id, signature):
    from backend.queue import cipher
    scope(db, job_id, organization_id, repository_id)
    row = db.get(AnalysisCheckpoint, job_id)
    if row is None:
        return None
    if (row.organization_id, row.repository_id) != (organization_id, repository_id):
        raise ValueError("Analysis checkpoint scope is invalid.")
    if row.expires_at <= now():
        return None
    if row.signature != signature:
        return None
    raw = cipher().decrypt(row.ciphertext.encode())
    if hashlib.sha256(raw).hexdigest() != row.result_digest:
        raise ValueError("Analysis checkpoint digest is invalid.")
    envelope = json.loads(raw)
    if (envelope.get("schema"), envelope.get("job_id"), envelope.get("organization_id"),
        envelope.get("repository_id"), envelope.get("signature")) != (
            "projecttrace-analysis-checkpoint-v1", job_id, organization_id, repository_id, signature):
        raise ValueError("Analysis checkpoint envelope is invalid.")
    return envelope["result"]


def save(db, job_id, organization_id, repository_id, signature, result, checkpoint):
    from backend.queue import cipher
    scope(db, job_id, organization_id, repository_id)
    maximum = int(os.getenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "64000000"))
    if not 1_000_000 <= maximum <= 256_000_000:
        raise ValueError("Analysis checkpoint size configuration is outside its bounded range.")
    envelope = {"schema": "projecttrace-analysis-checkpoint-v1", "job_id": job_id,
                "organization_id": organization_id, "repository_id": repository_id,
                "signature": signature, "result": {**result, "files": list(result["files"])}
                if "files" in result else result}
    raw = bytearray()
    for chunk in json.JSONEncoder(sort_keys=True).iterencode(envelope):
        encoded = chunk.encode()
        if len(raw) + len(encoded) > maximum:
            # Never truncate a receipt or buffer an entire oversized result.
            return False
        raw.extend(encoded)
    checkpoint()  # Fenced renewal locks the claim through receipt commit.
    retained = db.get(AnalysisInput, job_id)
    row = db.get(AnalysisCheckpoint, job_id)
    if row and (row.organization_id, row.repository_id) != (organization_id, repository_id):
        raise ValueError("Analysis checkpoint scope is invalid.")
    if row is None:
        row = AnalysisCheckpoint(job_id=job_id, organization_id=organization_id, repository_id=repository_id)
        db.add(row)
    row.signature = signature
    row.expires_at = min(retained.expires_at if retained else "9999", 
                         (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat())
    row.result_digest = hashlib.sha256(raw).hexdigest()
    row.ciphertext = cipher().encrypt(bytes(raw)).decode()
    db.commit()
    return True
