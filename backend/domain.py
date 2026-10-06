import difflib
import json
import uuid
from collections import deque
from datetime import datetime, timezone

from sqlalchemy import or_, select

from analyzers.engine import VERSION, analyze, hash_text, redact, validate_files
from analyzers.verifiers import claim_key
from backend.db import Audit, CloudAsset, NativeProfile, Record, now


def uid():
    return str(uuid.uuid4())


def add(db, org, repo, kind, data, natural_key=None):
    record = Record(
        id=uid(), organization_id=org, repository_id=repo, kind=kind, natural_key=natural_key or uid(), data=data
    )
    db.add(record)
    db.flush()
    return record


def audit(db, user, action, target, data, repo=None):
    db.add(
        Audit(
            id=uid(),
            organization_id=user.organization_id,
            repository_id=repo,
            actor=user.email,
            action=action,
            target=target,
            data=data,
        )
    )


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
        if f["severity"] == "CRITICAL" and f.get("confidence") == "HIGH":
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


def scoped_snapshot_records(db, organization_id, repository_id, snapshot_id):
    """Read one graph version, always applying both tenant and repository scope."""
    if not snapshot_id:
        return []
    return list(
        db.scalars(
            select(Record).where(
                Record.organization_id == organization_id,
                Record.repository_id == repository_id,
                or_(
                    Record.data["scope"]["snapshot_id"].as_string() == snapshot_id,
                    Record.data["snapshot_id"].as_string() == snapshot_id,
                ),
            )
        )
    )


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
):
    if repo.organization_id != user.organization_id:
        raise ValueError("Repository does not belong to the current organization.")
    files = validate_files(files)
    digest = hash_text("\n".join(p + ":" + hash_text(t) for p, t in sorted(files.items())))
    profile_row = db.scalar(
        select(NativeProfile).where(
            NativeProfile.organization_id == user.organization_id, NativeProfile.scope_key == repo.id
        )
    )
    if profile_row is None:
        profile_row = db.scalar(
            select(NativeProfile).where(
                NativeProfile.organization_id == user.organization_id, NativeProfile.scope_key == "organization"
            )
        )
    profile = {**profile_row.data, "version": profile_row.version} if profile_row else {}
    key = hash_text(
        json.dumps(
            {
                "organization": user.organization_id,
                "repository": repo.id,
                "branch": branch,
                "content": digest,
                "analyzer": VERSION,
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
        return existing
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
    result = analyze(
        files,
        base_data.get("analysis_cache"),
        progress,
        verification_context=base_data.get("verification_cache"),
        profile=profile,
    )
    if progress:
        progress("BUILDING_EVIDENCE")
    previous_hashes = base_data.get("hashes", {})
    hashes = {p: hash_text(t) for p, t in files.items()}
    changed = sorted(p for p in set(hashes) | set(previous_hashes) if hashes.get(p) != previous_hashes.get(p))
    model_changed = bool(base) and base_data.get("analyzer_version") != VERSION
    snapshot = add(
        db,
        user.organization_id,
        repo.id,
        "snapshot",
        {
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
            "analysis_at": now(),
            "status": "PARTIAL"
            if result["warnings"]
            else "COMPLETED"
            if result["findings"]
            else "COMPLETED_NO_FINDINGS",
            "warnings": result["warnings"],
            "claim_extraction": {
                "state": "COMPLETED",
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
            "verification_cache": result.get("verification_cache", {}),
            "engines": result.get("engines", {}),
            "native_profile": profile,
            "quality_metrics": result.get("quality_metrics", []),
            "reused_files": result["reused_files"],
            "limitations": [
                "Static analysis only; runtime not connected.",
                "Content digest is not a Git commit SHA.",
                "Unsupported claim types remain unverified.",
            ],
        },
        key,
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
    base_records = scoped_snapshot_records(db, user.organization_id, repo.id, base_id)
    base_evidence = {r.id: r.data for r in base_records if r.kind == "evidence"}
    base_claim_records = {r.id: r for r in base_records if r.kind == "claim"}
    base_findings = {r.data.get("fingerprint"): r for r in base_records if r.kind == "finding"}
    evidence, head_evidence = {}, {}
    for path, source in result["files"].items():
        node = add(
            db,
            user.organization_id,
            repo.id,
            "evidence",
            {
                "path": path,
                "source": redact(source),
                "hash": hashes[path],
                "class": "DOCUMENTATION" if path.endswith(".md") else "SOURCE_CODE",
                "authority": "DECLARED" if path.endswith(".md") else "STATIC",
                "scope": scope,
            },
        )
        evidence[path] = node.id
        head_evidence[node.id] = node.data
    previous_claims = {c.get("claim_key") or claim_key(c): c for c in base_data.get("claims", [])}
    matched_previous_ids = set()
    claims, findings, drifts = [], [], []
    for data in result["claims"]:
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
                "scope": scope,
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
    for data in result["findings"]:
        record = add(
            db,
            user.organization_id,
            repo.id,
            "finding",
            {
                **data,
                "evidence_ids": [evidence[data["path"]]],
                "scope": scope,
                "owner": repo.owner,
                "provider": "ProjectTrace native",
            },
        )
        findings.append({"id": record.id, **record.data})
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
    deps, sca_issues = [], {}
    for d in result["dependencies"]:
        cache_key = f"{d['ecosystem']}:{d['name']}@{d['version']}"
        cached = (advisory_cache or {}).get(cache_key)
        if cached is not None:
            cached = [{**v, "summary": redact(v.get("summary", ""))} for v in cached]
        data = {
            **d,
            "scope": scope,
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
                    "title": f"{d['name']} {d['version']} · {vulnerability['id']}",
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
    if progress:
        progress("CORRELATING")

    old_sources = {item.get("path"): item.get("source", "") for item in base_evidence.values()}
    changed_lines = {}
    for path in changed:
        old, head = old_sources.get(path, "").splitlines(), redact(files.get(path, "")).splitlines()
        changed_lines[path] = [
            (j1 + 1, max(j1 + 1, j2))
            for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, old, head, autojunk=False).get_opcodes()
            if tag != "equal"
        ]
    old_signatures = set()
    for prior in base_findings.values():
        item = prior.data
        lines = old_sources.get(item.get("path"), "").splitlines()
        line = item.get("line", 1)
        text = lines[line - 1].strip() if isinstance(line, int) and 0 < line <= len(lines) else ""
        old_signatures.add(hash_text(str(item.get("rule")) + ":" + str(item.get("path")) + ":" + text))
    for item in findings:
        lines = redact(files.get(item["path"], "")).splitlines()
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
        rec = db.get(Record, item["id"])
        rec.data = {**rec.data, "delta": item["delta"], "new_code": item["new_code"]}
    # Normalize findings without losing native/advisory provenance.
    # Reviews only
    # carry when the same issue still cites exactly the same source fingerprints.
    for packed_finding in findings:
        record = db.get(Record, packed_finding["id"])
        data = record.data
        related_claim = next((c for c in claims if c["id"] == data.get("claim_id")), None)
        fingerprint = data.get("fingerprint") or hash_text(
            f"{data['rule']}:{data['path']}:{(related_claim or {}).get('claim_key', data['title'])}"
        )
        identity_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"projecttrace:{user.organization_id}:{repo.id}:finding:{fingerprint}")
        )
        previous_finding = base_findings.get(fingerprint)
        previous_data = previous_finding.data if previous_finding else {}
        unchanged = bool(previous_finding) and evidence_signature(previous_data, base_evidence) == evidence_signature(
            data, head_evidence
        )
        suffix = data["path"].rsplit(".", 1)[-1].lower()
        record.data = {
            **data,
            "fingerprint": fingerprint,
            "identity_id": identity_id,
            "provider_finding_id": data.get("provider_finding_id", fingerprint),
            "rule_id": data["rule"],
            "rule_version": data.get("rule_version", VERSION),
            "language": {"py": "Python", "js": "JavaScript", "ts": "TypeScript", "java": "Java"}.get(
                suffix, "Configuration"
            ),
            "previous_version_id": previous_finding.id if previous_finding else None,
            "first_seen": previous_data.get("first_seen", previous_finding.created_at if previous_finding else now()),
            "last_seen": now(),
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

    # Persist structural graph nodes as scoped records rather than drawing invented topology.
    def node(kind, title, **metadata):
        identity = hash_text(json.dumps([kind, title, metadata.get("path"), metadata.get("policy_key")]))
        return add(
            db,
            user.organization_id,
            repo.id,
            "graph_node",
            {
                "class": kind,
                "title": title,
                "scope": scope,
                "provenance": "STATIC",
                "identity_id": str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"projecttrace:{user.organization_id}:{repo.id}:node:{identity}")
                ),
                **metadata,
            },
        )

    def edge(source, target, relationship):
        add(
            db,
            user.organization_id,
            repo.id,
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
    for path, eid in evidence.items():
        artifact = node("ARTIFACT", path, path=path, hash=hashes[path])
        edge(snapshot_node.id, artifact.id, "CONTAINS")
        edge(artifact.id, eid, "HAS_FILE_EVIDENCE")
        if path.endswith(".md"):
            for line_no, line in enumerate(files[path].splitlines(), 1):
                if line.startswith("#"):
                    section = node("DOCUMENTATION_SECTION", redact(line.lstrip("# ")), path=path, line=line_no)
                    edge(section.id, eid, "DOCUMENTED_BY")
    for signal in result["signals"]:
        if signal["type"] == "route":
            endpoint = node("API_ENDPOINT", signal["value"], path=signal["path"], line=signal["line"])
            edge(component_node.id, endpoint.id, "EXPOSES")
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
        kind = (
            "CLOUD_IDENTITY"
            if "iam" in resource["kind"].lower() or resource["kind"] == "ServiceAccount"
            else "CONTAINER_WORKLOAD"
            if resource["provider"] in {"KUBERNETES", "COMPOSE"}
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
        for relation in resource.get("relations", []):
            targets = [value for (_, identity), value in resource_nodes.items() if identity == relation["target"]]
            if len(targets) == 1:
                edge(resource_nodes[(resource["path"], resource["identity"])].id, targets[0].id, relation["type"])
    for signal in result["signals"]:
        if signal["type"] == "function":
            function = node(
                "FUNCTION", signal["value"], path=signal["path"], line=signal["line"], end_line=signal.get("end_line")
            )
            edge(function.id, evidence[signal["path"]], "IMPLEMENTED_IN")
    for claim in claims:
        shared = [f["id"] for f in findings if set(f.get("evidence_ids", [])) & set(claim["evidence_ids"])]
        for fid in shared[:20]:
            edge(fid, claim["id"], "RELATED_EVIDENCE")
    gate = policy_gate(claims, findings, new_findings_only=profile.get("gate_scope") == "NEW_FINDINGS")
    evaluated = {item["id"]: item for item in [*claims, *findings]}
    for decision in gate["results"]:
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
    db.flush()
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
    snapshot.data = {
        **snapshot.data,
        "claims": claims,
        "findings": findings,
        "dependencies": deps,
        "cloud_assets": cloud_records,
        "risk_paths": risk_paths,
        "changed_lines": changed_lines,
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
    return snapshot
