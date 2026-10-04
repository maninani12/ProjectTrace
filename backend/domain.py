import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from analyzers.engine import VERSION, analyze, hash_text, redact, validate_files
from backend.db import Audit, Record, now


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


def policy_gate(claims, findings, exceptions=()):
    active = {e["target"] for e in exceptions if datetime.fromisoformat(e["expires_at"]) > datetime.now(timezone.utc)}
    results = []
    for f in findings:
        if f.get("id") in active or f.get("review_status") in {"RESOLVED", "FALSE_POSITIVE"}:
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
    for c in claims:
        if c["status"] == "CONTRADICTED" and c.get("id") not in active:
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
        else "PASS"
    )
    return {"overall": status, "mode": "ADVISORY", "results": results}


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
):
    files = validate_files(files)
    digest = hash_text("\n".join(p + ":" + hash_text(t) for p, t in sorted(files.items())))
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
    if base and (
        base.organization_id != user.organization_id or base.repository_id != repo.id or base.kind != "snapshot"
    ):
        raise ValueError("Base snapshot does not belong to the selected repository.")
    base_data = base.data if base else {}
    result = analyze(files, base_data.get("analysis_cache"))
    previous_hashes = base_data.get("hashes", {})
    hashes = {p: hash_text(t) for p, t in files.items()}
    changed = sorted(p for p in set(hashes) | set(previous_hashes) if hashes.get(p) != previous_hashes.get(p))
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
            "analyzer_version": VERSION,
            "base_id": base_id,
            "analysis_at": now(),
            "status": "COMPLETED",
            "file_count": len(files),
            "analysis_cache": result["analysis_cache"],
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
    evidence = {}
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
    previous_claims = {c["text"]: c for c in base_data.get("claims", [])}
    claims, findings, drifts = [], [], []
    for data in result["claims"]:
        signals = data.pop("signals")
        previous = previous_claims.get(data["text"])
        evidence_ids = list(dict.fromkeys([evidence[data["path"]]] + [evidence[s["path"]] for s in signals]))
        supporting = list(dict.fromkeys(evidence[s["path"]] for s in signals))
        history = (previous or {}).get("history", [])[:]
        if previous and previous["status"] != data["status"]:
            history.append(
                {"status": "STALE", "at": now(), "reason": "Related evidence changed; reverification required."}
            )
        history.append({"status": data["status"], "at": now(), "snapshot_id": snapshot.id, "reason": data["reason"]})
        claim = add(
            db,
            user.organization_id,
            repo.id,
            "claim",
            {
                **data,
                "evidence_ids": evidence_ids,
                "supporting_ids": supporting if data["status"] in {"VERIFIED", "INFERRED"} else [],
                "contradicting_ids": supporting if data["status"] == "CONTRADICTED" else [],
                "scope": scope,
                "owner": repo.owner,
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
        if data["status"] == "CONTRADICTED" or previous and previous["status"] != data["status"]:
            drift = add(
                db,
                user.organization_id,
                repo.id,
                "drift",
                {
                    "claim_id": claim.id,
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
    deps = []
    for d in result["dependencies"]:
        cache_key = f"{d['ecosystem']}:{d['name']}@{d['version']}"
        cached = (advisory_cache or {}).get(cache_key)
        data = {
            **d,
            "scope": scope,
            "vulnerability_status": "CHECKED" if cached is not None else "NOT_CHECKED",
            "vulnerabilities": cached or [],
        }
        dep = add(db, user.organization_id, repo.id, "dependency", data)
        deps.append({"id": dep.id, **data})
        for vulnerability in cached or []:
            record = add(
                db,
                user.organization_id,
                repo.id,
                "finding",
                {
                    "title": f"{d['name']} {d['version']} · {vulnerability['id']}",
                    "category": "SCA",
                    "severity": vulnerability.get("severity", "UNKNOWN"),
                    "confidence": "HIGH",
                    "path": d["path"],
                    "line": 1,
                    "rule": vulnerability["id"],
                    "rule_version": VERSION,
                    "analyzer_version": VERSION,
                    "explanation": vulnerability.get("summary", "Known vulnerability reported by cached OSV data."),
                    "remediation": "Upgrade to a version outside the advisory affected range; review the linked advisory.",
                    "advisory": vulnerability,
                    "provider": "OSV cached advisory",
                    "evidence_ids": [evidence[d["path"]]],
                    "scope": scope,
                    "owner": repo.owner,
                    "review_status": "OPEN",
                },
            )
            findings.append({"id": record.id, **record.data})
            add(
                db,
                user.organization_id,
                repo.id,
                "edge",
                {"source": record.id, "target": dep.id, "relationship": "AFFECTS", "snapshot_id": snapshot.id},
            )
    gate = policy_gate(claims, findings)
    snapshot.data = {
        **snapshot.data,
        "claims": claims,
        "findings": findings,
        "dependencies": deps,
        "drifts": drifts,
        "gate": gate,
        "scope": scope,
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
                "affected_claims": [c["id"] for c in claims if c["status"] != "VERIFIED"],
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
