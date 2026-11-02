"""Projection read contracts: compare real results without changing expectations."""

import json
import os
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.orm import aliased, with_loader_criteria

from tests import graph_scalar_prototype as scalar
from tests.graph_index_compatibility import seed
from tests.graph_index_prototype import clone

pytestmark = pytest.mark.skipif(
    not os.getenv("SCALE001_PROTOTYPE_ROOT"), reason="Explicit disposable ownership required"
)


@pytest.fixture
def owned(tmp_path):
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"])
    source = json.loads((root / "preserved.json").read_text())["databases"]["147"]
    path = clone(source, tmp_path / "owned.db")
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        seed(db)
    return path


def compiled(statement, projected=False):
    compiler = statement.compile(dialect=scalar.dialect() if projected else dialect())
    expanded = compiler.construct_expanded_state()
    processors = {**compiler._bind_processors, **expanded.processors}
    return expanded.statement, tuple(
        processors[key](expanded.parameters[key]) if key in processors else expanded.parameters[key]
        for key in expanded.positiontup
    )


@pytest.mark.parametrize("extra", ["version", "id_in", "path"])
def test_filtered_mixed_sequences_match_complete_baseline(owned, extra):
    from backend.db import Record
    from backend.domain import snapshot_record_query

    query = snapshot_record_query("owned-eq", "owned-eq", "compat-a")
    if extra == "version":
        query = query.where(Record.version >= 1)
    elif extra == "id_in":
        query = query.where(Record.id.in_(["compat-edge-0001", "compat-edge-0011", "compat-node-0000"]))
    else:
        query = query.where(Record.data["path"].as_string().like("owned/%"))
    with sqlite3.connect(owned) as db:
        expected = db.execute(*compiled(query)).fetchall()
        scalar.install(db, "projection")
        assert db.execute(*compiled(query, True)).fetchall() == expected


def test_rowid_read_namespace_is_preserved(owned):
    query = (
        select(literal_column("records.rowid"), literal_column("records.id"))
        .select_from(__import__("backend.db", fromlist=["Record"]).Record)
        .order_by(literal_column("records.id"))
        .limit(3)
    )
    with sqlite3.connect(owned) as db:
        expected = db.execute(*compiled(query)).fetchall()
        scalar.install(db, "projection")
        assert db.execute(*compiled(query, True)).fetchall() == expected


@pytest.mark.parametrize("shape", ["alias", "quoted", "self_join", "outer_join", "ranked", "loader", "correlated"])
def test_alias_join_rank_security_and_original_ast(owned, shape):
    from sqlalchemy import func

    from backend.db import Record
    from backend.json_query import indexed_text

    left = aliased(Record, name='odd " unicode 東京' if shape == "quoted" else None)
    right = aliased(Record)
    query = (
        select(left.id, left.data)
        .where(left.organization_id == "owned-eq", left.id.like("compat-%"))
        .order_by(left.id)
        .limit(7)
    )
    if shape == "alias" or shape == "quoted":
        query = query.where(left.kind == "graph_node", indexed_text(left.data, "scope", "snapshot_id") == "compat-a")
    elif shape == "self_join":
        query = query.join(right, right.id == left.id).where(right.organization_id == "owned-eq")
    elif shape == "outer_join":
        query = (
            select(left.id, right.id)
            .outerjoin(right, right.id == "missing")
            .where(left.organization_id == "owned-eq")
            .order_by(left.id)
            .limit(7)
        )
    elif shape == "ranked":
        ranked = (
            select(
                Record.id,
                func.row_number()
                .over(partition_by=Record.repository_id, order_by=(Record.created_at.desc(), Record.id.desc()))
                .label("position"),
            )
            .where(Record.organization_id == "owned-eq")
            .subquery()
        )
        query = (
            select(Record.id).join(ranked, ranked.c.id == Record.id).where(ranked.c.position == 1).order_by(Record.id)
        )
    elif shape == "loader":
        option = with_loader_criteria(Record, Record.organization_id == "owned-eq", include_aliases=True)
        query = select(Record.id).where(Record.kind == "edge").options(option).order_by(Record.id)
    elif shape == "correlated":
        inner = select(Record.id).where(Record.kind == "edge", indexed_text(Record.data, "source") == left.id)
        query = query.where(inner.exists())
    original_sql = compiled(query)
    with sqlite3.connect(owned) as db:
        expected = db.execute(*original_sql).fetchall()
        scalar.install(db, "projection")
        assert db.execute(*compiled(query, True)).fetchall() == expected
        assert compiled(query) == original_sql


def test_named_runtime_path_is_not_substituted(owned):
    from sqlalchemy import bindparam

    from backend.db import Record

    query = select(Record.id, Record.data[bindparam("dynamic_path", value="source")].as_string()).where(
        Record.id == "compat-edge-0001"
    )
    with sqlite3.connect(owned) as db:
        before = {
            key: db.execute(*compiled(query.params(dynamic_path=key))).fetchall() for key in ("$.source", "$.target")
        }
        scalar.install(db, "projection")
        for key, expected in before.items():
            sql, values = compiled(query.params(dynamic_path=key), True)
            assert "JSON_EXTRACT" in sql
            assert db.execute(sql, values).fetchall() == expected
