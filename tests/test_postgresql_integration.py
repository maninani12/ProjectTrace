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


def test_postgresql_generation_recovery_scope_and_atomic_promotion(postgres, monkeypatch):
    from backend.generation_models import AnalysisGeneration, GenerationRecord, PublishedGeneration
    from backend.generations import Generation
    factory = initialize(postgres)
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    save = Generation.save

    def stop(self, stage, state):
        save(self, stage, state)
        if stage == "HISTORY":
            raise RuntimeError("PostgreSQL committed-stage interruption")

    monkeypatch.setattr(Generation, "save", stop)
    with factory() as db:
        user, repo = db.get(User, "a"), db.get(Repository, "a1")
        inventory = capture(db, user.organization_id, repo, [("app.py", b"def value():\n return 1\n"),
                            ("README.md", b"# Architecture\nBackend uses Python.\n")])
        db.commit()
        inventory_id = inventory.id
        with pytest.raises(RuntimeError):
            execute_analysis(db, user, repo, RepositoryFiles(db, "a", "a1", inventory_id))
        generation = db.scalar(select(AnalysisGeneration))
        job_id, generation_id = generation.job_id, generation.id
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
        private_id = db.scalar(select(GenerationRecord.record_id))
        with pytest.raises(IntegrityError):
            db.execute(GenerationRecord.__table__.update().where(GenerationRecord.record_id == private_id)
                       .values(organization_id="b", repository_id="b1"))
        db.rollback()
    monkeypatch.setattr(Generation, "save", save)
    with factory() as db:
        snapshot, job = execute_analysis(db, db.get(User, "a"), db.get(Repository, "a1"),
            RepositoryFiles(db, "a", "a1", inventory_id), job=db.get(Record, job_id))
        assert job.data["generation_receipts_reused"] == 7
        assert db.get(AnalysisGeneration, generation_id).state == "PUBLISHED"
        assert db.get(PublishedGeneration, ("a", "a1", "main")).generation_id == generation_id
        assert db.get(Record, snapshot.id)
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 1


def test_postgresql_connection_loss_before_promotion_leaves_private_recoverable_output(postgres, monkeypatch):
    from sqlalchemy.exc import DBAPIError

    from backend.generation_models import AnalysisGeneration
    from backend.generations import Generation
    factory = initialize(postgres)
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    promote = Generation.promote
    engine, _ = postgres

    def interrupt(self, snapshot):
        target_pid = self.db.scalar(text("SELECT pg_backend_pid()"))
        with engine.begin() as controller:
            assert controller.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": target_pid})
        promote(self, snapshot)

    monkeypatch.setattr(Generation, "promote", interrupt)
    with factory() as db:
        user, repo = db.get(User, "a"), db.get(Repository, "a1")
        inventory = capture(db, "a", repo, [("app.py", b"def identity(value):\n return value\n")])
        inventory_id = inventory.id
        db.commit()
        with pytest.raises(DBAPIError):
            execute_analysis(db, user, repo, RepositoryFiles(db, "a", "a1", inventory_id))
    monkeypatch.setattr(Generation, "promote", promote)
    with factory() as db:
        generation = db.scalar(select(AnalysisGeneration))
        assert generation.state == "VALIDATED"
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
        snapshot, job = execute_analysis(db, db.get(User, "a"), db.get(Repository, "a1"),
            RepositoryFiles(db, "a", "a1", inventory_id), job=db.get(Record, generation.job_id))
        assert job.data["generation_receipts_reused"] == 14
        assert snapshot.id == generation.snapshot_id
        assert db.get(AnalysisGeneration, generation.id).state == "PUBLISHED"


def test_postgresql_competing_generations_promote_one_branch_pointer(postgres, monkeypatch):
    from threading import Barrier

    from backend.generation_models import AnalysisGeneration, PublishedGeneration
    from backend.generations import Generation
    from backend.scheduling import JobCancelled

    factory = initialize(postgres)
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    inventories = []
    with factory() as db:
        for number in range(2):
            inventory = capture(db, "a", db.get(Repository, "a1"), [
                ("app.py", f"def value():\n return {number}\n".encode())])
            inventories.append(inventory.id)
        db.commit()
    barrier = Barrier(2)
    promote = Generation.promote

    def compete(self, snapshot):
        barrier.wait(timeout=60)
        promote(self, snapshot)

    monkeypatch.setattr(Generation, "promote", compete)

    def run(inventory_id):
        with factory() as db:
            try:
                snapshot, _ = execute_analysis(db, db.get(User, "a"), db.get(Repository, "a1"),
                    RepositoryFiles(db, "a", "a1", inventory_id))
                return snapshot.id
            except JobCancelled:
                return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(run, inventories))
    assert sum(result is not None for result in results) == 1
    with factory() as db:
        pointer = db.get(PublishedGeneration, ("a", "a1", "main"))
        winner = db.get(AnalysisGeneration, pointer.generation_id)
        assert pointer.revision == 1 and winner.state == "PUBLISHED"
        assert winner.snapshot_id == next(result for result in results if result)
        assert sorted(db.scalars(select(AnalysisGeneration.state))) == ["PUBLISHED", "VALIDATED"]
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 1


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
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0025"


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


def test_postgresql_private_publication_receipts_scope_and_fencing(postgres):
    from backend.db import PublicationUnit
    from backend.publication_units import Drafts, key
    from backend.scheduling import JobCancelled
    factory = initialize(postgres)
    with factory() as db:
        job = queued(db, "a", "a1")
        assert claim(db, job, 120)["state"] == "CLAIMED"

        def fenced():
            ensure_current(db, job, renew_seconds=120)

        drafts = Drafts(db, job.id, "a", "a1", "a" * 64, fenced)
        drafts.save("MANIFEST", "", {"file_count": 0})
        assert drafts.require("MANIFEST") == {"file_count": 0}
        with pytest.raises(IntegrityError, match="fk_publication_unit_job_scope"):
            db.execute(PublicationUnit.__table__.insert().values(job_id=job.id,unit_key="b"*64,
                organization_id="b",repository_id="b1",signature="a"*64,stage="MANIFEST",
                ciphertext="inert",result_digest="c"*64,expires_at="2099-01-01"))
        db.rollback()
        row = db.get(QueueEntry, job.id)
        row.worker_token = "replacement-token"
        db.commit()
        with pytest.raises(JobCancelled):
            drafts.save("EVIDENCE", "app.py", {}, ("MANIFEST", ""))
        db.rollback()
        assert db.get(PublicationUnit, (job.id, key("a" * 64, "EVIDENCE", "app.py"))) is None


def test_postgresql_record_tenant_scope_rejects_direct_sql(postgres):
    factory = initialize(postgres)
    with factory() as db:
        with pytest.raises(IntegrityError, match="fk_records_repository_scope"):
            db.execute(Record.__table__.insert().values(id="invalid-record-scope",organization_id="b",
                repository_id="a1",kind="claim",natural_key="invalid-record-scope",data={}))
        db.rollback()
        assert db.get(Record,"invalid-record-scope") is None
