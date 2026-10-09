"""Measured publication bottlenecks retain history, isolation and bounded writes."""

import pytest
from sqlalchemy import event, func, select

from backend.db import FindingIdentity, FindingOccurrence, ParserArtifact, Repository
from backend.domain import add
from backend.finding_history import project
from backend.partitioned_analysis import analyze_inventory
from tests.test_repository_store import captured
from tests.test_repository_store import storage as storage


def test_completed_partition_survives_deadline_at_its_progress_checkpoint(storage):
    db, _, _ = storage
    files = captured(storage, {f"app{i}.py": "VALUE = 1\n" for i in range(20)})
    calls = 0

    def progress(_state):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TimeoutError("Deadline reached immediately after a completed partition")

    with pytest.raises(TimeoutError):
        analyze_inventory(db, files, progress=progress)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(ParserArtifact)) == 20


def test_scoped_cache_query_uses_both_tenant_and_artifact_key(storage):
    db, user, _ = storage
    rows = [
        dict(
            id=f"cache-{i}",
            organization_id=user.organization_id,
            content_hash=f"hash-{i}",
            language="Python",
            parser_version="fixture",
            rule_version="fixture",
            data={"index": i},
        )
        for i in range(600)
    ]
    db.execute(ParserArtifact.__table__.insert(), rows)
    db.commit()
    ids = [f"cache-{i}" for i in range(0, 600, 6)]
    query = select(ParserArtifact.id, ParserArtifact.data).where(
        ParserArtifact.organization_id == user.organization_id, ParserArtifact.id.in_(ids)
    )
    sql = str(query.compile(db.get_bind(), compile_kwargs={"literal_binds": True}))
    plan = db.connection().exec_driver_sql("EXPLAIN QUERY PLAN " + sql).all()
    assert any("ix_parser_artifact_lookup" in row[3] and "organization_id=? AND id=?" in row[3] for row in plan)
    assert {row.id for row in db.execute(query)} == set(ids)
    assert not db.execute(query.where(ParserArtifact.organization_id == "other")).all()


def test_history_batches_queries_and_flushes_without_losing_occurrences(storage):
    db, user, repo = storage
    snapshot = add(db, user.organization_id, repo.id, "snapshot", {"branch": "main", "commit": "a" * 40})
    findings = []
    for i in range(510):
        row = add(db, user.organization_id, repo.id, "finding", {}, defer_flush=True)
        findings.append(
            {
                "id": row.id,
                "identity_id": f"concept-{i}",
                "rule": "PT-SAST-005",
                "path": "app.py",
                "line": i + 1,
                "fingerprint": f"fingerprint-{i}",
            }
        )
        if i % 100 == 99:
            db.flush()
    db.flush()
    selections, flush_sizes = [], []

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def count_query(_c, _cursor, statement, *_):
        if statement.lstrip().upper().startswith("SELECT") and "FROM finding_identities" in statement:
            selections.append(statement)

    @event.listens_for(db, "before_flush")
    def count_flush(session, *_):
        flush_sizes.append(len(session.new) + len(session.dirty))

    project(db, snapshot, findings, [], {}, model_changed=False, warnings=[], files={"app.py": "inert"})
    assert len(selections) == 3
    assert max(flush_sizes) <= 250
    assert db.scalar(select(func.count()).select_from(FindingIdentity)) == 510
    rows = list(db.scalars(select(FindingOccurrence)))
    assert len(rows) == 510
    assert {r.status for r in rows} == {"INTRODUCED"}
    assert {r.finding_id for r in rows} == {f["id"] for f in findings}
    assert {r.identity_id for r in rows} == {f["identity_id"] for f in findings}


def test_history_prefetched_identity_cannot_cross_tenants(storage):
    db, user, repo = storage
    snapshot = add(db, user.organization_id, repo.id, "snapshot", {"branch": "main", "commit": "a" * 40})
    other_repo = Repository(
        id="other-repo",
        organization_id="other",
        name="Other",
        system="Other",
        component="Other",
        owner="Other",
        provider="LOCAL",
    )
    db.add(other_repo)
    db.flush()
    other_snapshot = add(db, "other", other_repo.id, "snapshot", {})
    db.add(
        FindingIdentity(
            id="other-concept",
            organization_id="other",
            repository_id=other_repo.id,
            introduced_snapshot_id=other_snapshot.id,
            rule="PT-SAST-005",
        )
    )
    db.flush()
    with pytest.raises(ValueError, match="Cross-tenant"):
        project(
            db,
            snapshot,
            [{"identity_id": "other-concept", "id": "untrusted", "rule": "PT-SAST-005"}],
            [],
            {},
            model_changed=False,
            warnings=[],
            files={},
        )
    assert db.scalar(select(func.count()).select_from(FindingOccurrence)) == 0


def test_reference_memo_retains_all_scope_checks_and_expires_each_flush(storage, monkeypatch):
    db, user, repo = storage
    original, lookups = db.get, []

    def measured(model, identity, *a, **kw):
        lookups.append((model, identity))
        return original(model, identity, *a, **kw)

    monkeypatch.setattr(db, "get", measured)
    rows = [add(db, user.organization_id, repo.id, "graph_node", {}, defer_flush=True) for _ in range(250)]
    db.flush()
    assert len(lookups) == 1
    rows[0].organization_id = "other"
    with pytest.raises(ValueError, match="Tenant scope is immutable"):
        db.flush()
    db.rollback()
    add(db, user.organization_id, repo.id, "graph_node", {}, defer_flush=True)
    add(db, "other", repo.id, "graph_node", {}, defer_flush=True)
    with pytest.raises(ValueError, match="Cross-tenant repository"):
        db.flush()
