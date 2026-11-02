"""Disposable-only graph-index candidates. Never imported by application code."""

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

NAMES = ("ix_records_graph_class", "ix_records_graph_snapshot", "ix_records_graph_source", "ix_records_graph_target")
MODES = ("baseline", "rebuilt", "partial", "validated_partial", "guarded")


def mark(path):
    path = Path(path).resolve()
    allowed = os.environ.get("SCALE001_PROTOTYPE_ROOT")
    if not allowed or not path.is_relative_to(Path(allowed).resolve()):
        raise ValueError("Disposable database must be under the explicitly configured prototype root.")
    # Mutation requires an exact, explicit ownership marker beside this DB.
    marker = path.with_suffix(".scale001-disposable")
    marker.write_text(str(path))
    return path


def writable(connection):
    path = Path(connection.execute("PRAGMA database_list").fetchone()[2]).resolve()
    marker = path.with_suffix(".scale001-disposable")
    allowed = os.environ.get("SCALE001_PROTOTYPE_ROOT")
    if (
        not allowed
        or not path.is_relative_to(Path(allowed).resolve())
        or not marker.exists()
        or marker.read_text() != str(path)
    ):
        raise ValueError("Refusing index mutation without exact disposable database ownership.")
    return path


def clone(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    allowed = os.environ.get("SCALE001_PROTOTYPE_ROOT")
    if not allowed or not destination.is_relative_to(Path(allowed).resolve()):
        raise ValueError("Refusing copy outside explicit disposable ownership root.")
    if source == destination or destination.exists():
        raise ValueError("Disposable destination must be new and distinct.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect("file:" + source.as_posix() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(destination) as target:
            original.backup(target)
    return mark(destination)


def split_columns(text):
    parts, start, depth, quote = [], 0, 0, None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
        index += 1
    parts.append(text[start:].strip())
    return parts


def definitions(connection):
    return dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE name IN (?,?,?,?) ORDER BY name", NAMES))


def install(connection, mode):
    path = writable(connection)
    if mode not in MODES:
        raise ValueError("Unknown prototype mode.")
    original = definitions(connection)
    if set(original) != set(NAMES):
        raise ValueError("All four original graph indexes are required; legacy schema is not silently upgraded.")
    if any(" WHERE " in sql.upper() or "CASE " in sql.upper() for sql in original.values()):
        raise ValueError("Expected original full graph indexes, not an already modified schema.")
    started = time.perf_counter()
    if mode != "baseline":
        connection.execute("SAVEPOINT scale001_indexes")
        try:
            for name, sql in original.items():
                connection.execute('DROP INDEX "' + name + '"')
                if mode == "rebuilt":
                    candidate = sql
                elif mode in ("partial", "validated_partial"):
                    candidate = sql + " WHERE kind != 'snapshot'"
                else:
                    prefix, columns = sql.split("(", 1)
                    values = split_columns(columns.rsplit(")", 1)[0])
                    values = [
                        "CASE WHEN kind != 'snapshot' THEN " + value + " END" if "JSON_" in value else value
                        for value in values
                    ]
                    candidate = prefix + "(" + ", ".join(values) + ")"
                connection.execute(candidate)
            if mode == "validated_partial":
                # Preserve malformed snapshot JSON rejection using the existing
                # JSON1 parser, not json_valid's narrower strict-text semantics.
                # Multi-path extraction visits every graph-indexed root field
                # through one parse. No new SQLite feature or Python UDF.
                required = [row[1] for row in connection.execute("PRAGMA table_info(records)") if row[3]]
                present = " AND ".join('NEW."' + name + '" IS NOT NULL' for name in required)
                for operation in ("INSERT", "UPDATE OF data, kind"):
                    name = "scale001_snapshot_" + operation.split()[0].lower()
                    connection.execute(
                        "CREATE TRIGGER " + name + " BEFORE " + operation + " ON records "
                        "WHEN NEW.kind = 'snapshot' AND " + present + " BEGIN SELECT json_extract(NEW.data, "
                        "'$.scope', '$.snapshot_id', '$.source', '$.target', '$.class'); END"
                    )
            connection.execute("RELEASE scale001_indexes")
        except BaseException:
            connection.execute("ROLLBACK TO scale001_indexes")
            connection.execute("RELEASE scale001_indexes")
            raise
    return {
        "mode": mode,
        "database": str(path),
        "before": original,
        "after": definitions(connection),
        "triggers": list(
            connection.execute("SELECT name,sql FROM sqlite_master WHERE name LIKE 'scale001_snapshot_%' ORDER BY name")
        ),
        "seconds": time.perf_counter() - started,
    }


def guarded_statement(statement, parameters=None):
    """Prove an AND-conjunct excludes snapshots; leave everything else untouched.

    No alias guessing, OR/NOT inference, collation changes, or runtime bind
    overrides. This is a prototype query adapter, not production code.
    """
    from sqlalchemy import literal
    from sqlalchemy.sql import operators
    from sqlalchemy.sql.elements import BindParameter, BooleanClauseList

    from backend.db import Record

    if parameters:
        return statement, False

    def proven(clause):
        if isinstance(clause, BooleanClauseList) and clause.operator is operators.and_:
            return any(proven(child) for child in clause.clauses)
        left, right = getattr(clause, "left", None), getattr(clause, "right", None)
        if getattr(left, "table", None) is not Record.__table__ or getattr(left, "key", None) != "kind":
            return False
        if not isinstance(right, BindParameter) or right.callable is not None:
            return False
        if clause.operator is operators.eq:
            return type(right.value) is str and right.value != "snapshot"
        if clause.operator is operators.in_op:
            values = right.value
            return (
                isinstance(values, (list, tuple, set, frozenset))
                and bool(values)
                and all(type(value) is str and value != "snapshot" for value in values)
            )
        return False

    if any(proven(clause) for clause in getattr(statement, "_where_criteria", ())):
        return statement.where(Record.kind != literal("snapshot", literal_execute=True)), True
    return statement, False


def listen_for_guards(engine, counters=None):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    def scoped(execution):
        if not execution.is_select or execution.session.get_bind() is not engine:
            return
        updated, changed = guarded_statement(execution.statement, execution.parameters)
        if changed:
            execution.statement = updated
            if counters is not None:
                counters["guarded_statements"] = counters.get("guarded_statements", 0) + 1

    event.listen(Session, "do_orm_execute", scoped)
    return lambda: event.remove(Session, "do_orm_execute", scoped)


def digest_rows(rows):
    def typed(value):
        return ["blob", value.hex()] if isinstance(value, bytes) else [type(value).__name__, value]

    return hashlib.sha256(
        json.dumps([[typed(value) for value in row] for row in rows], ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def size(connection):
    result = {
        "page_size": connection.execute("PRAGMA page_size").fetchone()[0],
        "page_count": connection.execute("PRAGMA page_count").fetchone()[0],
        "freelist_count": connection.execute("PRAGMA freelist_count").fetchone()[0],
    }
    try:
        result["objects"] = list(
            connection.execute("SELECT name,sum(pgsize),sum(payload),count(*) FROM dbstat GROUP BY name ORDER BY name")
        )
    except sqlite3.OperationalError as error:
        result["dbstat_unavailable"] = str(error)
    return result
