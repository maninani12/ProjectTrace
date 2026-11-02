"""Disposable full-membership scalar projection; no production imports.

Records retain their eight-column schema. Native triggers maintain a one-to-one
scalar table anchored to the original hidden rowid. A per-engine SQLite compiler
renders a flat joined table group; SQLAlchemy ASTs/options/aliases are untouched.
Only original literal-path JSON index expressions are mapped to scalar keys.
"""

import time

from sqlalchemy import String
from sqlalchemy.dialects.sqlite.base import SQLiteCompiler, SQLiteDialect
from sqlalchemy.sql import elements, operators
from sqlalchemy.sql.selectable import Alias

from tests import graph_index_prototype as original

V1_INSTALL = original.install
TABLE = "scale001_graph_scalar_keys"
PATHS = (("scope", "snapshot_id"), ("snapshot_id",), ("source",), ("target",), ("class",))
FIELDS = ("key_scope", "key_snapshot", "key_source", "key_target", "key_class")
PACK_PATHS = ",".join("'$" + "".join('."' + key + '"' for key in path) + "'" for path in PATHS)


def _record_table():
    from backend.db import Record

    return Record.__table__


def _is_records(table):
    return table is _record_table() or (getattr(table, "name", None) == "records" and table.compare(_record_table()))


def _extract(alias, identity):
    """One bounded row, one materialized multipath parse; never all-row materialization."""
    return (
        "WITH scalar_input AS MATERIALIZED (SELECT rowid AS rid,id,organization_id,repository_id,kind,natural_key,"
        "json_extract(data," + PACK_PATHS + ") AS packed FROM records WHERE rowid=" + identity + ") "
        "SELECT rid,id,organization_id,repository_id,kind,natural_key,"
        + ",".join(
            "CAST(json_extract(packed,'$[" + str(i) + "]') AS VARCHAR) AS " + field for i, field in enumerate(FIELDS)
        )
        + " FROM scalar_input "
        + alias
    )


def _canonical_guard():
    return (
        "NOT EXISTS(SELECT 1 FROM ("
        + _extract("", "NEW.rid")
        + ") AS canonical WHERE "
        + " AND ".join(
            "NEW." + name + " IS canonical." + name
            for name in ("rid", "id", "organization_id", "repository_id", "kind", "natural_key")
        )
        + " AND "
        + " AND ".join("NEW." + name + " IS canonical." + name for name in FIELDS)
        + ")"
    )


def _upsert(identity):
    columns = ("rid", "id", "organization_id", "repository_id", "kind", "natural_key", *FIELDS)
    select = _extract("", identity)
    # Explicit column aliases keep the materialized output independent of SQL
    # function spelling and preserve native SQL TEXT/NULL values.
    return (
        "INSERT INTO " + TABLE + "(" + ",".join(columns) + ") "
        "SELECT * FROM ("
        + select
        + ") AS derived WHERE NOT EXISTS(SELECT 1 FROM "
        + TABLE
        + " AS present WHERE "
        + " AND ".join("present." + name + " IS derived." + name for name in columns)
        + ") ON CONFLICT(rid) DO UPDATE SET "
        + ",".join(name + "=excluded." + name for name in columns[1:])
    )


def install(connection, mode):
    original.writable(connection)
    if mode == "baseline":
        return V1_INSTALL(connection, mode)
    definitions = original.definitions(connection)
    if set(definitions) != set(original.NAMES):
        raise ValueError("All four original graph indexes are required.")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone():
        raise ValueError("Projection already installed.")
    started = time.perf_counter()
    connection.execute("SAVEPOINT scale001_scalar")
    try:
        connection.execute(
            "CREATE TABLE " + TABLE + "(rid INTEGER PRIMARY KEY,id VARCHAR(80) NOT NULL UNIQUE,"
            "organization_id VARCHAR NOT NULL,repository_id VARCHAR,kind VARCHAR NOT NULL,natural_key VARCHAR NOT NULL,"
            + ",".join(field + " VARCHAR" for field in FIELDS)
            + ",FOREIGN KEY(id) REFERENCES records(id) "
            "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED)"
        )
        for name in definitions:
            connection.execute('DROP INDEX "' + name + '"')
        # Backfill one row at a time. Only rowids cross into Python, never JSON.
        cursor = connection.execute("SELECT rowid FROM records ORDER BY rowid")
        while rows := cursor.fetchmany(128):
            for (identity,) in rows:
                connection.execute(_upsert(str(identity)))
        required = [row[1] for row in connection.execute("PRAGMA table_info(records)") if row[3]]
        present = " AND ".join('NEW."' + field + '" IS NOT NULL' for field in required)
        for event in ("INSERT", "UPDATE OF data,kind,id,organization_id,repository_id"):
            label = event.split()[0].lower()
            connection.execute(
                "CREATE TRIGGER scale001_scalar_validate_"
                + label
                + " BEFORE "
                + event
                + " ON records WHEN "
                + present
                + " BEGIN SELECT json_extract(NEW.data,"
                + PACK_PATHS
                + "); END"
            )
        orphan_same_id = (
            "DELETE FROM " + TABLE + " WHERE id=NEW.id AND rid IS NOT NEW.rowid "
            "AND NOT EXISTS(SELECT 1 FROM records WHERE rowid=" + TABLE + ".rid); "
        )
        connection.execute("CREATE INDEX scale001_scalar_natural ON " + TABLE + "(organization_id,kind,natural_key)")
        # REPLACE can delete another ID through the original natural-key UNIQUE
        # constraint without DELETE triggers. Cleanup is indexed to that exact
        # key, not an unbounded all-projection scan.
        orphan_same_id += (
            "DELETE FROM " + TABLE + " WHERE organization_id IS NEW.organization_id AND kind IS NEW.kind "
            "AND natural_key IS NEW.natural_key AND id IS NOT NEW.id "
            "AND NOT EXISTS(SELECT 1 FROM records WHERE rowid=" + TABLE + ".rid); "
        )
        connection.execute(
            "CREATE TRIGGER scale001_scalar_insert AFTER INSERT ON records BEGIN "
            + orphan_same_id
            + _upsert("NEW.rowid")
            + "; END"
        )
        connection.execute(
            "CREATE TRIGGER scale001_scalar_update AFTER UPDATE OF data,kind,id,organization_id,repository_id,rowid,_rowid_,oid "
            "ON records BEGIN DELETE FROM "
            + TABLE
            + " WHERE rid=OLD.rowid AND OLD.rowid IS NOT NEW.rowid; "
            + orphan_same_id
            + _upsert("NEW.rowid")
            + "; END"
        )
        # Nullable composite FKs do not cascade; this also covers FK-disabled
        # owned recovery fixtures. The parent row is gone before this trigger.
        connection.execute(
            "CREATE TRIGGER scale001_scalar_delete AFTER DELETE ON records BEGIN DELETE FROM "
            + TABLE
            + " WHERE rid=OLD.rowid; END"
        )
        # Projection writes must exactly match the authoritative record. No
        # privileged bypass flag or dependence on recursive_triggers=OFF.
        for event in ("INSERT", "UPDATE"):
            connection.execute(
                "CREATE TRIGGER scale001_scalar_guard_"
                + event.lower()
                + " BEFORE "
                + event
                + " ON "
                + TABLE
                + " WHEN "
                + _canonical_guard()
                + " BEGIN SELECT RAISE(ABORT,'Derived scalar projection is immutable'); END"
            )
        connection.execute(
            "CREATE TRIGGER scale001_scalar_guard_delete BEFORE DELETE ON "
            + TABLE
            + " WHEN EXISTS(SELECT 1 FROM records WHERE rowid=OLD.rid) "
            "BEGIN SELECT RAISE(ABORT,'Derived scalar projection is immutable'); END"
        )
        expressions = {
            "ix_records_graph_snapshot": "organization_id,repository_id,kind,CAST(key_scope AS VARCHAR)",
            "ix_records_graph_class": "organization_id,repository_id,kind,CAST(key_scope AS VARCHAR),CAST(key_class AS VARCHAR),id",
            "ix_records_graph_source": "organization_id,repository_id,kind,CAST(key_snapshot AS VARCHAR),CAST(key_source AS VARCHAR)",
            "ix_records_graph_target": "organization_id,repository_id,kind,CAST(key_snapshot AS VARCHAR),CAST(key_target AS VARCHAR)",
        }
        for name in definitions:
            connection.execute('CREATE INDEX "' + name + '" ON ' + TABLE + "(" + expressions[name] + ")")
        assert (
            connection.execute("SELECT count(*) FROM records").fetchone()[0]
            == connection.execute("SELECT count(*) FROM " + TABLE).fetchone()[0]
        )
        connection.execute("RELEASE scale001_scalar")
    except BaseException:
        # SQLITE_INTERRUPT may already have rolled back the whole transaction.
        # Preserve the cancellation, rather than masking it with a missing savepoint.
        if connection.in_transaction:
            connection.execute("ROLLBACK TO scale001_scalar")
            connection.execute("RELEASE scale001_scalar")
        raise
    return {
        "mode": "full_membership_scalar_table",
        "historical_harness_label": mode,
        "before": definitions,
        "after": original.definitions(connection),
        "seconds": time.perf_counter() - started,
        "triggers": list(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'scale001_scalar_%' ORDER BY name"
            )
        ),
    }


class ScalarCompiler(SQLiteCompiler):
    def _selected(self):
        return bool(self.stack and getattr(self.stack[-1].get("selectable"), "is_select", False))

    def _group(self, alias):
        ordinal = getattr(self, "_scalar_groups", 0)
        self._scalar_groups = ordinal + 1
        base = self.preparer.quote("__pt_base_" + str(ordinal))
        keys = self.preparer.quote("__pt_keys_" + str(ordinal))
        return (
            "(records AS "
            + base
            + " JOIN "
            + TABLE
            + " AS "
            + keys
            + " ON "
            + keys
            + ".rid="
            + base
            + ".rowid AND "
            + keys
            + ".id="
            + base
            + ".id AND "
            + keys
            + ".organization_id="
            + base
            + ".organization_id AND "
            + keys
            + ".repository_id IS "
            + base
            + ".repository_id AND "
            + keys
            + ".kind="
            + base
            + ".kind) AS "
            + alias
        )

    def visit_table(self, table, asfrom=False, from_linter=None, **kw):
        if asfrom and self._selected() and _is_records(table):
            if from_linter:
                from_linter.froms[table] = table.fullname
            return self._group(self.preparer.quote(table.name))
        return super().visit_table(table, asfrom=asfrom, from_linter=from_linter, **kw)

    def visit_alias(self, alias, asfrom=False, from_linter=None, **kw):
        if asfrom and self._selected() and isinstance(alias, Alias) and _is_records(alias.element):
            name = (
                self._truncated_identifier("alias", alias.name)
                if isinstance(alias.name, elements._truncated_label)
                else alias.name
            )
            if from_linter:
                from_linter.froms[alias._de_clone()] = name
            return self._group(self.preparer.format_alias(alias, name))
        return super().visit_alias(alias, asfrom=asfrom, from_linter=from_linter, **kw)

    def visit_json_getitem_op_binary(self, binary, operator, _cast_applied=False, **kw):
        if self._selected() and kw.get("literal_binds") and binary.type._type_affinity is String:
            path, current = [], binary
            while isinstance(current, elements.BinaryExpression) and current.operator is operators.json_getitem_op:
                value = current.right
                if (
                    not isinstance(value, elements.BindParameter)
                    or not value.unique
                    or value.callable is not None
                    or type(value.value) is not str
                ):
                    break
                path.append(value.value)
                current = current.left
            else:
                table = getattr(current, "table", None)
                real = _is_records(table) if table is not None else False
                aliased = isinstance(table, Alias) and _is_records(table.element)
                if tuple(reversed(path)) in PATHS and getattr(current, "name", None) == "data" and (real or aliased):
                    key = FIELDS[PATHS.index(tuple(reversed(path)))]
                    column = elements.ColumnClause(key, String(), _selectable=table)
                    return "CAST(" + self.process(column, **kw) + " AS VARCHAR)"
        return super().visit_json_getitem_op_binary(binary, operator, _cast_applied=_cast_applied, **kw)


def dialect():
    result = SQLiteDialect()
    result.statement_compiler = ScalarCompiler
    return result


def enable_compiler(engine, counters=None):
    """Owned engine only; no global event listeners or shared metadata changes."""
    with engine.connect() as connection:
        original.writable(connection.connection.driver_connection)
        if not connection.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).first():
            raise ValueError("Scalar projection missing on owned engine.")
    before = engine.dialect.statement_compiler
    engine.clear_compiled_cache()
    engine.dialect.statement_compiler = ScalarCompiler

    def close():
        engine.clear_compiled_cache()
        engine.dialect.statement_compiler = before

    return close


def query_results(connection, *, adapt=False, repeats=7):
    from sqlalchemy.dialects.sqlite import dialect as ordinary_dialect

    from tests.graph_index_compatibility import queries

    projected = bool(connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone())
    results = []
    for name, statement, ordered in queries():
        compiled = statement.compile(
            dialect=dialect() if projected else ordinary_dialect(), compile_kwargs={"render_postcompile": True}
        )
        parameters = tuple(
            compiled._bind_processors[key](compiled.params[key])
            if key in compiled._bind_processors
            else compiled.params[key]
            for key in compiled.positiontup
        )
        sql = str(compiled)
        rows = list(connection.execute(sql, parameters))
        elapsed = []
        for _ in range(repeats):
            started = time.perf_counter()
            again = list(connection.execute(sql, parameters))
            elapsed.append(time.perf_counter() - started)
            assert again == rows
        results.append(
            {
                "name": name,
                "sql": sql,
                "parameters": parameters,
                "rows": rows,
                "plan": list(connection.execute("EXPLAIN QUERY PLAN " + sql, parameters)),
                "sha256": original.digest_rows(rows),
                "seconds": elapsed,
                "ordered_contract": ordered,
            }
        )
    return results
