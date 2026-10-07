"""Repository-scoped trust projections and audited organization controls."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import func, select

from analyzers.capabilities import registry
from analyzers.engine import VERSION, redact, redact_metadata
from backend.accuracy import report as accuracy_report
from backend.db import CloudAsset, QualityAnalysis, Record, TenantPolicy
from backend.domain import audit
from backend.security import allowed_repositories, authenticate, require_repo
from backend.trust import integrity, policy

router = APIRouter(prefix="/api/trust", tags=["Trust and coverage"])


@router.get("/exceptions")
def exceptions(
    request: Request,
    repository_id: str | None = None,
    state: Literal["ACTIVE", "EXPIRED", "REVOKED"] | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    with session() as db:
        user, _ = authenticate(db, request)
        current = datetime.now(timezone.utc).isoformat()
        query = repo_scope(db, user, repository_id).where(Record.kind == "exception")
        expiry = Record.data["expires_at"].as_string()
        revoked = Record.data["state"].as_string() == "REVOKED"
        if state == "REVOKED":
            query = query.where(revoked)
        elif state == "ACTIVE":
            query = query.where(expiry > current, ~func.coalesce(revoked, False))
        elif state == "EXPIRED":
            query = query.where(expiry <= current, ~func.coalesce(revoked, False))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Record.created_at.desc(), Record.id).offset(offset).limit(limit))
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
            "items": [
                {
                    "id": r.id,
                    "version": r.version,
                    "repository_id": r.repository_id,
                    **r.data,
                    "state": "REVOKED"
                    if r.data.get("state") == "REVOKED"
                    else "ACTIVE"
                    if r.data.get("expires_at", "") > current
                    else "EXPIRED",
                }
                for r in rows
            ],
            "basis": "Expiry and revocation are organization policies; gate eligibility also requires matching issue context.",
        }


class ExceptionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    action: Literal["EXTEND", "REVOKE"]
    reason: str = Field(min_length=8, max_length=2000)
    days: int = Field(default=1, ge=1, le=90)


@router.post("/exceptions/{exception_id}")
def change_exception(exception_id: str, body: ExceptionChange, request: Request):
    with session() as db:
        user, _ = authenticate(db, request, True)
        if user.role not in {"ORG_OWNER", "ADMIN", "SECURITY_REVIEWER"}:
            raise HTTPException(403, "Exception administration requires a privileged reviewer.")
        row = db.get(Record, exception_id)
        if not row or row.kind != "exception" or row.organization_id != user.organization_id or not row.repository_id:
            raise HTTPException(404, "Exception unavailable in authorized scope.")
        require_repo(db, user, row.repository_id)
        if row.version != body.expected_version:
            raise HTTPException(409, "Exception changed; refresh before updating.")
        if body.days > policy(db, user.organization_id)["maximum_exception_days"]:
            raise HTTPException(422, "Exception exceeds the organization duration policy.")
        expiry = datetime.now(timezone.utc) + timedelta(days=body.days if body.action == "EXTEND" else -1)
        details = {
            "action": body.action,
            "actor": user.email,
            "reason": redact(body.reason),
            "at": datetime.now(timezone.utc).isoformat(),
            "old_expiry": row.data.get("expires_at"),
            "new_expiry": expiry.isoformat(),
        }
        row.data = {
            **row.data,
            "expires_at": expiry.isoformat(),
            "state": "ACTIVE" if body.action == "EXTEND" else "REVOKED",
            "administration": [*row.data.get("administration", []), details],
        }
        audit(db, user, "EXCEPTION_" + body.action, row.id, details, row.repository_id)
        db.commit()
        return {"id": row.id, "version": row.version, **row.data}


def session():
    from backend.main import Session

    return Session()


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    source_egress: Literal["NO_EXTERNAL_SOURCE_EGRESS"] = "NO_EXTERNAL_SOURCE_EGRESS"
    ai_mode: Literal["DISABLED"] = "DISABLED"
    package_coordinate_advisories: StrictBool = False
    github_check_metadata: StrictBool = False
    maximum_exception_days: int = Field(default=90, ge=1, le=90)


@router.get("/capabilities")
def capabilities(request: Request):
    with session() as db:
        authenticate(db, request)
        return registry(VERSION)


@router.get("/policy")
def get_policy(request: Request):
    with session() as db:
        user, _ = authenticate(db, request)
        return policy(db, user.organization_id)


@router.post("/policy")
def update_policy(body: PolicyUpdate, request: Request):
    with session() as db:
        user, _ = authenticate(db, request, True)
        if user.role not in {"ORG_OWNER", "ADMIN"}:
            raise HTTPException(403, "Only organization administrators can change egress policy.")
        row = db.scalar(
            select(TenantPolicy).where(TenantPolicy.organization_id == user.organization_id).with_for_update()
        )
        if body.version != (row.version if row else 0):
            raise HTTPException(409, "Policy changed; refresh before saving.")
        data = body.model_dump(exclude={"version"})
        if row:
            row.data = data
        else:
            row = TenantPolicy(organization_id=user.organization_id, data=data)
            db.add(row)
        db.flush()
        audit(db, user, "TENANT_EGRESS_POLICY_UPDATED", user.organization_id, {**data, "version": row.version})
        db.commit()
        return policy(db, user.organization_id)


@router.get("/audit-integrity")
def audit_integrity(request: Request):
    with session() as db:
        user, _ = authenticate(db, request)
        if user.role not in {"ORG_OWNER", "ADMIN"}:
            raise HTTPException(403, "Organization administrators verify the organization audit chain.")
        return integrity(db, user.organization_id)


class CheckpointBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: str = Field(max_length=4096)
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    algorithm: Literal["HMAC-SHA256"]
    key_id: str = Field(max_length=100)


@router.post("/audit-checkpoint/verify")
def audit_checkpoint(body: CheckpointBody, request: Request):
    from backend.trust import verify_checkpoint

    with session() as db:
        user, _ = authenticate(db, request, True)
        if user.role not in {"ORG_OWNER", "ADMIN"}:
            raise HTTPException(403, "Only administrators verify retained organization checkpoints.")
        try:
            return verify_checkpoint(db, user.organization_id, body.model_dump())
        except ValueError:
            raise HTTPException(422, "Checkpoint signature or organization scope is invalid.") from None


def repo_scope(db, user, repository_id=None):
    ids = (
        [require_repo(db, user, repository_id).id] if repository_id else [r.id for r in allowed_repositories(db, user)]
    )
    return select(Record).where(Record.organization_id == user.organization_id, Record.repository_id.in_(ids))


@router.get("/snapshots")
def snapshots(
    request: Request,
    repository_id: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    with session() as db:
        user, _ = authenticate(db, request)
        query = repo_scope(db, user, repository_id).where(Record.kind == "snapshot")
        rows = db.execute(
            query.with_only_columns(
                Record.id,
                Record.repository_id,
                Record.data["branch"].as_string().label("branch"),
                Record.data["commit"].as_string().label("commit"),
                Record.data["analysis_at"].as_string().label("analysis_at"),
            )
            .order_by(Record.created_at.desc(), Record.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ).all()
        return {"items": [dict(r._mapping) for r in rows[:limit]], "offset": offset, "has_more": len(rows) > limit}


@router.get("/coverage")
def analysis_coverage(
    request: Request,
    repository_id: str | None = None,
    snapshot_id: str | None = None,
    state: str | None = None,
    q: str = Query("", max_length=240),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    with session() as db:
        user, _ = authenticate(db, request)
        query = repo_scope(db, user, repository_id).where(Record.kind == "snapshot")
        if snapshot_id:
            query = query.where(Record.id == snapshot_id)
        snapshot = db.scalar(query.order_by(Record.created_at.desc(), Record.id.desc()).limit(1))
        if not snapshot:
            if snapshot_id:
                raise HTTPException(404, "Snapshot unavailable in authorized scope.")
            return {"state": "NOT_AVAILABLE", "items": [], "total": 0, "summary": {}, "languages": []}
        coverage = snapshot.data.get("analysis_coverage")
        if not coverage:
            return {
                "state": "LEGACY_NOT_MEASURED",
                "snapshot_id": snapshot.id,
                "items": [],
                "total": 0,
                "summary": {},
                "languages": [],
                "limitations": [
                    "Run a new analysis to capture complete file coverage; previous snapshots remain unchanged."
                ],
            }
        inventory_fields = {
            "path",
            "component",
            "language",
            "kind",
            "coverage_source",
            "analysis_state",
            "bytes",
            "loc",
            "reason",
            "parser",
            "parser_state",
            "analyzer_support",
            "quality_support",
            "security_support",
            "source_parser_completed",
            "native_scan_performed",
            "authority",
            "runtime_observed",
            "precision",
        }
        inventory = [
            redact_metadata(
                {
                    **{k: v for k, v in row.items() if k in inventory_fields},
                    "diagnostics": [
                        {k: d.get(k) for k in ("analyzer", "code", "state", "message")}
                        for d in row.get("diagnostics", [])
                    ],
                }
            )
            for row in coverage["inventory"]
        ]
        selected = [
            r
            for r in inventory
            if (not state or r["analysis_state"] == state)
            and (not q or q.lower() in r["path"].lower() or q.lower() in r["language"].lower())
        ]
        job = db.scalar(
            repo_scope(db, user, snapshot.repository_id)
            .where(Record.kind == "job", Record.data["snapshot_id"].as_string() == snapshot.id)
            .order_by(Record.created_at.desc())
            .limit(1)
        )
        quality = db.get(QualityAnalysis, snapshot.id)
        resources = db.execute(
            select(Record.data["format"].as_string(), func.count())
            .join(CloudAsset, CloudAsset.id == Record.id)
            .where(
                CloudAsset.organization_id == user.organization_id,
                CloudAsset.repository_id == snapshot.repository_id,
                CloudAsset.snapshot_id == snapshot.id,
                Record.data["authority"].as_string() == "STATIC",
            )
            .group_by(Record.data["format"].as_string())
        ).all()
        counts = dict(resources)
        formats = {
            "Terraform": "TERRAFORM",
            "CloudFormation": "CLOUDFORMATION",
            "Kubernetes": "KUBERNETES",
            "Compose": "COMPOSE",
            "Dockerfile": "DOCKERFILE",
        }
        infrastructure = []
        for label, key in formats.items():
            format_inventory = [r for r in inventory if r["language"] == label]
            infrastructure.append(
                {
                    "format": key,
                    "files": len(format_inventory),
                    "analyzed_files": sum(r["native_scan_performed"] for r in format_inventory),
                    "resources": counts.get(key, 0),
                    "parse_failures": sum(r["analysis_state"] == "PARSE_FAILED" for r in format_inventory),
                    "maturity": "PARTIAL",
                    "authority": "STATIC",
                    "runtime_evidence": "UNOBSERVED",
                    "diagnostics": [{"path": r["path"], **d} for r in format_inventory for d in r["diagnostics"]],
                }
            )
        return {
            k: redact_metadata(v)
            for k, v in coverage.items()
            if k
            in {
                "schema",
                "summary",
                "languages",
                "authority",
                "runtime_evidence",
                "customer_code_executed",
                "external_llm_used",
                "source_sent_to_external_ai",
                "limitations",
            }
        } | {
            "state": snapshot.data["status"],
            "repository_id": snapshot.repository_id,
            "snapshot_id": snapshot.id,
            "branch": snapshot.data["branch"],
            "commit": snapshot.data["commit"],
            "commit_source": snapshot.data.get("commit_source"),
            "analysis_at": snapshot.data["analysis_at"],
            "analyzer_version": snapshot.data["analyzer_version"],
            "ruleset_version": snapshot.data.get("parser_signature", snapshot.data["analyzer_version"]),
            "quality_gate_version": (quality.data if quality else {}).get("gate_version"),
            "quality_profile_lineage": (quality.data if quality else {}).get("profile_lineage", []),
            "base_snapshot_id": snapshot.data.get("base_id"),
            "infrastructure": infrastructure,
            "profile_version": snapshot.data.get("native_profile", {}).get("version", 0),
            "job_id": job.id if job else None,
            "total": len(selected),
            "offset": offset,
            "limit": limit,
            "items": selected[offset : offset + limit],
            "has_more": offset + limit < len(selected),
        }


@router.get("/rule-health")
def rule_health(request: Request, repository_id: str | None = None):
    with session() as db:
        user, _ = authenticate(db, request)
        reviews = list(
            db.scalars(
                repo_scope(db, user, repository_id)
                .where(Record.kind == "review")
                .order_by(Record.created_at.desc())
                .limit(20001)
            )
        )
        groups = defaultdict(lambda: Counter())
        # Count latest judgment per occurrence, not repeated actions as independent labels.
        seen = set()
        for review in reviews[:20000]:
            item = review.data
            if item.get("target") in seen or not item.get("rule"):
                continue
            if item.get("action") in {
                "REOPEN",
                "RESOLVE",
                "IN_REVIEW",
                "REQUEST_MORE_EVIDENCE",
                "ACCEPT_RISK",
                "CREATE_EXCEPTION",
            }:
                seen.add(item["target"])
                continue
            if item.get("action") not in {"CONFIRM", "FALSE_POSITIVE"}:
                continue
            seen.add(item["target"])
            key = (
                item["rule"],
                item.get("rule_version", "UNKNOWN"),
                item.get("language", "UNKNOWN"),
                item.get("framework", "UNKNOWN"),
            )
            groups[key][item["action"]] += 1
        rows = []
        for key, counts in sorted(groups.items()):
            n = counts["CONFIRM"] + counts["FALSE_POSITIVE"]
            rows.append(
                dict(zip(("rule", "rule_version", "language", "framework"), key))
                | {
                    "confirmed": counts["CONFIRM"],
                    "dismissed": counts["FALSE_POSITIVE"],
                    "reviewed_occurrences": n,
                    "dismissal_fraction": counts["FALSE_POSITIVE"] / n,
                    "precision": "UNMEASURED",
                    "blocking_eligible": False,
                }
            )
        return {
            "groups": rows,
            "validation": accuracy_report(),
            "truncated": len(reviews) > 20000,
            "limitations": [
                "Voluntary review feedback is biased; dismissal fraction is not precision, recall or a population false-positive rate.",
                "Legacy reviews lack rule metadata. One dismissal never disables a rule globally.",
            ],
        }


@router.get("/accuracy")
def accuracy(request: Request):
    with session() as db:
        authenticate(db, request)
        return accuracy_report()


@router.get("/infrastructure")
def infrastructure(
    request: Request,
    repository_id: str | None = None,
    snapshot_id: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    infrastructure_format: Literal["TERRAFORM", "CLOUDFORMATION", "KUBERNETES", "COMPOSE", "DOCKERFILE"] | None = Query(
        None, alias="format"
    ),
):
    with session() as db:
        user, _ = authenticate(db, request)
        query = repo_scope(db, user, repository_id)
        snapshot_scope = query.where(Record.kind == "snapshot")
        metadata_query = snapshot_scope.with_only_columns(
            Record.id,
            Record.repository_id,
            Record.data["engines"].label("engines"),
            Record.data["warnings"].label("warnings"),
        )
        if snapshot_id:
            snapshots = db.execute(metadata_query.where(Record.id == snapshot_id)).all()
            if not snapshots:
                raise HTTPException(404, "Snapshot unavailable in authorized scope.")
        else:
            ranked = snapshot_scope.with_only_columns(
                Record.id.label("snapshot_id"),
                func.row_number()
                .over(partition_by=Record.repository_id, order_by=(Record.created_at.desc(), Record.id.desc()))
                .label("rank"),
            ).subquery()
            snapshots = db.execute(
                metadata_query.join(ranked, ranked.c.snapshot_id == Record.id)
                .where(ranked.c.rank == 1)
                .order_by(Record.repository_id)
                .limit(201)
            ).all()
        scope_truncated = len(snapshots) > 200
        snapshots = snapshots[:200]
        ids = [s.id for s in snapshots]
        scoped = query.where(Record.data["scope"]["snapshot_id"].as_string().in_(ids))
        resource_scope = (
            scoped.where(Record.data["format"].as_string() == infrastructure_format)
            if infrastructure_format
            else scoped
        )
        finding_scope = (
            scoped.where(Record.data["infrastructure_format"].as_string() == infrastructure_format)
            if infrastructure_format
            else scoped
        )
        resources = list(
            db.scalars(
                resource_scope.where(
                    Record.kind == "graph_node",
                    Record.data["authority"].as_string() == "STATIC",
                    Record.id.in_(
                        select(CloudAsset.id).where(
                            CloudAsset.organization_id == user.organization_id, CloudAsset.snapshot_id.in_(ids)
                        )
                    ),
                    Record.data["class"]
                    .as_string()
                    .in_(["CLOUD_RESOURCE", "CLOUD_IDENTITY", "CONTAINER_WORKLOAD", "CONTAINER_IMAGE"]),
                )
                .order_by(Record.id)
                .offset(offset)
                .limit(limit + 1)
            )
        )
        findings = list(
            db.scalars(
                finding_scope.where(Record.kind == "finding", Record.data["category"].as_string() == "IAC")
                .order_by(Record.id)
                .offset(offset)
                .limit(limit + 1)
            )
        )
        format_counts = dict(
            db.execute(
                select(Record.data["format"].as_string(), func.count())
                .join(CloudAsset, CloudAsset.id == Record.id)
                .where(CloudAsset.organization_id == user.organization_id, CloudAsset.snapshot_id.in_(ids))
                .where(Record.data["authority"].as_string() == "STATIC")
                .group_by(Record.data["format"].as_string())
            ).all()
        )
        format_counts = {key or "LEGACY_UNKNOWN": count for key, count in format_counts.items()}
        return {
            "authority": "STATIC",
            "runtime_observed": False,
            "format_counts": dict(format_counts),
            "resources": [{"id": r.id, "kind": r.kind, "version": r.version, **r.data} for r in resources[:limit]],
            "findings": [{"id": r.id, "kind": r.kind, "version": r.version, **r.data} for r in findings[:limit]],
            "has_more_resources": len(resources) > limit,
            "has_more_findings": len(findings) > limit,
            "offset": offset,
            "scope_truncated": scope_truncated,
            "coverage": [
                {
                    "snapshot_id": s.id,
                    "repository_id": s.repository_id,
                    "engine": (s.engines or {}).get("IAC", {}),
                    "diagnostics": [w for w in (s.warnings or []) if w.get("analyzer") == "IAC"],
                }
                for s in snapshots
            ],
            "limitations": [
                "Declared configuration only; symbolic expressions and remote modules are not executed or fetched.",
                "No runtime reachability, credential validity, image CVE or deployment compliance assertion.",
            ],
        }
