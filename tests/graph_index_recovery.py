"""Opt-in disposable recovery experiment; no production imports or migration.

The three historical mode names describe repaired algorithms here. Unlike the
frozen v1 experiment, every exclusion variant validates snapshot writes. The
reader detects the installed schema, not a test name or expected row sequence.
"""

import time

from tests import graph_index_compatibility as corpus
from tests import graph_index_prototype as original

V1_INSTALL = original.install
V1_GUARD = original.guarded_statement


def install(connection, mode):
    """Retain each index strategy; repair validation in the two unsafe ones."""
    original.writable(connection)
    started = time.perf_counter()
    connection.execute("SAVEPOINT scale001_recovery_install")
    try:
        result = _install(connection, mode)
        connection.execute("RELEASE scale001_recovery_install")
        result["seconds"] = time.perf_counter() - started
        return result
    except BaseException:
        connection.execute("ROLLBACK TO scale001_recovery_install")
        connection.execute("RELEASE scale001_recovery_install")
        raise


def _install(connection, mode):
    validation = validate_legacy_schema(connection)
    result = V1_INSTALL(connection, mode)
    if mode == "guarded":
        # CASE has no TEXT affinity even when its THEN arm is CAST. Restore the
        # original affinity outside CASE in both the index and reader.
        for name, sql in original.definitions(connection).items():
            prefix, columns = sql.split("(", 1)
            values = original.split_columns(columns.rsplit(")", 1)[0])
            values = ["CAST(" + value + " AS VARCHAR)" if value.startswith("CASE ") else value for value in values]
            connection.execute('DROP INDEX "' + name + '"')
            connection.execute(prefix + "(" + ", ".join(values) + ")")
    if mode in ("partial", "guarded"):
        # Same required-column/error-precedence condition as the proven v1
        # validated candidate. No json_valid or narrowed JSON dialect.
        required = [row[1] for row in connection.execute("PRAGMA table_info(records)") if row[3]]
        present = " AND ".join('NEW."' + name + '" IS NOT NULL' for name in required)
        connection.execute("SAVEPOINT scale001_recovery_validation")
        try:
            for operation in ("INSERT", "UPDATE OF data, kind"):
                name = "scale001_snapshot_" + operation.split()[0].lower()
                connection.execute(
                    "CREATE TRIGGER " + name + " BEFORE " + operation + " ON records "
                    "WHEN NEW.kind = 'snapshot' AND " + present + " BEGIN SELECT json_extract(NEW.data, "
                    "'$.scope', '$.snapshot_id', '$.source', '$.target', '$.class'); END"
                )
            connection.execute("RELEASE scale001_recovery_validation")
        except BaseException:
            connection.execute("ROLLBACK TO scale001_recovery_validation")
            connection.execute("RELEASE scale001_recovery_validation")
            raise
    result["recovery_revision"] = 2
    result["legacy_schema_validation"] = validation
    result["after"] = original.definitions(connection)
    result["triggers"] = list(
        connection.execute("SELECT name,sql FROM sqlite_master WHERE name LIKE 'scale001_snapshot_%' ORDER BY name")
    )
    return result


def validate_legacy_schema(connection):
    """Fail closed before relying on hidden rowid or original traversal keys."""
    table_sql = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='records'").fetchone()[0]
    columns = list(connection.execute("PRAGMA table_info(records)"))
    if "WITHOUT ROWID" in table_sql.upper() or any(row[1].lower() in ("rowid", "_rowid_", "oid") for row in columns):
        raise ValueError("Expected unshadowed SQLite hidden rowid.")
    connection.execute("SELECT records.rowid FROM records LIMIT 0")
    info = list(connection.execute("PRAGMA index_xinfo(ix_records_graph_target)"))
    expected = [("organization_id", 1), ("repository_id", 1), ("kind", 1), (None, 1), (None, 1), (None, 0)]
    if (
        len(info) != 6
        or [(row[2], row[5]) for row in info] != expected
        or any(row[3] != 0 or row[4] != "BINARY" for row in info)
        or info[-1][1] != -1
    ):
        raise ValueError("Expected original graph-target ASC/BINARY/rowid traversal.")
    definition = original.definitions(connection).get("ix_records_graph_target", "")
    parts = original.split_columns(definition.split("(", 1)[1].rsplit(")", 1)[0])
    if parts[3:] != [
        "CAST(JSON_EXTRACT(data, '$.\"snapshot_id\"') AS VARCHAR)",
        "CAST(JSON_EXTRACT(data, '$.\"target\"') AS VARCHAR)",
    ]:
        raise ValueError("Expected exact original graph-target CAST/JSON expressions.")
    return {"index_xinfo": info, "hidden_rowid": "unshadowed", "original_index_sql": definition}


def schema_mode(connection):
    definitions = original.definitions(connection)
    if len(definitions) != 4:
        raise ValueError("Four graph indexes required for replay.")
    if all(" WHERE kind != 'snapshot'" in sql for sql in definitions.values()):
        return "partial"
    if all("CASE WHEN kind != 'snapshot'" in sql for sql in definitions.values()):
        return "guarded"
    if all(" WHERE " not in sql.upper() and "CASE " not in sql.upper() for sql in definitions.values()):
        return "baseline"
    raise ValueError("Mixed or unrecognized prototype index schema.")


def _already_excluded(statement):
    from sqlalchemy.sql import operators
    from sqlalchemy.sql.elements import BindParameter, BooleanClauseList

    from backend.db import Record

    def proven(clause):
        if isinstance(clause, BooleanClauseList) and clause.operator is operators.and_:
            return any(proven(child) for child in clause.clauses)
        left, right = getattr(clause, "left", None), getattr(clause, "right", None)
        return (
            getattr(clause, "operator", None) is operators.ne
            and getattr(left, "table", None) is Record.__table__
            and getattr(left, "key", None) == "kind"
            and isinstance(right, BindParameter)
            and right.callable is None
            and type(right.value) is str
            and right.value == "snapshot"
        )

    return any(proven(clause) for clause in statement._where_criteria)


def _legacy_mixed_shape(statement):
    """Only the actual single-Record scoped OR shape, not arbitrary selects."""
    from sqlalchemy.sql import operators
    from sqlalchemy.sql.elements import BindParameter, BooleanClauseList

    from backend.db import Record

    descriptions = statement.column_descriptions
    if (
        len(descriptions) != 1
        or descriptions[0].get("entity") is not Record
        or descriptions[0].get("expr") is not Record
        or statement._order_by_clauses
        or statement._group_by_clauses
        or statement._having_criteria
        or statement._distinct
        or len(statement._where_criteria) != 3
        or len(statement.get_final_froms()) != 1
        or not statement.get_final_froms()[0].compare(Record.__table__)
    ):
        return False
    fixed, matching_scope = set(), False
    scope = Record.data["scope"]["snapshot_id"].as_string()
    top = Record.data["snapshot_id"].as_string()
    for clause in statement._where_criteria:
        if isinstance(clause, BooleanClauseList) and clause.operator is operators.or_ and len(clause.clauses) == 2:
            pairs = list(clause.clauses)
            if all(
                getattr(pair, "operator", None) is operators.eq
                and isinstance(pair.right, BindParameter)
                and pair.right.callable is None
                and type(pair.right.value) is str
                for pair in pairs
            ):
                matching_scope = (
                    pairs[0].left.compare(scope)
                    and pairs[1].left.compare(top)
                    and pairs[0].right.value == pairs[1].right.value
                )
        if getattr(clause, "operator", None) is operators.eq:
            left, right = clause.left, clause.right
            if (
                getattr(left, "table", None) is Record.__table__
                and getattr(left, "key", None) in ("organization_id", "repository_id")
                and isinstance(right, BindParameter)
                and right.callable is None
                and type(right.value) is str
            ):
                fixed.add(left.key)
    return matching_scope and fixed == {"organization_id", "repository_id"}


def legacy_traversal_order(statement):
    """Reproduce measured full graph-target ASC/BINARY traversal plus rowid.

    SQLite-specific compatibility prototype. The caller must validate the old
    schema's index_xinfo/rowid contract. This is not a portable ordering policy.
    """
    from sqlalchemy import Integer, literal_column

    from backend.db import Record
    from backend.json_query import indexed_text

    clauses = (
        Record.organization_id.collate("BINARY").asc(),
        Record.repository_id.collate("BINARY").asc(),
        Record.kind.collate("BINARY").asc(),
        indexed_text(Record.data, "snapshot_id").collate("BINARY").asc(),
        indexed_text(Record.data, "target").collate("BINARY").asc(),
        literal_column("records.rowid", Integer()).asc(),
    )
    return statement.order_by(*(clause._annotate({"scale001_order": True}) for clause in clauses))


def guarded_statement(statement, parameters=None, *, mode="partial", counters=None):
    """Rebuild nested SELECTs before applying the original conservative proof."""
    from sqlalchemy import String, case, cast, literal
    from sqlalchemy.sql import visitors
    from sqlalchemy.sql.base import ExecutableOption
    from sqlalchemy.sql.selectable import CTE, Select

    from backend.db import Record
    from backend.json_query import IndexedText

    if mode == "baseline":
        return statement, False
    if mode not in ("partial", "guarded"):
        raise ValueError("Unknown replay strategy.")
    if any(isinstance(node, CTE) and node.recursive for node in visitors.iterate(statement)):
        if counters is not None:
            counters["refused_recursive_cte"] = counters.get("refused_recursive_cte", 0) + 1
        return statement, False
    refuse_parameters = bool(parameters) or any(
        bool(getattr(node, "_params", None)) for node in visitors.iterate(statement)
    )
    changed, memo = False, {}

    def transform(element):
        nonlocal changed
        if isinstance(element, ExecutableOption):
            # Security/loader options are immutable execution contracts, not
            # query AST subjects. Preserve the exact objects and their guards.
            return element
        if not isinstance(element, Select):
            return None
        if id(element) in memo:
            return memo[id(element)]
        # Replacement traversal stops at replacements: explicitly visit inner
        # selects first, preserving shared references via the memo.
        rebuilt = visitors.replacement_traverse(
            element, {}, lambda child: None if child is element else transform(child)
        )
        # Remove only our own prior additions, then re-prove this final AST.
        # Callers may append predicates/subqueries or change named bind defaults
        # on a transformed statement; inherited flags cannot prove validity.
        rebuilt._where_criteria = tuple(
            clause for clause in rebuilt._where_criteria if not clause._annotations.get("scale001_guard")
        )
        retained_order = [
            clause for clause in rebuilt._order_by_clauses if not clause._annotations.get("scale001_order")
        ]
        rebuilt = rebuilt.order_by(None).order_by(*retained_order)
        current_cleanup = rebuilt

        def unwrap_current(node):
            if isinstance(node, ExecutableOption):
                return node
            if isinstance(node, (Select, CTE)) and node is not current_cleanup:
                return node
            if node._annotations.get("scale001_case"):
                return node.clause.whens[0][1]
            return None

        rebuilt = visitors.replacement_traverse(rebuilt, {}, unwrap_current)
        if not refuse_parameters and _legacy_mixed_shape(rebuilt):
            rebuilt = legacy_traversal_order(rebuilt)
            changed = True
            if counters is not None:
                counters["legacy_order_added"] = counters.get("legacy_order_added", 0) + 1
        updated, guarded = (rebuilt, False) if refuse_parameters or _already_excluded(rebuilt) else V1_GUARD(rebuilt)
        if guarded:
            updated = rebuilt.where(updated._where_criteria[-1]._annotate({"scale001_guard": True}))
            changed = True
            if counters is not None:
                counters["guarded_selects"] = counters.get("guarded_selects", 0) + 1
        if not refuse_parameters and mode == "guarded" and (guarded or _already_excluded(updated)):

            def indexed_case(node):
                if (
                    isinstance(node, IndexedText)
                    and node.path in (("scope", "snapshot_id"), ("snapshot_id",), ("source",), ("target",), ("class",))
                    and node.column.compare(Record.__table__.c.data)
                ):
                    return cast(
                        case((Record.kind != literal("snapshot", literal_execute=True), node)), String()
                    )._annotate({"scale001_case": True})
                return None

            current = updated

            def scoped_case(node):
                if isinstance(node, ExecutableOption):
                    return node
                # A proof for this SELECT says nothing about an inner SELECT
                # over the same table (which may deliberately select snapshots).
                if isinstance(node, (Select, CTE)) and node is not current:
                    return node
                return indexed_case(node)

            updated = visitors.replacement_traverse(updated, {}, scoped_case)
        memo[id(element)] = updated
        return updated

    updated = visitors.replacement_traverse(statement, {}, transform)
    return (statement, False) if updated.compare(statement) else (updated, True)


def listen_for_guards(engine, counters=None, *, mode="partial"):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    if engine.dialect.name != "sqlite":
        raise ValueError("This rowid ordering prototype supports SQLite only.")

    def scoped(execution):
        if execution.is_select and execution.session.get_bind() is engine:
            execution.statement, _ = guarded_statement(
                execution.statement, execution.parameters, mode=mode, counters=counters
            )

    event.listen(Session, "do_orm_execute", scoped)
    return lambda: event.remove(Session, "do_orm_execute", scoped)


def query_results(connection, *, adapt=False, repeats=7):
    """Frozen corpus, new implementation. Never substitute expected results."""
    from sqlalchemy.dialects.sqlite import dialect

    mode = schema_mode(connection)
    results = []
    for name, statement, ordered in corpus.queries():
        before = statement
        statement, changed = guarded_statement(statement, mode=mode)
        compiled = statement.compile(dialect=dialect(), compile_kwargs={"render_postcompile": True})
        parameters = tuple(
            compiled._bind_processors[key](compiled.params[key])
            if key in compiled._bind_processors
            else compiled.params[key]
            for key in compiled.positiontup
        )
        sql = str(compiled)
        plan = [list(row) for row in connection.execute("EXPLAIN QUERY PLAN " + sql, parameters)]
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
                "original_sql": str(before.compile(dialect=dialect(), compile_kwargs={"render_postcompile": True})),
                "ordered_contract": ordered,
                "guard_added": changed,
                "plan": plan,
                "rows": rows,
                "sha256": original.digest_rows(rows),
                "seconds": elapsed,
            }
        )
    return results


def frozen_api_bindings():
    """Explicit dependency bindings for the unchanged v1 assertions/harnesses.

    Only fresh test processes use this. Modes keep their actual index DDL;
    partial and validated converge on the same validation after the repair.
    """
    return {"install": install, "query_results": query_results, "guarded_statement": guarded_statement}


if __name__ == "__main__":
    raise SystemExit("Use an explicit disposable runner; this is not an application command.")
