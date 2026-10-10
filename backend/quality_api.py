"""Authorized, paged quality reads and audited profile/report mutations."""
import csv
import io
import json
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from analyzers.code_quality import VERSION
from analyzers.code_quality.core import gate, hotspot_rows, summary
from analyzers.code_quality.coverage import absent, import_report
from analyzers.code_quality.rules import config, registry
from backend.db import NativeProfile, QualityAnalysis, QualityOccurrence, Record, now
from backend.domain import add, audit, uid
from backend.governance import require_permission
from backend.quality_domain import current_findings, eligible_findings
from backend.quality_profiles import effective, merge, scope_key
from backend.security import authenticate, require_repo

router = APIRouter(prefix="/api/code-quality", tags=["Native Code Quality"])


def session():
    from backend.main import Session

    return Session()


def context(db, request, repo_id, snapshot_id=None, write=False):
    user, _ = authenticate(db, request, write)
    repo = require_repo(db, user, repo_id)
    query = select(Record).where(
        Record.organization_id == user.organization_id, Record.repository_id == repo.id, Record.kind == "snapshot"
    )
    if snapshot_id:
        query = query.where(Record.id == snapshot_id)
    snapshot = db.scalar(query.order_by(Record.created_at.desc(), Record.id).limit(1))
    if not snapshot:
        raise HTTPException(404, "Snapshot is not available in this repository.")
    return user, repo, snapshot, db.get(QualityAnalysis, snapshot.id)


def report_for(db, projection):
    row = db.scalar(
        select(Record)
        .where(
            Record.organization_id == projection.organization_id,
            Record.repository_id == projection.repository_id,
            Record.kind == "coverage_report",
            Record.data["snapshot_id"].as_string() == projection.snapshot_id,
        )
        .order_by(Record.created_at.desc(), Record.id)
        .limit(1)
    )
    return {"id": row.id, "created_at": row.created_at, **row.data} if row else absent()


def effective_gate(db, projection):
    findings = current_findings(db, projection)
    eligible = eligible_findings(db, projection.organization_id, projection.repository_id, findings)
    result = gate(projection.data, eligible, report_for(db, projection))
    result.update(
        evaluated_at=now(), analysis_snapshot=projection.snapshot_id, exempt_findings=len(findings) - len(eligible)
    )
    return result


@router.get("/rules")
def rules(request: Request):
    with session() as db:
        authenticate(db, request)
        return {"rules": registry(), "count": len(registry())}


@router.get("/{repo_id}/snapshots")
def snapshots(repo_id: str, request: Request):
    with session() as db:
        user, _ = authenticate(db, request)
        require_repo(db, user, repo_id)
        rows = list(
            db.scalars(
                select(Record)
                .where(
                    Record.organization_id == user.organization_id,
                    Record.repository_id == repo_id,
                    Record.kind == "snapshot",
                )
                .order_by(Record.created_at.desc(), Record.id)
                .limit(201)
            )
        )
        return {
            "items": [
                {
                    "id": r.id,
                    "branch": r.data["branch"],
                    "commit": r.data["commit"],
                    "created_at": r.created_at,
                    "analyzer_version": r.data["analyzer_version"],
                    "quality_available": bool(db.get(QualityAnalysis, r.id)),
                }
                for r in rows[:200]
            ],
            "truncated": len(rows) > 200,
        }


@router.get("/{repo_id}/overview")
def overview(repo_id: str, request: Request, snapshot_id: str | None = None):
    with session() as db:
        _, repo, snapshot, projection = context(db, request, repo_id, snapshot_id)
        meta = {
            "snapshot_id": snapshot.id,
            "scope": snapshot.data.get("scope"),
            "repository": repo.name,
            "branch": snapshot.data["branch"],
            "commit": snapshot.data["commit"],
            "base_id": snapshot.data.get("base_id"),
        }
        if not projection:
            return {
                **meta,
                "state": "NOT_AVAILABLE",
                "reason": "This historical snapshot predates Code Intelligence 1.5. Analyze a new snapshot; previous evidence is preserved.",
            }
        data = projection.data
        if snapshot.data.get("comparison", {}).get("analysis_model_changed"):
            data = {**data, "resolved": []}
        findings = current_findings(db, projection)
        return {
            **meta,
            **{
                k: data.get(k)
                for k in [
                    "version",
                    "state",
                    "configuration",
                    "profile_hash",
                    "profile_version",
                    "baseline_state",
                    "scope_counts",
                    "languages",
                    "history_scope",
                    "limitations",
                    "performance",
                    "parser_signature",
                    "parsers",
                ]
            },
            "summary": summary(data, findings),
            "gate": effective_gate(db, projection),
            "coverage": {k: v for k, v in report_for(db, projection).items() if k != "files"},
            "duplication": {k: v for k, v in data["duplication"].items() if k not in {"groups", "lines_by_path"}},
            "resolved": data["resolved"][:200],
        }


@router.get("/{repo_id}/findings")
def findings_page(
    repo_id: str,
    request: Request,
    snapshot_id: str | None = None,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(50, ge=1, le=100),
    q: str = Query("", max_length=200),
    severity: str = "",
    dimension: str = "",
    language: str = "",
    delta: str = "",
    rule: str = "",
    review: str = "",
    new_code: bool = False,
):
    with session() as db:
        _, _, snapshot, projection = context(db, request, repo_id, snapshot_id)
        if not projection:
            return {"items": [], "total": 0, "state": "NOT_AVAILABLE", "offset": offset, "limit": limit}
        query = (
            select(Record)
            .join(QualityOccurrence, QualityOccurrence.finding_id == Record.id)
            .where(
                QualityOccurrence.snapshot_id == snapshot.id,
                QualityOccurrence.organization_id == projection.organization_id,
                QualityOccurrence.repository_id == repo_id,
            )
        )
        for key, value in [
            ("severity", severity),
            ("dimension", dimension),
            ("language", language),
            ("delta", delta),
            ("rule", rule),
        ]:
            if value:
                query = query.where(getattr(QualityOccurrence, key) == value)
        if review:
            query = query.where(Record.data["review_status"].as_string() == review)
        if new_code:
            query = query.where(Record.data["new_code"].as_boolean().is_(True))
        if q:
            query = query.where(
                or_(
                    QualityOccurrence.path.icontains(q, autoescape=True),
                    QualityOccurrence.symbol.icontains(q, autoescape=True),
                    Record.data["title"].as_string().icontains(q, autoescape=True),
                )
            )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(
            query.order_by(QualityOccurrence.path, QualityOccurrence.rule, Record.id).offset(offset).limit(limit)
        )
        return {
            "items": [{"id": r.id, "kind": "finding", "version": r.version, **r.data} for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
            "state": projection.data["state"],
        }


@router.get("/{repo_id}/{section}")
def section_page(
    repo_id: str,
    section: str,
    request: Request,
    snapshot_id: str | None = None,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(50, ge=1, le=100),
    q: str = Query("", max_length=200),
    days: int = Query(30, ge=1, le=90),
):
    if section not in {"metrics", "inventory", "duplication", "coverage", "hotspots", "trends", "source", "export"}:
        raise HTTPException(404, "Unknown quality view.")
    with session() as db:
        _, _, snapshot, projection = context(db, request, repo_id, snapshot_id)
        if not projection:
            return {"items": [], "total": 0, "state": "NOT_AVAILABLE"}
        data = projection.data
        if section == "coverage":
            report = report_for(db, projection)
            return {
                **report,
                "files": report.get("files", [])[offset : offset + limit],
                "total": len(report.get("files", [])),
            }
        if section == "source":
            record = db.scalar(
                select(Record)
                .where(
                    Record.organization_id == projection.organization_id,
                    Record.repository_id == repo_id,
                    Record.kind == "evidence",
                    Record.data["scope"]["snapshot_id"].as_string() == snapshot.id,
                    Record.data["path"].as_string() == q,
                )
                .limit(1)
            )
            if not record:
                raise HTTPException(404, "Source is not available in this snapshot.")
            return {
                "id": record.id,
                "path": q,
                "source": "\n".join(record.data["source"].splitlines()[offset : offset + limit]),
                "first_line": offset + 1,
                "total_lines": len(record.data["source"].splitlines()),
                "hash": record.data.get("hash"),
                "scope": record.data["scope"],
            }
        history = list(
            db.scalars(
                select(Record)
                .where(
                    Record.organization_id == projection.organization_id,
                    Record.repository_id == repo_id,
                    Record.kind == "snapshot",
                    Record.data["branch"].as_string() == snapshot.data["branch"],
                    Record.created_at <= snapshot.created_at,
                )
                .order_by(Record.created_at.desc())
                .limit(201)
            )
        )
        if section == "trends":
            since = (datetime.fromisoformat(snapshot.created_at) - timedelta(days=days)).isoformat()
            items = []
            for row in history[:200]:
                previous = db.get(QualityAnalysis, row.id)
                if row.created_at < since:
                    continue
                if not previous:
                    items.append(
                        {
                            "snapshot_id": row.id,
                            "at": row.created_at,
                            "state": "NOT_AVAILABLE",
                            "annotation": "Historical analyzer has no quality projection.",
                        }
                    )
                    continue
                report = report_for(db, previous)
                items.append(
                    {
                        "snapshot_id": row.id,
                        "at": row.created_at,
                        "branch": row.data["branch"],
                        "commit": row.data["commit"],
                        **previous.data["summary"],
                        "profile_hash": previous.profile_hash,
                        "analyzer_version": previous.analyzer_version,
                        "comparable": previous.profile_hash == projection.profile_hash
                        and previous.analyzer_version == projection.analyzer_version,
                        "coverage_state": report["state"],
                        "line_coverage": report.get("line_percent"),
                        "duplication_percent": previous.data["duplication"]["density_percent"],
                        "annotation": "Comparable captured scope/profile/analyzer"
                        if previous.profile_hash == projection.profile_hash
                        and previous.analyzer_version == projection.analyzer_version
                        else "Analyzer/profile/scope/baseline changed; counts are not directly comparable",
                    }
                )
        elif section == "hotspots":
            items = hotspot_rows(
                data,
                eligible_findings(
                    db, projection.organization_id, projection.repository_id, current_findings(db, projection)
                ),
                [h.data for h in history[:200]],
            )
        elif section == "duplication":
            items = data["duplication"]["groups"]
        elif section == "export":
            return sarif(current_findings(db, projection), snapshot)
        else:
            items = data[section]
        if q:
            items = [i for i in items if q.lower() in str(i).lower()]
        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "offset": offset,
            "limit": limit,
            "state": data["state"],
            "history_truncated": len(history) > 200,
        }


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository_id: str | None = None
    team_id: str | None = None
    expected_version: int = Field(ge=0)
    configuration: dict


@router.get("/profiles/current")
def profile(request: Request, repository_id: str | None = None, team_id: str | None = None):
    with session() as db:
        user, _ = authenticate(db, request)
        if repository_id:
            require_repo(db, user, repository_id)
        try:
            resolved, row = effective(db, user.organization_id, repository_id, team_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return {
            "version": row.version if row else 0,
            "configuration": resolved["quality"],
            "overrides": row.data.get("quality", {}) if row else {},
            "team_id": row.data.get("quality_team") if row and repository_id else team_id,
            "source": "REPOSITORY"
            if row and repository_id
            else "TEAM"
            if team_id
            else "ORGANIZATION"
            if resolved["profile_lineage"]
            else "RECOMMENDED",
            "inheritance": resolved["profile_lineage"],
            "inherited_version": resolved["profile_lineage"][-1]["version"]
            if resolved["profile_lineage"] and not row
            else None,
        }


@router.post("/profiles/current")
def save_profile(body: ProfileBody, request: Request):
    with session() as db:
        user, _ = authenticate(db, request, True)
        require_permission(db,user,"organization.settings.manage")
        if body.repository_id:
            require_repo(db, user, body.repository_id)
        try:
            selected_scope = scope_key(body.repository_id, body.team_id)
            # Validate the patch itself, then validate the effective inherited configuration.
            config(body.configuration)
            resolved, _ = effective(db, user.organization_id, body.repository_id, body.team_id)
            configuration = config(merge(resolved["quality"], body.configuration))
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        if configuration["baseline_id"]:
            if not body.repository_id:
                raise HTTPException(422, "A baseline belongs to a repository profile.")
            context(db, request, body.repository_id, configuration["baseline_id"])
        row = db.scalar(
            select(NativeProfile)
            .where(
                NativeProfile.organization_id == user.organization_id,
                NativeProfile.scope_key == selected_scope,
            )
            .with_for_update()
        )
        if body.expected_version != (row.version if row else 0):
            raise HTTPException(409, "Profile changed. Refresh before saving.")
        if row:
            row.data = {**row.data, "quality": body.configuration}
        else:
            row = NativeProfile(
                id=uid(),
                organization_id=user.organization_id,
                repository_id=body.repository_id,
                scope_key=selected_scope,
                data={"quality": body.configuration},
            )
            db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Profile was created concurrently. Refresh before saving.") from None
        audit(
            db,
            user,
            "QUALITY_PROFILE_UPDATED",
            row.id,
            {"version": row.version, "configuration": configuration},
            body.repository_id,
        )
        resolved, _ = effective(db, user.organization_id, body.repository_id, body.team_id)
        add(
            db,
            user.organization_id,
            body.repository_id,
            "quality_profile_version",
            {
                "profile_id": row.id,
                "scope": selected_scope,
                "version": row.version,
                "overrides": body.configuration,
                "configuration": resolved["quality"],
                "inheritance": resolved["profile_lineage"],
                "gate_version": row.version,
                "actor": user.email,
                "recorded_at": now(),
            },
        )
        db.commit()
        return {"version": row.version, "configuration": resolved["quality"]}


class CoverageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str
    report: str = Field(max_length=1000000)
    format: str = Field(default="auto", max_length=30)
    declared_commit: str | None = Field(default=None, max_length=80)
    strip_prefix: str = Field(default="", max_length=240)
    source_root: str = Field(default="", max_length=240)
    source: str = Field(default="uploaded report", max_length=240)


class TeamAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository_id: str
    team_id: str | None = None
    expected_version: int = Field(ge=0)


@router.post("/profiles/team-assignment")
def assign_team(body: TeamAssignment, request: Request):
    with session() as db:
        user, _ = authenticate(db, request, True)
        require_permission(db,user,"organization.settings.manage")
        require_repo(db, user, body.repository_id)
        if body.team_id:
            try:
                team_scope = scope_key(team_id=body.team_id)
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            if not db.scalar(
                select(NativeProfile).where(
                    NativeProfile.organization_id == user.organization_id, NativeProfile.scope_key == team_scope
                )
            ):
                raise HTTPException(404, "Team profile unavailable in this organization.")
        _, row = effective(db, user.organization_id, body.repository_id)
        if body.expected_version != (row.version if row else 0):
            raise HTTPException(409, "Repository profile changed; refresh before assignment.")
        if not row:
            row = NativeProfile(
                id=uid(),
                organization_id=user.organization_id,
                repository_id=body.repository_id,
                scope_key=body.repository_id,
                data={},
            )
            db.add(row)
        row.data = {**row.data, "quality_team": body.team_id}
        db.flush()
        resolved, _ = effective(db, user.organization_id, body.repository_id)
        revision = add(
            db,
            user.organization_id,
            body.repository_id,
            "quality_profile_version",
            {
                "profile_id": row.id,
                "scope": body.repository_id,
                "version": row.version,
                "team_id": body.team_id,
                "overrides": row.data.get("quality", {}),
                "configuration": resolved["quality"],
                "inheritance": resolved["profile_lineage"],
                "actor": user.email,
                "recorded_at": now(),
                "gate_version": row.version,
            },
        )
        audit(
            db,
            user,
            "QUALITY_TEAM_ASSIGNED",
            revision.id,
            {"team_id": body.team_id, "version": row.version},
            body.repository_id,
        )
        db.commit()
        return {"version": row.version, "team_id": body.team_id, "configuration": resolved["quality"]}


@router.get("/profiles/versions")
def profile_versions(
    request: Request,
    repository_id: str | None = None,
    team_id: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    with session() as db:
        user, _ = authenticate(db, request)
        if repository_id:
            require_repo(db, user, repository_id)
        try:
            selected_scope = scope_key(repository_id, team_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        query = select(Record).where(
            Record.organization_id == user.organization_id,
            Record.kind == "quality_profile_version",
            Record.data["scope"].as_string() == selected_scope,
        )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Record.created_at.desc(), Record.id.desc()).offset(offset).limit(limit))
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": [{"id": r.id, "created_at": r.created_at, **r.data} for r in rows],
            "legacy_note": "Versions begin with hardening changes; pre-existing settings and audit records are retained.",
        }


@router.post("/{repo_id}/coverage")
def coverage_upload(repo_id: str, body: CoverageBody, request: Request):
    with session() as db:
        user, _, snapshot, projection = context(db, request, repo_id, body.snapshot_id, True)
        if not projection:
            raise HTTPException(409, "Analyze a Code Intelligence snapshot before importing coverage.")
        paths = {
            r["path"]
            for r in projection.data["inventory"]
            if r["kind"] in {"SOURCE", "TEST", "EXAMPLE"} and r["parser_state"] in {"COMPLETED", "PARTIAL"}
        }
        sources = {
            r.data["path"]: r.data["source"]
            for r in db.scalars(
                select(Record).where(
                    Record.organization_id == user.organization_id,
                    Record.repository_id == repo_id,
                    Record.kind == "evidence",
                    Record.data["scope"]["snapshot_id"].as_string() == snapshot.id,
                )
            )
            if r.data.get("path") in paths
        }
        report = import_report(
            body.report,
            sources,
            format=body.format,
            declared_commit=body.declared_commit,
            snapshot_commit=snapshot.data["commit"],
            changed_lines=snapshot.data.get("changed_lines"),
            strip_prefix=body.strip_prefix,
            source_root=body.source_root,
            source=body.source,
        )
        if report["state"] not in {"VALID", "PARTIAL"}:
            raise HTTPException(
                422, {"message": report["state"] + ": " + "; ".join(report["errors"]), "report": report}
            )
        row = add(
            db,
            user.organization_id,
            repo_id,
            "coverage_report",
            {**report, "snapshot_id": snapshot.id, "imported_at": now(), "actor": user.email},
        )
        audit(
            db,
            user,
            "COVERAGE_REPORT_IMPORTED",
            row.id,
            {"snapshot_id": snapshot.id, "report_hash": report["report_hash"], "state": report["state"]},
            repo_id,
        )
        db.commit()
        return {
            "id": row.id,
            "state": report["state"],
            "report_hash": report["report_hash"],
            "gate": effective_gate(db, projection),
        }


def sarif(findings, snapshot):
    metadata = registry()
    indices = {r["id"]: i for i, r in enumerate(metadata)}
    return {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ProjectTrace Native Code Quality",
                        "version": "1.5.0",
                        "rules": [
                            {
                                "id": r["id"],
                                "name": r["id"].replace("-", ""),
                                "shortDescription": {"text": r["title"]},
                                "help": {"text": r["remediation"]},
                                "properties": {"dimension": r["dimension"], "status": r["status"]},
                            }
                            for r in metadata
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": f["rule"],
                        "ruleIndex": indices[f["rule"]],
                        "level": "error"
                        if f["severity"] in {"HIGH", "CRITICAL"}
                        else "warning"
                        if f["severity"] == "MEDIUM"
                        else "note",
                        "message": {"text": f["explanation"]},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": quote(f["path"], safe="/")},
                                    "region": {"startLine": f["line"], "endLine": f.get("end_line", f["line"])},
                                }
                            }
                        ],
                        "partialFingerprints": {"projectTraceSymbol/v2": f["fingerprint"]},
                        "properties": {
                            "snapshotId": snapshot.id,
                            "humanReview": f.get("review_status", "OPEN"),
                            "machineDelta": f.get("delta"),
                            "dimension": f["dimension"],
                        },
                    }
                    for f in findings
                ],
            }
        ],
    }


@router.get("/{repo_id}/exports/csv")
def csv_export(repo_id: str, request: Request, snapshot_id: str | None = None):
    with session() as db:
        _, _, _, projection = context(db, request, repo_id, snapshot_id)
        rows = current_findings(db, projection) if projection else []
        output = io.StringIO()
        fields = [
            "rule",
            "dimension",
            "severity",
            "confidence",
            "path",
            "line",
            "symbol",
            "delta",
            "review_status",
            "fingerprint",
        ]
        writer = csv.writer(output)
        writer.writerow(fields)
        for row in rows:
            writer.writerow(
                [
                    ("'" + str(row.get(k, "")))
                    if str(row.get(k, "")).startswith(("=", "+", "-", "@", "\t", "\r"))
                    else row.get(k, "")
                    for k in fields
                ]
            )
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ProjectTrace-quality.csv"'},
        )


@router.get("/{repo_id}/exports/json")
def json_export(repo_id: str, request: Request, snapshot_id: str | None = None):
    with session() as db:
        _, _, snapshot, projection = context(db, request, repo_id, snapshot_id)
        rows = current_findings(db, projection) if projection else []
        return Response(
            json.dumps(
                {"analyzer_version": VERSION, "snapshot_id": snapshot.id if snapshot else None, "findings": rows}
            ),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="ProjectTrace-quality.json"'},
        )


# Specific routes must precede the generic read-view path.
router.routes.sort(key=lambda route: "{section}" in route.path)
