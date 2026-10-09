"""Repository catalogue reads never depend on finding or graph aggregation."""
from sqlalchemy import func, select

from backend.db import Grant, Record, Repository
from backend.workspace_read import KINDS, analysis_state, preview

JOB_FIELDS = ("state", "stage", "type", "branch", "snapshot_id", "execution", "started_at", "finished_at",
              "error_detail", "error_code", "errors", "retry_count", "recovery_count")


def repository_page(db, user, repository_id, search, offset, limit):
    query = select(Repository).join(Grant, Grant.repository_id == Repository.id).where(
        Repository.organization_id == user.organization_id, Grant.user_id == user.id)
    if repository_id:
        query = query.where(Repository.id == repository_id)
    if search:
        query = query.where(Repository.name.icontains(search, autoescape=True))
    total = db.scalar(query.with_only_columns(func.count()).order_by(None))
    repos = list(db.scalars(query.order_by(Repository.name, Repository.id).offset(offset).limit(limit)))
    return repos, {"offset": offset, "limit": limit, "total": total, "has_more": offset + len(repos) < total,
                   "scope": "AUTHORIZED_REPOSITORIES", "search": search}


def job_previews(db, user, repos):
    from types import SimpleNamespace
    ranked = select(Record.id, func.row_number().over(partition_by=Record.repository_id, order_by=(
        func.coalesce(Record.data["started_at"].as_string(), Record.data["queued_at"].as_string(), Record.created_at).desc(),
        Record.id.desc())).label("position")).where(Record.organization_id == user.organization_id,
            Record.repository_id.in_([repo.id for repo in repos]), Record.kind == "job").subquery()
    rows = db.execute(select(Record.id, Record.repository_id, *(Record.data[key].label(key) for key in JOB_FIELDS))
        .join(ranked, ranked.c.id == Record.id).where(ranked.c.position == 1))
    return {row.repository_id: SimpleNamespace(id=row.id, data={key: row._mapping[key] for key in JOB_FIELDS
             if row._mapping[key] is not None}) for row in rows}


def listing(db, user, repos, snapshots, page, include_analysis):
    jobs = job_previews(db, user, repos) if include_analysis and repos else {}
    return {
        "repositories": [{"id": repo.id, "name": repo.name, "system": repo.system, "component": repo.component,
            "owner": repo.owner, "provider": repo.provider,
            "snapshot": {"id": snapshots[repo.id].id, **snapshots[repo.id].data} if repo.id in snapshots else None,
            "latest_job": {"id": jobs[repo.id].id, **jobs[repo.id].data} if repo.id in jobs else None} for repo in repos],
        "repository_page": page,
        "analysis": {"state": analysis_state(repos, snapshots, jobs) if include_analysis else "NOT_REQUESTED",
                     "truncated": False, "scope": "REPOSITORY_PAGE_ONLY"},
        **{kind: [] for kind in (*KINDS, "edge", "job", "graph_node")},
        "limitations": ["Repository listing includes no workspace finding or claim totals. Analysis metadata is a bounded preview."],
    }


def diagnostics(data):
    """Legacy claim metadata is interpreted without rewriting immutable snapshots."""
    result = preview(data)
    warnings = data.get("warnings") or []
    engines = data.get("engines") or {}
    partial_engines = {name: value.get("state", "UNKNOWN") for name, value in engines.items()
        if value.get("state") not in {"COMPLETED", "COMPLETED_NO_FINDINGS"}}
    claims = data.get("claim_extraction") or {}
    return {**result, "partial_engines": partial_engines, "warning_count": len(warnings), "warnings": warnings[:50],
        "warnings_complete": len(warnings) <= 50,
        "effective_claim_extraction_state": engines.get("CLAIMS", {}).get("state", claims.get("state", "UNKNOWN")),
        "runtime_evidence": "UNOBSERVED", "customer_code_executed": False}
