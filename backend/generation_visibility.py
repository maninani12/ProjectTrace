"""Default-deny visibility for private generation output on every ORM read.

Only the worker Session holding a generation context can read that generation.
This is a publication boundary, in addition to existing tenant authorization.
Core/raw SQL requires an explicit visible predicate; it is not an ORM reader.
"""
from sqlalchemy import event, exists, select
from sqlalchemy.orm import Session, with_loader_criteria

from backend.admin_models import ActivityEvent
from backend.db import (
    Audit,
    CloudAsset,
    FindingIdentity,
    FindingOccurrence,
    QualityAnalysis,
    QualityOccurrence,
    Record,
    SnapshotInventory,
    SnapshotView,
)


def visible_record(identity, active=None):
    from backend.generation_models import AnalysisGeneration, GenerationRecord
    owners, generations = GenerationRecord.__table__, AnalysisGeneration.__table__
    hidden = select(owners.c.record_id).join(generations, generations.c.id == owners.c.generation_id).where(
        owners.c.record_id == identity, generations.c.state != "PUBLISHED")
    if active:
        hidden = hidden.where(generations.c.id != active)
    return ~exists(hidden)


def visible_audit(identity, activity=False, active=None):
    from backend.generation_models import AnalysisGeneration, GenerationAudit
    owners, generations = GenerationAudit.__table__, AnalysisGeneration.__table__
    hidden = select(owners.c.event_id).join(generations, generations.c.id == owners.c.generation_id).where(
        (owners.c.activity_id if activity else owners.c.event_id) == identity, generations.c.state != "PUBLISHED")
    if active:
        hidden = hidden.where(generations.c.id != active)
    return ~exists(hidden)


@event.listens_for(Session, "do_orm_execute")
def hide_unpublished(execution):
    if not execution.is_select:
        return
    context = execution.session.info.get("analysis_generation")
    active = context.row.id if context else None
    # These immutable SQL expressions contain no row data or permission result.
    # Rebuilding all ten on every SELECT also charged unrelated source/cache
    # queries. Retain one set per Session, replacing it whenever worker scope
    # changes; publication state is still checked by the database every time.
    cached = execution.session.info.get("_generation_visibility_criteria")
    if cached is None or cached[0] != active:
        options = [with_loader_criteria(Record, visible_record(Record.id, active), include_aliases=True)]
        for model, field in ((SnapshotView, "snapshot_id"), (SnapshotInventory, "snapshot_id"),
                             (CloudAsset, "snapshot_id"), (QualityAnalysis, "snapshot_id"),
                             (QualityOccurrence, "snapshot_id"), (FindingOccurrence, "snapshot_id"),
                             (FindingIdentity, "introduced_snapshot_id")):
            options.append(with_loader_criteria(model, visible_record(getattr(model, field), active), include_aliases=True))
        audit_options = (with_loader_criteria(Audit, visible_audit(Audit.id, active=active), include_aliases=True),
                        with_loader_criteria(ActivityEvent, visible_audit(ActivityEvent.id, True, active), include_aliases=True))
        cached = (active, tuple(options), audit_options)
        execution.session.info["_generation_visibility_criteria"] = cached
    options = cached[1]
    # Integrity checks verify the entire append-only chain, including private
    # preparation events; public audit/activity endpoints still hide those rows.
    if not execution.execution_options.get("generation_audit_integrity"):
        options += cached[2]
    execution.statement = execution.statement.options(*options)
