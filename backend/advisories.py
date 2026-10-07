"""Tenant-scoped exact-version advisory checks, independently queued from native analysis."""

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from analyzers.engine import hash_text, redact
from backend.db import Record, now
from backend.domain import add, audit, graph_impact, policy_gate, scoped_snapshot_records


def enqueue_advisories(db, user, repo, snapshot):
    from backend.queue import check_capacity, dispatch
    from backend.trust import require_egress

    require_egress(db, user.organization_id, "OSV")

    check_capacity(db, user, repo)
    job = add(
        db,
        user.organization_id,
        repo.id,
        "job",
        {
            "type": "ADVISORIES",
            "state": "QUEUED",
            "stage": "QUEUED",
            "snapshot_id": snapshot.id,
            "user_id": user.id,
            "queued_at": now(),
            "started_at": None,
            "finished_at": None,
            "execution": "CELERY",
            "warnings": [],
            "errors": [],
            "stages": [],
        },
    )
    from backend.scheduling import register
    register(db, job)
    db.commit()
    dispatch(db, job)
    return job


def normalized(advisory):
    identifier = advisory["id"]
    if not identifier or any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_." for c in identifier
    ):
        raise ValueError("Invalid advisory identity.")
    return {
        "id": identifier,
        "modified": advisory.get("modified"),
        "summary": redact(advisory.get("summary", "")[:2000]),
        "url": "https://osv.dev/vulnerability/" + identifier,
        "affected": advisory.get("affected", []),
        "severity": {"MODERATE": "MEDIUM", "HIGH": "HIGH", "LOW": "LOW", "CRITICAL": "CRITICAL"}.get(
            advisory.get("database_specific", {}).get("severity"), "UNKNOWN"
        ),
    }


def refresh_policy_graph(db, user, repo, snapshot, records, gate):
    """Update advisory-derived gate nodes while preserving evaluation history."""
    nodes = [r for r in records if r.kind == "graph_node" and r.data.get("class") == "POLICY"]
    existing = {(r.data["title"], r.data.get("policy_key", "default")): r for r in nodes}
    targets = {r.id: r for r in records if r.kind in {"claim", "finding"}}
    edges = {
        (r.data.get("source"), r.data.get("target"), r.data.get("relationship")) for r in records if r.kind == "edge"
    }
    current = set()
    for decision in gate["results"]:
        target = targets.get(decision.get("target"))
        policy_key = target.data.get("identity_id", target.id) if target else "default"
        key = (decision["policy"], policy_key)
        current.add(key)
        value = {
            "class": "POLICY",
            "title": decision["policy"],
            "policy_key": policy_key,
            "scope": snapshot.data["scope"],
            "provenance": "POLICY_EVALUATION",
            "version": decision["version"],
            "result": decision["result"],
            "reason": decision["reason"],
            "mode": gate["mode"],
            "evaluated_at": now(),
        }
        node = existing.get(key)
        if node:
            previous = node.data
            history = previous.get("evaluation_history", [])
            if previous.get("result") != value["result"]:
                history = [*history, {"result": previous.get("result"), "reason": previous.get("reason"), "at": now()}]
            node.data = {**previous, **value, "evaluation_history": history}
        else:
            identity = hash_text(json.dumps(["POLICY", decision["policy"], None, policy_key]))
            node = add(
                db,
                user.organization_id,
                repo.id,
                "graph_node",
                {
                    **value,
                    "identity_id": str(
                        uuid.uuid5(uuid.NAMESPACE_URL, f"projecttrace:{user.organization_id}:{repo.id}:node:{identity}")
                    ),
                },
            )
        if target and (node.id, target.id, "DERIVED_FROM") not in edges:
            add(
                db,
                user.organization_id,
                repo.id,
                "edge",
                {
                    "source": node.id,
                    "target": target.id,
                    "relationship": "DERIVED_FROM",
                    "snapshot_id": snapshot.id,
                },
            )
    for key, node in existing.items():
        if key not in current and node.data.get("result") != "PASS":
            node.data = {
                **node.data,
                "result": "PASS",
                "evaluated_at": now(),
                "reason": "The current reviewed records and active exceptions no longer require this gate result.",
                "evaluation_history": [
                    *node.data.get("evaluation_history", []),
                    {"result": node.data.get("result"), "reason": node.data.get("reason"), "at": now()},
                ],
            }


def run_checks(db, user, repo, snapshot, job, query):
    if (
        user.organization_id != repo.organization_id
        or snapshot.organization_id != user.organization_id
        or snapshot.repository_id != repo.id
        or snapshot.kind != "snapshot"
        or job.organization_id != user.organization_id
        or job.repository_id != repo.id
    ):
        raise ValueError("Advisory analysis scope is invalid.")
    from backend.security import require_repo

    require_repo(db, user, repo.id)
    from backend.trust import require_egress

    require_egress(db, user.organization_id, "OSV")
    records = scoped_snapshot_records(db, user.organization_id, repo.id, snapshot.id)
    evidence_by_path = {r.data["path"]: r for r in records if r.kind == "evidence"}
    issue_records = [r for r in records if r.kind == "finding" and r.data.get("category") == "SCA"]
    existing_edges = {
        (r.data.get("source"), r.data.get("target"), r.data.get("relationship")) for r in records if r.kind == "edge"
    }
    dependencies = list(
        db.scalars(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.repository_id == repo.id,
                Record.kind == "dependency",
                Record.data["scope"]["snapshot_id"].as_string() == snapshot.id,
            )
        )
    )
    start, checked, failures, cache_hits, requested = time.perf_counter(), 0, 0, 0, set()
    job.data = {**job.data, "state": "ANALYZING", "stage": "SCA", "started_at": now()}
    db.commit()
    warnings = []
    for dependency in dependencies:
        from backend.scheduling import ensure_current
        ensure_current(db, job, renew_seconds=120)
        data = dependency.data
        if data.get("version_kind") != "EXACT":
            dependency.data = {**data, "vulnerability_status": "UNKNOWN_VERSION"}
            continue
        key = f"{data['ecosystem']}:{data['name']}@{data['version']}"
        for finding in issue_records:
            if finding.data.get("title", "").startswith(
                f"{data['name']} {data['version']} · "
            ) and not finding.data.get("package_key"):
                finding.data = {**finding.data, "package_key": key}
        cache_key = hashlib.sha256(key.encode()).hexdigest()
        cached = db.scalar(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.kind == "advisory_cache",
                Record.natural_key == cache_key,
            )
        )
        fresh = (
            cached
            and (datetime.now(timezone.utc) - datetime.fromisoformat(cached.data["checked_at"])).total_seconds() < 86400
        )
        if fresh:
            result, checked_at = cached.data["vulnerabilities"], cached.data["checked_at"]
            cache_hits += 1
        elif len(requested) >= 32 or time.perf_counter() - start > 75:
            warnings.append(
                "Advisory budget reached; unchecked packages remain NOT_CHECKED. Run another advisory check to continue."
            )
            continue
        else:
            requested.add(key)
            try:
                result = [normalized(v) for v in query(data["ecosystem"], data["name"], data["version"])]
                checked_at = now()
                cache_data = {
                    "package_key": key,
                    "provider": "OSV",
                    "provider_api": "v1/query",
                    "checked_at": checked_at,
                    "dataset_modified": max((v.get("modified") or "" for v in result), default=None),
                    "vulnerabilities": result,
                }
                if cached:
                    cached.data = cache_data
                else:
                    add(db, user.organization_id, None, "advisory_cache", cache_data, cache_key)
            except Exception as error:
                dependency.data = {
                    **data,
                    "vulnerability_status": "CHECK_FAILED",
                    "advisory_error_type": type(error).__name__,
                    "advisory_checked_at": now(),
                    "advisory_provider": "OSV",
                }
                failures += 1
                db.commit()
                continue
        checked += 1
        dependency.data = {
            **data,
            "vulnerability_status": "VULNERABLE" if result else "CHECKED_NO_KNOWN_ADVISORY",
            "vulnerabilities": result,
            "advisory_checked_at": checked_at,
            "advisory_provider": "OSV",
            "advisory_dataset_modified": max((v.get("modified") or "" for v in result), default=None),
        }
        for advisory in result:
            fingerprint = hashlib.sha256((key + ":" + advisory["id"]).encode()).hexdigest()
            issue_key = hashlib.sha256((snapshot.id + ":" + fingerprint).encode()).hexdigest()
            title = f"{data['name']} {data['version']} · {advisory['id']}"
            finding = next(
                (
                    f
                    for f in issue_records
                    if (f.data.get("package_key") == key or f.data.get("title") == title)
                    and f.data.get("advisory", {}).get("id") == advisory["id"]
                ),
                None,
            )
            evidence = evidence_by_path.get(data["path"])
            evidence_ids = [evidence.id] if evidence else []
            if not finding:
                identity_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL, f"projecttrace:{user.organization_id}:{repo.id}:finding:{fingerprint}"
                    )
                )
                finding = add(
                    db,
                    user.organization_id,
                    repo.id,
                    "finding",
                    {
                        "title": title,
                        "category": "SCA",
                        "package_key": key,
                        "severity": advisory["severity"],
                        "confidence": "HIGH",
                        "path": data["path"],
                        "line": 1,
                        "rule": advisory["id"],
                        "rule_id": advisory["id"],
                        "rule_version": "OSV-v1",
                        "language": data["ecosystem"],
                        "fingerprint": fingerprint,
                        "identity_id": identity_id,
                        "review_identity_id": identity_id,
                        "provider_finding_id": advisory["id"],
                        "explanation": advisory["summary"],
                        "remediation": "Review the advisory and upgrade outside its affected range.",
                        "provider": "OSV",
                        "advisory": advisory,
                        "evidence_ids": evidence_ids,
                        "scope": data["scope"],
                        "owner": repo.owner,
                        "review_status": "OPEN",
                        "first_seen": checked_at,
                        "last_seen": checked_at,
                        "risk_factors": {
                            "severity": advisory["severity"],
                            "confidence": "HIGH",
                            "evidence_scope": "EXACT_DECLARED_VERSION",
                            "runtime_reachability": "UNOBSERVED",
                            "exposure": "UNOBSERVED",
                        },
                    },
                    issue_key,
                )
                issue_records.append(finding)
            old = finding.data
            combined_evidence = list(dict.fromkeys([*old.get("evidence_ids", []), *evidence_ids]))
            added_evidence = bool(set(combined_evidence) - set(old.get("evidence_ids", [])))
            reopened = old.get("resolution_source") == "OSV_NO_LONGER_REPORTED"
            observations = old.get("provider_observations", [])
            observation = {
                "provider": "OSV",
                "provider_id": advisory["id"],
                "dependency_id": dependency.id,
                "manifest": data["path"],
                "checked_at": checked_at,
                "dataset_modified": advisory.get("modified"),
            }
            observations = [
                o for o in observations if not (o.get("provider") == "OSV" and o.get("dependency_id") == dependency.id)
            ]
            finding.data = {
                **old,
                "package_key": key,
                "evidence_ids": combined_evidence,
                "dependency_ids": list(dict.fromkeys([*old.get("dependency_ids", []), dependency.id])),
                "provider_observations": [*observations, observation],
                "advisory_state": "REPORTED",
                "resolution_source": None,
                "last_seen": checked_at,
                "advisory": advisory,
                "severity": advisory["severity"],
                "explanation": advisory["summary"],
                "review_status": "OPEN" if added_evidence or reopened else old.get("review_status", "OPEN"),
                "review_identity_id": str(uuid.uuid4())
                if added_evidence or reopened
                else old.get("review_identity_id", old.get("identity_id")),
                "risk_factors": {
                    "severity": advisory["severity"],
                    "confidence": "HIGH",
                    "evidence_scope": "EXACT_DECLARED_VERSION",
                    "runtime_reachability": "UNOBSERVED",
                    "exposure": "UNOBSERVED",
                },
            }
            for target, relationship in [(dependency.id, "AFFECTS"), *[(eid, "DETECTED_IN") for eid in evidence_ids]]:
                if (finding.id, target, relationship) not in existing_edges:
                    add(
                        db,
                        user.organization_id,
                        repo.id,
                        "edge",
                        {
                            "source": finding.id,
                            "target": target,
                            "relationship": relationship,
                            "snapshot_id": snapshot.id,
                        },
                    )
                    existing_edges.add((finding.id, target, relationship))
        reported = {a["id"] for a in result}
        for finding in issue_records:
            if finding.data.get("package_key") == key and finding.data.get("advisory", {}).get("id") not in reported:
                finding.data = {
                    **finding.data,
                    "advisory_state": "NO_LONGER_REPORTED",
                    "review_status": "RESOLVED",
                    "resolution_source": "OSV_NO_LONGER_REPORTED",
                    "last_checked_at": checked_at,
                }
        db.commit()
    dependency_values = [{"id": d.id, **d.data} for d in dependencies]
    records = scoped_snapshot_records(db, user.organization_id, repo.id, snapshot.id)
    findings = [{"id": f.id, **f.data} for f in records if f.kind == "finding"]
    claims = [{"id": c.id, **c.data} for c in records if c.kind == "claim"]
    exceptions = [
        r.data
        for r in db.scalars(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.repository_id == repo.id,
                Record.kind == "exception",
            )
        )
    ]
    gate = policy_gate(
        claims,
        findings,
        exceptions,
        new_findings_only=snapshot.data.get("native_profile", {}).get("gate_scope") == "NEW_FINDINGS",
    )
    refresh_policy_graph(db, user, repo, snapshot, records, gate)
    db.flush()
    base_records = scoped_snapshot_records(db, user.organization_id, repo.id, snapshot.data.get("base_id"))
    head_records = scoped_snapshot_records(db, user.organization_id, repo.id, snapshot.id)
    impact = graph_impact(
        base_records, head_records, snapshot.data.get("changed_files", []), snapshot.data.get("base_id"), snapshot.id
    )
    impact["verification"] = snapshot.data.get("impact", {}).get("verification", {})
    unknown = sum(d.data.get("vulnerability_status") == "UNKNOWN_VERSION" for d in dependencies)
    unchecked = sum(d.data.get("vulnerability_status") in {"NOT_CHECKED", "CHECK_FAILED"} for d in dependencies)
    incomplete = failures or warnings or unknown or unchecked
    engine = {
        "state": "PARTIAL" if incomplete else "COMPLETED",
        "checked_declarations": checked,
        "cache_hits": cache_hits,
        "failed_declarations": failures,
        "provider": "OSV",
        "warnings": list(dict.fromkeys(warnings)),
        "unknown_version_declarations": unknown,
        "unchecked_declarations": unchecked,
        "limitations": ["Exact manifest/lock versions only; runtime reachability is not verified."],
    }
    native_partial = any(
        v.get("state") in {"PARTIAL", "FAILED"} for k, v in snapshot.data.get("engines", {}).items() if k != "OSV"
    )
    snapshot.data = {
        **snapshot.data,
        "dependencies": dependency_values,
        "findings": findings,
        "claims": claims,
        "engines": {**snapshot.data.get("engines", {}), "OSV": engine},
        "gate": gate,
        "impact": impact,
        "status": "PARTIAL"
        if incomplete or native_partial or snapshot.data.get("warnings")
        else "COMPLETED"
        if findings
        else "COMPLETED_NO_FINDINGS",
    }
    from backend.scheduling import ensure_current
    ensure_current(db, job)
    job.data = {
        **job.data,
        "state": "PARTIAL" if incomplete else "COMPLETED",
        "stage": "FINALIZING",
        "finished_at": now(),
        "warnings": engine["warnings"],
        "engines": {"OSV": engine},
        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
    }
    audit(
        db,
        user,
        "ADVISORIES_CHECKED",
        snapshot.id,
        {"checked": checked, "failed": failures, "cache_hits": cache_hits},
        repo.id,
    )
    db.commit()
