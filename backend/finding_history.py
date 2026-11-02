"""Branch-safe structural reconciliation over authoritative finding records."""

import uuid
from collections import defaultdict

from sqlalchemy import select

from backend.analysis_budget import checkpoint
from backend.db import FindingIdentity, FindingOccurrence, Record, now
from backend.quality_domain import ancestors


def reconcile(db, findings, base, base_records, files, *, path_context=None):
    before_path, after_path = (lambda p: p), (lambda p: p)
    scoped = False
    unresolved = False
    if path_context:
        before, after = path_context
        before_path, after_path = before.path, after.path
        scoped = bool(base) and (before.public or after.public)
        unresolved = before.state.startswith("UNRESOLVED") or after.state.startswith("UNRESOLVED")

    def supported(data):
        return (data.get("identity_version") == "structural-v2" and
                data.get("fingerprint_version") in {"native-statement-v1", "quality-symbol-v2"})

    def native(data):
        return data.get("category") in {"QUALITY", "SAST", "SECRET", "IAC"}

    def key(data, path):
        return (path(data.get("path")), data.get("rule"), data.get("structural_key"))
    prior = [r for r in base_records if r.kind == "finding"]
    by_key, by_fingerprint, old_files, new_files = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(set),
        defaultdict(set),
    )
    prior_paths = {before_path(r.data["path"]) for r in prior}
    unsupported = {(before_path(r.data.get("path")), r.data.get("rule")) for r in prior
                   if native(r.data) and not supported(r.data)}
    for row in prior:
        checkpoint(db)
        data = row.data
        by_fingerprint[data.get("fingerprint")].append(row)
        if data.get("identity_confidence") == "HIGH" and (not scoped or supported(data)):
            by_key[key(data, before_path)].append(row)
        if data.get("file_structure_hash"):
            old_files[data["file_structure_hash"]].add(before_path(data["path"]))
    for item in findings:
        checkpoint(db)
        if item.get("file_structure_hash"):
            new_files[item["file_structure_hash"]].add(after_path(item["path"]))
    matches, used = {}, set()
    for item in findings:
        checkpoint(db)
        if scoped and native(item) and (unresolved or not supported(item) or item.get("identity_confidence") != "HIGH"):
            item["identity_resolution"] = "UNRESOLVED"
            continue
        candidates = []
        if item.get("identity_confidence") == "HIGH":
            candidates = by_key.get(key(item, after_path), [])
            structure = item.get("file_structure_hash")
            old = old_files.get(structure, set())
            new = new_files.get(structure, set())
            # Full-file structural equivalence, unique old/new pair, actual removal.
            if not candidates and structure and len(old) == len(new) == 1:
                old_path = next(iter(old))
                head_old_path = (path_context[1].prefix + old_path) if path_context else old_path
                if head_old_path not in files and after_path(item["path"]) not in prior_paths:
                    candidates = by_key.get((old_path, item.get("rule"), item.get("structural_key")), [])
        if len(candidates) > 1:
            item["identity_resolution"] = "UNRESOLVED"
            continue
        if not candidates and item.get("identity_confidence") != "AMBIGUOUS":
            candidates = by_fingerprint.get(item.get("fingerprint"), [])
            if scoped and native(item):
                candidates = [r for r in candidates if supported(r.data) and
                              before_path(r.data.get("path")) == after_path(item["path"])]
        if len(candidates) == 1 and candidates[0].id not in used:
            matches[item["id"]] = (candidates[0], "EXISTING")
            used.add(candidates[0].id)
        elif scoped and (after_path(item["path"]), item.get("rule")) in unsupported:
            item["identity_resolution"] = "UNRESOLVED"
    # Reopen only from explicit ancestors. No cross-branch/global identity search.
    for parent in ancestors(db, base)[1:] if base else []:
        checkpoint(db)
        older = defaultdict(list)
        parent_path = before_path
        if scoped:
            from backend.db import Repository
            from backend.public_snapshot_paths import for_snapshot
            repository = db.get(Repository, parent.repository_id)
            resolver = for_snapshot(db, parent.data, parent.organization_id, parent.repository_id,
                                    repository.name, public_expected=True)
            if resolver.state.startswith("UNRESOLVED"):
                continue
            parent_path = resolver.path
        for item in parent.data.get("findings", []):
            checkpoint(db)
            if item.get("identity_confidence") == "HIGH" and (not scoped or supported(item)):
                older[key(item, parent_path)].append(item)
        for item in findings:
            checkpoint(db)
            anchor = key(item, after_path)
            if (item["id"] not in matches and item.get("identity_resolution") != "UNRESOLVED"
                    and item.get("identity_confidence") == "HIGH" and len(older[anchor]) == 1):
                row = db.get(Record, older[anchor][0]["id"])
                if row and row.id not in used:
                    matches[item["id"]] = (row, "REOPENED")
                    used.add(row.id)
    return matches


def project(db, snapshot, findings, prior, matches, *, model_changed, warnings, files, path_context=None):
    current, batch = set(), []

    def flush_checked():
        checkpoint(db, force=True)
        if not db.info.get("analysis_output_checkpoint"):
            db.flush()

    def publish_batch():
        if not batch:
            return
        # Establish finding/snapshot parents before the independent projection
        # mappers. Keep ordinary ORM tenant guards and immediate SQL FKs active.
        flush_checked()
        identities = {data["identity_id"] for data, _, _ in batch}
        concepts = {
            row.id: row for row in db.scalars(select(FindingIdentity).where(FindingIdentity.id.in_(identities)))
        }
        for data, _, _ in batch:
            checkpoint(db)
            concept = concepts.get(data["identity_id"])
            if concept and (concept.organization_id, concept.repository_id) != (
                snapshot.organization_id,
                snapshot.repository_id,
            ):
                raise ValueError("Cross-tenant finding identity reference rejected.")
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
                concepts[concept.id] = concept
        flush_checked()
        for data, status, finding_id in batch:
            checkpoint(db)
            generation = db.info.get("analysis_generation")
            identity = (str(uuid.uuid5(uuid.UUID(snapshot.id), f"history:{data['identity_id']}:{status}:{finding_id}"))
                        if generation else str(uuid.uuid4()))
            if generation and db.get(FindingOccurrence, identity):
                continue
            db.add(
                FindingOccurrence(
                    id=identity,
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
                            "identity_resolution",
                        )
                    }
                    | {
                        "branch": snapshot.data["branch"],
                        "commit": snapshot.data["commit"],
                        "reason": "Identity comparison unresolved; introduction or resolution is not established."
                        if data.get("identity_resolution") == "UNRESOLVED" else status.replace("_", " ").capitalize(),
                    },
                    created_at=now(),
                )
            )
        flush_checked()
        batch.clear()

    def event(data, status, finding_id=None):
        batch.append((data, status, finding_id))
        if len(batch) == 250:
            publish_batch()

    for item in findings:
        checkpoint(db)
        current.add(item["identity_id"])
        matched = matches.get(item["id"])
        status = "NOT_OBSERVED" if item.get("identity_resolution") == "UNRESOLVED" else "INTRODUCED"
        if matched:
            old, delta = matched
            status = (
                "REOPENED"
                if delta == "REOPENED"
                else "CONTEXT_CHANGED"
                if item["review_identity_id"] != old.data.get("review_identity_id", old.data.get("identity_id"))
                else "MOVED"
                if ((path_context[1].path(item["path"]) if path_context else item["path"]), item["line"]) != (
                    path_context[0].path(old.data.get("path")) if path_context else old.data.get("path"), old.data.get("line"))
                else "SEEN"
            )
        event(item, status, item["id"])
    failed_paths = {w.get("path") for w in warnings if w.get("analyzer") in {"PARSING", "IAC", "QUALITY"}}
    uncertain = {((path_context[1].path(f["path"]) if path_context else f["path"]), f.get("rule"))
                 for f in findings if f.get("identity_resolution") == "UNRESOLVED"}
    for row in prior:
        checkpoint(db)
        data = row.data
        if not data.get("identity_id") or data["identity_id"] in current:
            continue
        comparison_path = path_context[1].prefix + path_context[0].path(data.get("path")) if path_context else data.get("path")
        status = "NOT_OBSERVED" if model_changed or comparison_path in failed_paths else "RESOLVED"
        scoped = path_context and (path_context[0].public or path_context[1].public)
        if scoped and data.get("category") in {"QUALITY", "SAST", "SECRET", "IAC"} and (any(p.state.startswith("UNRESOLVED") for p in path_context)
                       or data.get("identity_version") != "structural-v2"
                       or data.get("fingerprint_version") not in {"native-statement-v1", "quality-symbol-v2"}
                       or data.get("identity_confidence") != "HIGH"
                       or (path_context[0].path(data.get("path")), data.get("rule")) in uncertain):
            status = "NOT_OBSERVED"
            warning = {"analyzer": "NATIVE_HISTORY", "state": "PARTIAL",
                       "message": "Native finding identity is unresolved; history does not establish introduction or resolution."}
            if warning not in warnings:
                warnings.append(warning)
        # Unsupported/fallback observations cannot establish resolution when source remains.
        if data.get("identity_confidence") != "HIGH" and data.get("path") in files:
            status = "NOT_OBSERVED"
        event(data, status)
    publish_batch()
