"""Quality projection and branch-baseline history, retaining graph authority."""

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from analyzers.code_quality.core import compare, gate, summary
from analyzers.observation_store import MetricRows
from backend.analysis_budget import checkpoint
from backend.db import QualityAnalysis, QualityOccurrence, Record


def ancestors(db, snapshot, limit=200):
    from backend.snapshot_context import comparison_snapshot

    rows, visited = [], set()
    current = snapshot
    while current and current.id not in visited and len(rows) < limit:
        checkpoint(db)
        visited.add(current.id)
        rows.append(current)
        parent = comparison_snapshot(db, current.data["base_id"], snapshot.organization_id, snapshot.repository_id) if current.data.get("base_id") else None
        current = (
            parent
            if parent
            and parent.kind == "snapshot"
            and parent.repository_id == snapshot.repository_id
            and parent.organization_id == snapshot.organization_id
            else None
        )
    return rows


def apply_comparison(db, quality, findings, base, changed_lines, model_changed, comparison_previous=None,
                     *, path_context=None, identity_matches=None):
    from backend.snapshot_context import quality_fields

    base_quality = quality_fields(db, base, ("detection_hash", "parser_signature", "metrics")) if base else {}
    detection_changed = bool(base_quality) and base_quality.get("detection_hash") != quality.get("detection_hash")
    detection_changed = (
        detection_changed
        or bool(base_quality)
        and base_quality.get("parser_signature") != quality.get("parser_signature")
    )
    model_changed = model_changed or detection_changed
    quality["comparison_model_changed"] = model_changed
    unresolved = any(f.get("category") == "QUALITY" and f.get("identity_resolution") == "UNRESOLVED" for f in findings)
    if path_context and base and (path_context[0].public or path_context[1].public):
        unresolved = unresolved or any(f.get("category") == "QUALITY" and
            (f.get("identity_version") != "structural-v2" or f.get("identity_confidence") != "HIGH"
             or f.get("fingerprint_version") != "quality-symbol-v2")
            for f in (comparison_previous if comparison_previous is not None else base.data.get("findings", [])))
    if path_context and base and any(p.state.startswith("UNRESOLVED") for p in path_context):
        unresolved = True
    quality["comparison_identity_unresolved"] = unresolved or any(
        f.get("identity_resolution") == "UNRESOLVED" for f in findings)
    if path_context and base and (path_context[0].public or path_context[1].public):
        quality["comparison_identity_unresolved"] |= any(
            f.get("category") in {"QUALITY", "SAST", "SECRET", "IAC"} and
            (f.get("identity_version") != "structural-v2" or f.get("identity_confidence") != "HIGH"
             or f.get("fingerprint_version") not in {"native-statement-v1", "quality-symbol-v2"})
            for f in (comparison_previous if comparison_previous is not None else base.data.get("findings", [])))
    compare(
        quality,
        findings,
        comparison_previous if comparison_previous is not None else base.data.get("findings", []) if base else [],
        changed_lines,
        base_id=base.id if base else None,
        model_changed=model_changed or unresolved,
    )
    previous_metrics = {
        (path_context[0].path(m["path"]) if path_context else m["path"], m.get("qualified_name", m["name"])): m
        for m in base_quality.get("metrics", [])
    }
    for position, metric in enumerate(quality["metrics"]):
        checkpoint(db)
        prior = previous_metrics.get((path_context[1].path(metric["path"]) if path_context else metric["path"],
                                      metric.get("qualified_name", metric["name"])))
        metric["new_code"] = (
            bool(base)
            and not model_changed
            and not unresolved
            and (
                not prior
                or any(
                    metric.get(k, 0) > prior.get(k, 0)
                    for k in ("cyclomatic", "nesting", "parameters", "length", "cognitive_approximation")
                )
            )
            and any(
                lo <= metric["end_line"] and hi >= metric["line"] for lo, hi in changed_lines.get(metric["path"], [])
            )
        )
        if isinstance(quality["metrics"], MetricRows):
            quality["metrics"]._replace(position, metric)
    chain = ancestors(db, base) if base else []
    older = {}
    for parent in chain[1:]:
        checkpoint(db)
        for item in parent.data.get("findings", []):
            checkpoint(db)
            if item.get("category") == "QUALITY":
                older.setdefault(item.get("fingerprint"), (item, parent))
    for item in findings:
        checkpoint(db)
        matched = (identity_matches or {}).get(item.get("id"))
        if item.get("category") == "QUALITY" and matched and matched[1] == "REOPENED":
            row = matched[0]
            item.update(delta="REOPENED", machine_status="REOPENED",
                        first_seen=row.data.get("first_seen", row.created_at),
                        introduced_snapshot=row.data.get("introduced_snapshot"))
        if item.get("category") == "QUALITY" and item.get("delta") == "NEW" and item["fingerprint"] in older:
            prior, parent = older[item["fingerprint"]]
            item.update(
                delta="REOPENED",
                machine_status="REOPENED",
                reopened_from=parent.id,
                first_seen=prior.get("first_seen", parent.created_at),
                introduced_snapshot=prior.get("introduced_snapshot", parent.id),
            )
    quality["history_scope"] = {
        "ancestor_snapshots": len(chain),
        "limit": 200,
        "truncated": len(chain) == 200,
        "basis": "Explicit BASE ancestry; no unrelated branch resolution",
    }
    quality["deltas"] = dict(Counter(f["delta"] for f in findings if f.get("category") == "QUALITY"))


def persist(db, snapshot, quality, findings):
    items = [f for f in findings if f.get("category") == "QUALITY"]
    store = db.merge if db.info.get("analysis_generation") else db.add
    for item in items:
        checkpoint(db)
        store(
            QualityOccurrence(
                finding_id=item["id"],
                snapshot_id=snapshot.id,
                organization_id=snapshot.organization_id,
                repository_id=snapshot.repository_id,
                fingerprint=item["fingerprint"],
                rule=item["rule"],
                path=item["path"],
                symbol=item["symbol"][:500],
                language=item["language"],
                dimension=item["dimension"],
                severity=item["severity"],
                delta=item["delta"],
            )
        )
    quality["summary"] = summary(quality, items)
    quality["gate"] = gate(quality, eligible_findings(db, snapshot.organization_id, snapshot.repository_id, items))
    store(
        QualityAnalysis(
            snapshot_id=snapshot.id,
            organization_id=snapshot.organization_id,
            repository_id=snapshot.repository_id,
            branch=snapshot.data["branch"],
            analyzer_version=quality["version"],
            profile_hash=quality["profile_hash"],
            data=quality,
        )
    )
    return quality["gate"]


def current_findings(db, projection):
    return [
        {"id": record.id, "version": record.version, **record.data}
        for record in db.scalars(
            select(Record)
            .join(QualityOccurrence, QualityOccurrence.finding_id == Record.id)
            .where(
                QualityOccurrence.snapshot_id == projection.snapshot_id,
                QualityOccurrence.organization_id == projection.organization_id,
                QualityOccurrence.repository_id == projection.repository_id,
            )
        )
    ]


def eligible_findings(db, organization_id, repository_id, findings):
    """Accepted risk suppresses a gate only while a matching exception is active."""
    active = set()
    for row in db.scalars(
        select(Record).where(
            Record.organization_id == organization_id, Record.repository_id == repository_id, Record.kind == "exception"
        )
    ):
        try:
            expiry = datetime.fromisoformat(row.data["expires_at"])
            identity = row.data.get("identity_id") or row.data.get("target")
            if expiry.tzinfo and expiry > datetime.now(timezone.utc) and isinstance(identity, str) and identity:
                active.add(identity)
        except (ValueError, TypeError, KeyError):
            continue
    return [f for f in findings if not {f.get("id"), f.get("review_identity_id", f.get("identity_id"))} & active]


def merge_gate(engineering, quality):
    rank = {"PASS": 0, "WARNING": 1, "REVIEW_REQUIRED": 2, "FAIL": 3}
    return {
        **engineering,
        "overall": max([engineering["overall"], quality["status"]], key=rank.get),
        "results": [*engineering["results"], *quality["results"]],
        "quality_gate": quality,
    }
