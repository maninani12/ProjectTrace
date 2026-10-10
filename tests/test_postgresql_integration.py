"""Opt-in real PostgreSQL checks in unique schemas; never use application schemas.

Set PROJECTTRACE_TEST_POSTGRES_URL to an operator-owned disposable database.
The same tests run on CI/staging; no imported source is executed.
"""

import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.db import (
    AnalysisInput,
    Base,
    FindingOccurrence,
    Grant,
    Organization,
    QueueEntry,
    Record,
    Repository,
    SourceInventoryFile,
    User,
    make_engine,
)
from backend.domain import add, audit
from backend.jobs import execute_analysis
from backend.queue import enqueue_analysis
from backend.repository_store import RepositoryFiles, capture
from backend.scheduling import claim, ensure_current, owns, recover_expired, register, release
from backend.trust import integrity


@pytest.fixture
def postgres(tmp_path, monkeypatch):
    value = os.getenv("PROJECTTRACE_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("Requires an explicit disposable PostgreSQL test database.")
    base_url = make_url(value)
    assert base_url.drivername.startswith("postgresql")
    schema = "pt_test_" + uuid.uuid4().hex
    admin = make_engine(base_url.render_as_string(hide_password=False))
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = base_url.update_query_dict({"options": "-csearch_path=" + schema})
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("JOB_MODE", "sync")
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("SOURCE_BLOB_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("SOURCE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ANALYSIS_KEY_FILE", str(tmp_path / "analysis.key"))
    engine = make_engine(url.render_as_string(hide_password=False))
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        engine.dispose()
        # Only the fresh UUID schema created above belongs to this test.
        assert schema.startswith("pt_test_") and len(schema) == 40
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def initialize(postgres):
    engine, factory = postgres
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add_all([Organization(id=org, name=org) for org in ("a", "b")])
        db.flush()
        for org in ("a", "b"):
            db.add(
                User(
                    id=org,
                    organization_id=org,
                    email=org + "@test.invalid",
                    password_hash="test-only",
                    role="ORG_OWNER",
                )
            )
            for number in (1, 2):
                db.add(
                    Repository(
                        id=org + str(number),
                        organization_id=org,
                        name=org + str(number),
                        system="Fixture",
                        component="Fixture",
                        owner="Fixture",
                    )
                )
        db.flush()
        db.add_all([Grant(user_id=org, repository_id=org + str(number)) for org in ("a", "b") for number in (1, 2)])
        db.commit()
    return factory


def queued(db, org, repo):
    job = add(db, org, repo, "job", {"state": "QUEUED", "source": "GITHUB", "execution": "CELERY"})
    register(db, job)
    db.commit()
    return job


def test_postgresql_migrations_preserve_prior_records(postgres):
    engine, _factory = postgres
    for revision in ("0005", "head", "0005", "head"):
        command = "downgrade" if revision == "0005" and inspect(engine).has_table("quality_analyses") else "upgrade"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", command, revision], capture_output=True, env=os.environ.copy()
        )
        assert result.returncode == 0, result.stderr.decode()[-4000:]
        with engine.begin() as db:
            if not db.scalar(text("SELECT COUNT(*) FROM organizations")):
                db.execute(text("INSERT INTO organizations VALUES ('preserved', 'Preserved')"))
                db.execute(
                    text(
                        "INSERT INTO records (id, organization_id, repository_id, kind, natural_key, data, created_at, version) VALUES ('preserved', 'preserved', NULL, 'claim', 'preserved', :data, '2026-10-09', 1)"
                    ),
                    {"data": '{"text":"Preserved claim"}'},
                )
            assert db.scalar(text("SELECT data->>'text' FROM records WHERE id='preserved'")) == "Preserved claim"
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0020"


def test_postgresql_concurrent_duplicate_claims_and_tenant_fairness(postgres):
    factory = initialize(postgres)
    with factory() as db:
        a1, a2, b1 = queued(db, "a", "a1"), queued(db, "a", "a2"), queued(db, "b", "b1")
        identifier = a1.id

    def attempt(_index):
        with factory() as db:
            return claim(db, db.get(Record, identifier), 120)["state"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        states = list(pool.map(attempt, range(4)))
    assert states.count("CLAIMED") == 1 and states.count("ALREADY_RUNNING") == 3
    with factory() as db:
        assert claim(db, db.get(Record, a2.id), 120)["state"] == "DEFERRED"
        assert claim(db, db.get(Record, b1.id), 120)["state"] == "CLAIMED"
        assert claim(db, db.get(Record, a2.id), 120)["state"] == "CLAIMED"
        assert db.scalar(select(func.count()).select_from(QueueEntry).where(QueueEntry.state == "RUNNING")) == 3


def test_postgresql_worker_lease_recovery_and_stale_release(postgres):
    factory = initialize(postgres)
    with factory() as db:
        job = queued(db, "a", "a1")
        token = claim(db, job, 120)["token"]
        job.data = {**job.data, "stage": "BUILDING_EVIDENCE", "performance": {"cache_hits": 14}}
        db.get(QueueEntry, job.id).lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
        assert recover_expired(db) == [job.id]
        db.refresh(job)
        assert job.data["attempt_history"][-1]["stage"] == "BUILDING_EVIDENCE"
        assert job.data["attempt_history"][-1]["performance"] == {"cache_hits": 14}
        new_token = claim(db, job, 120)["token"]
        assert token != new_token and not owns(db, job.id, token)
        release(db, job, token=token)
        db.commit()
        assert owns(db, job.id, new_token)
        ensure_current(db, job)


def test_postgresql_claim_refreshes_a_job_changed_by_dispatch(postgres):
    factory = initialize(postgres)
    with factory() as db:
        job_id = queued(db, "a", "a1").id
    with factory() as worker, factory() as dispatcher:
        stale = worker.get(Record, job_id)
        old_version = stale.version
        dispatched = dispatcher.get(Record, job_id)
        dispatched.data = {**dispatched.data, "dispatch": "SENT", "dispatch_receipt": "retained-metadata"}
        dispatcher.commit()
        assert dispatched.version > old_version
        assert claim(worker, stale, 120)["state"] == "CLAIMED"
        assert stale.data["dispatch_receipt"] == "retained-metadata"
        assert owns(worker, job_id, stale.data["worker_token"])


def test_postgresql_tenant_references_and_inventory_foreign_keys(postgres):
    factory = initialize(postgres)
    with factory() as db:
        db.add(Record(id="cross", organization_id="a", repository_id="b1", kind="claim", natural_key="cross", data={}))
        with pytest.raises(ValueError, match="Cross-tenant"):
            db.flush()
        db.rollback()
        inventory = capture(db, "a", db.get(Repository, "a1"), [("app.py", b"pass\n")])
        db.commit()
        db.add(
            SourceInventoryFile(
                inventory_id=inventory.id,
                path="cross.py",
                organization_id="b",
                repository_id="b1",
                digest=None,
                component="Fixture",
                data={},
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_postgresql_atomic_publication_cache_reuse_and_audit(postgres):
    factory = initialize(postgres)
    files = {
        f"module{index}.py": f"def work{index}(value):\n    return value + {index}\n".encode() for index in range(20)
    }
    files.update(
        {
            "README.md": b"Backend uses FastAPI.\n",
            "app.py": b"from fastapi import FastAPI\napp=FastAPI()\ndef unsafe(value):\n    return eval(value)\n",
        }
    )
    with factory() as db:
        user, repo = db.get(User, "a"), db.get(Repository, "a1")
        inventory = capture(db, "a", repo, files.items())
        db.commit()
        snapshots = []
        for index in range(2):
            snapshot, job = execute_analysis(
                db, user, repo, RepositoryFiles(db, "a", repo.id, inventory.id), branch="validation-" + str(index)
            )
            assert job.data["state"] in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}
            assert snapshot.data["analysis_coverage"]["summary"]["files_discovered"] == len(files)
            snapshots.append(snapshot)
        assert job.data["performance"]["counters"]["parser_cache_hits"] == len(files)
        findings = list(
            db.scalars(
                select(Record).where(
                    Record.kind == "finding", Record.data["scope"]["snapshot_id"].as_string() == snapshots[-1].id
                )
            )
        )
        assert findings and len({row.data["fingerprint"] for row in findings}) == len(findings)
        assert db.scalar(
            select(func.count()).select_from(FindingOccurrence).where(FindingOccurrence.snapshot_id == snapshots[-1].id)
        ) == len(findings)
        assert integrity(db, "a")["state"] == "VERIFIED"
        assert (
            db.scalar(
                select(func.count()).select_from(Record).where(Record.kind == "snapshot", Record.organization_id == "b")
            )
            == 0
        )


def test_postgresql_idempotent_retry_preserves_snapshot_provenance(postgres):
    factory = initialize(postgres)
    with factory() as db:
        user, repo = db.get(User, "a"), db.get(Repository, "a1")
        files = {"app.py": "def work(value):\n    return value\n"}
        snapshot, original = execute_analysis(db, user, repo, files)
        db.refresh(snapshot)  # Compare the canonical stored JSON, including list encodings.
        captured, version = dict(snapshot.data), snapshot.version
        reused, later = execute_analysis(db, user, repo, files)
        db.refresh(snapshot)
        assert reused.id == snapshot.id and later.id != original.id
        assert later.data["snapshot_id"] == original.data["snapshot_id"] == snapshot.id
        assert snapshot.data == captured and snapshot.version == version
        assert snapshot.data["job_id"] == original.id


def test_postgresql_failure_rolls_back_output_and_keeps_input(postgres, monkeypatch):
    import backend.jobs

    factory = initialize(postgres)
    with factory() as db:
        user, repo = db.get(User, "a"), db.get(Repository, "a1")
        job = enqueue_analysis(db, user, repo, {"app.py": "pass\n"})
        db.commit()
        assert claim(db, job, 120)["state"] == "CLAIMED"

        def interrupt(db, user, repo, *_args, **_kwargs):
            add(db, user.organization_id, repo.id, "claim", {"text": "Unpublished"})
            raise RuntimeError("Controlled publication interruption")

        monkeypatch.setattr(backend.jobs, "persist_analysis", interrupt)
        with pytest.raises(RuntimeError):
            execute_analysis(db, user, repo, {"app.py": "pass\n"}, job=job)
        assert db.get(Record, job.id).data["state"] == "FAILED"
        assert db.get(AnalysisInput, job.id) is not None
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind.in_(["claim", "snapshot"]))) == 0
        audit(db, user, "RECOVERY_TEST_VERIFIED", job.id, {"partial_output_visible": False}, repo.id)
        db.commit()
        assert integrity(db, "a")["state"] == "VERIFIED"
