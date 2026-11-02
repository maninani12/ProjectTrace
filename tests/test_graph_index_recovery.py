"""Additional opt-in disposable recovery proofs; no changed expectations."""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from tests import graph_index_compatibility as corpus
from tests import graph_index_prototype as original
from tests import graph_index_recovery as recovery

pytestmark = pytest.mark.skipif(
    not os.environ.get("SCALE001_PROTOTYPE_ROOT"), reason="Explicit disposable prototype ownership required."
)


@pytest.fixture
def owned(tmp_path):
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"])
    manifest = json.loads((root / "preserved.json").read_text())
    path = original.clone(manifest["databases"]["147"], tmp_path / "seeded.db")
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        corpus.seed(db)
    return path


def compiled(statement):
    from sqlalchemy.dialects.sqlite import dialect

    result = statement.compile(dialect=dialect())
    expanded = result.construct_expanded_state()
    processors = {**result._bind_processors, **expanded.processors}
    return expanded.statement, tuple(
        processors[key](expanded.parameters[key]) if key in processors else expanded.parameters[key]
        for key in expanded.positiontup
    )


@pytest.mark.parametrize("mode", ["partial", "validated_partial", "guarded"])
def test_frozen_rows_and_writes_are_never_redefined(owned, mode, tmp_path):
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"])
    frozen = json.loads((root.parent / "graph-index-prototype-20261027" / "compatibility-4.json").read_text())[
        "reports"
    ]["baseline"]
    path = original.clone(owned, tmp_path / "candidate.db")
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        recovery.install(db, mode)
        actual = recovery.query_results(db, repeats=1)
        assert len(actual) == len(frozen["queries"]) == 62
        assert all(a["rows"] == [list(row) for row in b["rows"]] for a, b in zip(frozen["queries"], actual))
        assert corpus.writes(db) == frozen["writes"]


@pytest.mark.parametrize("mode", ["partial", "validated_partial", "guarded"])
def test_mixed_sequence_null_affinity_and_true_rowid_pagination(owned, mode, tmp_path):
    from backend.domain import snapshot_record_query

    with sqlite3.connect(owned) as baseline:
        for number, value in enumerate(
            (None, "", 0, 1, 1.5, True, "1", "01", "é", "e\u0301", "東京", "A\u0000B", {}, [], "same", "same")
        ):
            # Reverse lexical ids expose accidental id-vs-rowid tie-breaking.
            corpus.insert_record(
                baseline,
                f"tie-{999 - number:04}",
                "edge",
                json.dumps({"scope": {"snapshot_id": "compat-a"}, "snapshot_id": "compat-a", "target": value}),
            )
        baseline.commit()
        statement = snapshot_record_query("owned-eq", "owned-eq", "compat-a")
        expected = baseline.execute(*compiled(statement)).fetchall()
        info = list(baseline.execute("PRAGMA index_xinfo(ix_records_graph_target)"))
        assert info[-1][1] == -1 and info[-1][4] == "BINARY"  # hidden rowid
    path = original.clone(owned, tmp_path / "candidate.db")
    with sqlite3.connect(path) as db:
        recovery.install(db, mode)
        for limit in (0, 1, 3, 7, 1000):
            for offset in (0, 1, 49, 50, 65, 95, 170, 190, 1000):
                candidate, changed = recovery.guarded_statement(
                    statement.limit(limit).offset(offset), mode="guarded" if mode == "guarded" else "partial"
                )
                assert changed
                assert db.execute(*compiled(candidate)).fetchall() == expected[offset : offset + limit]
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("mode", ["partial", "guarded"])
def test_nested_union_and_count_restore_both_endpoint_seeks(owned, mode):
    with sqlite3.connect(owned) as db:
        recovery.install(db, mode)
        for q in recovery.query_results(db, repeats=1):
            if q["name"].startswith(("neighborhood_", "neighbor_total_")):
                source = [p[3] for p in q["plan"] if "ix_records_graph_source" in p[3]]
                target = [p[3] for p in q["plan"] if "ix_records_graph_target" in p[3]]
                assert source and target, q["name"]
                assert all(p.count("<expr>=?") == 2 for p in source + target), (q["name"], q["plan"])


def test_nested_correlated_select_shared_subquery_and_idempotence(owned):
    from sqlalchemy import func, select
    from sqlalchemy.orm import aliased

    from backend.db import Record
    from backend.json_query import indexed_text

    outer = aliased(Record)
    edges = select(Record.id).where(
        Record.organization_id == outer.organization_id,
        Record.repository_id == outer.repository_id,
        Record.kind == "edge",
        indexed_text(Record.data, "source") == outer.id,
    )
    shared = select(Record.id).where(Record.kind == "edge", Record.organization_id == "owned-eq").subquery()
    cases = [
        select(outer.id)
        .where(
            outer.organization_id == "owned-eq",
            outer.id.in_(["compat-node-0000", "compat-node-0001", "compat-node-0119"]),
            edges.exists(),
        )
        .order_by(outer.id),
        select(
            outer.id,
            select(func.count())
            .select_from(Record)
            .where(Record.kind == "edge", Record.repository_id == outer.repository_id)
            .scalar_subquery(),
        )
        .where(outer.organization_id == "owned-eq")
        .order_by(outer.id)
        .limit(3),
        select(func.count()).select_from(shared).where(shared.c.id.in_(select(shared.c.id))),
    ]
    with sqlite3.connect(owned) as db:
        before = [db.execute(*compiled(q)).fetchall() for q in cases]
        recovery.install(db, "validated_partial")
        for statement, expected in zip(cases, before):
            original_sql = compiled(statement)
            candidate, changed = recovery.guarded_statement(statement)
            assert changed
            assert compiled(statement) == original_sql
            assert db.execute(*compiled(candidate)).fetchall() == expected
            again, changed_again = recovery.guarded_statement(candidate)
            assert not changed_again and compiled(again) == compiled(candidate)
            overridden, changed_override = recovery.guarded_statement(statement, {"runtime": "snapshot"})
            assert not changed_override and overridden is statement


def test_recursive_cte_is_refused_without_damaging_original():
    from sqlalchemy import literal, select

    seed = select(literal(1).label("n")).cte("owned_recursive", recursive=True)
    tree = seed.union_all(select((seed.c.n + 1).label("n")).where(seed.c.n < 3))
    statement = select(tree.c.n)
    counters = {}
    candidate, changed = recovery.guarded_statement(statement, counters=counters)
    assert not changed and candidate is statement
    assert counters == {"refused_recursive_cte": 1}


def test_guarded_outer_proof_does_not_rewrite_inner_snapshot_scope(owned):
    from sqlalchemy import select

    from backend.db import Record
    from backend.json_query import indexed_text

    snapshots = (
        select(Record.id)
        .where(Record.kind == "snapshot", indexed_text(Record.data, "scope", "snapshot_id") == "compat-a")
        .correlate(None)
    )
    statement = select(Record.id).where(Record.kind == "edge", snapshots.exists()).order_by(Record.id)
    with sqlite3.connect(owned) as db:
        expected = db.execute(*compiled(statement)).fetchall()
        assert expected
        recovery.install(db, "guarded")
        candidate, changed = recovery.guarded_statement(statement, mode="guarded")
        assert changed
        assert db.execute(*compiled(candidate)).fetchall() == expected


def test_atomic_install_rolls_back_trigger_failure(owned):
    class FailingConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.startswith("CREATE TRIGGER scale001_snapshot_update"):
                raise sqlite3.OperationalError("owned injected trigger failure")
            return super().execute(sql, *args, **kwargs)

    with sqlite3.connect(owned, factory=FailingConnection) as db:
        before = list(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"))
        with pytest.raises(sqlite3.OperationalError, match="owned injected"):
            recovery.install(db, "guarded")
        assert list(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")) == before
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_explicit_order_is_not_applied_to_alias_or_existing_order():
    from sqlalchemy import select
    from sqlalchemy.orm import aliased

    from backend.db import Record
    from backend.domain import snapshot_record_query

    statements = [
        select(aliased(Record)),
        snapshot_record_query("owned-eq", "owned-eq", "compat-a").order_by(Record.id),
    ]
    for statement in statements:
        changed, _ = recovery.guarded_statement(statement)
        assert compiled(changed) == compiled(statement)


def test_id_filtered_mixed_query_keeps_its_actual_baseline_traversal(owned):
    from backend.db import Record
    from backend.domain import snapshot_record_query

    statement = snapshot_record_query("owned-eq", "owned-eq", "compat-a").where(
        Record.id.in_(["compat-edge-0001", "compat-edge-0011", "compat-node-0000"])
    )
    with sqlite3.connect(owned) as db:
        expected = db.execute(*compiled(statement)).fetchall()
        recovery.install(db, "validated_partial")
        candidate, changed = recovery.guarded_statement(statement)
        assert not changed and compiled(candidate) == compiled(statement)
        assert db.execute(*compiled(candidate)).fetchall() == expected


@pytest.mark.parametrize("mode", ["partial", "guarded"])
def test_mutated_ast_reproves_binds_and_visits_new_subquery(owned, mode):
    from sqlalchemy import bindparam, select

    from backend.db import Record

    base = select(Record.id).where(Record.kind == bindparam("selected", value="edge")).order_by(Record.id)
    once, _ = recovery.guarded_statement(base, mode=mode)
    mutated = once.params(selected="snapshot")
    inner = select(Record.id).where(Record.kind == "edge", Record.organization_id == "owned-eq").correlate(None)
    appended = once.where(inner.exists())
    with sqlite3.connect(owned) as db:
        expected_snapshot = db.execute(*compiled(base.params(selected="snapshot"))).fetchall()
        expected_appended = db.execute(*compiled(base.where(inner.exists()))).fetchall()
        recovery.install(db, "guarded" if mode == "guarded" else "validated_partial")
        actual, _ = recovery.guarded_statement(mutated, mode=mode)
        assert db.execute(*compiled(actual)).fetchall() == expected_snapshot
        actual_appended, _ = recovery.guarded_statement(appended, mode=mode)
        assert compiled(actual_appended)[0].count("!= 'snapshot'") == 2
        assert db.execute(*compiled(actual_appended)).fetchall() == expected_appended


@pytest.mark.parametrize("mode", ["partial", "validated_partial", "guarded"])
def test_extra_version_filter_preserves_complete_baseline_sequence(owned, mode):
    """Mandatory broad-compatibility assertion; retain failure if not recovered."""
    from backend.db import Record
    from backend.domain import snapshot_record_query

    statement = snapshot_record_query("owned-eq", "owned-eq", "compat-a").where(Record.version >= 1)
    with sqlite3.connect(owned) as db:
        expected = db.execute(*compiled(statement)).fetchall()
        recovery.install(db, mode)
        candidate, _ = recovery.guarded_statement(statement, mode="guarded" if mode == "guarded" else "partial")
        assert db.execute(*compiled(candidate)).fetchall() == expected


def test_loader_security_options_preserved_by_identity(owned):
    from sqlalchemy import select
    from sqlalchemy.orm import with_loader_criteria

    from backend.db import Record, Repository

    option = with_loader_criteria(Record, Record.organization_id == "owned-eq", include_aliases=True)
    statement = select(Record.id).where(Record.kind == "edge").options(option).order_by(Record.id)
    candidate, changed = recovery.guarded_statement(statement)
    assert changed and candidate._with_options[0] is option
    with sqlite3.connect(owned) as db:
        expected = db.execute(*compiled(statement)).fetchall()
        recovery.install(db, "validated_partial")
        assert db.execute(*compiled(candidate)).fetchall() == expected
    unrelated = select(Repository).options(option)
    untouched, changed = recovery.guarded_statement(unrelated, {"pk": "owned-eq"})
    assert not changed and untouched is unrelated
