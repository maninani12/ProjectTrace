"""Authenticated native rule profiles, separate from external evidence adapters."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from analyzers.engine import RULES
from backend.db import NativeProfile
from backend.domain import audit, uid
from backend.security import require_repo


def profile_scope(db, user, repo_id):
    if repo_id:
        require_repo(db, user, repo_id)
    return select(NativeProfile).where(
        NativeProfile.organization_id == user.organization_id, NativeProfile.scope_key == (repo_id or "organization")
    )


def save_profile(db, user, body):
    if user.role not in {"ORG_OWNER", "ADMIN"}:
        raise HTTPException(403, "Only organization administrators can change native profiles.")
    row = db.scalar(profile_scope(db, user, body.repository_id).with_for_update())
    if row and body.version != row.version:
        raise HTTPException(409, "Profile changed; refresh its version before updating.")
    if len(body.rules) > len(RULES) or any(key not in RULES for key in body.rules):
        raise HTTPException(422, "Unknown native rule.")
    for setting in body.rules.values():
        if not isinstance(setting, dict) or setting.keys() - {"enabled", "severity"}:
            raise HTTPException(422, "Rules accept enabled and severity settings only.")
        if (
            "enabled" in setting
            and type(setting["enabled"]) is not bool
            or "severity" in setting
            and setting["severity"] not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
        ):
            raise HTTPException(422, "Invalid native rule setting.")
    data = {"rules": body.rules, "licenses": body.licenses, "gate_scope": body.gate_scope}
    if row is None:
        row = NativeProfile(
            id=uid(),
            organization_id=user.organization_id,
            repository_id=body.repository_id,
            scope_key=body.repository_id or "organization",
            data=data,
        )
        db.add(row)
    else:
        row.data = data
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Profile was created concurrently; refresh its version before updating.") from None
    audit(
        db,
        user,
        "NATIVE_PROFILE_UPDATED",
        row.id,
        {"version": row.version, "rule_count": len(body.rules)},
        body.repository_id,
    )
    db.commit()
    return {"id": row.id, "version": row.version, "repository_id": row.repository_id, **row.data}
