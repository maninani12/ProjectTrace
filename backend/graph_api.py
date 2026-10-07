"""Authorized pages and one-hop neighborhoods from the existing authoritative graph."""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, or_, select

router = APIRouter(prefix="/api/graph")
NODE_KINDS = {"claim", "finding", "graph_node", "dependency", "evidence"}


def safe_node(row):
    from backend.main import packed

    data = packed(row)
    data.pop("source", None)
    data.pop("source_blob_digest", None)
    return data


def snapshot(db, user, repository_id, snapshot_id):
    from backend.db import Record
    from backend.security import require_repo

    require_repo(db, user, repository_id)
    # A graph page needs identity only, never the full repository-sized snapshot JSON.
    query = select(Record.id, Record.kind, Record.repository_id).where(
        Record.organization_id == user.organization_id,
        Record.repository_id == repository_id,
        Record.kind == "snapshot",
    )
    if snapshot_id:
        query = query.where(Record.id == snapshot_id)
    row = db.execute(query.order_by(Record.created_at.desc(), Record.id.desc()).limit(1)).first()
    if snapshot_id and not row:
        raise HTTPException(404, "Snapshot is not available in your authorized scope.")
    return row


@router.get("/nodes")
def nodes(
    request: Request,
    repository_id: str,
    snapshot_id: str | None = None,
    node_class: str | None = Query(default=None, max_length=60, pattern=r"^[A-Z_]+$"),
    component: str | None = Query(default=None, max_length=200),
    search: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    # The app's injected session factory is also used by controlled validation.
    from backend import main
    from backend.db import Record
    from backend.security import authenticate

    with main.Session() as db:
        user, _ = authenticate(db, request)
        selected = snapshot(db, user, repository_id, snapshot_id)
        if not selected:
            return {"snapshot_id": None, "items": [], "total": 0, "offset": offset, "limit": limit}
        query = select(Record).where(
            Record.organization_id == user.organization_id,
            Record.repository_id == repository_id,
            Record.kind.in_(NODE_KINDS),
            Record.data["scope"]["snapshot_id"].as_string() == selected.id,
        )
        if node_class:
            query = query.where(Record.data["class"].as_string() == node_class)
        if component:
            query = query.where(Record.data["scope"]["component"].as_string() == component)
        if search:
            pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.where(
                or_(
                    Record.data["path"].as_string().ilike(pattern, escape="\\"),
                    Record.data["title"].as_string().ilike(pattern, escape="\\"),
                    Record.data["name"].as_string().ilike(pattern, escape="\\"),
                )
            )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Record.kind, Record.id).offset(offset).limit(limit))
        return {
            "snapshot_id": selected.id,
            "items": [safe_node(row) for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
            "source_loaded": False,
            "authority": "CAPTURED_GRAPH",
        }


@router.get("/neighborhood")
def neighborhood(
    request: Request,
    node_id: str,
    relationship: str | None = Query(default=None, max_length=60),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    from backend import main
    from backend.db import Record
    from backend.security import authenticate

    with main.Session() as db:
        user, _ = authenticate(db, request)
        center = main.authorized_record(db, user, node_id)
        selected = center.data.get("scope", {}).get("snapshot_id")
        if center.kind not in NODE_KINDS or not selected or not center.repository_id:
            raise HTTPException(422, "Select a node from a captured repository graph.")
        query = select(Record).where(
            Record.organization_id == user.organization_id,
            Record.repository_id == center.repository_id,
            Record.kind == "edge",
            Record.data["snapshot_id"].as_string() == selected,
            or_(Record.data["source"].as_string() == node_id, Record.data["target"].as_string() == node_id),
        )
        if relationship:
            query = query.where(Record.data["relationship"].as_string() == relationship)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        edges = list(db.scalars(query.order_by(Record.id).offset(offset).limit(limit)))
        identifiers = {node_id} | {edge.data.get(key) for edge in edges for key in ("source", "target")}
        linked = list(
            db.scalars(
                select(Record).where(
                    Record.organization_id == user.organization_id,
                    Record.repository_id == center.repository_id,
                    Record.kind.in_(NODE_KINDS),
                    Record.id.in_(identifiers),
                    Record.data["scope"]["snapshot_id"].as_string() == selected,
                )
            )
        )
        retained = {row.id for row in linked}
        return {
            "snapshot_id": selected,
            "center_id": node_id,
            "nodes": [safe_node(row) for row in linked],
            "edges": [main.packed(edge) for edge in edges if {edge.data["source"], edge.data["target"]} <= retained],
            "total": total,
            "offset": offset,
            "limit": limit,
            "depth": 1,
            "source_loaded": False,
            "limitations": [
                "A page contains at most 100 captured edges; no runtime or complete cross-file semantic proof.",
                "Scoped expression indexes support captured graph lookup; this endpoint is a bounded one-hop page.",
            ],
        }
