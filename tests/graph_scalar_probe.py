"""Fresh owned measurements of the scalar-table prototype, never production DDL."""

import argparse
import ctypes
import json
import sqlite3
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

from tests import graph_index_prototype as original
from tests import graph_scalar_prototype as scalar


class IOCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_operations",
            "write_operations",
            "other_operations",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


def io_stats():
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    ctypes.windll.kernel32.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(IOCounters)]
    ctypes.windll.kernel32.GetProcessIoCounters.restype = wintypes.BOOL
    data = IOCounters()
    if not ctypes.windll.kernel32.GetProcessIoCounters(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(data)):
        raise ctypes.WinError()
    return {name: getattr(data, name) for name, _ in data._fields_}


def publish(root, mode, all_phases=False):
    from tests import graph_index_publication_probe as probe

    def deferred_compiler(engine, counters):
        # The publication probe installs DDL in metadata.after_create. Its old
        # guard hook ran before that event; validate on the creating connection
        # after the earlier DDL listener, rather than opening an unowned DB.
        from sqlalchemy import event

        from backend.db import Base

        before = engine.dialect.statement_compiler
        activated = False

        def activate(target, connection, **kwargs):
            nonlocal activated
            raw = connection.connection.driver_connection
            original.writable(raw)
            assert raw.execute("SELECT 1 FROM sqlite_master WHERE name=?", (scalar.TABLE,)).fetchone()
            engine.clear_compiled_cache()
            engine.dialect.statement_compiler = scalar.ScalarCompiler
            activated = True

        event.listen(Base.metadata, "after_create", activate)

        def close():
            event.remove(Base.metadata, "after_create", activate)
            if activated:
                engine.clear_compiled_cache()
                engine.dialect.statement_compiler = before

        return close

    class IORecorder(probe.pipeline.Recorder):
        @contextmanager
        def span(self, name, **attributes):
            before = io_stats() if name in ("DB_EXECUTE_SNAPSHOT_WRITE", "ATOMIC_PUBLICATION_COMMIT") else None
            with super().span(name, **attributes) as item:
                yield item
            if before is not None:
                after = io_stats()
                item["io_delta"] = {key: after[key] - before[key] for key in before}

    with (
        patch.object(probe, "install", scalar.install),
        patch.object(probe, "listen_for_guards", deferred_compiler),
        patch.object(probe.pipeline, "Recorder", IORecorder),
    ):
        return probe.run(root, mode, None if all_phases else 30000, all_phases=all_phases)


def api(source, root):
    from tests import graph_index_api_probe as probe

    root.mkdir()
    with ExitStack() as stack:
        stack.enter_context(patch.object(original, "install", scalar.install))
        stack.enter_context(patch.object(original, "listen_for_guards", scalar.enable_compiler))
        responses = {
            mode: probe.read_api(original.clone(source, root / (mode + ".db")), mode)
            for mode in ("baseline", "validated_partial")
        }
    differences = [a["case"] for a, b in zip(responses["baseline"], responses["validated_partial"]) if a != b]
    result = {"responses": responses, "differences": differences}
    (root / "result.json").write_text(json.dumps(result, indent=2))
    return result


def component(source, root, mode, operation):
    from backend.domain import snapshot_record_query
    from tests.snapshot_materialization_probe import Recorder
    from tests.sqlite_memory_probe import SQLiteMemory
    from tests.test_graph_scalar_reading import compiled

    root.mkdir()
    path = original.clone(source, root / "prototype.db")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA cache_size=-32768")
        schema = scalar.install(connection, mode)
        identity, version = connection.execute(
            "SELECT id,version FROM records WHERE kind='snapshot' ORDER BY created_at,id LIMIT 1"
        ).fetchone()
        payload = (
            connection.execute("SELECT data FROM records WHERE id=?", (identity,)).fetchone()[0]
            if operation == "micro"
            else None
        )
        recorder, memory = Recorder(), SQLiteMemory()
        native = memory.begin()
        begin_io, begin_changes = io_stats(), connection.total_changes
        if operation == "mixed":
            statement = snapshot_record_query("owned-eq", "owned-eq", identity)
            sql, values = compiled(statement, mode != "baseline")
            with recorder.span("MIXED_COMPLETE_RECORD_QUERY"):
                rows = connection.execute(sql, values).fetchall()
        else:
            sql, values = (
                "UPDATE records SET data=?,version=? WHERE id=? AND version=?",
                (payload, version, identity, version),
            )
            with recorder.span("SAME_VALUE_SNAPSHOT_UPDATE"):
                assert connection.execute(sql, values).rowcount == 1
            rows = None
        allocated = memory.end(native)
        end_io = io_stats()
        changes = connection.total_changes - begin_changes
        with recorder.span("COMMIT"):
            connection.commit()
        committed_io = io_stats()
        recorder.close()
        # Hash work follows measurement, not part of query RSS/native window.
        result = {
            "operation": operation,
            "mode": mode,
            "schema": schema,
            "events": recorder.events,
            "sqlite_malloc": allocated,
            "io_delta": {key: end_io[key] - begin_io[key] for key in begin_io},
            "io_update_plus_commit": {key: committed_io[key] - begin_io[key] for key in begin_io},
            "total_changes": changes,
            "size": original.size(connection),
            "rows": len(rows) if rows is not None else None,
            "complete_rows_sha256": original.digest_rows(rows) if rows is not None else None,
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "fk": list(connection.execute("PRAGMA foreign_key_check")),
            "settings": {"cache_size_kib": 32768},
        }
        if operation == "mixed":
            result.update(
                sql=sql, parameters=values, plan=list(connection.execute("EXPLAIN QUERY PLAN " + sql, values))
            )
        else:
            assert connection.execute("SELECT version,data FROM records WHERE id=?", (identity,)).fetchone() == (
                version,
                payload,
            )
            result["same_values_preserved"] = True
    (root / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("publish", "all_phases", "micro", "mixed", "api"))
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
        result = api(args.source, args.root)
        print(
            json.dumps(
                {"requests_per_mode": len(result["responses"]["baseline"]), "differences": result["differences"]}
            )
        )
    else:
        result = component(args.source, args.root, args.mode, args.operation)
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "events": result["events"],
                    "sqlite_malloc": result["sqlite_malloc"],
                    "io_delta": result["io_delta"],
                    "total_changes": result["total_changes"],
                }
            )
        )
