"""Identical owned datasets, exact SQL results/errors and prototype query plans."""

import json
import sqlite3
import time
from types import SimpleNamespace

from tests.graph_index_prototype import digest_rows, guarded_statement


def insert_record(db, identity, kind, value, *, organization="owned-eq", repository="owned-eq"):
    db.execute(
        "INSERT INTO records(id,organization_id,repository_id,kind,natural_key,data,created_at,version) "
        "VALUES(?,?,?,?,?,?,?,1)",
        (identity, organization, repository, kind, identity, value, "2026-10-27T00:00:00+00:00"),
    )


def seed(db):
    db.execute("INSERT INTO organizations(id,name) VALUES('scale-other','Other owned tenant')")
    columns = [row[1] for row in db.execute("PRAGMA table_info(repositories)")]
    row = dict(zip(columns, db.execute("SELECT * FROM repositories WHERE id='owned-eq'").fetchone()))
    row.update(id="scale-other", organization_id="scale-other", name="Other owned repository")
    db.execute(
        "INSERT INTO repositories(" + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in columns) + ")",
        tuple(row[c] for c in columns),
    )
    for identity in ("compat-a", "compat-b"):
        insert_record(
            db,
            identity,
            "snapshot",
            json.dumps({"branch": "compat", "status": "PARTIAL", "scope": {"snapshot_id": identity}}),
        )
    for n, value in enumerate(("zz", "aa", "東京", "", None, 1, True, {}, [])):
        insert_record(
            db,
            f"compat-snapshot-shape-{n:04}",
            "snapshot",
            json.dumps(
                {
                    "status": "PARTIAL",
                    "scope": {"snapshot_id": "compat-a"},
                    "snapshot_id": "compat-a",
                    "source": value,
                    "target": value,
                    "class": value,
                }
            ),
        )
    fields = [
        None,
        "",
        0,
        1,
        1.5,
        True,
        False,
        "1",
        "01",
        "é",
        "e\u0301",
        "ß",
        "SS",
        "東京",
        "emoji-😀",
        [],
        {},
        ["x"],
        {"x": "y"},
        'quote"\\%_\u0000',
    ]
    for n in range(120):
        value = {
            "scope": {"snapshot_id": "compat-a", "component": "owned"},
            "class": "FUNCTION" if n % 2 else "COMPONENT",
            "path": f"owned/{n}.py",
            "title": f"Owned {n}",
            "severity": "HIGH" if n % 3 else "INFO",
            "status": "VERIFIED",
        }
        insert_record(
            db,
            f"compat-node-{n:04}",
            ("graph_node", "claim", "finding", "evidence", "dependency")[n % 5],
            json.dumps(value),
        )
    for n, value in enumerate(fields):
        insert_record(
            db,
            f"compat-field-{n:04}",
            "graph_node",
            json.dumps({"scope": {"snapshot_id": value}, "class": value, "path": str(value)}),
        )
        insert_record(db, f"compat-empty-{n:04}", "graph_node", json.dumps({"scope": value}))
    for n in range(45):
        value = {
            "snapshot_id": "compat-a",
            "source": f"compat-node-{n % 12:04}",
            "target": f"compat-node-{(n + 1) % 12 if n % 4 else n % 12:04}",
            "relationship": "SELF" if n % 4 == 0 else "LINK",
        }
        insert_record(db, f"compat-edge-{n:04}", "edge", json.dumps(value))
    insert_record(
        db,
        "compat-foreign-node",
        "graph_node",
        json.dumps({"scope": {"snapshot_id": "compat-a", "organization_id": "owned-eq"}, "class": "FUNCTION"}),
        organization="scale-other",
        repository="scale-other",
    )
    insert_record(
        db,
        "compat-foreign-edge",
        "edge",
        json.dumps({"snapshot_id": "compat-a", "source": "compat-node-0001", "target": "compat-node-0002"}),
        organization="scale-other",
        repository="scale-other",
    )
    for n, value in enumerate(
        (
            "{}",
            "[]",
            "null",
            "1",
            '"text"',
            '{"scope":{"snapshot_id":"compat-a","snapshot_id":"compat-b"},"class":"FIRST","class":"SECOND"}',
            '{"scope":{"snapshot_id":"compat-a"},"scope":{"snapshot_id":"compat-b"}}',
            "{scope:{snapshot_id:'compat-a'},class:'JSON5',}",
            '{"scope":{"snapshot_id":"compat-a"},"class":"A\\u0000B"}',
        )
    ):
        insert_record(db, f"compat-legacy-{n:04}", "legacy", value)
    db.commit()


def queries():
    from sqlalchemy import func, or_, select

    from backend.db import Record
    from backend.domain import snapshot_record_query
    from backend.json_query import indexed_text
    from backend.workspace_read import scoped_current

    org, repo, snapshot = "owned-eq", "owned-eq", "compat-a"
    kinds = ["claim", "finding", "graph_node", "dependency", "evidence"]
    scope = indexed_text(Record.data, "scope", "snapshot_id")
    top = indexed_text(Record.data, "snapshot_id")
    base = select(Record).where(
        Record.organization_id == org, Record.repository_id == repo, Record.kind.in_(kinds), scope == snapshot
    )
    result = []

    def add(name, statement, ordered=True):
        result.append((name, statement, ordered))

    for offset in (0, 1, 7, 100, 125):
        add("node_page_" + str(offset), base.order_by(Record.kind, Record.id).offset(offset).limit(7))
    for value in (None, "FUNCTION", "COMPONENT", "FIRST", "1", 1, 1.5, "é", "e\u0301", "ß", "SS", "東京"):
        predicate = (
            indexed_text(Record.data, "class").is_(None)
            if value is None
            else indexed_text(Record.data, "class") == value
        )
        add("class_" + repr(value), base.where(predicate).order_by(Record.id))
    for value in (None, "", 0, 1, "1", "01", True, 1.5, "[]", "{}", "é", "e\u0301", "東京", 'quote"\\%_\u0000'):
        if isinstance(value, (list, dict)):
            continue
        predicate = scope.is_(None) if value is None else scope == value
        add(
            "scope_" + repr(value),
            select(Record)
            .where(Record.organization_id == org, Record.repository_id == repo, Record.kind == "graph_node", predicate)
            .order_by(Record.id),
        )
    add(
        "class_nocase",
        base.where(indexed_text(Record.data, "class").collate("NOCASE") == "function").order_by(Record.id),
    )
    add(
        "all_graph_field_types_and_content",
        select(
            Record.id,
            scope,
            top,
            indexed_text(Record.data, "source"),
            indexed_text(Record.data, "target"),
            indexed_text(Record.data, "class"),
            func.typeof(scope),
        )
        .where(
            Record.organization_id == org,
            Record.repository_id == repo,
            Record.id.startswith("compat-", autoescape=True),
        )
        .order_by(Record.id),
    )
    for needle in ("owned", "%", "_", "é", "\u0000"):
        add(
            "literal_search_" + repr(needle),
            base.where(
                or_(
                    Record.data["path"].as_string().icontains(needle, autoescape=True),
                    Record.data["title"].as_string().icontains(needle, autoescape=True),
                )
            ).order_by(Record.kind, Record.id),
        )
    endpoints = select(Record.id).where(
        Record.organization_id == org, Record.repository_id == repo, Record.kind == "edge", top == snapshot
    )
    for center in ("compat-node-0000", "compat-node-0001", "compat-foreign-node"):
        ids = (
            endpoints.where(indexed_text(Record.data, "source") == center)
            .union(endpoints.where(indexed_text(Record.data, "target") == center))
            .subquery()
        )
        edges = select(Record).join(ids, ids.c.id == Record.id)
        for offset in (0, 1, 7):
            add("neighborhood_" + center + "_" + str(offset), edges.order_by(Record.id).offset(offset).limit(5))
        add("neighbor_total_" + center, select(func.count()).select_from(ids))
    core = snapshot_record_query(org, repo, snapshot).where(
        Record.kind.in_(["claim", "finding", "dependency", "drift"])
    )
    add("existing_core_implicit_order", core, False)
    add("existing_mixed_implicit_order", snapshot_record_query(org, repo, snapshot), False)
    add("mixed_ordered_reference", snapshot_record_query(org, repo, snapshot).order_by(Record.kind, Record.id))
    add(
        "snapshot_scoped",
        select(Record)
        .where(
            Record.organization_id == org, Record.repository_id == repo, Record.kind == "snapshot", scope == snapshot
        )
        .order_by(Record.created_at.desc(), Record.id.desc()),
    )
    add(
        "snapshot_latest",
        select(Record.id, Record.version)
        .where(Record.organization_id == org, Record.repository_id == repo, Record.kind == "snapshot")
        .order_by(Record.created_at.desc(), Record.id.desc())
        .limit(1),
    )
    for kind in ("claim", "finding", "graph_node"):
        q = scoped_current(
            SimpleNamespace(organization_id=org),
            [SimpleNamespace(id=repo)],
            {repo: SimpleNamespace(id=snapshot)},
            [kind],
        )
        add("workspace_page_" + kind, q.order_by(Record.created_at.desc(), Record.id.desc()).offset(1).limit(11))
        add("workspace_count_" + kind, q.with_only_columns(func.count()))
    add(
        "mixed_kind_includes_snapshot",
        select(Record)
        .where(
            Record.organization_id == org,
            Record.repository_id == repo,
            Record.kind.in_(["snapshot", "graph_node"]),
            scope == snapshot,
        )
        .order_by(Record.kind, Record.id),
    )
    return result


def query_results(db, *, adapt=False, repeats=7):
    from sqlalchemy.dialects.sqlite import dialect

    results = []
    for name, statement, ordered in queries():
        original = statement
        statement, changed = guarded_statement(statement) if adapt else (statement, False)
        compiled = statement.compile(dialect=dialect(), compile_kwargs={"render_postcompile": True})
        sql = str(compiled)
        values = compiled.params
        processors = compiled._bind_processors
        parameters = tuple(
            processors[key](values[key]) if key in processors else values[key] for key in compiled.positiontup
        )
        plan = [list(row) for row in db.execute("EXPLAIN QUERY PLAN " + sql, parameters)]
        rows = list(db.execute(sql, parameters))
        elapsed = []
        for _ in range(repeats):
            start = time.perf_counter()
            again = list(db.execute(sql, parameters))
            elapsed.append(time.perf_counter() - start)
            assert again == rows
        results.append(
            {
                "name": name,
                "sql": sql,
                "parameters": parameters,
                "original_sql": str(original.compile(dialect=dialect(), compile_kwargs={"render_postcompile": True})),
                "ordered_contract": ordered,
                "guard_added": changed,
                "plan": plan,
                "rows": rows,
                "sha256": digest_rows(rows),
                "seconds": elapsed,
            }
        )
    return results


def write_inputs(db):
    values = [
        None,
        "",
        "{",
        '{"scope":',
        "not-json",
        "{}",
        "[]",
        "null",
        "1",
        '"text"',
        '{"scope":null}',
        '{"scope":[]}',
        '{"scope":"not-json"}',
        '{"scope":{"snapshot_id":1},"source":{},"target":[],"class":true}',
        '{"scope":{"snapshot_id":"first","snapshot_id":"second"},"class":"A","class":"B"}',
        "{scope:{snapshot_id:'compat-a'},source:Infinity,target:NaN,}",
        b'{"scope":{"snapshot_id":"compat-a"}}',
        b"\x00",
        b"\x8f\xff",
    ]
    try:
        binary = db.execute(
            "SELECT jsonb(?)",
            (json.dumps({"scope": {"snapshot_id": "compat-a"}, "source": "x", "other": {"bad": "ok"}}),),
        ).fetchone()[0]
        values.append(binary)
        for offset in range(len(binary)):
            values.append(binary[:offset] + b"\xff" + binary[offset + 1 :])
    except sqlite3.OperationalError:
        pass
    return values


def writes(db):
    outcomes = []
    for kind in ("snapshot", "graph_node", "edge"):
        for number, value in enumerate(write_inputs(db)):
            db.execute("SAVEPOINT scale001_write")
            try:
                insert_record(db, "write-probe", kind, value)
                row = db.execute("SELECT typeof(data),data FROM records WHERE id=?", ("write-probe",)).fetchone()
                result = {
                    "outcome": "OK",
                    "row": {
                        "storage_type": row[0],
                        "value_type": type(row[1]).__name__,
                        "value": row[1].hex() if isinstance(row[1], bytes) else row[1],
                    },
                    "in_transaction": db.in_transaction,
                }
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
                db.execute("ROLLBACK TO scale001_write")
                db.execute("RELEASE scale001_write")
            assert not db.execute("SELECT 1 FROM records WHERE id='write-probe'").fetchall()
            outcomes.append(
                {
                    "case": kind + ":" + str(number),
                    "input_type": type(value).__name__,
                    "input_hex_or_text": value.hex() if isinstance(value, bytes) else value,
                    "result": result,
                }
            )
    for name, sql, args in [
        ("update_bad_snapshot", "UPDATE records SET data=? WHERE id='compat-a'", ("{",)),
        ("update_kind", "UPDATE records SET kind=? WHERE id='compat-node-0000'", ("snapshot",)),
        (
            "update_scope",
            "UPDATE records SET data=? WHERE id='compat-node-0000'",
            ('{"scope":{"snapshot_id":"compat-b"},"class":4}',),
        ),
        ("cross_tenant_fk", "UPDATE records SET organization_id='scale-other' WHERE id='compat-node-0000'", ()),
        (
            "duplicate_id_bad_json",
            "INSERT INTO records(id,organization_id,repository_id,kind,natural_key,data,created_at,version) VALUES('compat-a','owned-eq','owned-eq','snapshot',NULL,'{','2026',1)",
            (),
        ),
        (
            "duplicate_id_valid_natural_bad_json",
            "INSERT INTO records(id,organization_id,repository_id,kind,natural_key,data,created_at,version) VALUES('compat-a','owned-eq','owned-eq','snapshot','compat-a','{','2026',1)",
            (),
        ),
        ("unique_duplicate", "INSERT INTO records SELECT * FROM records WHERE id='compat-a'", ()),
    ]:
        db.execute("SAVEPOINT scale001_write")
        try:
            db.execute(sql, args)
            result = {"outcome": "OK"}
        except sqlite3.Error as error:
            result = {
                "outcome": "ERROR",
                "class": type(error).__name__,
                "message": str(error),
                "code": error.sqlite_errorcode,
                "name": error.sqlite_errorname,
            }
        finally:
            db.execute("ROLLBACK TO scale001_write")
            db.execute("RELEASE scale001_write")
        outcomes.append({"case": name, "result": result})
    return outcomes
