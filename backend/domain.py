import difflib
import json
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import or_, select

from analyzers.code_quality.classification import ownership, ownership_rules
from analyzers.engine import PARSER_SIGNATURE, VERSION, analyze, hash_text, redact, validate_files
from analyzers.verifiers import claim_key
from backend import quality_domain
from backend.analysis_budget import checkpoint as output_checkpoint
from backend.db import CloudAsset, Record, now
from backend.record_identity import record_uid


def uid():
    return str(uuid.uuid4())


def add(db, org, repo, kind, data, natural_key=None, *, defer_flush=False):
    checkpoint = db.info.get("analysis_output_checkpoint")
    if checkpoint:
        output_checkpoint(db, flush=not defer_flush)
        count = db.info.get("analysis_output_records", 0) + 1
        db.info["analysis_output_records"] = count
        if count >= 250:
            db.info["analysis_output_records"] = 0
    if kind in {"claim", "finding", "snapshot", "risk_path", "graph_node"}:
        data = {
            **data,
            "trust": {
                "schema": "projecttrace-trust-v1",
                "authority": data.get("authority", "STATIC"),
                "method": data.get("provider", "ProjectTrace deterministic analysis"),
                "analyzer_version": data.get("analyzer_version", VERSION),
                "rule_version": data.get("rule_version", VERSION),
                "confidence": data.get("confidence", "UNSPECIFIED"),
                "scope": data.get("scope"),
                "precision": data.get("precision_status", "UNMEASURED"),
                "runtime_observed": data.get("runtime_observed", False),
                "limitations": data.get(
                    "limitations", ["Interpret within the captured evidence and supported static analysis scope."]
                ),
            },
        }
    identity = record_uid()
    record = Record(
        id=identity, organization_id=org, repository_id=repo, kind=kind, natural_key=natural_key or identity, data=data
    )
    db.add(record)
    # Output rows use explicit UUIDs, so dependent graph JSON can refer to a
    # pending row. Keep snapshots immediately flushed for their SQL FK, and
    # bound other publication batches to 250 rows in the same atomic transaction.
    if not defer_flush and (not checkpoint or kind == "snapshot" or count >= 250):
        db.flush()
    if kind == "job":
        from backend.admin_quotas import attribute_job
        attribute_job(db,record)
    return record


def audit(db, user, action, target, data, repo=None):
    from backend.admin_models import ActivityEvent
    from backend.trust import append_audit
    event=append_audit(db, user, action, target, data, repo)
    category="ADMINISTRATION" if data.get("permission") else "ANALYSIS" if action.startswith(("ANALYSIS_","JOB_","SNAPSHOT_")) else "AUTHENTICATION" if action.startswith(("LOGIN_","LOGOUT","OIDC_","SESSION_")) else "APPLICATION"
    # Offline maintenance actors retain their existing audit identity but have
    # no authenticated user ID. Do not attribute their activity to a customer.
    db.add(ActivityEvent(id=uid(),organization_id=user.organization_id,actor_id=getattr(user,"id",None),repository_id=repo,
        action=action,category=category,outcome="FAILED" if "FAILED" in action else "DENIED" if "DENIED" in action else "SUCCEEDED",
        target_id=str(target)[:100],correlation_id=str(data.get("request_id") or data.get("command_id") or target)[:100],
        data={"audit_event_id":event.id,**{key:data[key] for key in ("permission","source","snapshot_id","retry_count","error_type") if key in data}}))
    return event


def policy_gate(claims, findings, exceptions=(), *, new_findings_only=False):
    active = set()
    for exception in exceptions:
        try:
            expiry = datetime.fromisoformat(exception["expires_at"])
            if expiry.tzinfo is not None and expiry > datetime.now(timezone.utc):
                target = exception.get("identity_id") or exception["target"]
                if isinstance(target, str) and target:
                    active.add(target)
        except (KeyError, TypeError, ValueError):
            # Invalid/ambiguous exception dates cannot suppress a policy result.
            continue

    def exempt(item):
        return bool({item.get("id"), item.get("review_identity_id", item.get("identity_id"))} & active)

    results = []
    for f in findings:
        if new_findings_only and f.get("delta") in {"EXISTING", "ANALYZER_BASELINE"}:
            continue
        if exempt(f) or f.get("review_status") in {"RESOLVED", "FALSE_POSITIVE"}:
            continue
        if f["severity"] == "CRITICAL" and f.get("confidence") == "HIGH" and f.get("blocking_eligible") is True:
            results.append(
                {
                    "policy": "No high-confidence critical findings",
                    "version": 1,
                    "result": "FAIL",
                    "target": f.get("id"),
                    "reason": f["title"],
                }
            )
        elif f["severity"] in {"CRITICAL", "HIGH"}:
            results.append(
                {
                    "policy": "Review material security risks",
                    "version": 1,
                    "result": "REVIEW_REQUIRED",
                    "target": f.get("id"),
                    "reason": f["title"],
                }
            )
        elif f.get("category") == "QUALITY" and f["severity"] == "MEDIUM" and f.get("new_code"):
            results.append(
                {
                    "policy": "Review maintainability on changed lines",
                    "version": 1,
                    "result": "WARNING",
                    "target": f.get("id"),
                    "reason": f["title"],
                }
            )
    for c in claims:
        if c["status"] == "CONTRADICTED" and not exempt(c):
            results.append(
                {
                    "policy": "Review contradicted engineering claims",
                    "version": 1,
                    "result": "REVIEW_REQUIRED",
                    "target": c.get("id"),
                    "reason": c["text"],
                }
            )
    if not results:
        results = [
            {
                "policy": "Default engineering gate",
                "version": 1,
                "result": "PASS",
                "reason": "No current blocking or review-required result in supported analysis scope.",
            }
        ]
    status = (
        "FAIL"
        if any(r["result"] == "FAIL" for r in results)
        else "REVIEW_REQUIRED"
        if any(r["result"] == "REVIEW_REQUIRED" for r in results)
        else "WARNING"
        if any(r["result"] == "WARNING" for r in results)
        else "PASS"
    )
    return {"overall": status, "mode": "ADVISORY", "results": results}


def snapshot_record_query(organization_id, repository_id, snapshot_id):
    return select(Record).where(
        Record.organization_id == organization_id,
        Record.repository_id == repository_id,
        or_(
            Record.data["scope"]["snapshot_id"].as_string() == snapshot_id,
            Record.data["snapshot_id"].as_string() == snapshot_id,
        ),
    )


def scoped_snapshot_records(db, organization_id, repository_id, snapshot_id, *, core=False):
    """Read one authorized version; large analyses keep their non-graph core only."""
    if not snapshot_id:
        return []
    query = snapshot_record_query(organization_id, repository_id, snapshot_id)
    if core:
        query = query.where(Record.kind.in_(["claim", "finding", "dependency", "drift"]))
    return list(db.scalars(query))


def impact_graph_records(db, organization_id, repository_id, snapshot_id, changed, *, limit=5000):
    """Load a bounded reverse neighborhood, never the entire repository graph."""
    if not snapshot_id or not changed:
        return [], False
    base = snapshot_record_query(organization_id, repository_id, snapshot_id)
    seeds = list(
        db.scalars(base.where(Record.kind == "evidence", Record.data["path"].as_string().in_(changed)).limit(limit + 1))
    )
    truncated = len(seeds) > limit
    found = {row.id: row for row in seeds[:limit]}
    frontier, seen = set(found), set()
    traversable = {
        "SUPPORTED_BY",
        "CONTRADICTED_BY",
        "DOCUMENTED_BY",
        "DETECTED_IN",
        "DECLARED_IN",
        "HAS_FILE_EVIDENCE",
        "IMPLEMENTED_IN",
        "DERIVED_FROM",
        "AFFECTS",
        "EXPOSES",
    }
    for _ in range(5):
        frontier -= seen
        if not frontier:
            break
        seen.update(frontier)
        remaining = max(0, limit - len(found))
        if not remaining:
            truncated = True
            break
        edges = list(
            db.scalars(
                base.where(
                    Record.kind == "edge",
                    Record.data["target"].as_string().in_(frontier),
                    Record.data["relationship"].as_string().in_(traversable),
                )
                .order_by(Record.id)
                .limit(remaining + 1)
            )
        )
        truncated |= len(edges) > remaining
        edges = edges[:remaining]
        for row in edges:
            found[row.id] = row
        identifiers = {row.data["source"] for row in edges} - set(found)
        if len(found) + len(identifiers) > limit:
            identifiers = set(sorted(identifiers)[: max(0, limit - len(found))])
            truncated = True
        nodes = list(db.scalars(base.where(Record.id.in_(identifiers)))) if identifiers else []
        found.update((row.id, row) for row in nodes)
        frontier = {row.id for row in nodes}
        if len(found) >= limit:
            truncated = True
            break
    return list(found.values()), truncated


def evidence_signature(item, evidence_by_id):
    return sorted(
        (evidence_by_id[eid].get("path"), evidence_by_id[eid].get("hash"))
        for eid in item.get("evidence_ids", [])
        if eid in evidence_by_id
    )


def graph_impact(base_records, head_records, changed_files, base_id, head_id):
    """Traverse observed dependency edges, including evidence removed in the head.

    These are static dependency/review impacts, not runtime reachability or a risk score.
    Containment edges are intentionally not traversed: a changed file must not imply
    that every other artifact in its repository has changed.
    """
    empty = {
        "base_id": base_id,
        "head_id": head_id,
        "changed_files": changed_files,
        "affected_claims": [],
        "affected_documentation": [],
        "affected_architecture": [],
        "affected_api": [],
        "affected_findings": [],
        "affected_policies": [],
        "removed_claims": [],
        "affected_nodes": [],
        "method": "OBSERVED_REVERSE_GRAPH_DEPENDENCIES",
        "limitations": ["Static evidence associations only; runtime reachability is unobserved."],
    }
    if not base_id:
        return {**empty, "initial_baseline": True}
    node_kinds = {"claim", "finding", "evidence", "dependency", "graph_node"}
    traversable = {
        "SUPPORTED_BY",
        "CONTRADICTED_BY",
        "DOCUMENTED_BY",
        "DETECTED_IN",
        "DECLARED_IN",
        "HAS_FILE_EVIDENCE",
        "IMPLEMENTED_IN",
        "DERIVED_FROM",
        "AFFECTS",
        "EXPOSES",
    }
    changed = set(changed_files)
    affected, visited = {}, set()
    for records in [base_records, head_records]:
        nodes = {r.id: r for r in records if r.kind in node_kinds}
        reverse = {}
        for record in records:
            if record.kind == "edge" and record.data.get("relationship") in traversable:
                source, target = record.data.get("source"), record.data.get("target")
                if source in nodes and target in nodes:
                    reverse.setdefault(target, []).append((source, record.id))
        queue = deque((r.id, []) for r in records if r.kind == "evidence" and r.data.get("path") in changed)
        while queue:
            identifier, via = queue.popleft()
            if identifier in visited:
                continue
            visited.add(identifier)
            record = nodes[identifier]
            data = record.data
            affected[identifier] = {
                "id": identifier,
                "class": "FILE_EVIDENCE" if record.kind == "evidence" else data.get("class") or record.kind.upper(),
                "path": data.get("path"),
                "snapshot_id": data.get("scope", {}).get("snapshot_id"),
                "via": via,
            }
            queue.extend((source, [*via, edge_id]) for source, edge_id in reverse.get(identifier, []))

    head_nodes = {r.id: r for r in head_records if r.kind in node_kinds}
    head_identities = {r.data["identity_id"]: r.id for r in head_nodes.values() if r.data.get("identity_id")}
    head_claim_keys = {
        r.data.get("claim_key") or claim_key(r.data): r.id for r in head_nodes.values() if r.kind == "claim"
    }
    head_fingerprints = {r.data.get("fingerprint"): r.id for r in head_nodes.values() if r.kind == "finding"}
    head_structures = {
        (r.data.get("class"), r.data.get("title"), r.data.get("path")): r.id
        for r in head_nodes.values()
        if r.kind == "graph_node"
    }
    all_nodes = {r.id: r for r in [*base_records, *head_records] if r.kind in node_kinds}
    current_ids = set()
    removed_claims = set()
    documents = set()
    for identifier in affected:
        record = all_nodes[identifier]
        identity = record.data.get("identity_id")
        mapped = identifier if identifier in head_nodes else head_identities.get(identity)
        if not mapped and record.kind == "claim":
            mapped = head_claim_keys.get(record.data.get("claim_key") or claim_key(record.data))
        elif not mapped and record.kind == "finding":
            mapped = head_fingerprints.get(record.data.get("fingerprint"))
        elif not mapped and record.kind == "graph_node":
            mapped = head_structures.get((record.data.get("class"), record.data.get("title"), record.data.get("path")))
        if mapped:
            current_ids.add(mapped)
        elif record.kind == "claim":
            removed_claims.add(identity or identifier)
        if record.kind == "claim" and record.data.get("origin", "DOCUMENTATION") == "DOCUMENTATION":
            documents.add(record.data.get("path"))
        if record.kind == "graph_node" and record.data.get("class") == "DOCUMENTATION_SECTION":
            documents.add(record.data.get("path"))

    def identifiers(kind=None, classes=()):
        return sorted(
            identifier
            for identifier in current_ids
            if (kind and head_nodes[identifier].kind == kind) or head_nodes[identifier].data.get("class") in classes
        )

    return {
        **empty,
        "initial_baseline": False,
        "affected_claims": identifiers("claim"),
        "affected_documentation": sorted(p for p in documents if p),
        "affected_architecture": identifiers(classes={"COMPONENT", "API_ENDPOINT"}),
        "affected_api": identifiers(classes={"API_ENDPOINT"}),
        "affected_findings": identifiers("finding"),
        "affected_policies": identifiers(classes={"POLICY"}),
        "removed_claims": sorted(removed_claims),
        "affected_nodes": [affected[k] for k in sorted(affected)],
    }


def persist_analysis(
    db,
    user,
    repo,
    files,
    branch="main",
    base_id=None,
    pr_number=None,
    advisory_cache=None,
    git_commit=None,
    pr_title=None,
    progress=None,
    job_id=None,
):
    if repo.organization_id != user.organization_id:
        raise ValueError("Repository does not belong to the current organization.")
    if job_id:
        linked_job = db.get(Record, job_id)
        if not linked_job or (
            linked_job.kind, linked_job.organization_id, linked_job.repository_id
        ) != ("job", user.organization_id, repo.id):
            raise ValueError("Analysis job does not belong to the selected repository.")
    from backend.repository_store import BlobStore, RepositoryFiles

    stored_input = isinstance(files, RepositoryFiles)
    if not stored_input:
        files = validate_files(files, keep_excluded=True)
    digest = hash_text(
        "\n".join(p + ":" + (files.hash_for(p) if stored_input else hash_text(files[p])) for p in sorted(files))
    )
    if getattr(files, "intake", []):
        digest = hash_text(digest + json.dumps(files.intake, sort_keys=True))
    from backend.quality_profiles import effective as effective_profile

    profile, _ = effective_profile(db, user.organization_id, repo.id)
    base_id = base_id or profile.get("quality", {}).get("baseline_id")
    key = hash_text(
        json.dumps(
            {
                "organization": user.organization_id,
                "repository": repo.id,
                "branch": branch,
                "content": digest,
                "analyzer": VERSION,
                "parser_signature": PARSER_SIGNATURE,
                "base": base_id,
                "advisories": advisory_cache or {},
                "native_profile": profile,
                "git_commit": git_commit,
            },
            sort_keys=True,
        )
    )
    existing = db.scalar(
        select(Record).where(
            Record.organization_id == user.organization_id, Record.kind == "snapshot", Record.natural_key == key
        )
    )
    if existing:
        # Idempotent reuse must retain the snapshot's original capture/job
        # provenance. Each later job already links to this snapshot separately.
        return existing
    if stored_input and base_id:
        from backend.snapshot_context import comparison_snapshot

        base = comparison_snapshot(db, base_id, user.organization_id, repo.id)
    else:
        base = db.get(Record, base_id) if base_id else None
    if base_id and not base:
        raise ValueError("Base snapshot does not exist.")
    if base and (
        base.organization_id != user.organization_id or base.repository_id != repo.id or base.kind != "snapshot"
    ):
        raise ValueError("Base snapshot does not belong to the selected repository.")
    base_data = base.data if base else {}
    if progress:
        progress("PARSING")
    if stored_input:
        from backend.partitioned_analysis import analyze_inventory

        result = analyze_inventory(
            db, files, progress=progress, verification_context=base_data.get("verification_cache"), profile=profile
        )
    else:
        result = analyze(
            files,
            base_data.get("analysis_cache"),
            progress,
            verification_context=base_data.get("verification_cache"),
            profile=profile,
        )
    if getattr(progress, "retain_completed_analysis", None):
        progress.retain_completed_analysis(result, files)
    if progress:
        progress("BUILDING_EVIDENCE")
    previous_hashes = base_data.get("hashes", {})
    hashes = {p: files.hash_for(p) if stored_input else hash_text(files[p]) for p in files}
    changed = sorted(p for p in set(hashes) | set(previous_hashes) if hashes.get(p) != previous_hashes.get(p))
    base_parser = base_data.get("parser_signature") or next(
        (
            item.get("parser_signature")
            for item in base_data.get("analysis_cache", {}).values()
            if item.get("parser_signature")
        ),
        None,
    )
    model_changed = bool(base) and (
        base_data.get("analyzer_version") != VERSION or bool(base_parser) and base_parser != PARSER_SIGNATURE
    )
    captured_snapshot_data = {
        **({"job_id": job_id} if job_id else {}),
        "branch": branch,
        "commit": git_commit or digest[:40],
        "commit_source": "GIT_SHA" if git_commit else "CONTENT_DIGEST",
        "hashes": hashes,
        "changed_files": changed,
        "comparison": {
            "source_changed": bool(changed),
            "analysis_model_changed": model_changed,
            "base_analyzer_version": base_data.get("analyzer_version"),
            "head_analyzer_version": VERSION,
        },
        "analyzer_version": VERSION,
        "base_id": base_id,
        "parser_signature": PARSER_SIGNATURE,
        "analysis_at": now(),
        "status": "PARTIAL"
        if result["warnings"]
        else "COMPLETED"
        if result["findings"]
        else "COMPLETED_NO_FINDINGS",
        "warnings": result["warnings"],
        "claim_extraction": {
            "state": result.get("engines", {}).get("CLAIMS", {}).get("state", "UNKNOWN"),
            "implementation": sum(c.get("origin") == "IMPLEMENTATION" for c in result["claims"]),
            "documentation": sum(c.get("origin") == "DOCUMENTATION" for c in result["claims"]),
            "documentation_files": result["documentation_files"],
        },
        "analyzer_results": {
            "files": len(files),
            "claims": len(result["claims"]),
            "native_findings": len(result["findings"]),
            "dependencies": len(result["dependencies"]),
            "reused_files": result["reused_files"],
        },
        "file_count": len(files),
        "analysis_cache": result["analysis_cache"],
        **(
            {"source_storage": result["source_storage"], "source_inventory_id": files.inventory_id,
             "source_provenance": files.data.get("provenance", {})}
            if stored_input
            else {}
        ),
        "verification_cache": result.get("verification_cache", {}),
        "engines": result.get("engines", {}),
        "native_profile": profile,
        "quality_metrics": result.get("quality_metrics", []),
        "analysis_coverage": result.get("analysis_coverage", {}),
        "reused_files": result["reused_files"],
        "limitations": [
            "Static analysis only; runtime not connected.",
            "Content digest is not a Git commit SHA.",
            "Unsupported claim types remain unverified.",
        ],
    }
    initial_snapshot_data = (
        {name: captured_snapshot_data[name] for name in (
            "branch", "commit", "analysis_at", "analyzer_version", "parser_signature",
            "base_id", "status", "limitations", "file_count", "source_inventory_id", "job_id",
        ) if name in captured_snapshot_data}
        if stored_input else captured_snapshot_data
    )
    # The row ID is needed for dependent records. Persist the repository-sized
    # captured payload once, after temporary analysis collections are released.
    snapshot = add(db, user.organization_id, repo.id, "snapshot", initial_snapshot_data, key)
    if stored_input:
        from backend.db import SnapshotInventory

        db.add(
            SnapshotInventory(
                snapshot_id=snapshot.id,
                organization_id=user.organization_id,
                repository_id=repo.id,
                inventory_id=files.inventory_id,
            )
        )
    scope = {
        "organization_id": user.organization_id,
        "system": repo.system,
        "component": repo.component,
        "repository": repo.name,
        "repository_id": repo.id,
        "branch": branch,
        "commit": git_commit or digest[:40],
        "snapshot_id": snapshot.id,
        "analyzer_version": VERSION,
        "rule_version": VERSION,
        "analysis_at": snapshot.data["analysis_at"],
    }

    def path_scope(path):
        if stored_input and files.metadata_for(path):
            metadata = files.metadata_for(path)
            return {
                **scope,
                "component": files.component_for(path),
                "component_root": metadata.get("component_root", "."),
                "component_basis": metadata.get("component_basis", "REPOSITORY_ASSIGNMENT"),
            }
        return scope

    base_records = scoped_snapshot_records(db, user.organization_id, repo.id, base_id, core=stored_input)
    if stored_input and base_id:
        rows = db.execute(
            snapshot_record_query(user.organization_id, repo.id, base_id)
            .where(Record.kind == "evidence")
            .with_only_columns(
                Record.id,
                Record.data["path"].as_string().label("path"),
                Record.data["hash"].as_string().label("hash"),
                Record.data["source_blob_digest"].as_string().label("source_blob_digest"),
            )
        )
        base_evidence = {row.id: dict(row._mapping) for row in rows}
    else:
        base_evidence = {r.id: r.data for r in base_records if r.kind == "evidence"}
    base_claim_records = {r.id: r for r in base_records if r.kind == "claim"}
    base_findings = {r.data.get("fingerprint"): r for r in base_records if r.kind == "finding"}
    evidence, head_evidence = {}, {}
    added_line_counts = {}
    evidence_store = files.store if stored_input else None
    previous_evidence_by_path = {item.get("path"): item for item in base_evidence.values()}
    publication_performance = getattr(progress, "performance", None)
    publication_started = time.perf_counter()
    for path in result["files"]:
        output_checkpoint(db)
        file_started = time.perf_counter()
        previous_file = previous_evidence_by_path.get(path, {})
        retained_digest = previous_file.get("source_blob_digest") if previous_file.get("hash") == hashes[path] else None
        if stored_input:
            if not retained_digest:
                # RepositoryFiles already decrypts and verifies the captured digest.
                # Reuse that reference only when redaction leaves the bytes intact.
                # Changed/redacted evidence still goes through checked blob storage.
                read_started = time.perf_counter()
                source = files[path]
                if publication_performance:
                    publication_performance.record("EVIDENCE_SOURCE_READ", time.perf_counter() - read_started)
                redact_started = time.perf_counter()
                redacted = redact(source)
                if publication_performance:
                    publication_performance.record("EVIDENCE_REDACTION", time.perf_counter() - redact_started)
                if path not in previous_evidence_by_path:
                    added_line_counts[path] = len(redacted.splitlines())
                store_started = time.perf_counter()
                retained_digest = (
                    hashes[path]
                    if hash_text(redacted) == hashes[path]
                    else evidence_store.put(db, user.organization_id, redacted.encode())[0]
                )
                if publication_performance:
                    publication_performance.record("EVIDENCE_BLOB_STORE", time.perf_counter() - store_started)
            source_data = {"source_blob_digest": retained_digest}
        else:
            source_data = {"source": redact(files[path])}
        node = add(
            db,
            user.organization_id,
            repo.id,
            "evidence",
            {
                "path": path,
                **source_data,
                "hash": hashes[path],
                "class": "DOCUMENTATION" if path.endswith(".md") else "SOURCE_CODE",
                "authority": "DECLARED" if path.endswith(".md") else "STATIC",
                "scope": path_scope(path),
            },
        )
        evidence[path] = node.id
        head_evidence[node.id] = {"path": path, "hash": hashes[path]}
        if publication_performance:
            publication_performance.record("EVIDENCE_FILE", time.perf_counter() - file_started, path)
    if publication_performance:
        publication_performance.record("EVIDENCE_FILES", time.perf_counter() - publication_started)
    publication_started = time.perf_counter()
    previous_claims = {c.get("claim_key") or claim_key(c): c for c in base_data.get("claims", [])}
    matched_previous_ids = set()
    claims, findings, drifts = [], [], []
    # Strong references to this attempt's findings prevent repeated SELECTs and
    # per-finding autoflushes after SQLAlchemy's weak identity map releases rows.
    finding_records = {}
    for data in result["claims"]:
        from backend.claim_read import inventory_basis
        data = inventory_basis(data)
        data = data.copy()
        signals = data.pop("signals")
        key = data.get("claim_key") or claim_key(data)
        identity_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"projecttrace:{user.organization_id}:{repo.id}:{key}"))
        previous = previous_claims.get(key)
        if not previous:
            legacy = [
                c
                for c in previous_claims.values()
                if not c.get("claim_key")
                and (c.get("path"), c.get("category"), c.get("expected"), c.get("origin", "DOCUMENTATION"))
                == (data.get("path"), data.get("category"), data.get("expected"), data.get("origin", "DOCUMENTATION"))
            ]
            # Migrate unambiguous legacy identity in place; never guess between facts.
            if len(legacy) == 1:
                previous = legacy[0]
        if previous:
            matched_previous_ids.add(previous.get("id"))
        evidence_ids = list(dict.fromkeys([evidence[data["path"]]] + [evidence[s["path"]] for s in signals]))
        supporting = list(dict.fromkeys(evidence[s["path"]] for s in signals))
        previous_record = base_claim_records.get((previous or {}).get("id"))
        previous_data = previous_record.data if previous_record else previous or {}
        unchanged = bool(previous) and evidence_signature(previous_data, base_evidence) == evidence_signature(
            {"evidence_ids": evidence_ids}, head_evidence
        )
        history = (previous or {}).get("history", [])[:]
        if previous and (previous["status"] != data["status"] or not unchanged and not data.get("verification_reused")):
            history.append(
                {
                    "status": "STALE",
                    "at": now(),
                    "reason": "Analysis rules changed; reverification required."
                    if model_changed and not changed
                    else "Related evidence changed; reverification required.",
                }
            )
        history.append({"status": data["status"], "at": now(), "snapshot_id": snapshot.id, "reason": data["reason"]})
        claim = add(
            db,
            user.organization_id,
            repo.id,
            "claim",
            {
                **data,
                "claim_key": key,
                "identity_id": identity_id,
                "claim_version": (previous or {}).get("claim_version", 1) + 1 if previous else 1,
                "previous_version_id": (previous or {}).get("id"),
                "evidence_ids": evidence_ids,
                "supporting_ids": supporting if data["status"] in {"VERIFIED", "INFERRED"} else [],
                "contradicting_ids": supporting if data["status"] == "CONTRADICTED" else [],
                "scope": path_scope(data["path"]),
                "owner": previous_data.get("owner", repo.owner) if unchanged else repo.owner,
                "review_status": previous_data.get("review_status", "OPEN") if unchanged else "OPEN",
                "review_reason": previous_data.get("review_reason") if unchanged else None,
                "review_identity_id": previous_data.get("review_identity_id", identity_id)
                if unchanged
                else identity_id
                if not previous
                else uid(),
                "history": history,
                "recommendation": "Update the documentation or provide stronger scoped evidence."
                if data["status"] != "VERIFIED"
                else "Keep this claim linked to future implementation changes.",
            },
        )
        packed = {"id": claim.id, **claim.data}
        claims.append(packed)
        for eid in evidence_ids:
            relation = (
                "CONTRADICTED_BY"
                if eid in claim.data["contradicting_ids"]
                else "SUPPORTED_BY"
                if eid in claim.data["supporting_ids"]
                else "DOCUMENTED_BY"
            )
            add(
                db,
                user.organization_id,
                repo.id,
                "edge",
                {"source": claim.id, "target": eid, "relationship": relation, "snapshot_id": snapshot.id},
            )
        if previous and previous["status"] != data["status"] and changed:
            drift = add(
                db,
                user.organization_id,
                repo.id,
                "drift",
                {
                    "claim_id": claim.id,
                    "identity_id": identity_id,
                    "previous_version_id": (previous or {}).get("id"),
                    "base_id": base_id,
                    "text": data["text"],
                    "type": data["category"] + "_DRIFT"
                    if data["category"] in {"API", "ARCHITECTURE"}
                    else "DOCUMENTATION_DRIFT",
                    "path": data["path"],
                    "old_status": (previous or {}).get("status", "UNVERIFIED"),
                    "status": data["status"],
                    "reason": data["reason"],
                    "severity": data["severity"],
                    "owner": repo.owner,
                    "scope": scope,
                    "pr_number": pr_number,
                    "review_status": "OPEN",
                },
            )
            drifts.append({"id": drift.id, **drift.data})
        if (
            data["status"] == "CONTRADICTED"
            or data["category"] == "API"
            and data["origin"] == "DOCUMENTATION"
            and data["status"] == "UNVERIFIED"
        ):
            record = add(
                db,
                user.organization_id,
                repo.id,
                "finding",
                {
                    "title": "Documentation consistency: " + data["text"],
                    "category": "CONSISTENCY",
                    "severity": data["severity"],
                    "confidence": data["confidence"],
                    "path": data["path"],
                    "line": data["line"],
                    "rule": "PT-CONSISTENCY-001",
                    "explanation": data["reason"],
                    "remediation": "Review the contract/documentation against the linked current implementation evidence.",
                    "evidence_ids": evidence_ids,
                    "claim_id": claim.id,
                    "scope": scope,
                    "owner": repo.owner,
                    "provider": "ProjectTrace native",
                    "review_status": "OPEN",
                },
            )
            findings.append({"id": record.id, **record.data})
            finding_records[record.id] = record
            add(
                db,
                user.organization_id,
                repo.id,
                "edge",
                {"source": record.id, "target": claim.id, "relationship": "AFFECTS", "snapshot_id": snapshot.id},
            )
        audit(
            db,
            user,
            "CLAIM_VERIFIED",
            claim.id,
            {
                "old": (previous or {}).get("status"),
                "new": data["status"],
                "snapshot_id": snapshot.id,
                "reason": data["reason"],
            },
            repo.id,
        )
    if publication_performance:
        publication_performance.record("PUBLISH_CLAIMS", time.perf_counter() - publication_started)
    if base and changed:
        current_keys = {c["claim_key"] for c in claims}
        for key, previous in previous_claims.items():
            if key not in current_keys and previous.get("id") not in matched_previous_ids:
                record = add(
                    db,
                    user.organization_id,
                    repo.id,
                    "drift",
                    {
                        "text": previous["text"],
                        "identity_id": previous.get("identity_id"),
                        "previous_version_id": previous.get("id"),
                        "path": previous.get("path"),
                        "type": "CLAIM_REMOVED",
                        "old_status": previous["status"],
                        "status": "REMOVED",
                        "severity": "MEDIUM",
                        "reason": "This supported claim no longer exists in the new source/documentation snapshot.",
                        "base_id": base.id,
                        "scope": scope,
                        "owner": repo.owner,
                        "review_status": "OPEN",
                    },
                )
                drifts.append({"id": record.id, **record.data})
    if model_changed and not changed:
        change = {
            "base_id": base_id,
            "snapshot_id": snapshot.id,
            "scope": scope,
            "base_analyzer_version": base_data.get("analyzer_version"),
            "head_analyzer_version": VERSION,
            "reason": "Source hashes are unchanged. Updated analyzer rules establish a new analysis baseline; this is not software drift.",
        }
        event = add(db, user.organization_id, repo.id, "analysis_change", change)
        audit(db, user, "ANALYSIS_RULES_CHANGED", event.id, change, repo.id)
    publication_started = time.perf_counter()
    owners_by_path = {}
    owner_rules = ownership_rules(files)
    for data in result["findings"]:
        if data.get("category") == "QUALITY" and data["path"] not in owners_by_path:
            owners_by_path[data["path"]] = ownership(data["path"], files, repo.owner, rules=owner_rules)
        record = add(
            db,
            user.organization_id,
            repo.id,
            "finding",
            {
                **data,
                "evidence_ids": [evidence[data["path"]]],
                "scope": path_scope(data["path"]),
                **(
                    owners_by_path[data["path"]]
                    if data.get("category") == "QUALITY"
                    else {"owner": repo.owner}
                ),
                "provider": "ProjectTrace native",
            },
        )
        findings.append({"id": record.id, **record.data})
        finding_records[record.id] = record
        add(
            db,
            user.organization_id,
            repo.id,
            "edge",
            {
                "source": record.id,
                "target": evidence[data["path"]],
                "relationship": "DETECTED_IN",
                "snapshot_id": snapshot.id,
            },
        )
    if publication_performance:
        publication_performance.record("PUBLISH_FINDINGS", time.perf_counter() - publication_started)
    publication_started = time.perf_counter()
    deps, sca_issues = [], {}
    for d in result["dependencies"]:
        cache_key = f"{d['ecosystem']}:{d['name']}@{d['version']}"
        cached = (advisory_cache or {}).get(cache_key)
        if cached is not None:
            cached = [{**v, "summary": redact(v.get("summary", ""))} for v in cached]
        data = {
            **d,
            "scope": path_scope(d["path"]),
            "vulnerability_status": "VULNERABLE"
            if cached
            else "CHECKED_NO_KNOWN_ADVISORY"
            if cached is not None
            else "UNKNOWN_VERSION"
            if d.get("version_kind") != "EXACT"
            else "NOT_CHECKED",
            "vulnerabilities": cached or [],
        }
        dep = add(db, user.organization_id, repo.id, "dependency", data)
        deps.append({"id": dep.id, **data})
        add(
            db,
            user.organization_id,
            repo.id,
            "edge",
            {
                "source": dep.id,
                "target": evidence[d["path"]],
                "relationship": "DECLARED_IN",
                "snapshot_id": snapshot.id,
            },
        )
        for vulnerability in cached or []:
            issue_key = f"{cache_key}:{vulnerability['id']}"
            if issue_key in sca_issues:
                record = sca_issues[issue_key]
                record.data = {
                    **record.data,
                    "evidence_ids": list(dict.fromkeys([*record.data["evidence_ids"], evidence[d["path"]]])),
                    "dependency_ids": [*record.data["dependency_ids"], dep.id],
                    "manifest_paths": list(dict.fromkeys([*record.data["manifest_paths"], d["path"]])),
                }
                next(f for f in findings if f["id"] == record.id).update(record.data)
                add(
                    db,
                    user.organization_id,
                    repo.id,
                    "edge",
                    {
                        "source": record.id,
                        "target": dep.id,
                        "relationship": "AFFECTS",
                        "snapshot_id": snapshot.id,
                    },
                )
                add(
                    db,
                    user.organization_id,
                    repo.id,
                    "edge",
                    {
                        "source": record.id,
                        "target": evidence[d["path"]],
                        "relationship": "DETECTED_IN",
                        "snapshot_id": snapshot.id,
                    },
                )
                continue
            record = add(
                db,
                user.organization_id,
                repo.id,
                "finding",
                {
                    "title": f"{d['name']} {d['version']} Â· {vulnerability['id']}",
                    "category": "SCA",
                    "package_key": cache_key,
                    "fingerprint": hash_text(issue_key),
                    "dependency_ids": [dep.id],
                    "manifest_paths": [d["path"]],
                    "severity": vulnerability.get("severity", "UNKNOWN"),
                    "confidence": "HIGH",
                    "path": d["path"],
                    "line": 1,
                    "rule": vulnerability["id"],
                    "provider_finding_id": vulnerability["id"],
                    "rule_version": VERSION,
                    "analyzer_version": VERSION,
                    "explanation": redact(
                        vulnerability.get("summary", "Known vulnerability reported by cached OSV data.")
                    ),
                    "remediation": "Upgrade to a version outside the advisory affected range; review the linked advisory.",
                    "advisory": vulnerability,
                    "provider": "OSV cached advisory",
                    "evidence_ids": [evidence[d["path"]]],
                    "scope": scope,
                    "owner": repo.owner,
                    "review_status": "OPEN",
                },
            )
            sca_issues[issue_key] = record
            findings.append({"id": record.id, **record.data})
            finding_records[record.id] = record
            add(
                db,
                user.organization_id,
                repo.id,
                "edge",
                {"source": record.id, "target": dep.id, "relationship": "AFFECTS", "snapshot_id": snapshot.id},
            )
            add(
                db,
                user.organization_id,
                repo.id,
                "edge",
                {
                    "source": record.id,
                    "target": evidence[d["path"]],
                    "relationship": "DETECTED_IN",
                    "snapshot_id": snapshot.id,
                },
            )
    if publication_performance:
        publication_performance.record("PUBLISH_DEPENDENCIES", time.perf_counter() - publication_started)
    if progress:
        progress("CORRELATING")
    correlation_started = time.perf_counter()

    old_evidence_by_path = {item.get("path"): item for item in base_evidence.values()}

    def old_source(path):
        item = old_evidence_by_path.get(path, {})
        if item.get("source_blob_digest"):
            return BlobStore().read(user.organization_id, item["source_blob_digest"]).decode("utf-8")
        if stored_input and item.get("id"):
            return db.get(Record, item["id"]).data.get("source", "")
        return item.get("source", "")

    @lru_cache(maxsize=1)
    def head_lines(path):
        # One parser-bounded file only; preserve whole-file redaction and offsets.
        return redact(files.get(path, "")).splitlines()

    @lru_cache(maxsize=1)
    def old_lines(path):
        return old_source(path).splitlines()

    changed_lines = {}
    for path in changed:
        output_checkpoint(db)
        if path in added_line_counts:
            count = added_line_counts[path]
            changed_lines[path] = [(1, count)] if count else []
            continue
        old, head = old_lines(path), head_lines(path)
        changed_lines[path] = [
            (j1 + 1, max(j1 + 1, j2))
            for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, old, head, autojunk=False).get_opcodes()
            if tag != "equal"
        ]
    old_signatures = set()
    prior_by_path = defaultdict(list)
    for prior in base_findings.values():
        output_checkpoint(db)
        prior_by_path[prior.data.get("path")].append(prior)
    for path, priors in prior_by_path.items():
        output_checkpoint(db)
        lines = old_lines(path)
        for prior in priors:
            output_checkpoint(db)
            item = prior.data
            line = item.get("line", 1)
            text = lines[line - 1].strip() if isinstance(line, int) and 0 < line <= len(lines) else ""
            old_signatures.add(hash_text(str(item.get("rule")) + ":" + str(item.get("path")) + ":" + text))
    findings_by_path = defaultdict(list)
    for item in findings:
        output_checkpoint(db)
        findings_by_path[item["path"]].append(item)
    for path, path_findings in findings_by_path.items():
        output_checkpoint(db)
        lines = head_lines(path)
        for item in path_findings:
            output_checkpoint(db)
            text = lines[item["line"] - 1].strip() if 0 < item.get("line", 1) <= len(lines) else ""
            signature = hash_text(str(item.get("rule")) + ":" + item["path"] + ":" + text)
            item["delta"] = (
                "ANALYZER_BASELINE"
                if model_changed and not changed
                else "EXISTING"
                if signature in old_signatures
                else "NEW"
            )
            item["new_code"] = not base or any(
                lo <= item.get("end_line", item["line"]) and hi >= item["line"]
                for lo, hi in changed_lines.get(item["path"], [])
            )
            rec = finding_records[item["id"]]
            rec.data = {**rec.data, "delta": item["delta"], "new_code": item["new_code"]}
    from backend import finding_history

    identity_matches = finding_history.reconcile(db, findings, base, base_records, files)
    comparison_previous = [dict(r.data, id=r.id) for r in base_records if r.kind == "finding"]
    comparison_by_id = {item["id"]: item for item in comparison_previous}
    for item in findings:
        output_checkpoint(db)
        match = identity_matches.get(item["id"])
        if match and match[1] == "EXISTING":
            previous = comparison_by_id.get(match[0].id)
            if previous:
                previous["fingerprint"] = item.get("fingerprint")
    quality_domain.apply_comparison(
        db, result["code_quality"], findings, base, changed_lines, model_changed, comparison_previous
    )
    for item in findings:
        output_checkpoint(db)
        if item.get("category") == "QUALITY":
            record = finding_records[item["id"]]
            record.data = {**record.data, **{k: v for k, v in item.items() if k != "id"}}
    # Normalize findings without losing native/advisory provenance.
    # Reviews only
    # carry when the same issue still cites exactly the same source fingerprints.
    claims_by_id = {claim["id"]: claim for claim in claims}
    for packed_finding in findings:
        output_checkpoint(db)
        record = finding_records[packed_finding["id"]]
        data = record.data
        related_claim = claims_by_id.get(data.get("claim_id"))
        fingerprint = data.get("fingerprint") or hash_text(
            f"{data['rule']}:{data['path']}:{(related_claim or {}).get('claim_key', data['title'])}"
        )
        identity_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"projecttrace:{user.organization_id}:{repo.id}:finding:{fingerprint}")
        )
        match = identity_matches.get(record.id)
        previous_finding = match[0] if match else base_findings.get(fingerprint)
        if data.get("identity_confidence") == "AMBIGUOUS":
            previous_finding = None
            identity_id = uid()
        previous_data = previous_finding.data if previous_finding else {}
        if previous_data.get("identity_id"):
            identity_id = previous_data["identity_id"]
        unchanged = bool(previous_finding) and evidence_signature(previous_data, base_evidence) == evidence_signature(
            data, head_evidence
        )
        if data.get("category") == "QUALITY":
            unchanged = bool(previous_finding) and previous_data.get("observation_hash") == data.get("observation_hash")
        elif data.get("fingerprint_version") == "native-statement-v1":
            unchanged = bool(previous_finding) and previous_data.get("security_context_hash") == data.get(
                "security_context_hash"
            )
            unchanged = unchanged and all(
                previous_data.get(key) == data.get(key)
                for key in ("rule_version", "severity", "confidence", "classification")
            )
        if data.get("identity_confidence") == previous_data.get("identity_confidence") == "HIGH":
            unchanged = data.get("structural_context_hash") == previous_data.get("structural_context_hash") and all(
                previous_data.get(key) == data.get(key)
                for key in ("rule_version", "severity", "confidence", "classification", "threshold", "measured")
            )
        if match and match[1] == "REOPENED":
            unchanged = False
        if (
            data.get("identity_version") == "structural-v2"
            and data.get("identity_confidence") != "HIGH"
            and data.get("category") in {"QUALITY", "SAST", "SECRET", "IAC"}
        ):
            unchanged = False
        if match:
            data = {
                **data,
                "delta": match[1],
                "machine_status": "REOPENED" if match[1] == "REOPENED" else data.get("machine_status", "OPEN"),
            }
        suffix = data["path"].rsplit(".", 1)[-1].lower()
        record.data = {
            **data,
            "fingerprint": fingerprint,
            "identity_id": identity_id,
            "provider_finding_id": data.get("provider_finding_id", fingerprint),
            "rule_id": data["rule"],
            "rule_version": data.get("rule_version", VERSION),
            "language": data.get("language")
            or {"py": "Python", "js": "JavaScript", "ts": "TypeScript", "java": "Java"}.get(suffix, "Configuration"),
            "previous_version_id": previous_finding.id if previous_finding else None,
            "introduced_snapshot": previous_data.get(
                "introduced_snapshot", data.get("introduced_snapshot", snapshot.id)
            ),
            "last_seen_snapshot": snapshot.id,
            "introduced_commit": previous_data.get("introduced_commit", snapshot.data["commit"]),
            "introduced_pr": previous_data.get("introduced_pr", pr_number),
            "last_seen_commit": snapshot.data["commit"],
            "first_seen": data.get("first_seen")
            or previous_data.get("first_seen", previous_finding.created_at if previous_finding else now()),
            "last_seen": now(),
            "reopened_count": previous_data.get("reopened_count", 0) + int(bool(match) and match[1] == "REOPENED"),
            "review_status": previous_data.get("review_status", "OPEN") if unchanged else "OPEN",
            "review_reason": previous_data.get("review_reason") if unchanged else None,
            "review_identity_id": previous_data.get("review_identity_id", identity_id)
            if unchanged
            else identity_id
            if not previous_finding
            else uid(),
            "risk_factors": data.get(
                "risk_factors",
                {
                    "severity": data["severity"],
                    "confidence": data.get("confidence", "UNKNOWN"),
                    "evidence_scope": "STATIC",
                    "runtime_reachability": "UNOBSERVED",
                    "exposure": "UNOBSERVED",
                },
            ),
        }
        packed_finding.update(record.data)

    if publication_performance:
        publication_performance.record("FINDING_CORRELATION", time.perf_counter() - correlation_started)
    correlation_started = time.perf_counter()
    finding_history.project(
        db,
        snapshot,
        findings,
        [r for r in base_records if r.kind == "finding"],
        identity_matches,
        model_changed=model_changed,
        warnings=result["warnings"],
        files=files,
    )
    if publication_performance:
        publication_performance.record("FINDING_HISTORY", time.perf_counter() - correlation_started)
    correlation_started = time.perf_counter()

    # Graph IDs are assigned before insertion. Flush bounded batches through the
    # same ORM tenant guards instead of issuing one flush per node and edge.
    graph_pending = 0

    output_checkpoint(db, force=True)

    def graph_add(kind, data):
        nonlocal graph_pending
        record = add(db, user.organization_id, repo.id, kind, data, defer_flush=True)
        graph_pending += 1
        if graph_pending >= 250:
            db.flush()
            graph_pending = 0
        return record

    # Persist structural graph nodes as scoped records rather than drawing invented topology.
    def node(kind, title, **metadata):
        identity = hash_text(json.dumps([kind, title, metadata.get("path"), metadata.get("policy_key")]))
        return graph_add(
            "graph_node",
            {
                "class": kind,
                "title": title,
                "scope": path_scope(metadata.get("path")),
                "provenance": "STATIC",
                "identity_id": str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"projecttrace:{user.organization_id}:{repo.id}:node:{identity}")
                ),
                **metadata,
            },
        )

    def edge(source, target, relationship):
        graph_add(
            "edge",
            {"source": source, "target": target, "relationship": relationship, "snapshot_id": snapshot.id},
        )

    repository_node = node("REPOSITORY", repo.name, provenance="METADATA")
    system_node = node("SYSTEM", repo.system, provenance="METADATA")
    component_node = node("COMPONENT", repo.component, provenance="METADATA")
    snapshot_node = node("SNAPSHOT", snapshot.id, base_id=base_id)
    edge(system_node.id, component_node.id, "CONTAINS")
    edge(component_node.id, repository_node.id, "CONTAINS")
    edge(repository_node.id, snapshot_node.id, "HAS_SNAPSHOT")
    components = {}

    def file_component(path):
        scoped = path_scope(path)
        root = scoped.get("component_root", ".")
        key = (root, scoped["component"])
        if key not in components:
            if root == "." and scoped["component"] == repo.component:
                components[key] = component_node
            else:
                components[key] = node(
                    "COMPONENT", scoped["component"], path=root, provenance=scoped.get("component_basis", "DECLARED")
                )
                edge(repository_node.id, components[key].id, "CONTAINS")
        return components[key]

    for path, eid in evidence.items():
        output_checkpoint(db, flush=False)
        artifact = node("ARTIFACT", path, path=path, hash=hashes[path])
        edge(snapshot_node.id, artifact.id, "CONTAINS")
        if stored_input:
            edge(file_component(path).id, artifact.id, "CONTAINS")
        edge(artifact.id, eid, "HAS_FILE_EVIDENCE")
        if path.endswith(".md"):
            for line_no, line in enumerate(files[path].splitlines(), 1):
                output_checkpoint(db, flush=False)
                if line.startswith("#"):
                    section = node("DOCUMENTATION_SECTION", redact(line.lstrip("# ")), path=path, line=line_no)
                    edge(section.id, eid, "DOCUMENTED_BY")
    output_checkpoint(db, force=True)
    graph_pending = 0
    if publication_performance:
        publication_performance.record("ARTIFACT_GRAPH", time.perf_counter() - correlation_started)
    correlation_started = time.perf_counter()
    for signal in result["signals"]:
        output_checkpoint(db)
        if signal["type"] == "route":
            endpoint = node("API_ENDPOINT", signal["value"], path=signal["path"], line=signal["line"])
            edge(file_component(signal["path"]).id if stored_input else component_node.id, endpoint.id, "EXPOSES")
            edge(endpoint.id, evidence[signal["path"]], "IMPLEMENTED_IN")
        elif signal["type"] in {"ci", "infrastructure", "database"}:
            declaration = node(
                "CI_WORKFLOW" if signal["type"] == "ci" else "CONFIGURATION",
                signal["value"],
                path=signal["path"],
                line=signal["line"],
                signal_type=signal["type"],
            )
            edge(declaration.id, evidence[signal["path"]], "DECLARED_IN")
    cloud_records, risk_paths = [], []
    resource_nodes = {}
    for resource in result.get("cloud_assets", []):
        output_checkpoint(db)
        kind = (
            "CLOUD_IDENTITY"
            if "iam" in resource["kind"].lower()
            or resource["kind"] in {"ServiceAccount", "Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"}
            else "CONTAINER_WORKLOAD"
            if resource["kind"]
            in {
                "Pod",
                "Deployment",
                "StatefulSet",
                "DaemonSet",
                "ReplicaSet",
                "ReplicationController",
                "Job",
                "CronJob",
                "ContainerWorkload",
            }
            else "CONTAINER_IMAGE"
            if resource["kind"] == "ContainerImage"
            else "CLOUD_RESOURCE"
        )
        resource_node = node(
            kind,
            resource["identity"],
            **{key: value for key, value in resource.items() if key != "kind"},
            asset_kind=resource["kind"],
            owner=repo.owner,
            evidence_ids=[evidence[resource["path"]]],
        )
        resource_nodes[(resource["path"], resource["identity"])] = resource_node
        cloud_records.append({"id": resource_node.id, **resource_node.data})
        # The projection has an immediate FK to the deferred graph record.
        # Establish that parent before adding the independent projection mapper.
        db.flush()
        db.add(
            CloudAsset(
                id=resource_node.id,
                organization_id=user.organization_id,
                repository_id=repo.id,
                snapshot_id=snapshot.id,
                provider=resource["provider"],
                resource_id=resource["identity"],
                asset_kind=resource["kind"],
                exposure=resource["public"],
                encryption=resource["encryption"],
                observed_at=now(),
            )
        )
        edge(resource_node.id, evidence[resource["path"]], "DECLARED_IN")
        related = [
            item
            for item in findings
            if item.get("resource_identity") == resource["identity"] and item["path"] == resource["path"]
        ]
        for issue in related:
            edge(issue["id"], resource_node.id, "AFFECTS")
        if resource["public"] == "DECLARED_PUBLIC":
            exposure = node(
                "EXPOSURE",
                "Public access declared: " + resource["identity"],
                path=resource["path"],
                line=resource["line"],
                authority="STATIC",
                verification_scope="DECLARED_CONFIGURATION",
                evidence_ids=[evidence[resource["path"]]],
            )
            edge(exposure.id, resource_node.id, "EXPOSES")
            path_data = {
                "title": "Declared public access to " + resource["identity"],
                "scope": scope,
                "authority": "STATIC",
                "owner": repo.owner,
                "classification": "DECLARED_CONFIGURATION_RISK",
                "runtime_reachability": "UNOBSERVED",
                "factors": [
                    "Explicit public ACL/ingress/policy",
                    "Supported configuration resource",
                    "Deployment and effective access unobserved",
                ],
                "node_ids": [exposure.id, resource_node.id] + [item["id"] for item in related],
                "evidence_ids": [evidence[resource["path"]]],
                "severity": "HIGH",
                "review_status": "OPEN",
                "remediation": "Remove the public declaration and verify deployed policy with an authorized read-only inventory.",
            }
            risk = add(db, user.organization_id, repo.id, "risk_path", path_data)
            risk_paths.append({"id": risk.id, **risk.data})
    for resource in result.get("cloud_assets", []):
        output_checkpoint(db)
        for relation in resource.get("relations", []):
            output_checkpoint(db)
            targets = [
                value
                for (target_path, identity), value in resource_nodes.items()
                if identity == relation["target"]
                and (not relation.get("target_path") or target_path == relation["target_path"])
            ]
            if len(targets) == 1:
                edge(resource_nodes[(resource["path"], resource["identity"])].id, targets[0].id, relation["type"])
            elif not targets and relation["type"] in {"USES_IMAGE", "BASED_ON"} and not relation.get("target_path"):
                image = node(
                    "CONTAINER_IMAGE",
                    relation["target"],
                    path=resource["path"],
                    authority="STATIC",
                    verification_scope="DECLARED_IMAGE_REFERENCE",
                    runtime_observed=False,
                    evidence_ids=[evidence[resource["path"]]],
                )
                edge(resource_nodes[(resource["path"], resource["identity"])].id, image.id, relation["type"])
    if publication_performance:
        publication_performance.record("CONFIGURATION_GRAPH", time.perf_counter() - correlation_started)
    correlation_started = time.perf_counter()
    quality_findings_by_path = defaultdict(list)
    for item in findings:
        output_checkpoint(db)
        if item.get("category") == "QUALITY":
            quality_findings_by_path[item["path"]].append(item)
    # Configuration projections have SQL FKs and their own ordering. Drain that
    # work before the function writer counts only its graph rows in each batch.
    output_checkpoint(db, force=True)
    graph_pending = 0
    for signal in result["signals"]:
        output_checkpoint(db, flush=False)
        if signal["type"] == "function":
            function = node(
                "FUNCTION", signal["value"], path=signal["path"], line=signal["line"], end_line=signal.get("end_line")
            )
            edge(function.id, evidence[signal["path"]], "IMPLEMENTED_IN")
            for finding in quality_findings_by_path.get(signal["path"], ()):
                output_checkpoint(db, flush=False)
                if (
                    finding.get("category") == "QUALITY"
                    and finding["path"] == signal["path"]
                    and signal["line"] <= finding["line"] <= signal.get("end_line", signal["line"])
                ):
                    edge(finding["id"], function.id, "AFFECTS_FUNCTION")
    output_checkpoint(db, force=True)
    graph_pending = 0
    if publication_performance:
        publication_performance.record("FUNCTION_GRAPH", time.perf_counter() - correlation_started)
    correlation_started = time.perf_counter()
    for claim in claims:
        output_checkpoint(db)
        shared = [f["id"] for f in findings if set(f.get("evidence_ids", [])) & set(claim["evidence_ids"])]
        for fid in shared[:20]:
            edge(fid, claim["id"], "RELATED_EVIDENCE")
    for row in result["code_quality"]["inventory"]:
        output_checkpoint(db)
        if row["path"] not in owners_by_path:
            owners_by_path[row["path"]] = ownership(row["path"], files, repo.owner, rules=owner_rules)
        row.update(owners_by_path[row["path"]])
    for finding in findings:
        output_checkpoint(db)
        if finding.get("category") == "QUALITY":
            quality_owner = node("OWNER", finding["owner"], provenance=finding.get("owner_source", "METADATA"))
            edge(finding["id"], quality_owner.id, "OWNED_BY")
    if publication_performance:
        publication_performance.record("OWNERSHIP_GRAPH", time.perf_counter() - correlation_started)
    correlation_started = time.perf_counter()
    output_checkpoint(db, force=True)
    graph_pending = 0
    quality_gate = quality_domain.persist(db, snapshot, result["code_quality"], findings)
    # Typed projections must not occupy an extra slot beside a full graph batch.
    output_checkpoint(db, force=True)
    gate = quality_domain.merge_gate(
        policy_gate(
            claims,
            [f for f in findings if f.get("category") != "QUALITY"],
            new_findings_only=profile.get("gate_scope") == "NEW_FINDINGS",
        ),
        quality_gate,
    )
    evaluated = {item["id"]: item for item in [*claims, *findings]}
    for decision in gate["results"]:
        output_checkpoint(db)
        target = decision.get("target")
        policy = node(
            "POLICY",
            decision["policy"],
            policy_key=evaluated.get(target, {}).get("identity_id", "default"),
            version=decision["version"],
            result=decision["result"],
            reason=decision["reason"],
            mode=gate["mode"],
        )
        if target in evaluated:
            edge(policy.id, target, "DERIVED_FROM")
        for fid in decision.get("finding_ids", []):
            if fid in evaluated:
                edge(policy.id, fid, "DERIVED_FROM")
    db.flush()
    if publication_performance:
        publication_performance.record("POLICY_PROJECTION", time.perf_counter() - correlation_started)
    correlation_started = time.perf_counter()
    if stored_input:
        head_records = scoped_snapshot_records(db, user.organization_id, repo.id, snapshot.id, core=True)
        old_graph, old_partial = impact_graph_records(db, user.organization_id, repo.id, base_id, changed)
        head_graph, head_partial = (
            impact_graph_records(db, user.organization_id, repo.id, snapshot.id, changed) if base_id else ([], False)
        )
        impact = graph_impact([*base_records, *old_graph], [*head_records, *head_graph], changed, base_id, snapshot.id)
        impact["truncated"] = old_partial or head_partial
        impact["neighborhood_record_budget"] = 5000
        if impact["truncated"]:
            result["warnings"].append(
                {
                    "analyzer": "IMPACT",
                    "state": "PARTIAL",
                    "message": "Reverse graph neighborhood exceeded its record budget; impact coverage is incomplete.",
                }
            )
    else:
        head_records = scoped_snapshot_records(db, user.organization_id, repo.id, snapshot.id)
        impact = graph_impact(base_records, head_records, changed, base_id, snapshot.id)
    impact["verification"] = {
        "reused": result.get("reused_verifications", 0),
        "reverified": result.get("reverified_claims", 0),
        "reused_claim_ids": [c["id"] for c in claims if c.get("verification_reused")],
        "reverified_claim_ids": [
            c["id"] for c in claims if c.get("origin") == "DOCUMENTATION" and not c.get("verification_reused")
        ],
    }
    if publication_performance:
        publication_performance.record("IMPACT_GRAPH", time.perf_counter() - correlation_started)
    snapshot.data = {
        **snapshot.data,
        **captured_snapshot_data,
        "claims": claims,
        "findings": findings,
        "dependencies": deps,
        "cloud_assets": cloud_records,
        "risk_paths": risk_paths,
        "changed_lines": changed_lines,
        "quality_summary": result["code_quality"]["summary"],
        "quality_gate": quality_gate,
        "finding_delta": {
            state: sum(item.get("delta") == state for item in findings)
            for state in ["NEW", "EXISTING", "ANALYZER_BASELINE"]
        },
        "drifts": drifts,
        "gate": gate,
        "scope": scope,
        "impact": impact,
        "status": "PARTIAL" if result["warnings"] else "COMPLETED" if findings else "COMPLETED_NO_FINDINGS",
    }
    if stored_input:
        # The quality projection and graph are already flushed in this transaction.
        # Release parsing/correlation working sets before serializing the final
        # snapshot. Keep its referenced metrics, coverage and captured decisions.
        # No output is committed here; a later failure still rolls everything back.
        del result, base_records, head_records, captured_snapshot_data, initial_snapshot_data
        del base_evidence, head_evidence, evidence
        del previous_evidence_by_path, old_evidence_by_path
        del previous_claims, base_claim_records, base_findings
        del finding_records, findings_by_path, prior_by_path, comparison_by_id, claims_by_id
        import gc

        gc.collect()
    if pr_number:
        add(
            db,
            user.organization_id,
            repo.id,
            "pr",
            {
                "number": pr_number,
                "title": redact(pr_title or f"Engineering change #{pr_number}"),
                "base_id": base_id,
                "head_id": snapshot.id,
                "changed_files": changed,
                "scope": scope,
                "gate": gate,
                "affected_claims": impact["affected_claims"],
                "impact": impact,
                "owner": repo.owner,
                "review_status": "OPEN",
            },
        )
    from backend.engineering_changes import persist as persist_engineering_change

    persist_engineering_change(db, user, repo, snapshot, base, pr_number)
    audit(
        db,
        user,
        "ANALYSIS_COMPLETED",
        snapshot.id,
        {
            "files": len(files),
            "changed_files": changed,
            "claims": len(claims),
            "findings": len(findings),
            "analyzer_version": VERSION,
        },
        repo.id,
    )
    from backend.workspace_read import project_snapshot

    project_snapshot(db, snapshot)
    return snapshot
