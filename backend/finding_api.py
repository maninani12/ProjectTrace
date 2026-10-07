"""Authorized concept history with bounded pagination and legacy visibility."""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from backend.db import FindingOccurrence, Record
from backend.security import authenticate, require_repo

router = APIRouter(prefix="/api/findings", tags=["Finding History"])


@router.get("/{finding_id}/history")
def history(finding_id: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    from backend.main import Session

    with Session() as db:
        user, _ = authenticate(db, request)
        row = db.get(Record, finding_id)
        if not row or row.organization_id != user.organization_id or row.kind != "finding":
            raise HTTPException(404, "Finding is unavailable.")
        require_repo(db, user, row.repository_id)
        query = select(FindingOccurrence).where(
            FindingOccurrence.organization_id == user.organization_id,
            FindingOccurrence.repository_id == row.repository_id,
            FindingOccurrence.identity_id == row.data.get("identity_id"),
        )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        entries = db.scalars(
            query.order_by(FindingOccurrence.created_at.desc(), FindingOccurrence.id).offset(offset).limit(limit)
        )
        return {
            "identity_id": row.data.get("identity_id"),
            "identity_version": row.data.get("identity_version", "LEGACY"),
            "total": total,
            "offset": offset,
            "limit": limit,
            "legacy_history": not total,
            "basis": "Explicit BASE ancestry; prior records remain available in snapshots and audit.",
            "items": [
                {
                    "id": e.id,
                    "status": e.status,
                    "at": e.created_at,
                    "snapshot_id": e.snapshot_id,
                    "finding_id": e.finding_id,
                    **e.data,
                }
                for e in entries
            ],
        }
