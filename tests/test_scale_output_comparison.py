import json
import sqlite3

import pytest

from scripts.compare_scale_outputs import fingerprints


def fixture(path, prefix):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE records(id TEXT,kind TEXT,data TEXT);
        CREATE TABLE source_inventories(id TEXT);
        CREATE TABLE source_inventory_files(inventory_id TEXT,path TEXT,digest TEXT,data TEXT);
        CREATE TABLE parser_artifacts(id TEXT,data TEXT);
        CREATE TABLE quality_analyses(snapshot_id TEXT,data TEXT);
        """)
        scope = {"snapshot_id": prefix + "snapshot", "analysis_at": prefix + "time"}
        rows = [
            ("snapshot", "snapshot", {"branch": "owned", "commit": "1" * 40, "source_inventory_id": prefix + "inventory"}),
            ("evidence", "evidence", {"path": "a.py", "hash": "a" * 64, "scope": scope}),
            ("claim", "claim", {"claim_key": "stable-key", "status": "VERIFIED", "evidence_ids": [prefix + "evidence"], "scope": scope}),
            ("node", "graph_node", {"class": "SNAPSHOT", "title": prefix + "snapshot", "identity_id": prefix + "node-identity", "scope": scope}),
            ("edge", "edge", {"source": prefix + "node", "target": prefix + "evidence", "relationship": "HAS_FILE_EVIDENCE", "snapshot_id": prefix + "snapshot"}),
        ]
        db.executemany("INSERT INTO records VALUES (?,?,?)", [(prefix + k, kind, json.dumps(d)) for k, kind, d in rows])
        db.execute("INSERT INTO source_inventories VALUES (?)", (prefix + "inventory",))
        db.execute("INSERT INTO source_inventory_files VALUES (?,?,?,?)", (prefix + "inventory", "a.py", "a" * 64, '{"bytes":4}'))
        db.execute("INSERT INTO parser_artifacts VALUES (?,?)", ("stable-artifact", '{"signals":[{"type":"auth","value":"jwt"}]}'))
        db.execute("INSERT INTO quality_analyses VALUES (?,?)", (prefix + "snapshot", '{"metrics":[{"cyclomatic":2}],"state":"PARTIAL"}'))


@pytest.mark.parametrize("change", ["none", "edge", "missing_edge", "claim", "metric", "source", "artifact"])
def test_comparison_detects_semantic_changes_and_retains_every_graph_edge(tmp_path, change):
    before, after = tmp_path / "before.db", tmp_path / "after.db"
    fixture(before, "before-")
    fixture(after, "after-")
    with sqlite3.connect(after) as db:
        if change in {"edge", "claim"}:
            kind = change
            data = json.loads(db.execute("SELECT data FROM records WHERE kind=?", (kind,)).fetchone()[0])
            data["relationship" if kind == "edge" else "status"] = "INCORRECT_RELATIONSHIP" if kind == "edge" else "CONTRADICTED"
            db.execute("UPDATE records SET data=? WHERE kind=?", (json.dumps(data), kind))
        elif change == "missing_edge":
            db.execute("DELETE FROM records WHERE kind='edge'")
        elif change == "metric":
            db.execute("UPDATE quality_analyses SET data=?", ('{"metrics":[{"cyclomatic":3}],"state":"PARTIAL"}',))
        elif change == "source":
            db.execute("UPDATE source_inventory_files SET digest='changed'")
        elif change == "artifact":
            db.execute("UPDATE parser_artifacts SET data='{}'")
    assert (fingerprints(before) == fingerprints(after)) is (change == "none")


def test_ambiguous_snapshot_identity_fails_instead_of_collapsing_outputs(tmp_path):
    database = tmp_path / "owned.db"
    fixture(database, "owned-")
    with sqlite3.connect(database) as db:
        data = db.execute("SELECT data FROM records WHERE kind='snapshot'").fetchone()[0]
        db.execute("INSERT INTO records VALUES ('another-snapshot','snapshot',?)", (data,))
    with pytest.raises(ValueError, match="never collapse"):
        fingerprints(database)
