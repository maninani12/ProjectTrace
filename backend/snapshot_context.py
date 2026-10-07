"""Read comparison context without loading unrelated captured coverage/metrics."""

from types import SimpleNamespace

from sqlalchemy import select

from backend.db import QualityAnalysis, Record

SNAPSHOT_FIELDS = (
    "base_id", "branch", "commit", "analyzer_version", "parser_signature",
    "verification_cache", "hashes", "claims", "findings", "dependencies", "cloud_assets", "gate",
)


def comparison_snapshot(db, identifier, organization_id, repository_id):
    metadata = db.execute(
        select(Record.id, Record.organization_id, Record.repository_id, Record.kind, Record.created_at)
        .where(Record.id == identifier)
    ).first()
    if not metadata:
        return None
    result = SimpleNamespace(**metadata._mapping, data={})
    if (result.organization_id, result.repository_id, result.kind) != (
        organization_id, repository_id, "snapshot"
    ):
        return result  # The caller rejects the reference before reading its payload.
    values = db.execute(
        select(*(Record.data[name].label(name) for name in SNAPSHOT_FIELDS)).where(
            Record.id == identifier, Record.organization_id == organization_id,
            Record.repository_id == repository_id, Record.kind == "snapshot",
        )
    ).one()
    result.data = {name: value for name, value in values._mapping.items() if value is not None}
    if not result.data.get("parser_signature"):
        # Older inline snapshots can carry their signature only in the cache.
        result.data["analysis_cache"] = db.scalar(
            select(Record.data["analysis_cache"]).where(
                Record.id == identifier, Record.organization_id == organization_id,
                Record.repository_id == repository_id, Record.kind == "snapshot",
            )
        ) or {}
    return result


def quality_fields(db, snapshot, names):
    row = db.execute(
        select(*(QualityAnalysis.data[name].label(name) for name in names)).where(
            QualityAnalysis.snapshot_id == snapshot.id,
            QualityAnalysis.organization_id == snapshot.organization_id,
            QualityAnalysis.repository_id == snapshot.repository_id,
        )
    ).first()
    return {"_exists": True, **{name: value for name, value in row._mapping.items() if value is not None}} if row else {}
