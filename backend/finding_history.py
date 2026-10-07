"""Branch-safe structural reconciliation over authoritative finding records."""

import uuid
from collections import defaultdict

from backend.db import FindingIdentity, FindingOccurrence, Record, now
from backend.quality_domain import ancestors


def reconcile(db, findings, base, base_records, files):
    prior = [r for r in base_records if r.kind == "finding"]
    by_key, old_files, new_files = defaultdict(list), defaultdict(set), defaultdict(set)
    for row in prior:
        data = row.data
        if data.get("identity_confidence") == "HIGH":
            by_key[(data.get("path"), data.get("structural_key"))].append(row)
        if data.get("file_structure_hash"):
            old_files[data["file_structure_hash"]].add(data["path"])
    for item in findings:
        if item.get("file_structure_hash"):
            new_files[item["file_structure_hash"]].add(item["path"])
    matches, used = {}, set()
    for item in findings:
        candidates = []
        if item.get("identity_confidence") == "HIGH":
            candidates = by_key.get((item["path"], item.get("structural_key")), [])
            structure = item.get("file_structure_hash")
            old = old_files.get(structure, set())
            new = new_files.get(structure, set())
            # Full-file structural equivalence, unique old/new pair, actual removal.
            if not candidates and structure and len(old) == len(new) == 1:
                old_path = next(iter(old))
                if old_path not in files and item["path"] not in {r.data["path"] for r in prior}:
                    candidates = by_key.get((old_path, item.get("structural_key")), [])
        if not candidates and item.get("identity_confidence") != "AMBIGUOUS":
            candidates = [r for r in prior if r.data.get("fingerprint") == item.get("fingerprint")]
        if len(candidates) == 1 and candidates[0].id not in used:
            matches[item["id"]] = (candidates[0], "EXISTING")
            used.add(candidates[0].id)
    # Reopen only from explicit ancestors. No cross-branch/global identity search.
    for parent in ancestors(db, base)[1:] if base else []:
        older = defaultdict(list)
        for item in parent.data.get("findings", []):
            if item.get("identity_confidence") == "HIGH":
                older[(item.get("path"), item.get("structural_key"))].append(item)
        for item in findings:
            key = (item["path"], item.get("structural_key"))
            if item["id"] not in matches and item.get("identity_confidence") == "HIGH" and len(older[key]) == 1:
                row = db.get(Record, older[key][0]["id"])
                if row and row.id not in used:
                    matches[item["id"]] = (row, "REOPENED")
                    used.add(row.id)
    return matches


def project(db, snapshot, findings, prior, matches, *, model_changed, warnings, files):
    current = set()

    def identity(data):
        concept = db.get(FindingIdentity, data["identity_id"])
        if not concept:
            concept = FindingIdentity(
                id=data["identity_id"],
                organization_id=snapshot.organization_id,
                repository_id=snapshot.repository_id,
                introduced_snapshot_id=data.get("introduced_snapshot", snapshot.id),
                rule=data["rule"],
                created_at=data.get("first_seen", now()),
            )
            db.add(concept)
            db.flush()
        return concept

    def event(data, status, finding_id=None):
        identity(data)
        db.add(
            FindingOccurrence(
                id=str(uuid.uuid4()),
                organization_id=snapshot.organization_id,
                repository_id=snapshot.repository_id,
                identity_id=data["identity_id"],
                snapshot_id=snapshot.id,
                finding_id=finding_id,
                status=status,
                data={
                    k: data.get(k)
                    for k in (
                        "path",
                        "line",
                        "end_line",
                        "fingerprint",
                        "identity_version",
                        "identity_confidence",
                        "previous_version_id",
                        "review_identity_id",
                        "reopened_count",
                    )
                }
                | {
                    "branch": snapshot.data["branch"],
                    "commit": snapshot.data["commit"],
                    "reason": status.replace("_", " ").capitalize(),
                },
                created_at=now(),
            )
        )

    for item in findings:
        current.add(item["identity_id"])
        matched = matches.get(item["id"])
        status = "INTRODUCED"
        if matched:
            old, delta = matched
            status = (
                "REOPENED"
                if delta == "REOPENED"
                else "CONTEXT_CHANGED"
                if item["review_identity_id"] != old.data.get("review_identity_id", old.data.get("identity_id"))
                else "MOVED"
                if (item["path"], item["line"]) != (old.data.get("path"), old.data.get("line"))
                else "SEEN"
            )
        event(item, status, item["id"])
    failed_paths = {w.get("path") for w in warnings if w.get("analyzer") in {"PARSING", "IAC", "QUALITY"}}
    for row in prior:
        data = row.data
        if not data.get("identity_id") or data["identity_id"] in current:
            continue
        status = "NOT_OBSERVED" if model_changed or data.get("path") in failed_paths else "RESOLVED"
        # Unsupported/fallback observations cannot establish resolution when source remains.
        if data.get("identity_confidence") != "HIGH" and data.get("path") in files:
            status = "NOT_OBSERVED"
        event(data, status)
