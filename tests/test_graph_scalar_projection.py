"""Opt-in native trigger/ownership contracts for the disposable scalar table."""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from tests import graph_index_compatibility as corpus
from tests import graph_index_prototype as original
from tests import graph_scalar_prototype as scalar

pytestmark = pytest.mark.skipif(
    not os.environ.get("SCALE001_PROTOTYPE_ROOT"), reason="Explicit disposable prototype ownership required."
)


def _connect(path, *, foreign_keys=True, recursive=False):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=" + ("ON" if foreign_keys else "OFF"))
    db.execute("PRAGMA recursive_triggers=" + ("ON" if recursive else "OFF"))
    return db


def _insert(db, identity, *, repo="owned-eq", kind="job", natural=None, data=None, rowid=None):
    value = json.dumps(data if data is not None else {"scope": {"snapshot_id": "scalar-owned"}, "source": identity})
    columns = "id,organization_id,repository_id,kind,natural_key,data,created_at,version"
    values = (identity, "owned-eq", repo, kind, natural or identity, value, "2026-10-27T00:00:00+00:00", 1)
    if rowid is not None:
        columns, values = "rowid," + columns, (rowid, *values)
    db.execute("INSERT INTO records(" + columns + ") VALUES(" + ",".join("?" for _ in values) + ")", values)
    return db.execute("SELECT rowid FROM records WHERE id=?", (identity,)).fetchone()[0]


def _coverage(db):
    # Keep the original native JSON_QUOTE/CAST expression, not Python decoding
    # or the candidate's own direct-path extraction, as the equality oracle.
    expressions = [
        "CAST(json_extract(json_quote(json_extract(r.data,'$.\"scope\"')),'$.\"snapshot_id\"') AS VARCHAR)",
        *[
            "CAST(json_extract(r.data,'$.\"" + key + "\"') AS VARCHAR)"
            for key in ("snapshot_id", "source", "target", "class")
        ],
    ]
    comparisons = [
        "p.rid IS r.rowid",
        "p.id IS r.id",
        "p.organization_id IS r.organization_id",
        "p.repository_id IS r.repository_id",
        "p.kind IS r.kind",
        "p.natural_key IS r.natural_key",
    ]
    comparisons += ["p." + field + " IS " + expression for field, expression in zip(scalar.FIELDS, expressions)]
    count = db.execute("SELECT count(*) FROM records").fetchone()[0]
    assert db.execute("SELECT count(*) FROM " + scalar.TABLE).fetchone()[0] == count
    mismatch = db.execute(
        "SELECT r.rowid FROM records r LEFT JOIN "
        + scalar.TABLE
        + " p ON p.rid=r.rowid WHERE NOT ("
        + " AND ".join(comparisons)
        + ") LIMIT 1"
    ).fetchone()
    assert mismatch is None, mismatch
    assert (
        db.execute(
            "SELECT p.rid FROM "
            + scalar.TABLE
            + " p LEFT JOIN records r ON r.rowid=p.rid WHERE r.rowid IS NULL LIMIT 1"
        ).fetchone()
        is None
    )
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def _attempt(db, sql, args=()):
    db.execute("SAVEPOINT scalar_contract")
    try:
        db.execute(sql, args)
        result = {"outcome": "OK", "in_transaction": db.in_transaction}
    except sqlite3.Error as error:
        result = {
            "outcome": "ERROR",
            "class": type(error).__name__,
            "message": str(error),
            "code": error.sqlite_errorcode,
            "name": error.sqlite_errorname,
            "in_transaction": db.in_transaction,
        }
    finally:
        db.execute("ROLLBACK TO scalar_contract")
        db.execute("RELEASE scalar_contract")
    return result


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"])
    manifest = json.loads((root / "preserved.json").read_text())
    directory = tmp_path_factory.mktemp("scalar_controls")
    baseline = original.clone(manifest["databases"]["147"], directory / "baseline.db")
    with _connect(baseline) as db:
        corpus.seed(db)
    projected = original.clone(baseline, directory / "projected.db")
    with _connect(projected) as db:
        scalar.install(db, "scalar")
        _coverage(db)
    return baseline, projected


@pytest.fixture
def paired(controls, tmp_path):
    baseline = original.clone(controls[0], tmp_path / "baseline.db")
    projected = original.clone(controls[1], tmp_path / "projected.db")
    return baseline, projected


def test_all_229_native_write_errors_and_eight_column_contracts(paired):
    with _connect(paired[0]) as baseline, _connect(paired[1]) as projected:
        expected, actual = corpus.writes(baseline), corpus.writes(projected)
        assert len(expected) == len(actual) == 229
        assert actual == expected
        assert len(projected.execute("SELECT * FROM records LIMIT 0").description) == 8
        values = ("scalar-positional", "owned-eq", None, "job", "scalar-positional", "{}", "2026", 1)
        sql = "INSERT INTO records VALUES(?,?,?,?,?,?,?,?)"
        assert _attempt(projected, sql, values) == _attempt(baseline, sql, values)
        _coverage(projected)


def test_natural_key_only_update_preserves_projection_metadata(paired):
    """Retain this failure: REPLACE cleanup depends on current natural metadata."""
    with _connect(paired[0]) as baseline, _connect(paired[1]) as projected:
        for db in (baseline, projected):
            _insert(db, "scalar-natural-only", natural="scalar-natural-before")
            db.execute(
                "UPDATE records SET natural_key=? WHERE id=?",
                ("scalar-natural-after", "scalar-natural-only"),
            )
        assert (
            projected.execute("SELECT id,natural_key FROM records WHERE id='scalar-natural-only'").fetchall()
            == baseline.execute("SELECT id,natural_key FROM records WHERE id='scalar-natural-only'").fetchall()
        )
        _coverage(projected)


@pytest.mark.parametrize("kind", ["snapshot", "graph_node", "edge", "job"])
def test_malformed_update_error_precedence_for_every_kind(paired, kind):
    with _connect(paired[0]) as baseline, _connect(paired[1]) as projected:
        for db in (baseline, projected):
            _insert(db, "scalar-bad-original", kind=kind)
            _insert(db, "scalar-bad-conflict", kind=kind)
        variants = [
            ("UPDATE records SET data='{',id='scalar-bad-conflict' WHERE id='scalar-bad-original'", ()),
            ("UPDATE records SET data='{',natural_key='scalar-bad-conflict' WHERE id='scalar-bad-original'", ()),
            ("UPDATE records SET data='{',natural_key=NULL WHERE id='scalar-bad-original'", ()),
            ("UPDATE records SET data=NULL,natural_key=NULL WHERE id='scalar-bad-original'", ()),
        ]
        for sql, args in variants:
            assert _attempt(projected, sql, args) == _attempt(baseline, sql, args), sql
        _coverage(projected)


@pytest.mark.parametrize("operation", ["update_key", "update_tenant", "insert_forged", "delete_live"])
def test_projection_tampering_is_rejected_and_rolled_back(paired, operation):
    with _connect(paired[1]) as db:
        rid = _insert(db, "scalar-tamper")
        before = db.execute("SELECT * FROM " + scalar.TABLE + " WHERE rid=?", (rid,)).fetchone()
        if operation == "update_key":
            sql, args = "UPDATE " + scalar.TABLE + " SET key_source='forged' WHERE rid=?", (rid,)
        elif operation == "update_tenant":
            sql, args = "UPDATE " + scalar.TABLE + " SET organization_id='scale-other' WHERE rid=?", (rid,)
        elif operation == "insert_forged":
            columns = "rid,id,organization_id,repository_id,kind,natural_key," + ",".join(scalar.FIELDS)
            sql = "INSERT INTO " + scalar.TABLE + "(" + columns + ") VALUES(" + ",".join("?" for _ in before) + ")"
            args = (rid + 100000, "scalar-forged", *before[2:])
        else:
            sql, args = "DELETE FROM " + scalar.TABLE + " WHERE rid=?", (rid,)
        result = _attempt(db, sql, args)
        assert result["outcome"] == "ERROR" and result["message"] == "Derived scalar projection is immutable"
        assert db.execute("SELECT * FROM " + scalar.TABLE + " WHERE rid=?", (rid,)).fetchone() == before
        assert db.execute("SELECT count(*) FROM records WHERE id='scalar-tamper'").fetchone()[0] == 1
        _coverage(db)


@pytest.mark.parametrize("foreign_keys", [False, True])
@pytest.mark.parametrize("recursive", [False, True])
def test_nullable_repository_delete_and_reinsert_keeps_coverage(paired, foreign_keys, recursive):
    with _connect(paired[1], foreign_keys=foreign_keys, recursive=recursive) as db:
        _insert(db, "scalar-null-repo", repo=None)
        db.execute("DELETE FROM records WHERE id='scalar-null-repo'")
        assert db.execute("SELECT 1 FROM " + scalar.TABLE + " WHERE id='scalar-null-repo'").fetchone() is None
        _insert(db, "scalar-null-repo", repo=None)
        _coverage(db)


@pytest.mark.parametrize("identity_column", ["id", "rowid", "_rowid_", "oid"])
def test_identity_mutations_match_baseline_and_reanchor_projection(paired, identity_column):
    with _connect(paired[0]) as baseline, _connect(paired[1]) as projected:
        for db in (baseline, projected):
            _insert(db, "scalar-identity", repo=None)
        replacement = "scalar-identity-new" if identity_column == "id" else 1000000
        for db in (baseline, projected):
            db.execute("UPDATE records SET " + identity_column + "=? WHERE id='scalar-identity'", (replacement,))
        actual = projected.execute(
            "SELECT rowid,id,data,version FROM records WHERE id IN ('scalar-identity','scalar-identity-new')"
        ).fetchall()
        expected = baseline.execute(
            "SELECT rowid,id,data,version FROM records WHERE id IN ('scalar-identity','scalar-identity-new')"
        ).fetchall()
        assert actual == expected
        _coverage(projected)


@pytest.mark.parametrize("foreign_keys", [False, True])
@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("collision", ["id", "rowid", "natural", "id_and_rowid"])
def test_replace_contracts_across_recursive_and_fk_modes(paired, foreign_keys, recursive, collision):
    with (
        _connect(paired[0], foreign_keys=foreign_keys, recursive=recursive) as baseline,
        _connect(paired[1], foreign_keys=foreign_keys, recursive=recursive) as projected,
    ):
        rowids = []
        for db in (baseline, projected):
            first = _insert(db, "scalar-replace-a", repo=None)
            second = _insert(db, "scalar-replace-b", repo=None)
            rowids.append((first, second))
        assert rowids[0] == rowids[1]
        fields = "id,organization_id,repository_id,kind,natural_key,data,created_at,version"
        identity, natural, rid = "scalar-replace-new", "scalar-replace-new", None
        if collision == "id":
            identity = "scalar-replace-a"
        elif collision == "natural":
            natural = "scalar-replace-a"
        elif collision == "rowid":
            rid = rowids[0][0]
        else:
            rid, identity = rowids[0][0], "scalar-replace-b"
        values = (identity, "owned-eq", None, "job", natural, '{"source":"replacement"}', "2026", 1)
        if rid is not None:
            fields, values = "rowid," + fields, (rid, *values)
        sql = "INSERT OR REPLACE INTO records(" + fields + ") VALUES(" + ",".join("?" for _ in values) + ")"
        for db in (baseline, projected):
            db.execute(sql, values)
        query = "SELECT rowid,id,natural_key,data FROM records WHERE id LIKE 'scalar-replace-%' ORDER BY rowid"
        assert projected.execute(query).fetchall() == baseline.execute(query).fetchall()
        assert (
            projected.execute("SELECT count(*) FROM records").fetchone()
            == baseline.execute("SELECT count(*) FROM records").fetchone()
        )
        _coverage(projected)


def test_projection_trigger_failure_rolls_back_authoritative_record(paired):
    with _connect(paired[1]) as db:

        def deny_projection_insert(action, name, _column, _database, _trigger):
            return (
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and name == scalar.TABLE else sqlite3.SQLITE_OK
            )

        db.set_authorizer(deny_projection_insert)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                _insert(db, "scalar-admission-fail")
        finally:
            db.set_authorizer(None)
        assert db.execute("SELECT 1 FROM records WHERE id='scalar-admission-fail'").fetchone() is None
        assert db.execute("SELECT 1 FROM " + scalar.TABLE + " WHERE id='scalar-admission-fail'").fetchone() is None
        _coverage(db)


def test_transaction_rollback_restores_records_and_projection(paired):
    with _connect(paired[1]) as db:
        _insert(db, "scalar-rollback", repo=None)
        db.commit()
        before = db.execute("SELECT * FROM " + scalar.TABLE + " WHERE id='scalar-rollback'").fetchone()
        db.execute("BEGIN")
        db.execute("UPDATE records SET data='{\"source\":\"changed\"}' WHERE id='scalar-rollback'")
        _insert(db, "scalar-cancelled", repo=None)
        db.rollback()
        assert db.execute("SELECT 1 FROM records WHERE id='scalar-cancelled'").fetchone() is None
        assert db.execute("SELECT * FROM " + scalar.TABLE + " WHERE id='scalar-rollback'").fetchone() == before
        _coverage(db)


def test_interrupted_backfill_is_atomic_and_preserves_original_error(controls, tmp_path):
    path = original.clone(controls[0], tmp_path / "cancel-install.db")
    with _connect(path) as db:
        before = list(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"))
        state = {"insert_seen": False, "calls": 0, "cancelled": False}

        def authorizer(action, name, _column, _database, _trigger):
            if action == sqlite3.SQLITE_INSERT and name == scalar.TABLE:
                state["insert_seen"] = True
            return sqlite3.SQLITE_OK

        def progress():
            if state["insert_seen"]:
                state["calls"] += 1
            if state["calls"] >= 20 and not state["cancelled"]:
                state["cancelled"] = True
                return 1
            return 0

        db.set_authorizer(authorizer)
        db.set_progress_handler(progress, 100)
        try:
            with pytest.raises(sqlite3.OperationalError, match="interrupted"):
                scalar.install(db, "scalar")
        finally:
            db.set_progress_handler(None, 0)
            db.set_authorizer(None)
        assert state["cancelled"] and state["insert_seen"]
        assert list(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")) == before
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (scalar.TABLE,)).fetchone() is None
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_large_native_values_are_complete_without_copying_non_key_payload(paired):
    key, noise = "k" * 200000, "n" * 500000
    data = {
        "scope": {"snapshot_id": "scalar-large"},
        "source": key,
        "noise": noise,
        "class": {"nested": [1, True, None]},
    }
    with _connect(paired[0]) as baseline, _connect(paired[1]) as projected:
        for db in (baseline, projected):
            _insert(db, "scalar-large", data=data)
        row = projected.execute(
            "SELECT key_scope,key_source,key_class FROM " + scalar.TABLE + " WHERE id='scalar-large'"
        ).fetchone()
        expected = baseline.execute(
            "SELECT CAST(json_extract(json_quote(json_extract(data,'$.scope')),'$.snapshot_id') AS VARCHAR),CAST(json_extract(data,'$.source') AS VARCHAR),CAST(json_extract(data,'$.class') AS VARCHAR) FROM records WHERE id='scalar-large'"
        ).fetchone()
        assert row == expected
        assert len(row[1]) == 200000 and row[1] == key
        columns = [item[1] for item in projected.execute("PRAGMA table_info(" + scalar.TABLE + ")")]
        assert columns == ["rid", "id", "organization_id", "repository_id", "kind", "natural_key", *scalar.FIELDS]
        scalar_bytes = projected.execute(
            "SELECT "
            + "+".join("coalesce(length(CAST(" + field + " AS BLOB)),0)" for field in scalar.FIELDS)
            + " FROM "
            + scalar.TABLE
            + " WHERE id='scalar-large'"
        ).fetchone()[0]
        assert 200000 <= scalar_bytes < 201000
        assert noise not in "".join(str(value) for value in row)
        _coverage(projected)
