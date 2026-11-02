"""Normal expiry cannot relabel retained v2 history to permit an unsafe downgrade."""

import os
import subprocess
import sys
from datetime import datetime, timedelta

from sqlalchemy import func, select

from backend import generations
from backend.generation_models import GenerationChunk, GenerationContextPart, GenerationReceipt, PublishedGeneration
from tests.test_generation_context import context
from tests.test_repository_store import storage  # noqa: F401


def test_normal_expiry_keeps_v2_receipt_and_downgrade_fails_closed(storage, monkeypatch):  # noqa: F811
    generation, state = context(storage)
    generation.save("SNAPSHOT", state)
    db = generation.db
    receipt = db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT"))
    original = receipt.digest, receipt.dependency_digest, receipt.format_version, receipt.completed_at
    expires = generation.row.expires_at
    instant = (datetime.fromisoformat(expires) + timedelta(seconds=1)).isoformat()
    monkeypatch.setattr(generations, "now", lambda: instant)
    while generations.purge_expired_chunks(db):
        db.commit()
    db.commit()
    assert generation.row.expires_at == expires
    assert db.scalar(select(func.count()).select_from(GenerationChunk)) == 0
    assert db.scalar(select(func.count()).select_from(GenerationContextPart)) == 0
    assert (receipt.digest, receipt.dependency_digest, receipt.format_version, receipt.completed_at) == original
    assert receipt.format_version == 2
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0
    env = {**os.environ, "DATABASE_URL": str(db.get_bind().url), "APP_ENV": "demo"}
    subprocess.run([sys.executable, "-m", "alembic", "stamp", "0026"], env=env, capture_output=True, check=True)
    blocked = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0025"], env=env, capture_output=True, text=True
    )
    assert blocked.returncode != 0 and "Retained paged checkpoints" in blocked.stderr
    assert db.connection().exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0026"
    db.expire(receipt)
    assert (receipt.digest, receipt.dependency_digest, receipt.format_version, receipt.completed_at) == original
    assert db.connection().exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    assert not db.connection().exec_driver_sql("PRAGMA foreign_key_check").all()
