"""Owned tests for privacy-safe checkpoint rejection attribution."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from analyzers.sanitization import metadata
from backend import checkpoint_pages
from backend.checkpoint_diagnostics import count_v1_envelope_bytes, v1_size_diagnostic
from backend.db import AnalysisCheckpoint, AnalysisCheckpointPart, QueueEntry, Record
from backend.scheduling import JobCancelled, claim, ensure_current, register
from tests.test_checkpoint_pages import owned_job, persist, recover
from tests.test_repository_store import storage  # noqa: F401

LIMIT = 64_000_000
V1_IDENTITY = {"job_id": "owned-job", "organization_id": "owned-tenant", "repository_id": "owned-repo", "signature": "owned"}
MARKER = "OWNED_NONPUBLIC_FIXTURE_VALUE"


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_historical_raw_v1_boundary_matches_exact_utf8_count(delta):
    # Fixed-width chunks avoid a second whole-envelope allocation. The base
    # includes file-list normalization, Unicode escapes and structural framing.
    result = {"files": ("a.py", "nested/b.py"), "rows": ["x" * 64_000] * 999 + [""],
              "unicode": 'café 雪 "\\\n'}
    framing = count_v1_envelope_bytes(result, **V1_IDENTITY)
    result["rows"][-1] = "x" * (LIMIT + delta - framing)
    assert count_v1_envelope_bytes(result, **V1_IDENTITY) == LIMIT + delta
    assert v1_size_diagnostic(result, **V1_IDENTITY)["over_budget"] is (delta > 0)


@pytest.mark.parametrize(("site", "value"), [
    ("ROW_ENCODING", {"rows": [{"nested": ["雪", MARKER + "x" * 1_000_000]}]}),
    ("MANIFEST_ENCODING", {MARKER: "x" * 1_000_000}),
])
def test_encoder_records_only_a_raw_prefix_lower_bound(storage, monkeypatch, site, value):  # noqa: F811
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "1000000")
    db, job = owned_job(storage)
    rejection = {}
    assert not persist(db, job, value, rejection=rejection)
    assert rejection["site"] == site
    assert rejection["measurement"] == "RAW_UTF8_PREFIX_BYTES"
    assert rejection["site_limit_bytes"] == 1_000_000 - 4096
    assert rejection["measured_bytes"] > rejection["site_limit_bytes"]
    assert rejection["measurement_exact"] is False
    assert rejection["logical_v1_bytes"] is None and rejection["logical_v1_size_reason"] == "V1_ENVELOPE_NOT_SERIALIZED"
    assert rejection["cleanup"] == "ATTEMPT_REMOVED"
    assert MARKER not in json.dumps(rejection)
    assert len(json.dumps(rejection)) < 1024
    assert db.get(AnalysisCheckpoint, job.id) is None
    assert not db.scalar(select(func.count()).select_from(AnalysisCheckpointPart))


def test_manifest_aggregate_admission_is_inclusive(storage):  # noqa: F811
    from datetime import datetime, timezone
    from unittest.mock import patch

    result = {"files": [f"owned/{i:05}.py" for i in range(1500)], "findings": [{"value": "雪"}]}
    with patch.object(checkpoint_pages, "datetime", wraps=datetime) as clock:
        clock.now.return_value = datetime(2026, 11, 7, 1, 2, 3, 456789, tzinfo=timezone.utc)
        db, first = owned_job(storage)
        assert persist(db, first, result)
        page_bytes = db.scalar(select(func.sum(func.length(AnalysisCheckpointPart.ciphertext)))
                               .where(AnalysisCheckpointPart.job_id == first.id))
        root_bytes = len(db.get(AnalysisCheckpoint, first.id).ciphertext)
        attempted = page_bytes + root_bytes
        for delta in (1, 0, -1):
            db, job = owned_job(storage)
            rejection = {}
            accepted = checkpoint_pages.save(db, job, "a" * 64, result, attempted + delta, lambda: None,
                                             lambda: None, rejection=rejection)
            assert accepted is (delta >= 0)
            if accepted:
                assert not rejection
                replay = recover(db, job)
                assert list(replay["files"]) == result["files"]
                replay["files"].owner.close()
            else:
                assert rejection["site"] == "MANIFEST_ADMISSION"
                assert rejection["measurement"] == "ENCRYPTED_AGGREGATE_BYTES"
                assert rejection["measured_bytes"] == attempted
                assert rejection["measurement_exact"] is True
                assert rejection["retained_page_bytes"] == page_bytes
                assert rejection["proposed_ciphertext_bytes"] == root_bytes
                assert rejection["active_manifest_bytes"] == 0
                assert rejection["component_raw_bytes"] < root_bytes
                assert rejection["cleanup"] == "ATTEMPT_REMOVED"
                assert db.get(AnalysisCheckpoint, job.id) is None
                assert not db.scalar(select(func.count()).select_from(AnalysisCheckpointPart)
                                     .where(AnalysisCheckpointPart.job_id == job.id))
        assert db.connection().exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert not db.connection().exec_driver_sql("PRAGMA foreign_key_check").all()


@pytest.mark.parametrize(("error_type", "fail"), [
    (TypeError, lambda: object()),
    (ValueError, lambda: metadata([0] * 1_000_000)),
    (TimeoutError, lambda: (_ for _ in ()).throw(TimeoutError("Owned deadline"))),
    (OperationalError, lambda: (_ for _ in ()).throw(OperationalError(None, None, RuntimeError("Owned database failure")))),
])
def test_non_budget_failures_preserve_classification_and_reclaim_staged_pages(storage, error_type, fail):  # noqa: F811
    db, job = owned_job(storage)

    class OwnedRows(list):
        def __iter__(self):
            yield "x" * checkpoint_pages.PAGE_BYTES
            yield fail()

    rejection = {}
    with pytest.raises(error_type):
        persist(db, job, {"rows": OwnedRows([None, None])}, rejection=rejection)
    assert not rejection
    assert db.get(AnalysisCheckpoint, job.id) is None
    assert not db.scalar(select(func.count()).select_from(AnalysisCheckpointPart))


def test_concurrent_checkpoint_with_replaced_lease_preserves_winner(storage):  # noqa: F811
    db, job = owned_job(storage)
    job.data = {**job.data, "state": "QUEUED", "source": "INVENTORY"}
    register(db, job)
    db.commit()
    claim(db, job, 1800)
    job_id = job.id
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)

    def replacement():
        with factory() as other:
            replacement_job = other.get(Record, job_id)
            other.execute(update(QueueEntry).where(QueueEntry.job_id == job_id).values(worker_token="owned-replacement"))
            replacement_job.data = {**replacement_job.data, "worker_token": "owned-replacement"}
            other.commit()
            def fence():
                ensure_current(other, replacement_job)
            assert persist(other, replacement_job, {"rows": ["winner"]}, fence=fence)

    class OwnedRows(list):
        def __iter__(self):
            yield "x" * checkpoint_pages.PAGE_BYTES
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(replacement).result(timeout=15)
            yield "stale"

    rejection = {}
    with pytest.raises(JobCancelled):
        persist(db, job, {"rows": OwnedRows([None, None])}, fence=lambda: ensure_current(db, job), rejection=rejection)
    assert not rejection
    assert list(recover(db, job)["rows"]) == ["winner"]
    assert db.scalar(select(func.count(func.distinct(AnalysisCheckpointPart.attempt)))) == 1
