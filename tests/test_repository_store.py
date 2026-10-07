import io
import json
import zipfile

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import event, func, select
from sqlalchemy.orm import sessionmaker

from analyzers.engine import analyze
from backend.db import (
    Base,
    Organization,
    ParserArtifact,
    Record,
    Repository,
    SnapshotInventory,
    SourceBlob,
    User,
    make_engine,
)
from backend.domain import persist_analysis
from backend.encrypted_archive import EncryptedArchive
from backend.partitioned_analysis import analyze_inventory
from backend.repository_store import BlobStore, RepositoryFiles, archive_items, capture, limits


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_BLOB_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("SOURCE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())
    engine = make_engine("sqlite:///" + str(tmp_path / "source.db"))
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as db:
        db.add_all([Organization(id="tenant", name="Tenant"), Organization(id="other", name="Other")])
        db.flush()
        user = User(
            id="user", organization_id="tenant", email="cas@example.com", password_hash="unused", role="ORG_OWNER"
        )
        repo = Repository(
            id="repo",
            organization_id="tenant",
            name="Repository",
            system="System",
            component="Root",
            owner="Owner",
            provider="LOCAL",
        )
        db.add_all([user, repo])
        db.commit()
        yield db, user, repo
    engine.dispose()


def captured(storage, sources):
    db, user, repo = storage
    inventory = capture(
        db, user.organization_id, repo, ((p, t.encode() if isinstance(t, str) else t) for p, t in sources.items())
    )
    return RepositoryFiles(db, user.organization_id, repo.id, inventory.id)


def test_tenant_encryption_dedup_metadata_and_filtered_access(storage):
    db, user, repo = storage
    text = "secret customer data, not executable"
    files = captured(
        storage,
        {
            "src/app.py": text,
            "src/app.go": text,
            "bad.py": b"\xff",
            "huge.bin": {"bytes": 512001, "state": "SKIPPED_SIZE_LIMIT"},
            "service/package.json": '{"name":"service-a"}',
            "service/app.py": "pass\n",
        },
    )
    native = files.view(native_only=True)
    assert "src/app.go" in files and "src/app.go" not in native
    with pytest.raises(KeyError):
        native["src/app.go"]
    assert files["src/app.py"] == text
    assert files.component_for("service/app.py") == "service-a"
    assert files.metadata_for("bad.py")["physical_lines"] is None
    assert db.scalar(select(func.count()).select_from(SourceBlob)) == 4
    path = BlobStore().path(user.organization_id, files.hash_for("src/app.py"))
    assert text.encode() not in path.read_bytes()
    assert BlobStore().path("other", files.hash_for("src/app.py")) != path
    with pytest.raises(ValueError, match="authorized repository"):
        RepositoryFiles(db, "other", repo.id, files.inventory_id)
    path.write_bytes(b"tampered")
    with pytest.raises(Exception):
        files["src/app.py"]


def test_encrypted_seekable_upload_roundtrip_and_cleanup(storage):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as writer:
        writer.writestr("app.py", "def identity(value):\n    return value\n")
    payload = archive.getvalue()
    spool = EncryptedArchive(100000)
    root = spool.root
    with spool:
        for start in range(0, len(payload), 13):
            spool.append(payload[start : start + 13])
        assert b"def identity" not in b"".join(p.read_bytes() for p in spool.paths)
        assert dict(archive_items(spool))["app.py"].startswith(b"def identity")
        spool.seek(-9, io.SEEK_END)
        assert spool.read() == payload[-9:]
        with pytest.raises(ValueError):
            spool.append(b"x" * 100001)
    assert not root.exists()


def test_capture_refuses_traversal_duplicates_and_quotas(storage):
    db, user, repo = storage
    for items in [[("../escape.py", b"pass")], [("a.py", b"pass"), ("./a.py", b"pass")]]:
        with pytest.raises(ValueError):
            capture(db, user.organization_id, repo, items)
        db.rollback()
    with pytest.raises(ValueError, match="file inventory quota"):
        capture(db, user.organization_id, repo, [("a.py", b"pass"), ("b.py", b"pass")], quota={**limits(), "files": 1})


def test_partitioned_global_claims_and_network_policy_match_legacy(storage):
    sources = {
        "a/README.md": "# Architecture\nBackend uses FastAPI.\n",
        "z/app.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "a/deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: app}\nspec: {template: {spec: {containers: [{name: app, image: image:v1}]}}}\n",
        "z/policy.yaml": "apiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nmetadata: {name: policy}\nspec: {podSelector: {}, policyTypes: [Ingress]}\n",
    }
    sources.update({f"m/file{i:03}.py": f"VALUE_{i} = {i}\n" for i in range(101)})
    profile = {"infrastructure": {"require_network_policy": True}}
    files = captured(storage, sources)
    result = analyze_inventory(storage[0], files, profile=profile)
    legacy = analyze(sources, profile=profile)
    assert result["source_storage"]["partitions"] == 2
    assert result["source_storage"]["max_partition_files"] <= 100
    assert [(c["claim_key"], c["status"]) for c in result["claims"]] == [
        (c["claim_key"], c["status"]) for c in legacy["claims"]
    ]
    assert not any(f["rule"] == "PT-IAC-026" for f in result["findings"])
    assert {(f["rule"], f["path"], f["line"]) for f in result["findings"]} == {
        (f["rule"], f["path"], f["line"]) for f in legacy["findings"]
    }
    assert result["analysis_coverage"]["summary"] == legacy["analysis_coverage"]["summary"]


def test_incremental_one_file_and_quality_profile_reuse(storage):
    db = storage[0]
    sources = {f"app{i}.py": f"VALUE_{i} = {i}\n" for i in range(105)}
    first = captured(storage, sources)
    initial = analyze_inventory(db, first)
    assert initial["reused_files"] == 0
    changed = captured(storage, {**sources, "app1.py": "VALUE_1 = 900\n"})
    head = analyze_inventory(db, changed)
    assert head["source_storage"]["parser_cache_hits"] == 104
    assert head["source_storage"]["parser_cache_misses"] == 1
    profile = {"quality": {"rules": {"PT-QUALITY-013": {"threshold": 1}}}}
    revised = analyze_inventory(db, changed, profile=profile)
    assert revised["source_storage"]["parser_cache_hits"] == 105
    assert db.scalar(select(func.count()).select_from(ParserArtifact)) == 106
    assert all("source" not in row.data for row in db.scalars(select(ParserArtifact)))


def test_snapshot_references_encrypted_evidence_and_preserves_explicit_base(storage):
    db, user, repo = storage
    files = captured(storage, {"app.py": "def run(value):\n    return value\n"})
    base = persist_analysis(db, user, repo, files)
    db.commit()
    head = persist_analysis(
        db, user, repo, captured(storage, {"app.py": "def run(value):\n    return eval(value)\n"}), base_id=base.id
    )
    db.commit()
    assert head.data["base_id"] == base.id
    assert head.data["changed_files"] == ["app.py"]
    assert not head.data["analysis_cache"]
    assert db.get(SnapshotInventory, head.id).inventory_id == head.data["source_inventory_id"]
    evidence = list(db.scalars(select(Record).where(Record.kind == "evidence")))
    assert len(evidence) == 2 and all("source" not in row.data for row in evidence)
    assert b"return eval" in BlobStore().read(user.organization_id, evidence[-1].data["source_blob_digest"])
    assert "source_blob_digest" in json.dumps(evidence[-1].data)


def test_evidence_reference_reuse_preserves_redaction_and_source_integrity(storage, monkeypatch):
    db, user, repo = storage
    sources = {
        "safe.py": "VALUE = 1\n",
        "private.py": 'password = "private-fixture-password-012345"\n',
        "empty.py": "",
        "private-key.txt": "-----BEGIN PRIVATE KEY-----\nfixture-only-material\n-----END PRIVATE KEY-----\n",
    }
    files = captured(storage, sources)
    original_read = BlobStore.read
    reads = []

    def track(self, organization, digest):
        reads.append(digest)
        return original_read(self, organization, digest)

    # Parser artifacts are populated first, so the assertion isolates persistence.
    analyze_inventory(db, files)
    monkeypatch.setattr(BlobStore, "read", track)
    snapshot = persist_analysis(db, user, repo, files)
    db.commit()
    evidence = {r.data["path"]: r.data for r in db.scalars(select(Record).where(Record.kind == "evidence"))}
    assert evidence["safe.py"]["source_blob_digest"] == files.hash_for("safe.py")
    assert reads.count(files.hash_for("safe.py")) == 1
    assert evidence["private.py"]["source_blob_digest"] != files.hash_for("private.py")
    masked = original_read(files.store, user.organization_id, evidence["private.py"]["source_blob_digest"])
    assert b"private-fixture-password" not in masked and b"REDACTED" in masked
    assert snapshot.data["changed_lines"]["empty.py"] == []
    assert snapshot.data["changed_lines"]["private-key.txt"] == [(1, 1)]

    corrupted = captured(storage, {"corrupted.py": "VALUE = 2\n"})
    analyze_inventory(db, corrupted)
    files.store.path(user.organization_id, corrupted.hash_for("corrupted.py")).write_bytes(b"invalid ciphertext")
    with pytest.raises(ValueError, match="integrity check"):
        persist_analysis(db, user, repo, corrupted)
    db.rollback()


def test_unchanged_observations_require_no_source_decryption(storage, monkeypatch):
    files = captured(storage, {f"app{i}.py": f"VALUE_{i} = {i}\n" for i in range(105)})
    analyze_inventory(storage[0], files)
    reads = []
    original = BlobStore.read

    def track(self, tenant, digest):
        reads.append(digest)
        return original(self, tenant, digest)

    monkeypatch.setattr(BlobStore, "read", track)
    result = analyze_inventory(storage[0], files)
    assert result["reused_files"] == 105
    assert reads == []


def test_syntax_failure_is_retried_even_with_legacy_cached_artifact(storage, monkeypatch):
    from analyzers import engine
    from analyzers.infrastructure_deep import config
    from backend.partitioned_analysis import artifact_key

    sources = {"broken.py": "def broken(:\n    pass\n"}
    legacy = analyze(sources)
    cached = legacy["analysis_cache"]["broken.py"]
    assert any(f["rule"] == "PT-PARSE-001" for f in cached["findings"])
    files = captured(storage, sources)
    db = storage[0]
    # Previously persisted invalid observations must also fail cache admission.
    db.add(
        ParserArtifact(
            id=artifact_key(files, "broken.py", config(None)),
            organization_id=files.organization_id,
            content_hash=files.hash_for("broken.py"),
            language=".py",
            parser_version=engine.PARSER_SIGNATURE,
            rule_version=engine.VERSION,
            data=cached,
        )
    )
    db.flush()
    calls = []
    original = engine.python_analysis

    def track(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "python_analysis", track)
    for result in [analyze(sources, legacy["analysis_cache"]), analyze_inventory(db, files)]:
        assert result["reused_files"] == 0
        assert result["analysis_coverage"]["summary"]["source_files_parsed"] == 0
    assert calls == ["broken.py", "broken.py"]


def test_new_syntax_failure_is_not_persisted_as_reusable_artifact(storage):
    files = captured(storage, {"broken.py": "def broken(:\n    pass\n"})
    result = analyze_inventory(storage[0], files)
    assert result["source_storage"]["parser_cache_misses"] == 1
    assert storage[0].scalar(select(func.count()).select_from(ParserArtifact)) == 0


def test_job_link_is_captured_before_snapshot_insert_without_late_metadata_rewrite(storage):
    from backend.jobs import execute_analysis

    db, user, repo = storage
    files = captured(storage, {"app.py": "def transform(value):\n    return value + 1\n"})
    inserted, updated = [], []

    def inserted_snapshot(_mapper, _connection, row):
        if row.kind == "snapshot":
            inserted.append(row.data.get("job_id"))
            assert "quality_metrics" not in row.data and "analysis_coverage" not in row.data

    def updated_snapshot(_mapper, _connection, row):
        if row.kind == "snapshot":
            updated.append(row.id)

    event.listen(Record, "after_insert", inserted_snapshot)
    event.listen(Record, "after_update", updated_snapshot)
    try:
        snapshot, job = execute_analysis(db, user, repo, files)
        assert inserted == [job.id]
        # One captured-result update is allowed; attaching the job must not
        # serialize the complete repository-sized JSON a second time at commit.
        assert updated == [snapshot.id]
        assert snapshot.data["job_id"] == job.id and job.data["snapshot_id"] == snapshot.id
        assert snapshot.data["analysis_coverage"]["summary"]["source_files_parsed"] == 1
        assert snapshot.data["quality_metrics"] and snapshot.data["hashes"]["app.py"] == files.hash_for("app.py")
        original_id = snapshot.id
        repeated, repeated_job = execute_analysis(db, user, repo, files)
        assert repeated.id == original_id
        assert repeated.data["job_id"] == repeated_job.id
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 1
    finally:
        event.remove(Record, "after_insert", inserted_snapshot)
        event.remove(Record, "after_update", updated_snapshot)


def test_capture_batches_inventory_writes_while_blob_lookups_preserve_integrity(storage):
    db = storage[0]
    flushes = []

    def flushed(_session, _context):
        flushes.append(1)

    event.listen(db, "after_flush", flushed)
    try:
        files = captured(storage, {f"module{i}.py": f"VALUE = {i}\n" for i in range(205)})
        db.commit()
    finally:
        event.remove(db, "after_flush", flushed)
    assert len(files) == 205 and len(flushes) <= 8
    assert db.scalar(select(func.count()).select_from(SourceBlob)) == 205
    assert files["module204.py"] == "VALUE = 204\n"


def test_comparison_context_omits_large_unneeded_payload_without_rewriting_history(storage):
    from backend.snapshot_context import comparison_snapshot

    db, user, repo = storage
    base = persist_analysis(db, user, repo, captured(storage, {"app.py": "VALUE = 1\n"}))
    db.commit()
    original = json.dumps(base.data, sort_keys=True)
    context = comparison_snapshot(db, base.id, user.organization_id, repo.id)
    assert context.data["hashes"] == base.data["hashes"]
    assert context.data["parser_signature"] == base.data["parser_signature"]
    assert "quality_metrics" not in context.data and "analysis_coverage" not in context.data
    assert comparison_snapshot(db, base.id, "other", repo.id).data == {}
    assert comparison_snapshot(db, "missing", user.organization_id, repo.id) is None
    changed = captured(storage, {"app.py": "VALUE = 2\n"})
    head = persist_analysis(db, user, repo, changed, base_id=base.id)
    db.commit()
    assert head.data["changed_files"] == ["app.py"]
    db.refresh(base)
    assert json.dumps(base.data, sort_keys=True) == original


def test_owned_head_recovery_checks_every_hash_before_evicting_only_changed_artifacts(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from backend.db import SourceInventoryFile
    from backend.domain import add
    from backend.jobs import execute_analysis
    from scripts.benchmark_repository_scale import PARSER_SIGNATURE, fixture, recover_owned_head

    monkeypatch.setenv("SOURCE_BLOB_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())
    engine = make_engine("sqlite:///" + str(tmp_path / "benchmark.db"))
    Base.metadata.create_all(engine)
    args = SimpleNamespace(files=16, lines=10, fixture="python", work_dir=tmp_path,
                           initial_report=tmp_path / "initial.json")
    with sessionmaker(engine, expire_on_commit=False)() as db:
        db.add(Organization(id="benchmark", name="Owned"))
        db.flush()
        user = User(id="benchmark-user", organization_id="benchmark", email="fixture@invalid.example",
                    password_hash="unused", role="ORG_OWNER")
        repo = Repository(id="benchmark-repo", organization_id="benchmark", name="Owned", system="Owned",
                          component="Owned", owner="Owned", provider="LOCAL")
        db.add_all([user, repo])
        db.commit()
        initial = capture(db, user.organization_id, repo, (fixture(i, args) for i in range(16)), source="OWNED_BENCHMARK")
        base, _job = execute_analysis(db, user, repo, RepositoryFiles(db, user.organization_id, repo.id, initial.id))
        original = json.dumps(base.data, sort_keys=True)
        args.initial_report.write_text(json.dumps({
            "fixture": "OWNED_SYNTHETIC_FIRST_PARTY_STYLE_INERT", "customer_code_executed": False,
            "files_requested": 16, "fixture_kind": "python", "physical_lines_requested": 160,
            "parser_signature": PARSER_SIGNATURE, "implementation_hashes": {"owned-test": "a" * 64},
            "retained_prior_attempts": [], "phases": [{"snapshot_id": base.id, "state": base.data["status"],
                "files_discovered": 16, "physical_lines": 160,
                "persisted_records": db.scalar(select(func.count()).select_from(Record))}],
        }))
        head = capture(db, user.organization_id, repo, (fixture(i, args, 0 < i <= 8) for i in range(16)), source="OWNED_BENCHMARK")
        analyze_inventory(db, RepositoryFiles(db, user.organization_id, repo.id, head.id))
        failed = add(db, user.organization_id, repo.id, "job", {"state": "FAILED", "source": "INVENTORY"})
        db.commit()
        original_count = db.scalar(select(func.count()).select_from(ParserArtifact))
        assert original_count == 24
        path = fixture(1, args)[0]
        row = db.get(SourceInventoryFile, (head.id, path))
        valid_digest = row.digest
        row.digest = db.get(SourceInventoryFile, (initial.id, path)).digest
        db.commit()
        with pytest.raises(ValueError, match="Every captured"):
            recover_owned_head(db, args, {})
        assert db.scalar(select(func.count()).select_from(ParserArtifact)) == original_count
        row.digest = valid_digest
        db.commit()
        receipt = {"phases": [], "limitations": []}
        restored_user, restored_repo, base_id, retained_head = recover_owned_head(db, args, receipt)
        assert (restored_user.id, restored_repo.id, base_id, retained_head.id) == (user.id, repo.id, base.id, head.id)
        assert receipt["owned_changed_artifacts_removed_for_eight_file_experiment"] == 8
        assert db.scalar(select(func.count()).select_from(ParserArtifact)) == 16
        assert db.get(Record, failed.id).data["state"] == "FAILED"
        db.refresh(base)
        assert json.dumps(base.data, sort_keys=True) == original
    engine.dispose()


def test_snapshot_job_link_rejects_missing_wrong_kind_and_foreign_jobs(storage):
    from backend.domain import add

    db, user, repo = storage
    files = captured(storage, {"app.py": "pass\n"})
    foreign = add(db, "other", None, "job", {"state": "QUEUED"})
    wrong_kind = add(db, user.organization_id, repo.id, "evidence", {"path": "owned.py"})
    db.commit()
    for identifier in ["missing", foreign.id, wrong_kind.id]:
        with pytest.raises(ValueError, match="Analysis job"):
            persist_analysis(db, user, repo, files, job_id=identifier)
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0


def test_declarative_boundaries_and_human_corrections_preserve_prior_inventory(storage):
    from backend.domain import add

    db, user, repo = storage
    sources = {
        ".projecttrace/components.json": '{"version":1,"components":[{"root":"service","name":"declared"}]}',
        "service/package.json": '{"name":"manifest"}',
        "service/app.py": "pass\n",
    }
    first = captured(storage, sources)
    assert first.component_for("service/app.py") == "declared"
    add(
        db,
        user.organization_id,
        repo.id,
        "component_assignment",
        {"configuration": {"version": 1, "components": [{"root": "service", "name": "corrected"}]}},
    )
    second = captured(storage, sources)
    assert second.component_for("service/app.py") == "corrected"
    assert second.metadata_for("service/app.py")["component_basis"] == "HUMAN_ASSIGNMENT"
    assert first.component_for("service/app.py") == "declared"
    with pytest.raises(ValueError, match="configuration"):
        captured(storage, {".projecttrace/components.json": '{"version":2,"components":[]}'})
