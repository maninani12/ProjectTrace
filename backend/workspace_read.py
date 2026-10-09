"""Authorized bounded workspace reads. Records, not previews, remain authoritative."""
from types import SimpleNamespace

from sqlalchemy import func, literal, or_, select, union_all

from backend.db import Record, SnapshotView
from backend.json_query import indexed_text

KINDS = ("claim", "finding", "evidence", "dependency", "drift", "pr", "review", "exception", "risk_path")
FIELDS = (
    "branch", "commit", "scope", "status", "file_count", "gate", "changed_files", "engines", "impact",
    "reused_files", "analyzer_version", "base_id", "warnings", "claim_extraction", "commit_source",
    "analyzer_results", "parser_signature", "analysis_at", "source_storage", "source_provenance", "analysis_coverage",
)


def preview(data):
    """List previews disclose their bounds; detailed immutable records remain available."""
    result = {key: data[key] for key in FIELDS if key in data}
    for key in ("changed_files", "warnings"):
        values = result.get(key) or []
        result[key + "_count"] = len(values)
        result[key] = values[:20]
    impact = result.get("impact")
    if isinstance(impact, dict):
        result["impact"] = {key: value[:20] if isinstance(value, list) else value for key, value in impact.items()}
        result["impact_list_counts"] = {key: len(value) for key, value in impact.items() if isinstance(value, list)}
    engines = result.get("engines")
    if isinstance(engines, dict):
        result["engines"] = {
            name: {key: value[:20] if isinstance(value, list) else value for key, value in engine.items()}
            for name, engine in engines.items() if isinstance(engine, dict)
        }
    gate = result.get("gate")
    if isinstance(gate, dict):
        result["gate"] = {**gate, "results": gate.get("results", [])[:20], "result_count": len(gate.get("results", []))}
    coverage = result.pop("analysis_coverage", None)
    if isinstance(coverage, dict):
        result["coverage_summary"] = coverage.get("summary", {})
    result["metadata_preview"] = True
    return result


def project_snapshot(db, snapshot):
    """Same transaction as publication; no separately visible unfinished generation."""
    db.flush()
    row = db.get(SnapshotView, snapshot.id)
    if row is None:
        row = SnapshotView(snapshot_id=snapshot.id, organization_id=snapshot.organization_id,
                           repository_id=snapshot.repository_id, source_version=snapshot.version, data={})
        db.add(row)
    row.source_version, row.data = snapshot.version, preview(snapshot.data)
    return row


def snapshot_predicate(snapshot_id, kind=None):
    # Edges use a top-level snapshot, all core observations use the nested scope.
    if kind == "edge":
        return indexed_text(Record.data, "snapshot_id") == snapshot_id
    return indexed_text(Record.data, "scope", "snapshot_id") == snapshot_id


def scoped_current(user, repos, snapshots, kinds):
    scopes = [
        (Record.repository_id == repo.id) & snapshot_predicate(snapshots[repo.id].id)
        for repo in repos if repo.id in snapshots
    ]
    kind_scope = Record.kind == literal(kinds[0], literal_execute=True) if len(kinds) == 1 else Record.kind.in_(kinds)
    return select(Record).where(Record.organization_id == user.organization_id, kind_scope, or_(*scopes) if scopes else False)


def latest_jobs(db, user, repos):
    ranked = select(
        Record.id, func.row_number().over(partition_by=Record.repository_id, order_by=(
            func.coalesce(Record.data["started_at"].as_string(), Record.data["queued_at"].as_string(), Record.created_at).desc(), Record.id.desc())).label("position"),
    ).where(Record.organization_id == user.organization_id, Record.repository_id.in_([r.id for r in repos]), Record.kind == "job").subquery()
    return {row.repository_id: row for row in db.scalars(select(Record).join(ranked, ranked.c.id == Record.id).where(ranked.c.position == 1))}


def analysis_state(repos, snapshots, jobs):
    states = []
    for repo in repos:
        snapshot_state = snapshots[repo.id].data.get("status", "UNKNOWN") if repo.id in snapshots else "READY"
        job = jobs.get(repo.id)
        state = job.data.get("state", snapshot_state) if job else snapshot_state
        if job and job.data.get("type") == "ADVISORIES" and state in {"COMPLETED", "COMPLETED_NO_FINDINGS"} and snapshot_state == "PARTIAL":
            state = "PARTIAL"
        states.append(state)
    if not repos:
        return "NO_REPOSITORY"
    for state in ("FAILED", "FETCHING", "VALIDATING", "PARSING", "ANALYZING", "BUILDING_EVIDENCE", "EXTRACTING_CLAIMS", "VERIFYING", "CORRELATING", "FINALIZING", "QUEUED", "PARTIAL", "READY", "CANCELLED", "UNKNOWN"):
        if state in states:
            return state
    return "COMPLETED" if "COMPLETED" in states else "COMPLETED_NO_FINDINGS"


def summary_counts(db, user, repos, snapshots):
    # Restrict kinds before extracting JSON: half a million graph records are not summary inputs.
    per_repo = {repo.id: {"totals": {kind: 0 for kind in KINDS}, "claim_status": {}, "finding_severity": {}, "material_findings": 0} for repo in repos}
    # Covering snapshot-index counts do not fetch evidence/dependency payloads.
    def grouped(kinds, columns):
        # An OR across repositories lets SQLite scan a tenant-wide index instead
        # of seeking the repository/snapshot prefix. UNION keeps each immutable
        # scope a point range; bounded chunks avoid SQL compound-select limits.
        current = [repo for repo in repos if repo.id in snapshots]
        for offset in range(0, len(current), 200):
            queries = [scoped_current(user, [repo], snapshots, kinds).with_only_columns(
                Record.repository_id, *columns, func.count()).group_by(Record.repository_id, *columns)
                for repo in current[offset:offset + 200]]
            if queries:
                yield from db.execute(queries[0] if len(queries) == 1 else union_all(*queries))

    for repo_id, kind, count in grouped(KINDS, [Record.kind]):
        per_repo[repo_id]["totals"][kind] = count
    status = indexed_text(Record.data, "status")
    for repo_id, status_value, count in grouped(["claim"], [status]):
        per_repo[repo_id]["claim_status"][status_value or "UNKNOWN"] = count
    severity, review = indexed_text(Record.data, "severity"), indexed_text(Record.data, "review_status")
    for repo_id, severity_value, review_value, count in grouped(["finding"], [severity, review]):
        item = per_repo[repo_id]
        item["finding_severity"][severity_value or "UNKNOWN"] = item["finding_severity"].get(severity_value or "UNKNOWN", 0) + count
        if severity_value in {"HIGH", "CRITICAL"} and review_value not in {"RESOLVED", "FALSE_POSITIVE"}:
            item["material_findings"] += count
    total = {"totals": {kind: 0 for kind in KINDS}, "claim_status": {}, "finding_severity": {}, "material_findings": 0}
    for item in per_repo.values():
        total["material_findings"] += item["material_findings"]
        for name in ("totals", "claim_status", "finding_severity"):
            for key, value in item[name].items():
                total[name][key] = total[name].get(key, 0) + value
    return {**total, "repositories": per_repo, "scope": "LATEST_PUBLISHED_SNAPSHOT_PER_AUTHORIZED_REPOSITORY", "complete": True}


def projected_snapshots(db, ranked):
    query = select(ranked.c.id, ranked.c.repository_id, ranked.c.version, ranked.c.created_at, SnapshotView.data).join(
        SnapshotView, (SnapshotView.snapshot_id == ranked.c.id) & (SnapshotView.organization_id == ranked.c.organization_id)
        & (SnapshotView.repository_id == ranked.c.repository_id) & (SnapshotView.source_version == ranked.c.version),
    ).where(ranked.c.position == 1)
    return {row.repository_id: SimpleNamespace(id=row.id, kind="snapshot", repository_id=row.repository_id,
             version=row.version, created_at=row.created_at, data=row.data) for row in db.execute(query)}


def packed(row):
    result = {"id": row.id, "kind": row.kind, "repository_id": row.repository_id,
              "version": row.version, "created_at": row.created_at, **row.data}
    if row.kind == "evidence":
        result.pop("source", None)
        result.pop("source_blob_digest", None)
    if row.kind == "claim":
        from backend.claim_read import inventory_basis
        result = inventory_basis(result)
    return result


def workspace_summary(db, user, repos, snapshots):
    jobs = latest_jobs(db, user, repos)
    counts = summary_counts(db, user, repos, snapshots)
    claims = bounded_preview(db, user, repos, snapshots, "claim", indexed_text(Record.data, "status") == "CONTRADICTED")
    findings = bounded_preview(db, user, repos, snapshots, "finding",
        indexed_text(Record.data, "severity").in_(["HIGH", "CRITICAL"]),
        or_(indexed_text(Record.data, "review_status").is_(None), indexed_text(Record.data, "review_status").not_in(["RESOLVED", "FALSE_POSITIVE"]))
    )
    job_fields = ("state", "stage", "type", "branch", "source", "snapshot_id", "execution", "started_at", "finished_at",
                  "error_detail", "error_code", "errors", "retry_count", "recovery_count", "analyzer_results", "engines", "claim_extraction")
    result = {
        "analysis": {"state": analysis_state(repos, snapshots, jobs), "truncated": False, "warnings": []},
        "counts": counts,
        "repositories": [{"id": repo.id, "name": repo.name, "system": repo.system, "component": repo.component,
                          "owner": repo.owner, "provider": repo.provider,
                          "snapshot": {"id": snapshots[repo.id].id, **snapshots[repo.id].data} if repo.id in snapshots else None,
                          "latest_job": {"id": jobs[repo.id].id, **{key: jobs[repo.id].data[key] for key in job_fields if key in jobs[repo.id].data}} if repo.id in jobs else None}
                         for repo in repos],
        **{kind: [] for kind in (*KINDS, "edge", "job", "graph_node")},
        "previews": {"limit_per_kind": 5, "complete": False},
    }
    result["claim"], result["finding"] = [packed(row) for row in claims], [packed(row) for row in findings]
    return result


def bounded_preview(db, user, repos, snapshots, kind, *conditions):
    candidates = []
    current = [repo for repo in repos if repo.id in snapshots]
    for offset in range(0, len(current), 200):
        # Select bounded IDs before loading full documents. Each branch can seek
        # its repository/snapshot indexes; never scan all tenant finding JSON.
        branches = [scoped_current(user, [repo], snapshots, [kind]).where(*conditions).with_only_columns(
            Record.id, Record.created_at).order_by(Record.created_at.desc(), Record.id.desc()).limit(5).subquery()
            for repo in current[offset:offset + 200]]
        queries = [select(branch.c.id, branch.c.created_at) for branch in branches]
        if queries:
            query = queries[0] if len(queries) == 1 else union_all(*queries)
            candidates.extend(db.execute(query))
            candidates = sorted(candidates, key=lambda row: (row.created_at, row.id), reverse=True)[:5]
    if not candidates:
        return []
    rows = {row.id: row for row in db.scalars(select(Record).where(
        Record.organization_id == user.organization_id, Record.kind == kind,
        Record.id.in_([row.id for row in candidates])))}
    return [rows[row.id] for row in candidates]


VIEWS = {
    "Claim Ledger": ("claim",), "Architecture": ("claim",), "API Integrity": ("claim",),
    "Findings": ("finding",), "Security": ("finding",), "Secrets": ("finding",),
    "Drift": ("drift",), "Dependencies": ("dependency",), "Evidence": ("evidence",),
    "Pull Requests": ("pr",), "Reviews": ("claim", "finding", "drift"),
    "Cloud": ("graph_node",), "Cloud Assets": ("graph_node",), "Cloud Identities": ("graph_node",),
    "Exposure": ("graph_node",), "Risk Paths": ("risk_path",),
}


def page_query(user, repos, snapshots, view, search, state):
    query = scoped_current(user, repos, snapshots, VIEWS[view])
    category = {"Architecture": "ARCHITECTURE", "API Integrity": "API", "Secrets": "SECRET"}.get(view)
    if category:
        query = query.where(Record.data["category"].as_string() == category)
    if view == "Security":
        query = query.where(Record.data["category"].as_string().in_(["SAST", "SECRET", "SECRETS", "SCA", "IAC", "SECURITY", "CLOUD"]))
    if view == "Reviews":
        query = query.where(Record.data["review_status"].as_string().is_not(None), Record.data["review_status"].as_string() != "OPEN")
    if view in {"Cloud", "Cloud Assets", "Cloud Identities", "Exposure"}:
        classes = ["CLOUD_RESOURCE", "CLOUD_IDENTITY", "EXPOSURE"]
        if view == "Cloud Identities":
            classes = ["CLOUD_IDENTITY"]
        query = query.where(Record.data["class"].as_string().in_(classes))
        if view == "Exposure":
            query = query.where(or_(Record.data["class"].as_string() == "EXPOSURE", Record.data["public"].as_string().not_in(["UNKNOWN", "NO_INTERNET_RANGE_OBSERVED"])))
    if search:
        # Literal search, not caller-controlled SQL wildcard expansion.
        query = query.where(or_(*(Record.data[key].as_string().icontains(search, autoescape=True) for key in ("text", "title", "path", "name", "owner", "category"))))
    if state != "ALL":
        query = query.where(or_(*(Record.data[key].as_string() == state for key in ("status", "severity", "category", "classification", "review_status"))))
    return query
