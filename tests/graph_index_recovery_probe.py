"""Fresh-process opt-in v2 measurements on exactly owned disposable databases."""

import argparse
import json
import sqlite3
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tests import graph_index_prototype as original
from tests import graph_index_recovery as recovery


def publish(root, mode, all_phases=False):
    from tests import graph_index_publication_probe as probe

    with (
        patch.object(probe, "install", recovery.install),
        patch.object(probe, "listen_for_guards", recovery.listen_for_guards),
    ):
        return probe.run(root, mode, 30000 if not all_phases else None, all_phases=all_phases)


def micro(source, root, mode):
    from tests import graph_index_measure as probe

    with patch.object(probe, "install", recovery.install):
        return probe.measure(source, root, mode)


def api(source, root):
    from tests import graph_index_api_probe as probe

    root.mkdir()
    with ExitStack() as stack:
        stack.enter_context(patch.object(original, "install", recovery.install))
        stack.enter_context(patch.object(original, "listen_for_guards", recovery.listen_for_guards))
        results = {
            mode: probe.read_api(original.clone(source, root / (mode + ".db")), mode)
            for mode in ("baseline", "validated_partial")
        }
    differences = [a["case"] for a, b in zip(results["baseline"], results["validated_partial"]) if a != b]
    result = {"responses": results, "differences": differences}
    (root / "result.json").write_text(json.dumps(result, indent=2))
    assert not differences, differences
    return {"requests_per_mode": len(results["baseline"]), "differences": differences}


def mixed(source, root, mode):
    from backend.domain import snapshot_record_query
    from tests.snapshot_materialization_probe import Recorder
    from tests.sqlite_memory_probe import SQLiteMemory
    from tests.test_graph_index_recovery import compiled

    root.mkdir()
    path = original.clone(source, root / "prototype.db")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA cache_size=-32768")
        connection.execute("PRAGMA foreign_keys=ON")
        schema = recovery.install(connection, mode)
        identity = connection.execute(
            "SELECT id FROM records WHERE kind='snapshot' ORDER BY created_at,id LIMIT 1"
        ).fetchone()[0]
        statement = snapshot_record_query("owned-eq", "owned-eq", identity)
        if mode != "baseline":
            statement, _ = recovery.guarded_statement(statement)
        sql, values = compiled(statement)
        recorder, native = Recorder(), SQLiteMemory()
        begun = native.begin()
        with recorder.span("MIXED_COMPLETE_RECORD_QUERY"):
            rows = connection.execute(sql, values).fetchall()
        allocated = native.end(begun)
        recorder.close()
        # Hash complete values after the measured interval; hash allocation is
        # explicitly excluded, never mistaken for query peak.
        digest = original.digest_rows(rows)
        result = {
            "mode": mode,
            "schema": schema,
            "sql": sql,
            "parameters": values,
            "plan": list(connection.execute("EXPLAIN QUERY PLAN " + sql, values)),
            "rows": len(rows),
            "complete_rows_sha256": digest,
            "events": recorder.events,
            "sqlite_malloc": allocated,
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "fk": list(connection.execute("PRAGMA foreign_key_check")),
            "size": original.size(connection),
            "settings": {"cache_size_kib": 32768},
        }
    (root / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("publish", "all_phases", "micro", "api", "mixed"))
    parser.add_argument("root", type=Path)
    parser.add_argument("mode", choices=("baseline", "validated_partial"))
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.operation in ("publish", "all_phases"):
        result = publish(args.root, args.mode, all_phases=args.operation == "all_phases")
        print(
            json.dumps(
                {"states": result["states"], "integrity": result["integrity"], "final_process": result["final_process"]}
            )
        )
    elif args.operation == "api":
        print(json.dumps(api(args.source, args.root)))
    else:
        result = (micro if args.operation == "micro" else mixed)(args.source, args.root, args.mode)
        print(json.dumps({"mode": args.mode, "sqlite_malloc": result["sqlite_malloc"], "events": result["events"]}))
