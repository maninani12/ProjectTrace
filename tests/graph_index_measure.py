"""Fresh-process same-value snapshot UPDATE on an explicitly owned DB copy."""

import argparse
import gc
import hashlib
import json
import sqlite3
from pathlib import Path

from tests.graph_index_prototype import clone, install, size
from tests.snapshot_materialization_probe import Recorder
from tests.sqlite_memory_probe import SQLiteMemory


def text_hash(value):
    combined = hashlib.sha256()
    for offset in range(0, len(value), 65536):
        combined.update(value[offset : offset + 65536].encode())
    return combined.hexdigest()


def measure(source, root, mode):
    root.mkdir()
    path = clone(source, root / "prototype.db")
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA cache_size=-32768")
    schema = install(db, mode)
    identity, version, payload = db.execute(
        "SELECT id,version,data FROM records WHERE kind='snapshot' ORDER BY created_at,id LIMIT 1"
    ).fetchone()
    before = text_hash(payload)
    initial_size = size(db)
    gc.collect()
    recorder = Recorder()
    memory = SQLiteMemory()
    native = memory.begin()
    # Keep exact bytes and version unchanged: exercise index maintenance without
    # changing even the disposable copy's immutable snapshot contents/pointers.
    with recorder.span("SAME_VALUE_SNAPSHOT_UPDATE"):
        cursor = db.execute(
            "UPDATE records SET data=?,version=? WHERE id=? AND version=?", (payload, version, identity, version)
        )
        assert cursor.rowcount == 1
    sqlite_memory = memory.end(native)
    with recorder.span("COMMIT"):
        db.commit()
    with recorder.span("ROLLBACK_UPDATE"):
        db.execute(
            "UPDATE records SET data=?,version=? WHERE id=? AND version=?", (payload, version, identity, version)
        )
        db.rollback()
    assert db.execute("SELECT version,data FROM records WHERE id=?", (identity,)).fetchone() == (version, payload)
    final_size = size(db)
    integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    foreign = db.execute("PRAGMA foreign_key_check").fetchall()
    generations = db.execute("SELECT state,count(*) FROM analysis_generations GROUP BY state").fetchall()
    pointers = db.execute("SELECT generation_id,revision FROM published_generations ORDER BY branch").fetchall()
    recorder.close()
    db.close()
    result = {
        "scope": "DISPOSABLE_SAME_VALUE_UPDATE_ONLY",
        "mode": mode,
        "source": str(source),
        "database": str(path),
        "sqlite_version": sqlite3.sqlite_version,
        "schema": schema,
        "input_sha256": before,
        "input_characters": len(payload),
        "snapshot_id": identity,
        "snapshot_version": version,
        "events": recorder.events,
        "sqlite_malloc": sqlite_memory,
        "before_size": initial_size,
        "after_size": final_size,
        "integrity": integrity,
        "foreign_keys": foreign,
        "generation_states": generations,
        "pointers": pointers,
        "same_values_preserved": True,
        "settings": {"cache_size_kib": 32768, "foreign_keys": True, "journal": "WAL"},
    }
    (root / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("mode")
    args = parser.parse_args()
    result = measure(args.source, args.root, args.mode)
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "update_seconds": result["events"][0]["seconds"],
                "process_peak_rss": result["events"][0]["after"].get("peak_rss_bytes"),
                "sqlite_malloc": result["sqlite_malloc"],
            }
        )
    )
