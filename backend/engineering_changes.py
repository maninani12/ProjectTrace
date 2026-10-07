"""Captured BASE/HEAD correlations derived from the authoritative impact graph."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from backend.db import FindingOccurrence, Record
from backend.security import allowed_repositories, authenticate, require_repo

router = APIRouter(prefix="/api/engineering-changes", tags=["Engineering Changes"])


def persist(db, user, repo, snapshot, base, pr_number=None):
    from backend.domain import add, audit, snapshot_record_query
    from backend.snapshot_context import quality_fields

    if not base:
        return None  # An initial capture is a baseline, not evidence of a change.
    old, head = base.data, snapshot.data
    reevaluated = head.get("comparison", {}).get("analysis_model_changed", False)
    rows = []

    def change(category, label, before, after, reason, target=None, path=None, authority="STATIC"):
        rows.append(
            {
                "category": category,
                "label": label,
                "before": before,
                "after": after,
                "reason": reason,
                "target_id": target,
                "path": path,
                "authority": authority,
            }
        )

    old_claims = {c.get("claim_key", c.get("text")): c for c in old.get("claims", [])}
    for claim in head.get("claims", []):
        prior = old_claims.get(claim.get("claim_key", claim.get("text")))
        if prior and prior.get("status") != claim.get("status"):
            change(
                "CLAIM_STATUS_CHANGE",
                claim.get("text"),
                prior.get("status"),
                claim.get("status"),
                claim.get("reason"),
                claim.get("id"),
                claim.get("path"),
                "STATIC / DECLARED",
            )
    for drift in head.get("drifts", []):
        change(
            "ARCHITECTURE_CHANGE" if "ARCHITECTURE" in str(drift.get("type", "")) else "DOCUMENTATION_DRIFT",
            drift.get("title", drift.get("reason", "Documentation needs review")),
            drift.get("old_status", "UNOBSERVED"),
            drift.get("status", "REVIEW_REQUIRED"),
            drift.get("reason"),
            drift.get("id"),
            drift.get("path"),
        )
    quality = quality_fields(db, snapshot, ("metrics", "inventory"))
    previous_quality = quality_fields(db, base, ("metrics", "inventory"))
    previous_metrics = {
        (m["path"], m.get("qualified_name", m["name"])): m
        for m in previous_quality.get("metrics", [])
    }
    for metric in quality.get("metrics", []):
        prior = previous_metrics.get((metric["path"], metric.get("qualified_name", metric["name"])))
        if prior:
            for name in ("cyclomatic", "nesting", "parameters", "length", "cognitive_approximation"):
                if metric.get(name, 0) > prior.get(name, 0):
                    change(
                        "QUALITY_REGRESSION",
                        f"{metric.get('qualified_name', metric['name'])}: {name}",
                        prior.get(name),
                        metric.get(name),
                        "Measured syntax metric increased; approximation is not runtime behavior.",
                        path=metric["path"],
                    )
    for finding in head.get("findings", []):
        if finding.get("category") in {"SAST", "SECRET", "SCA", "LICENSE", "IAC"} and finding.get("delta") in {
            "NEW",
            "REOPENED",
        }:
            change(
                "SECURITY_CHANGE" if finding.get("category") != "IAC" else "INFRASTRUCTURE_CHANGE",
                finding.get("title", finding["rule"]),
                None,
                finding.get("severity"),
                finding.get("explanation"),
                finding.get("id"),
                finding.get("path"),
                finding.get("authority", "STATIC"),
            )
    resolved = db.scalars(
        select(FindingOccurrence).where(
            FindingOccurrence.organization_id == user.organization_id,
            FindingOccurrence.repository_id == repo.id,
            FindingOccurrence.snapshot_id == snapshot.id,
            FindingOccurrence.status == "RESOLVED",
        )
    )
    for occurrence in resolved:
        change(
            "FINDING_RESOLVED",
            occurrence.data.get("rule", "Finding resolved"),
            "OBSERVED",
            "RESOLVED",
            occurrence.data.get("reason"),
            path=occurrence.data.get("path"),
        )
    old_dependencies = {(d.get("ecosystem"), d.get("name"), d.get("path")): d for d in old.get("dependencies", [])}
    new_dependencies = {(d.get("ecosystem"), d.get("name"), d.get("path")): d for d in head.get("dependencies", [])}
    for key in sorted(old_dependencies.keys() | new_dependencies.keys(), key=str):
        prior, current = old_dependencies.get(key, {}), new_dependencies.get(key, {})
        if prior.get("version") != current.get("version") or bool(prior) != bool(current):
            change(
                "DEPENDENCY_CHANGE",
                f"{key[0]} / {key[1]}",
                prior.get("version"),
                current.get("version"),
                "Manifest declaration changed; upstream advisory completeness and runtime use are unobserved.",
                current.get("id"),
                key[2],
                "DECLARED",
            )
    old_assets = {(a.get("path"), a.get("identity")): a for a in old.get("cloud_assets", [])}
    new_assets = {(a.get("path"), a.get("identity")): a for a in head.get("cloud_assets", [])}
    for key in sorted(old_assets.keys() | new_assets.keys(), key=str):
        prior, current = old_assets.get(key, {}), new_assets.get(key, {})
        if prior.get("resource_context_hash") != current.get("resource_context_hash") or bool(prior) != bool(current):
            change(
                "INFRASTRUCTURE_CHANGE",
                key[1],
                {"exposure": prior.get("public", prior.get("exposure", "UNKNOWN")), "present": bool(prior)},
                {"exposure": current.get("public", current.get("exposure", "UNKNOWN")), "present": bool(current)},
                "Canonical declared resource changed; deployed state is unobserved.",
                current.get("id"),
                key[0],
            )
    if old.get("gate", {}).get("overall") != head.get("gate", {}).get("overall"):
        change(
            "POLICY_CHANGE",
            "Captured quality/security gate",
            old.get("gate", {}).get("overall"),
            head.get("gate", {}).get("overall"),
            "Captured gate decision changed; inspect versioned conditions and evidence.",
        )
    old_owners = {
        r["path"]: r.get("owner") for r in previous_quality.get("inventory", [])
    }
    for item in quality.get("inventory", []):
        if item["path"] in old_owners and old_owners[item["path"]] != item.get("owner"):
            change(
                "OWNERSHIP_CHANGE",
                item["path"],
                old_owners[item["path"]],
                item.get("owner"),
                "Captured ownership metadata changed.",
                path=item["path"],
                authority="DECLARED",
            )
    if head.get("changed_files"):
        change(
            "IMPLEMENTATION_CHANGE",
            "Captured file changes",
            len(old.get("hashes", {})),
            len(head.get("hashes", {})),
            f"{len(head['changed_files'])} file paths changed in the explicit comparison; causality requires linked evidence.",
        )
    if reevaluated:
        # Source and model differences can coexist; never attribute a reclassification solely to source.
        for item in rows:
            item["comparison_basis"] = "ANALYZER_REEVALUATION"
        change(
            "ANALYZER_CHANGE",
            "Analysis model changed",
            old.get("parser_signature"),
            head.get("parser_signature"),
            "Re-evaluation can change classifications independently of source edits.",
        )
    if not rows:
        return None
    counts = dict(Counter(r["category"] for r in rows))
    factors = []
    if not reevaluated:
        if any(r["category"] == "CLAIM_STATUS_CHANGE" and r["after"] == "CONTRADICTED" for r in rows):
            factors.append({"reason": "A previously captured claim is now contradicted", "weight": 40})
        if any(r["category"] == "SECURITY_CHANGE" and r["after"] in {"HIGH", "CRITICAL"} for r in rows):
            factors.append({"reason": "New high or critical static security evidence", "weight": 30})
        if head.get("gate", {}).get("overall") == "FAIL":
            factors.append({"reason": "Captured policy decision is FAIL", "weight": 20})
        if counts.get("QUALITY_REGRESSION"):
            factors.append({"reason": "Measured syntax metrics increased", "weight": 10})
    if not factors:
        factors.append(
            {
                "reason": "Explicit BASE/HEAD evidence requires review"
                if not reevaluated
                else "Analyzer re-evaluation requires review",
                "weight": 1,
            }
        )
    impact = head.get("impact", {})
    affected_ids = (
        {r.get("target_id") for r in rows}
        | set(impact.get("affected_claims", []))
        | set(impact.get("affected_documentation", []))
        | set(impact.get("affected_architecture", []))
        | set(impact.get("affected_policies", []))
    )
    links = sorted(
        set(
            db.scalars(
                snapshot_record_query(user.organization_id, repo.id, snapshot.id)
                .where(Record.id.in_(affected_ids))
                .with_only_columns(Record.id)
            )
        )
    )
    row = add(
        db,
        user.organization_id,
        repo.id,
        "engineering_change",
        {
            "base_snapshot_id": base.id,
            "head_snapshot_id": snapshot.id,
            "branch": head["branch"],
            "commit": head["commit"],
            "commit_source": head.get("commit_source"),
            "pr_number": pr_number,
            "component": repo.component,
            "system": repo.system,
            "owner": repo.owner,
            "actor": user.email,
            "actor_basis": "ANALYSIS_INITIATOR_NOT_COMMIT_AUTHOR",
            "files": head.get("changed_files", []),
            "scope": head.get("scope"),
            "at": head["analysis_at"],
            "counts": counts,
            "changes": rows[:500],
            "truncated": len(rows) > 500,
            "total_changes": len(rows),
            "priority": sum(f["weight"] for f in factors),
            "priority_factors": factors,
            "linked_record_ids": links[:500],
            "links_truncated": len(links) > 500,
            "impact": impact,
            "captured_gate": head.get("gate"),
            "analysis_model_changed": reevaluated,
            "authority": "STATIC / DECLARED",
            "runtime_evidence": "UNOBSERVED",
            "limitations": [
                "Correlation is not proof of causality. Use the existing Evidence Graph for provenance.",
                "The analysis initiator is recorded; commit authorship is unknown unless provided by the connector.",
                "Historical snapshots are not backfilled or rewritten; this projection starts with new analyses.",
            ],
        },
        natural_key=snapshot.id,
    )
    audit(
        db,
        user,
        "ENGINEERING_CHANGE_CAPTURED",
        row.id,
        {"base": base.id, "head": snapshot.id, "counts": counts},
        repo.id,
    )
    return row


def scoped(db, user, repository_id=None):
    ids = (
        [require_repo(db, user, repository_id).id] if repository_id else [r.id for r in allowed_repositories(db, user)]
    )
    return select(Record).where(
        Record.organization_id == user.organization_id,
        Record.repository_id.in_(ids),
        Record.kind == "engineering_change",
    )


@router.get("")
def listing(
    request: Request,
    repository_id: str | None = None,
    days: int = Query(7, ge=1, le=365),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    from backend.main import Session

    with Session() as db:
        user, _ = authenticate(db, request)
        query = scoped(db, user, repository_id).where(
            Record.created_at >= (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(
            query.order_by(Record.data["priority"].as_integer().desc(), Record.created_at.desc(), Record.id)
            .offset(offset)
            .limit(limit)
        )
        fields = {
            "base_snapshot_id",
            "head_snapshot_id",
            "branch",
            "commit",
            "pr_number",
            "component",
            "owner",
            "at",
            "counts",
            "priority",
            "priority_factors",
            "analysis_model_changed",
            "authority",
            "total_changes",
        }
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
            "items": [
                {"id": r.id, "repository_id": r.repository_id, **{k: v for k, v in r.data.items() if k in fields}}
                for r in rows
            ],
        }


@router.get("/{change_id}")
def detail(change_id: str, request: Request):
    from backend.main import Session

    with Session() as db:
        user, _ = authenticate(db, request)
        row = db.scalar(scoped(db, user).where(Record.id == change_id))
        if not row:
            raise HTTPException(404, "Engineering change unavailable in authorized scope.")
        return {"id": row.id, "repository_id": row.repository_id, "version": row.version, **row.data}
