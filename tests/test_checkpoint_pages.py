"""Bounded complete checkpoints, authenticated admission and independent replay."""
import hashlib
import json
import os
import random
import subprocess
import sys
import zlib

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from analyzers.observation_store import EncryptedRows
from backend import checkpoint_pages
from backend.analysis_checkpoints import load, save
from backend.db import AnalysisCheckpoint, AnalysisCheckpointPart, Record
from backend.domain import add
from backend.queue import cipher
from backend.scheduling import JobCancelled
from tests.test_repository_store import storage  # noqa: F401


def owned_job(storage):  # noqa: F811
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {"state": "VERIFYING"})
    db.commit()
    return db, job


def persist(db, job, value, **options):
    return save(db, job.id, job.organization_id, job.repository_id, "a" * 64, value,
                options.pop("fence", lambda: None), **options)


def recover(db, job, **options):
    return load(db, job.id, job.organization_id, job.repository_id, "a" * 64, **options)


def logical_hash(value):
    digest = hashlib.sha256()
    for part in json.JSONEncoder(sort_keys=True).iterencode(value):
        digest.update(part.encode())
    return digest.hexdigest()


def test_paged_complete_output_aliases_and_fresh_session_recovery(storage, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "1000000")
    db, job = owned_job(storage)
    metrics = [{"path": f"owned/{i}.py", "line": 1, "end_line": 10,
                "body_hash": str(i), "cyclomatic": i % 7, "name": "owned", "detail": "owned " * 100}
               for i in range(3000)]
    value = {"quality_metrics": metrics, "code_quality": {"metrics": metrics, "symbols": [{"name": "owned"}]},
             "claims": [{"status": "VERIFIED"}], "findings": [{"rule": "owned"}],
             "graph": {"edges": [{"source": "a", "target": "b"}]}, "files": ["owned.py"]}
    before = logical_hash(value)
    assert len(json.dumps(value)) > 1_000_000
    assert persist(db, job, value)
    size = db.scalar(select(func.sum(func.length(AnalysisCheckpointPart.ciphertext))))
    root = db.get(AnalysisCheckpoint, job.id)
    assert size + len(root.ciphertext) <= 1_000_000
    assert "owned " not in root.ciphertext
    factory, job_id = sessionmaker(db.get_bind(), expire_on_commit=False), job.id
    db.close()
    with factory() as resumed:
        job = resumed.get(Record, job_id)
        actual = recover(resumed, job)
        assert isinstance(actual["quality_metrics"], EncryptedRows)
        assert actual["quality_metrics"] is actual["code_quality"]["metrics"]
        assert logical_hash(actual) == before
        metric = actual["quality_metrics"][1]
        metric["new_code"] = True
        actual["quality_metrics"]._replace(1, metric)
        assert actual["code_quality"]["metrics"][1]["new_code"] is True
        assert actual["quality_metrics"].containing("owned/1.py", 5) == metric
        owner = actual["quality_metrics"].owner
        assert b"owned " not in owner.rows.connection.serialize()
        from backend.analysis_checkpoints import discard
        discard(resumed, job)
        resumed.commit()
        assert logical_hash(actual)  # Detached replay survives durable cleanup.
        owner.close()


def test_incompressible_exhaustion_preserves_previous_complete_receipt(storage, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "1000000")
    db, job = owned_job(storage)
    assert persist(db, job, {"old": [1, 2, 3]})
    old_digest = db.get(AnalysisCheckpoint, job.id).result_digest
    rng = random.Random(52)
    values = [rng.randbytes(1800).hex() for _ in range(600)]
    assert not persist(db, job, {"large": values})
    assert db.get(AnalysisCheckpoint, job.id).result_digest == old_digest
    assert recover(db, job) == {"old": [1, 2, 3]}
    assert db.scalar(select(func.count(func.distinct(AnalysisCheckpointPart.attempt)))) == 1


@pytest.mark.parametrize("damage", ["missing", "swap", "ciphertext", "identity", "extra", "expired", "compression"])
def test_page_tampering_never_exposes_partial_output(storage, damage):  # noqa: F811
    db, job = owned_job(storage)
    assert persist(db, job, {"rows": [{"text": "owned " * 1000} for _ in range(110)]})
    parts = list(db.scalars(select(AnalysisCheckpointPart).order_by(AnalysisCheckpointPart.ordinal)))
    assert len(parts) >= 2
    first = parts[0]
    if damage == "missing":
        db.delete(first)
    elif damage == "swap":
        first.ciphertext, parts[1].ciphertext = parts[1].ciphertext, first.ciphertext
        first.digest, parts[1].digest = parts[1].digest, first.digest
    elif damage == "ciphertext":
        first.ciphertext = first.ciphertext[:-4] + "xxxx"
    elif damage == "expired":
        first.expires_at = "2000-01-01"
    elif damage == "extra":
        db.add(AnalysisCheckpointPart(job_id=job.id, attempt=first.attempt, ordinal=999,
            organization_id=job.organization_id, repository_id=job.repository_id,
            ciphertext=first.ciphertext, digest=first.digest, expires_at=first.expires_at))
    else:
        packed = cipher().decrypt(first.ciphertext.encode())
        header, _, data = packed.partition(b"\n")
        if damage == "identity":
            context = json.loads(header)
            context[2] = "other-tenant"
            header = json.dumps(context).encode()
        else:
            data = zlib.compress(b"x" * (checkpoint_pages.PAGE_BYTES + 1))
        packed = header + b"\n" + data
        first.ciphertext, first.digest = cipher().encrypt(packed).decode(), hashlib.sha256(packed).hexdigest()
    db.commit()
    with pytest.raises((ValueError, InvalidToken)):
        recover(db, job)


def test_cancelled_page_write_reclaims_staging_without_admission(storage):  # noqa: F811
    db, job = owned_job(storage)
    def checked():
        if db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)):
            raise JobCancelled("Owned cancellation")
    with pytest.raises(JobCancelled):
        persist(db, job, {"rows": ["owned " * 1000] * 110}, check=checked)
    assert db.get(AnalysisCheckpoint, job.id) is None
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)) == 0


def test_cancelled_replay_closes_private_store_and_keeps_durable_receipt(storage, monkeypatch):  # noqa: F811
    db, job = owned_job(storage)
    assert persist(db, job, {"rows": ["owned"] * 600})
    closed, checks, close = [], [], checkpoint_pages.Replay.close
    def cleanup(owner):
        close(owner)
        closed.append(owner.rows.closed)
    def checked():
        checks.append(True)
        if len(checks) == 4:
            raise JobCancelled("Owned replay cancellation")
    monkeypatch.setattr(checkpoint_pages.Replay, "close", cleanup)
    with pytest.raises(JobCancelled):
        recover(db, job, checkpoint=checked)
    assert closed == [True]
    assert len(recover(db, job)["rows"]) == 600


def test_legacy_v1_envelope_remains_readable(storage):  # noqa: F811
    db, job = owned_job(storage)
    result = {"rows": [{"literal": {"schema": "not-a-reference", "$rows": 12}}]}
    raw = json.dumps({"schema": "projecttrace-analysis-checkpoint-v1", "job_id": job.id,
        "organization_id": job.organization_id, "repository_id": job.repository_id,
        "signature": "a" * 64, "result": result}).encode()
    db.add(AnalysisCheckpoint(job_id=job.id, organization_id=job.organization_id,
        repository_id=job.repository_id, signature="a" * 64, result_digest=hashlib.sha256(raw).hexdigest(),
        ciphertext=cipher().encrypt(raw).decode(), expires_at="2099-01-01"))
    db.commit()
    assert recover(db, job) == result


def test_replay_ordinal_substitution_is_rejected(storage):  # noqa: F811
    db, job = owned_job(storage)
    assert persist(db, job, {"a": [{"path": "a.py"}], "b": [{"path": "b.py"}]})
    result = recover(db, job)
    owner = result["a"].owner
    owner.rows.connection.execute("UPDATE positions SET ordinal=1 WHERE collection=0")
    with pytest.raises(ValueError, match="encrypted row"):
        result["a"][0]
    owner.close()


def test_lost_manifest_commit_acknowledgement_keeps_recoverable_pages(storage, monkeypatch):  # noqa: F811
    db, job = owned_job(storage)
    commit, raised = db.commit, []
    def lost():
        admitting = db.get(AnalysisCheckpoint, job.id) is not None
        commit()
        if admitting and not raised:
            raised.append(True)
            raise RuntimeError("Owned lost commit acknowledgement")
    monkeypatch.setattr(db, "commit", lost)
    with pytest.raises(RuntimeError, match="lost commit"):
        persist(db, job, {"rows": ["complete"] * 600})
    monkeypatch.setattr(db, "commit", commit)
    assert list(recover(db, job)["rows"]) == ["complete"] * 600


def test_actual_writer_exit_leaves_old_receipt_and_retry_reclaims_orphans(storage):  # noqa: F811
    db, job = owned_job(storage)
    assert persist(db, job, {"old": ["complete"]})
    code = """
import os,sys
from backend.db import make_engine,Record,AnalysisCheckpointPart
from sqlalchemy.orm import sessionmaker
from backend.analysis_checkpoints import save
engine=make_engine(sys.argv[1])
with sessionmaker(engine,expire_on_commit=False)() as db:
 job=db.get(Record,sys.argv[2]);commit=db.commit
 def interrupted():
  page=any(isinstance(row,AnalysisCheckpointPart) for row in db.new)
  commit()
  if page:os._exit(73)
 db.commit=interrupted
 save(db,job.id,job.organization_id,job.repository_id,'a'*64,{'rows':['owned '*1000]*110},lambda:None)
"""
    exited = subprocess.run([sys.executable, "-c", code, str(db.get_bind().url), job.id],
                            env=os.environ.copy(), capture_output=True, timeout=30)
    assert exited.returncode == 73, exited.stderr.decode()
    assert recover(db, job) == {"old": ["complete"]}
    assert db.scalar(select(func.count(func.distinct(AnalysisCheckpointPart.attempt)))) == 2
    assert persist(db, job, {"rows": ["new complete"] * 100})
    assert list(recover(db, job)["rows"]) == ["new complete"] * 100
    assert db.scalar(select(func.count(func.distinct(AnalysisCheckpointPart.attempt)))) == 1


def test_page_foreign_key_and_authenticated_retention_cannot_cross_scope(storage):  # noqa: F811
    from sqlalchemy.exc import IntegrityError
    db, job = owned_job(storage)
    with pytest.raises(IntegrityError):
        db.execute(AnalysisCheckpointPart.__table__.insert().values(job_id=job.id, attempt="owned", ordinal=0,
            organization_id="other", repository_id=job.repository_id, ciphertext="owned", digest="0"*64, expires_at="2099"))
    db.rollback()
    assert persist(db, job, {"rows": ["owned"]})
    db.get(AnalysisCheckpoint, job.id).expires_at = "2099"
    db.commit()
    with pytest.raises(ValueError, match="retention"):
        recover(db, job)


@pytest.mark.parametrize("damage", ["row_count", "page_count", "alias", "duplicate_key", "schema"])
def test_authenticated_manifest_still_validates_complete_inventory(storage, damage):  # noqa: F811
    db, job = owned_job(storage)
    rows = [{"value": "owned"}]
    assert persist(db, job, {"a": rows, "b": rows})
    receipt = db.get(AnalysisCheckpoint, job.id)
    manifest = json.loads(cipher().decrypt(receipt.ciphertext.encode()))
    if damage == "row_count":
        manifest["root"][1][0][1][3] += 1
    elif damage == "page_count":
        manifest["pages"] += 1
    elif damage == "alias":
        manifest["root"][1][1][1][3] += 1
    elif damage == "duplicate_key":
        manifest["root"][1].append(manifest["root"][1][0])
    else:
        manifest["schema"] = "unsupported-owned-format"
    raw = json.dumps(manifest).encode()
    receipt.ciphertext, receipt.result_digest = cipher().encrypt(raw).decode(), hashlib.sha256(raw).hexdigest()
    db.commit()
    with pytest.raises(ValueError):
        recover(db, job)


def test_literals_unicode_empty_and_cross_page_rows_remain_complete(storage):  # noqa: F811
    db, job = owned_job(storage)
    value = {"literal": {"schema": checkpoint_pages.SCHEMA, "$ref": [1, 2]}, "empty": [],
             "rows": ["owned\n\U0001f600\u2028\x00" * 45000, {"$rows": "literal user value"}]}
    expected = logical_hash(value)
    assert persist(db, job, value)
    assert logical_hash(recover(db, job)) == expected


def test_replay_expiry_and_explicit_cleanup_reclaim_private_pages(storage):  # noqa: F811
    from backend.queue import purge_expired_inputs
    db, job = owned_job(storage)
    assert persist(db, job, {"rows": ["owned"]})
    db.get(AnalysisCheckpoint, job.id).expires_at = "2000-01-01"
    for part in db.scalars(select(AnalysisCheckpointPart)):
        part.expires_at = "2000-01-01"
    db.commit()
    purge_expired_inputs(db)
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)) == 0
    assert persist(db, job, {"rows": ["new"]})
    from backend.analysis_checkpoints import discard
    discard(db, job)
    db.commit()
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)) == 0
    assert db.get(Record, job.id) is not None  # Historical/quota attribution is retained.


def test_budget_failure_still_blocks_publication_in_real_job(storage, monkeypatch):  # noqa: F811
    from backend.generation_models import PublishedGeneration
    from backend.intake_errors import IntakeError
    from backend.jobs import execute_analysis
    from tests.test_repository_store import captured
    db, user, repo = storage
    files = captured(storage, {"owned.py": "pass\n"})
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "1000000")
    monkeypatch.setattr("backend.partitioned_analysis.analyze_inventory", lambda *_a, **_k: {"value": "x" * 1000001})
    with pytest.raises(IntakeError, match="durable checkpoint"):
        execute_analysis(db, user, repo, files)
    job = db.scalar(select(Record).where(Record.kind == "job"))
    assert job.data["error_code"] == "GLOBAL_CHECKPOINT_BUDGET"
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)) == 0


def test_checkpoint_budget_failure_keeps_inventory_for_subsequent_valid_analysis(storage, monkeypatch):  # noqa: F811
    from backend import partitioned_analysis
    from backend.db import Repository, User
    from backend.generation_models import AnalysisGeneration, PublishedGeneration
    from backend.intake_errors import IntakeError
    from backend.jobs import execute_analysis
    from backend.repository_store import RepositoryFiles
    from tests.test_repository_store import captured

    db, user, repo = storage
    files = captured(storage, {"owned.py": "pass\n"})
    inventory_id = files.inventory_id
    actor_id, organization_id, repository_id = user.id, user.organization_id, repo.id
    analyze = partitioned_analysis.analyze_inventory
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "1000000")

    def oversized(*_args, **kwargs):
        for stage in ("ANALYZING", "EXTRACTING_CLAIMS", "VERIFYING"):
            kwargs["progress"](stage)
        return {"value": "x" * 1_000_001}

    monkeypatch.setattr(partitioned_analysis, "analyze_inventory", oversized)

    with pytest.raises(IntakeError, match="durable checkpoint"):
        execute_analysis(db, user, repo, files)

    failed_job = db.scalar(select(Record).where(Record.kind == "job").order_by(Record.created_at.desc()))
    failed_job_id = failed_job.id
    assert failed_job.data["state"] == "FAILED"
    assert failed_job.data["stage"] == "VERIFYING"
    assert failed_job.data["error_code"] == "GLOBAL_CHECKPOINT_BUDGET"
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    assert db.scalar(select(func.count()).select_from(AnalysisGeneration).where(
        AnalysisGeneration.job_id == failed_job_id)) == 0
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0
    assert db.get(AnalysisCheckpoint, failed_job_id) is None
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart).where(
        AnalysisCheckpointPart.job_id == failed_job_id)) == 0
    assert files["owned.py"] == "pass\n"

    monkeypatch.setattr(partitioned_analysis, "analyze_inventory", analyze)
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    db.close()
    with factory() as retry_db:
        actor = retry_db.get(User, actor_id)
        repository = retry_db.get(Repository, repository_id)
        retry_files = RepositoryFiles(retry_db, organization_id, repository_id, inventory_id)
        snapshot, successful_job = execute_analysis(retry_db, actor, repository, retry_files)
        assert successful_job.id != failed_job_id
        assert successful_job.data["state"] in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}
        assert retry_db.get(Record, failed_job_id).data["state"] == "FAILED"
        assert retry_db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 1
        assert retry_db.scalar(select(func.count()).select_from(AnalysisGeneration).where(
            AnalysisGeneration.job_id == successful_job.id, AnalysisGeneration.state == "PUBLISHED")) == 1
        assert retry_db.scalar(select(func.count()).select_from(PublishedGeneration)) == 1
        assert retry_db.get(AnalysisCheckpoint, successful_job.id) is None
        assert retry_db.scalar(select(func.count()).select_from(AnalysisCheckpointPart).where(
            AnalysisCheckpointPart.job_id.in_([failed_job_id, successful_job.id]))) == 0
        connection = retry_db.connection()
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_root_receipt_substitution_between_jobs_is_rejected(storage):  # noqa: F811
    db, first = owned_job(storage)
    _, second = owned_job(storage)
    assert persist(db, first, {"rows": ["first private value"]})
    assert persist(db, second, {"rows": ["second private value"]})
    a, b = db.get(AnalysisCheckpoint, first.id), db.get(AnalysisCheckpoint, second.id)
    b.ciphertext, b.result_digest, b.expires_at = a.ciphertext, a.result_digest, a.expires_at
    db.commit()
    with pytest.raises(ValueError, match="identity"):
        recover(db, second)


def test_expired_orphan_reclamation_is_batched(storage):  # noqa: F811
    from backend.analysis_checkpoints import purge_expired
    db, job = owned_job(storage)
    db.execute(AnalysisCheckpointPart.__table__.insert(), [dict(job_id=job.id, attempt="owned-expired",
        ordinal=i, organization_id=job.organization_id, repository_id=job.repository_id,
        ciphertext="owned expired opaque value", digest="0"*64, expires_at="2000-01-01") for i in range(1200)])
    db.commit()
    purge_expired(db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)) == 200
    purge_expired(db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)) == 0


def test_interleaved_tokenless_writer_cannot_admit_reaped_pages(storage, monkeypatch):  # noqa: F811
    db, job = owned_job(storage)
    factory, job_id = sessionmaker(db.get_bind(), expire_on_commit=False), job.id
    commit, interleaved = db.commit, []
    def after_page_commit():
        page = any(isinstance(row, AnalysisCheckpointPart) for row in db.new)
        commit()
        if page and not interleaved:
            interleaved.append(True)
            with factory() as other:
                newer_job = other.get(Record, job_id)
                assert persist(other, newer_job, {"rows": ["complete winning writer"]})
    monkeypatch.setattr(db, "commit", after_page_commit)
    with pytest.raises(ValueError, match="staged page inventory"):
        persist(db, job, {"rows": ["older staging writer"]})
    monkeypatch.setattr(db, "commit", commit)
    assert list(recover(db, job)["rows"]) == ["complete winning writer"]


def test_paged_checkpoint_retains_existing_key_rotation_contract(storage, monkeypatch):  # noqa: F811
    from cryptography.fernet import Fernet
    db, job = owned_job(storage)
    assert persist(db, job, {"rows": ["owned complete value"]})
    previous = os.environ["ANALYSIS_INPUT_KEY"]
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ANALYSIS_PREVIOUS_KEYS", json.dumps([previous]))
    assert list(recover(db, job)["rows"]) == ["owned complete value"]
    monkeypatch.setenv("ANALYSIS_PREVIOUS_KEYS", "[]")
    with pytest.raises(InvalidToken):
        recover(db, job)


def test_real_cancellation_writer_is_not_blocked_by_checkpoint_serialization(storage, monkeypatch):  # noqa: F811
    from sqlalchemy import update

    from backend.db import QueueEntry
    from backend.jobs import execute_analysis
    from backend.scheduling import claim, register
    from tests.test_repository_store import captured
    db, user, repo = storage
    files = captured(storage, {"owned.py": "pass\n"})
    job = add(db, user.organization_id, repo.id, "job", {"state": "QUEUED", "source": "INVENTORY",
        "execution": "CELERY", "user_id": user.id})
    register(db, job)
    db.commit()
    claim(db, job, 1800)
    cancelled = []
    def compute(db, *_a, progress, **_k):
        progress("VERIFYING")
        current = progress.check_current
        def checked():
            current()
            if not cancelled and db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)):
                with sessionmaker(db.get_bind())() as other:
                    other.connection().exec_driver_sql("PRAGMA busy_timeout=100")
                    other.execute(update(QueueEntry).where(QueueEntry.job_id == job.id).values(cancel_requested=True))
                    other.commit()
                cancelled.append(True)
                current()
        progress.check_current = checked
        return {"rows": ["owned " * 200] * 900}
    monkeypatch.setattr("backend.partitioned_analysis.analyze_inventory", compute)
    with pytest.raises(JobCancelled):
        execute_analysis(db, user, repo, files, job=job)
    assert cancelled and job.data["state"] == "CANCELLED"
    assert db.get(AnalysisCheckpoint, job.id) is None
    assert db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)) == 0
