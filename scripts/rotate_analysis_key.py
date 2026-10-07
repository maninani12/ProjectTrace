"""Operator key rotation over encrypted blobs/retained inputs; default is a read-only count."""

import argparse
import json

from sqlalchemy import func, select

from backend.db import AnalysisInput, OIDCAttempt, Session, SourceBlob
from backend.queue import cipher
from backend.repository_store import BlobStore


def rotate(db, *, apply=False):
    store, encryption = BlobStore(), cipher()
    result = {
        "applied": apply,
        "source_blobs": db.scalar(select(func.count()).select_from(SourceBlob)),
        "retained_inputs": db.scalar(select(func.count()).select_from(AnalysisInput)),
        "pending_oidc_attempts": db.scalar(select(func.count()).select_from(OIDCAttempt)),
    }
    if not apply:
        return result
    # Quiesce producers/consumers first. Cipher's first key writes new ciphertext;
    # ANALYSIS_PREVIOUS_KEYS supplies old decrypt keys during the rotation window.
    for blob in db.scalars(select(SourceBlob)).yield_per(100):
        raw = store.read(blob.organization_id, blob.digest)
        if store.remote:
            store.remote.put(blob.organization_id, blob.digest, encryption.encrypt(raw))
        else:
            store._write_local(store.path(blob.organization_id, blob.digest), raw)
    for model, field in ((AnalysisInput, "ciphertext"), (OIDCAttempt, "verifier_ciphertext")):
        for row in db.scalars(select(model)).yield_per(100):
            setattr(row, field, encryption.encrypt(encryption.decrypt(getattr(row, field).encode())).decode())
    db.commit()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Re-encrypt after a verified backup and quiescing writers/workers."
    )
    arguments = parser.parse_args()
    with Session() as db:
        print(json.dumps(rotate(db, apply=arguments.apply)))
