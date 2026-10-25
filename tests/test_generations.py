"""Private generation staging and publication acceptance, using captured source."""
import copy

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import aliased, sessionmaker

from backend.admin_models import ActivityEvent
from backend.db import (
    Audit,
    FindingOccurrence,
    QualityAnalysis,
    Record,
    Repository,
    SnapshotInventory,
    SnapshotView,
    User,
)
from backend.generation_models import (
    AnalysisGeneration,
    GenerationChunk,
    GenerationReceipt,
    GenerationRecord,
    PublishedGeneration,
)
from backend.generations import STAGES, Generation
from backend.jobs import execute_analysis
from backend.repository_store import RepositoryFiles
from backend.trust import integrity
from tests.test_repository_store import captured, storage  # noqa: F401

SOURCES = {
    "README.md": "# Architecture\nBackend uses FastAPI.\n",
    "app.py": "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health():\n return {'ok': True}\n",
    "storage.tf": 'resource "aws_s3_bucket" "public" {\n bucket = "qualification"\n acl = "public-read"\n}\n',
}


def test_visibility_scope_switches_in_one_session_and_rechecks_publication(storage, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    db, actor, repo = storage
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    save = Generation.save

    def stop(self, stage, state):
        save(self, stage, state)
        if stage == "SNAPSHOT":
            raise RuntimeError("Owned private snapshot")

    monkeypatch.setattr(Generation, "save", stop)
    for index in range(2):
        files = captured(storage, {f"owned-{index}.py": f"value = {index}\n"})
        with pytest.raises(RuntimeError, match="Owned private snapshot"):
            execute_analysis(db, actor, repo, files, branch=f"owned-{index}")
    generations = list(db.scalars(select(AnalysisGeneration).order_by(AnalysisGeneration.branch)))
    assert len(generations) == 2
    query = select(Record.id).where(Record.kind == "snapshot")
    alias = aliased(Record)
    aliased_query = select(alias.id).where(alias.kind == "snapshot")
    try:
        # Reuse one Session and the same statements while changing worker scope.
        for active in (generations[0], generations[1], None, generations[0], None):
            if active:
                db.info["analysis_generation"] = SimpleNamespace(row=active)
            else:
                db.info.pop("analysis_generation", None)
            expected = {active.snapshot_id} if active else set()
            assert set(db.scalars(query)) == expected
            assert set(db.scalars(aliased_query)) == expected
        # Criteria cache SQL, never a visibility decision. A database state
        # change must be observed even though the Session/scope did not change.
        # A controlled database-state fixture, not application promotion.
        db.execute(AnalysisGeneration.__table__.update().where(
            AnalysisGeneration.id == generations[0].id).values(state="PUBLISHED"))
        db.commit()
        assert set(db.scalars(query)) == {generations[0].snapshot_id}
    finally:
        db.info.pop("analysis_generation", None)


@pytest.mark.parametrize("exit_point", ["BATCH", "HISTORY", "VALIDATED"])
def test_actual_worker_exit_resumes_partial_stage_with_new_lease(storage, monkeypatch, exit_point):  # noqa: F811
    import json
    import os
    import subprocess
    import sys
    from datetime import datetime, timedelta, timezone

    from backend.db import AnalysisInput, QueueEntry
    from backend.domain import add
    from backend.queue import cipher
    from backend.scheduling import claim, recover_expired, register
    db, actor, repo = storage
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    files = captured(storage, {**SOURCES, **{f"src/m{i}.js": "eval(userInput);\n" for i in range(85)}})
    job = add(db, actor.organization_id, repo.id, "job", {
        "state": "QUEUED", "source": "INVENTORY", "user_id": actor.id})
    register(db, job)
    db.add(AnalysisInput(job_id=job.id, organization_id=actor.organization_id, repository_id=repo.id,
        ciphertext=cipher().encrypt(json.dumps({"inventory_id": files.inventory_id}).encode()).decode(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()))
    db.commit()
    script = '''
import os,sys
from sqlalchemy.orm import sessionmaker
from backend.db import Record,Repository,User,make_engine
from backend.generations import Generation
from backend.jobs import execute_analysis
from backend.repository_store import RepositoryFiles
from backend.scheduling import claim
engine=make_engine(sys.argv[1])
point=sys.argv[4]
batch,save,validate=Generation.batch,Generation.save,Generation.validate
def terminate_batch(self):
 batch(self)
 if point=='BATCH' and self.stage=='ARTIFACT_GRAPH' and self.ordinal>10: os._exit(73)
def terminate_receipt(self,stage,state):
 save(self,stage,state)
 if point=='HISTORY' and stage=='HISTORY': os._exit(73)
def terminate_validation(self,snapshot):
 validate(self,snapshot)
 if point=='VALIDATED': os._exit(73)
Generation.batch,Generation.save,Generation.validate=terminate_batch,terminate_receipt,terminate_validation
with sessionmaker(engine,expire_on_commit=False)() as db:
 job=db.get(Record,sys.argv[2])
 assert claim(db,job,120)['state']=='CLAIMED'
 actor,repo=db.get(User,'user'),db.get(Repository,'repo')
 execute_analysis(db,actor,repo,RepositoryFiles(db,'tenant','repo',sys.argv[3]),job=job)
'''
    completed = subprocess.run([sys.executable, "-c", script, str(db.get_bind().url), job.id,
                                files.inventory_id, exit_point], env=os.environ.copy(),
                               timeout=90, capture_output=True)
    assert completed.returncode == 73, completed.stderr.decode()
    db.expire_all()
    generation = db.scalar(select(AnalysisGeneration))
    assert generation.state == ("VALIDATED" if exit_point == "VALIDATED" else "STAGING")
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    owned = list(db.scalars(select(GenerationRecord.record_id)))
    assert owned
    before = {r.stage: r.digest for r in db.scalars(select(GenerationReceipt))}
    token = db.get(QueueEntry, job.id).worker_token
    db.get(QueueEntry, job.id).lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    db.commit()
    assert recover_expired(db) == [job.id]
    db.refresh(job)
    assert claim(db, job, 120)["token"] != token
    snapshot, job = execute_analysis(db, actor, repo, files, job=job)
    assert job.data["generation_receipts_reused"] == len(before)
    assert set(owned) <= set(db.scalars(select(GenerationRecord.record_id)))
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 1
    assert snapshot.data["findings"]
    for stage, receipt_digest in before.items():
        assert db.get(GenerationReceipt, (generation.id, stage)).digest == receipt_digest


@pytest.mark.parametrize("change", ["CANCELLED", "REPLACED", "REVOKED"])
def test_final_promotion_rejects_cancellation_replacement_and_access_revocation(storage, monkeypatch, change):  # noqa: F811
    from backend.db import Grant, QueueEntry
    from backend.domain import add
    from backend.scheduling import JobCancelled, claim, register
    db, actor, repo = storage
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    files = captured(storage, SOURCES)
    job = add(db, actor.organization_id, repo.id, "job", {
        "state": "QUEUED", "source": "INVENTORY", "user_id": actor.id})
    register(db, job)
    db.commit()
    assert claim(db, job, 120)["state"] == "CLAIMED"
    validate = Generation.validate

    def interrupt(self, snapshot):
        validate(self, snapshot)
        queue = db.get(QueueEntry, job.id)
        if change == "CANCELLED":
            queue.cancel_requested = True
        elif change == "REPLACED":
            queue.worker_token = "replacement-owner"
        else:
            db.delete(db.get(Grant, (actor.id, repo.id)))
        db.commit()

    monkeypatch.setattr(Generation, "validate", interrupt)
    from fastapi import HTTPException
    with pytest.raises(HTTPException if change == "REVOKED" else JobCancelled):
        execute_analysis(db, actor, repo, files, job=job)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    assert db.scalar(select(AnalysisGeneration)).state == "VALIDATED"
    assert db.get(Record, job.id).data["state"] not in {"COMPLETED", "PARTIAL", "COMPLETED_NO_FINDINGS"}


@pytest.mark.parametrize("corruption", ["DIGEST", "COUNT", "REFERENCE", "SOURCE", "PAYLOAD", "ASSOCIATION"])
def test_publication_validation_rejects_corrupted_receipts_or_output(storage, monkeypatch, corruption):  # noqa: F811
    db, actor, repo = storage
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    files = captured(storage, SOURCES)
    validate = Generation.validate

    def corrupt(self, snapshot):
        if corruption == "DIGEST":
            db.scalar(select(GenerationChunk)).digest = "0" * 64
        elif corruption == "COUNT":
            db.get(GenerationReceipt, (self.row.id, "EVIDENCE")).record_count += 1
        elif corruption == "REFERENCE":
            edge = db.scalar(select(Record).where(Record.kind == "edge"))
            edge.data = {**edge.data, "target": "unavailable"}
        elif corruption == "SOURCE":
            evidence = db.scalar(select(Record).where(Record.kind == "evidence"))
            evidence.data = {**evidence.data, "hash": "0" * 64}
        elif corruption == "PAYLOAD":
            finding = db.scalar(select(Record).where(Record.kind == "finding"))
            finding.data = {**finding.data, "title": "Different from the captured result"}
        else:
            finding = db.scalar(select(Record).where(Record.kind == "finding"))
            graph = db.scalar(select(Record).where(Record.kind == "graph_node"))
            finding.data = {**finding.data, "claim_id": graph.id}
            snapshot.data = {**snapshot.data, "findings": [
                {**item, "claim_id": graph.id} if item["id"] == finding.id else item for item in snapshot.data["findings"]]}
        db.commit()
        validate(self, snapshot)

    monkeypatch.setattr(Generation, "validate", corrupt)
    with pytest.raises(ValueError):
        execute_analysis(db, actor, repo, files)
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0


def test_public_api_readers_never_return_unpublished_snapshot_or_source(signed, monkeypatch):
    from backend import main
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    save = Generation.save

    def stop(self, stage, state):
        save(self, stage, state)
        if stage == "FINAL_OUTPUT":
            raise RuntimeError("API isolation qualification")

    monkeypatch.setattr(Generation, "save", stop)
    with main.Session() as db:
        actor, repo = db.get(User, "demo-engineer"), db.get(Repository, "clean")
        files = captured((db, actor, repo), SOURCES)
        with pytest.raises(RuntimeError):
            execute_analysis(db, actor, repo, files)
        generation = db.scalar(select(AnalysisGeneration))
        private_rows = db.connection().execute(select(Record.__table__.c.id, Record.__table__.c.kind).join(
            GenerationRecord.__table__, GenerationRecord.__table__.c.record_id == Record.__table__.c.id).where(
                GenerationRecord.__table__.c.generation_id == generation.id)).all()
        snapshot_id = next(row.id for row in private_rows if row.kind == "snapshot")
        evidence_id = next(row.id for row in private_rows if row.kind == "evidence")
        finding_id = next(row.id for row in private_rows if row.kind == "finding")
    for url in (f"/api/record/{snapshot_id}", f"/api/record/{evidence_id}",
                f"/api/graph/neighborhood?node_id={evidence_id}",
                f"/api/graph/nodes?repository_id=clean&snapshot_id={snapshot_id}",
                f"/api/code-quality/clean/overview?snapshot_id={snapshot_id}",
                f"/api/findings/{finding_id}/history", f"/api/gate/{snapshot_id}", f"/api/sbom/{snapshot_id}"):
        response = signed.get(url)
        assert response.status_code == 404, (url, response.status_code)
    for url in ("/api/workspace?repository_id=clean", "/api/repositories/clean/analysis",
                "/api/records/snapshot", "/api/audit?repository_id=clean"):
        response = signed.get(url)
        assert response.status_code == 200
        assert snapshot_id not in response.text and evidence_id not in response.text


@pytest.mark.parametrize("acknowledgement_lost", [False, True])
def test_final_commit_failure_or_lost_acknowledgement_is_consistent(storage, monkeypatch, acknowledgement_lost):  # noqa: F811
    db, actor, repo = storage
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    files = captured(storage, SOURCES)
    commit = db.commit
    injected = False

    def interrupted_commit():
        nonlocal injected
        context = db.info.get("analysis_generation")
        if context and context.row.state == "PUBLISHED" and not injected:
            injected = True
            if acknowledgement_lost:
                commit()
            raise RuntimeError("Controlled commit interruption")
        commit()

    monkeypatch.setattr(db, "commit", interrupted_commit)
    if acknowledgement_lost:
        snapshot, job = execute_analysis(db, actor, repo, files)
        assert job.data["state"] == snapshot.data["status"]
        assert db.scalar(select(AnalysisGeneration)).state == "PUBLISHED"
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 1
    else:
        with pytest.raises(RuntimeError, match="Controlled commit interruption"):
            execute_analysis(db, actor, repo, files)
        assert db.scalar(select(AnalysisGeneration)).state == "VALIDATED"
        assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
        assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0


def test_expired_checkpoint_cleanup_is_bounded_and_preserves_published_history(storage, monkeypatch):  # noqa: F811
    from backend.generations import purge_expired_chunks
    db, actor, repo = storage
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    snapshot, _ = execute_analysis(db, actor, repo, captured(storage, SOURCES))
    generation = db.scalar(select(AnalysisGeneration))
    db.refresh(snapshot)
    original = copy.deepcopy(snapshot.data)
    chunks = db.scalar(select(func.count()).select_from(GenerationChunk))
    generation.expires_at = "2000-01-01"
    db.commit()
    assert purge_expired_chunks(db, limit=2) == 2
    db.commit()
    assert db.scalar(select(func.count()).select_from(GenerationChunk)) == chunks - 2
    assert db.get(Record, snapshot.id).data == original
    assert generation.state == "PUBLISHED"
    assert db.scalar(select(func.count()).select_from(GenerationReceipt)) == len(STAGES)


def test_duplicate_content_reuses_published_generation_without_new_output(storage, monkeypatch):  # noqa: F811
    db, actor, repo = storage
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    files = captured(storage, SOURCES)
    first, _ = execute_analysis(db, actor, repo, files)
    before = db.scalar(select(func.count()).select_from(Record))
    second, job = execute_analysis(db, actor, repo, files)
    assert second.id == first.id
    assert job.data["snapshot_id"] == first.id
    assert db.scalar(select(func.count()).select_from(Record)) == before + 1  # Only a new job.
    assert db.scalar(select(func.count()).select_from(AnalysisGeneration)) == 1


def test_duplicate_graph_relationship_is_reused_before_ownership_batch_commits(storage):  # noqa: F811
    from backend.domain import add
    from backend.generations import clear
    db, actor, repo = storage
    files = captured(storage, SOURCES)
    job = add(db, actor.organization_id, repo.id, "job", {"user_id": actor.id, "source": "INVENTORY"})
    db.commit()
    generation = Generation(db, job.id, actor.organization_id, repo.id, "a" * 64, lambda: None,
                            inventory_id=files.inventory_id, content_key="b" * 64)
    generation.enter("ARTIFACT_GRAPH")
    data = {"source": "same-source", "target": "same-target", "relationship": "CONTAINS", "snapshot_id": "private"}
    first = add(db, actor.organization_id, repo.id, "edge", data, defer_flush=True)
    db.flush()  # Typed projections can require an early parent flush.
    second = add(db, actor.organization_id, repo.id, "edge", data, defer_flush=True)
    assert second.id == first.id
    assert len(generation.pending) == 1
    generation.batch()
    assert db.scalar(select(func.count()).select_from(GenerationRecord)) == 1
    clear(db)
    assert db.get(Record, first.id) is None


def test_profile_changed_after_validation_cannot_publish_captured_old_decisions(storage, monkeypatch):  # noqa: F811
    from backend.db import NativeProfile
    db, actor, repo = storage
    files = captured(storage, SOURCES)
    validate = Generation.validate

    def change_profile(self, snapshot):
        validate(self, snapshot)
        db.add(NativeProfile(id="changed-profile", organization_id=actor.organization_id,
            repository_id=repo.id, scope_key=repo.id, data={"gate_scope": "NEW_FINDINGS"}))
        db.commit()

    monkeypatch.setattr(Generation, "validate", change_profile)
    with pytest.raises(ValueError, match="configuration changed"):
        execute_analysis(db, actor, repo, files)
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0


@pytest.mark.parametrize("stopped_stage", STAGES)
def test_each_stage_survives_restart_without_private_reader_leaks(storage, monkeypatch, stopped_stage):  # noqa: F811
    db, actor, repository = storage
    # Existing public history is a real preceding capture, not an empty DB.
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "0")
    baseline, _ = execute_analysis(db, actor, repository, captured(storage, {"old.py": "value = 1\n"}))
    baseline_id = baseline.id
    db.refresh(baseline)
    original = copy.deepcopy(baseline.data)
    monkeypatch.setenv("PROJECTTRACE_GENERATION_PUBLICATION", "1")
    files = captured(storage, SOURCES)
    inventory_id, actor_id, repo_id = files.inventory_id, actor.id, repository.id
    save = Generation.save

    def stop(self, stage, state):
        save(self, stage, state)
        if stage == stopped_stage:
            raise RuntimeError("Controlled interruption after durable stage receipt")

    monkeypatch.setattr(Generation, "save", stop)
    with pytest.raises(RuntimeError, match="Controlled interruption"):
        execute_analysis(db, actor, repository, files, base_id=baseline_id)
    generation = db.scalar(select(AnalysisGeneration))
    assert generation.state == "STAGING"
    job_id, generation_id = generation.job_id, generation.id
    assert db.get(Record, job_id).data["state"] == "FAILED"
    # Record ID reads, counts, columns, aliases and typed projection reads must
    # all honor the default publication boundary after worker context cleanup.
    snapshot_ids = set(db.scalars(select(Record.id).where(Record.kind == "snapshot")))
    assert snapshot_ids == {baseline_id}
    staged = list(db.scalars(select(GenerationRecord.record_id)))
    assert staged and all(db.get(Record, identity) is None for identity in staged)
    alias = aliased(Record)
    assert db.scalar(select(func.count()).select_from(alias).where(alias.kind == "snapshot")) == 1
    assert set(db.scalars(select(SnapshotInventory.snapshot_id))) == {baseline_id}
    assert set(db.scalars(select(SnapshotView.snapshot_id))) == {baseline_id}
    assert set(db.scalars(select(QualityAnalysis.snapshot_id))) == {baseline_id}
    assert not set(staged) & {a.target for a in db.scalars(select(Audit))}
    assert not set(staged) & {a.target_id for a in db.scalars(select(ActivityEvent))}
    assert integrity(db, actor.organization_id)["state"] == "VERIFIED"
    receipts = {r.stage: r.digest for r in db.scalars(select(GenerationReceipt))}
    ciphertext = {(r.stage, r.ordinal): r.ciphertext for r in db.scalars(select(GenerationChunk))}
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    db.close()
    monkeypatch.setattr(Generation, "save", save)

    def no_native_analysis(*args, **kwargs):
        raise AssertionError("Completed native analysis must not repeat")

    monkeypatch.setattr("backend.partitioned_analysis.analyze_inventory", no_native_analysis)
    with factory() as resumed:
        actor, repository = resumed.get(User, actor_id), resumed.get(Repository, repo_id)
        content = RepositoryFiles(resumed, actor.organization_id, repo_id, inventory_id)
        snapshot, job = execute_analysis(resumed, actor, repository, content,
                                         job=resumed.get(Record, job_id), base_id=baseline_id)
        assert snapshot.id != baseline_id
        assert job.data["generation_receipts_reused"] == len(receipts)
        assert job.data["generation_maximum_batch_rows"] <= 250
        assert resumed.get(AnalysisGeneration, generation_id).state == "PUBLISHED"
        assert resumed.get(Record, baseline_id).data == original
        assert resumed.get(PublishedGeneration, (actor.organization_id, repo_id, "main")).generation_id == generation_id
        assert set(resumed.scalars(select(Record.id).where(Record.kind == "snapshot"))) == {baseline_id, snapshot.id}
        for stage, digest in receipts.items():
            assert resumed.get(GenerationReceipt, (generation_id, stage)).digest == digest
        for (stage, ordinal), cipher in ciphertext.items():
            assert resumed.get(GenerationChunk, (generation_id, stage, ordinal)).ciphertext == cipher
        edges = [tuple(r.data[k] for k in ("source", "target", "relationship")) for r in resumed.scalars(
            select(Record).where(Record.kind == "edge", Record.data["snapshot_id"].as_string() == snapshot.id))]
        assert len(edges) == len(set(edges))
        occurrences = list(resumed.scalars(select(FindingOccurrence).where(FindingOccurrence.snapshot_id == snapshot.id)))
        identities = [(r.identity_id, r.status, r.finding_id) for r in occurrences]
        assert len(identities) == len(set(identities))
        assert integrity(resumed, actor.organization_id)["state"] == "VERIFIED"
