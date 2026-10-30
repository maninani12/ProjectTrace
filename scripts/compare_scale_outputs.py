"""Canonical owned SQLite benchmark outputs, including every scoped graph edge.

Only known administrative identities/timestamps and generated timing diagnostics
are normalized. This is not a substitute for a completing large-workload replay.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

TIMES = {"analysis_at", "created_at", "updated_at", "finished_at", "first_seen", "last_seen", "reviewed_at"}
DURATIONS = {"duration_ms", "analysis_ms", "quality_ms", "analysis_seconds"}
UNORDERED = {"affected_nodes", "affected_policies", "affected_claims", "affected_findings", "affected_dependencies",
             "affected_documentation", "affected_architecture", "affected_api", "removed_claims", "via"}
KINDS = {"snapshot", "evidence", "claim", "finding", "dependency", "graph_node", "edge", "drift", "risk_path"}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def fingerprints(path):
    connection = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True)
    try:
        rows = [{"id": i, "kind": k, "data": json.loads(d)} for i, k, d in connection.execute("SELECT id,kind,data FROM records")]
        snapshots = {r["id"]: r for r in rows if r["kind"] == "snapshot"}
        ids = {i: "snapshot:" + sha([r["data"]["branch"], r["data"]["commit"]]) for i, r in snapshots.items()}
        if len(set(ids.values())) != len(ids):
            raise ValueError("Ambiguous snapshot comparison identities; never collapse distinct snapshots.")
        inventories = {}
        for identity, in connection.execute("SELECT id FROM source_inventories"):
            files = [[p, h, json.loads(d)] for p, h, d in connection.execute(
                "SELECT path,digest,data FROM source_inventory_files WHERE inventory_id=? ORDER BY path", (identity,))]
            ids[identity] = "inventory:" + sha(files)
            inventories[ids[identity]] = files
        for row in rows:
            if row["kind"] == "job" and row["data"].get("snapshot_id") in ids:
                ids[row["id"]] = "job-for:" + ids[row["data"]["snapshot_id"]]

        def operational(key, value):
            return isinstance(value, dict) and (
                key == "performance" and (value.get("schema") == "projecttrace-performance-v1" or set(value) == {"quality_ms"})
                or key == "observation_spill" and value.get("scope") == "ATTEMPT_PRIVATE_ENCRYPTED_TYPED_ROWS")

        def normalize(value, key=None):
            if key in TIMES:
                return "ADMINISTRATIVE_TIMESTAMP"
            if key in DURATIONS:
                return "MEASURED_DURATION"
            if isinstance(value, dict):
                return {k: normalize(v, k) for k, v in value.items() if not operational(k, v)}
            if isinstance(value, list):
                normalized = [normalize(v) for v in value]
                return sorted(normalized, key=lambda v: json.dumps(v, sort_keys=True)) if key in UNORDERED else normalized
            return ids.get(value, value) if isinstance(value, str) else value

        def scope(row):
            return row["data"].get("scope", {}).get("snapshot_id") or row["data"].get("snapshot_id")

        for row in rows:
            data = row["data"]
            if row["kind"] == "graph_node" and data.get("identity_id"):
                ids[data["identity_id"]] = "graph-identity:" + sha([
                    data.get("class"), normalize(data.get("title")), data.get("path"), data.get("policy_key")])
        for kind in ("evidence", "claim", "finding", "dependency", "graph_node", "drift", "risk_path", "edge"):
            for row in rows:
                if row["kind"] != kind or scope(row) not in snapshots:
                    continue
                data = row["data"]
                identity = ([data.get("path"), data.get("hash")] if kind == "evidence" else
                            [data.get("claim_key")] if kind == "claim" else
                            [data.get("fingerprint"), data.get("path"), data.get("line")] if kind == "finding" else normalize(data))
                ids[row["id"]] = kind + ":" + sha([ids[scope(row)], identity])
        result = {}
        for identity, snapshot in snapshots.items():
            selected = {kind: [] for kind in KINDS}
            selected["snapshot"] = [normalize(snapshot["data"])]
            for row in rows:
                if row["kind"] in KINDS - {"snapshot"} and scope(row) == identity:
                    selected[row["kind"]].append(normalize(row["data"]))
            for kind in selected:
                selected[kind].sort(key=lambda row: json.dumps(row, sort_keys=True))
            quality = connection.execute("SELECT data FROM quality_analyses WHERE snapshot_id=?", (identity,)).fetchone()
            if quality:
                selected["quality_projection"] = [normalize(json.loads(quality[0]))]
            result[ids[identity]] = {k: {"count": len(v), "sha256": sha(v)} for k, v in sorted(selected.items())}
        artifacts = [[i, normalize(json.loads(d))] for i, d in connection.execute("SELECT id,data FROM parser_artifacts ORDER BY id")]
        return {"snapshots": result, "source_inventories": {k: {"count": len(v), "sha256": sha(v)} for k, v in inventories.items()},
                "parser_artifacts": {"count": len(artifacts), "sha256": sha(artifacts)},
                "sqlite_integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_violations": len(connection.execute("PRAGMA foreign_key_check").fetchall())}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before, after = fingerprints(args.before), fingerprints(args.after)
    equal = before == after
    args.output.write_text(json.dumps({"equal": equal, "before": before, "after": after,
        "normalization": {"timestamps": sorted(TIMES), "durations": sorted(DURATIONS), "id_sets": sorted(UNORDERED),
                          "operational_fields": "Generated performance/spill diagnostics only; unknown fields retained",
                          "ids": "Known job/snapshot/inventory/scoped record/graph identities replaced by semantic references"}}, indent=2))
    print(json.dumps({"equal": equal, "snapshots": len(before["snapshots"])}))
    if not equal:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
