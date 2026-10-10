"""Bounded reads and serialized, audited, idempotent governance commands."""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text, update

from analyzers.engine import redact
from backend.admin_models import (
    AdministrativeCommand,
    GovernanceRevision,
    OrganizationMembership,
    SessionContext,
    Team,
)
from backend.db import Organization, User
from backend.domain import audit, uid
from backend.governance import (
    ROLE_PERMISSIONS,
    SELF_SERVICE_PERMISSIONS,
    permitted,
    require_permission,
    resolve_principal,
    team_ids,
)
from backend.security import authenticate

SENSITIVE = {"password", "password_hash", "token", "token_digest", "csrf", "digest", "session_digest", "client_secret",
    "ciphertext", "archive", "files", "private_key", "credentials", "invitation_token", "accept_url",
    "api_key", "access_token", "refresh_token", "authorization", "cookie", "set-cookie", "session_token",
    "source_code", "source_text", "request_body", "response_body", "question", "prompt", "chat", "ip_address", "user_agent"}
ADMIN_QUERY_SECONDS = 10


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommandBody(StrictBody):
    command_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,100}$")
    expected_version: int = Field(default=0, ge=0)
    reason: str = Field(min_length=10, max_length=500)


class ExpiringBody(CommandBody):
    expires_at: str | None = Field(default=None, max_length=50)

    @field_validator("expires_at")
    @classmethod
    def valid_expiration(cls, value):
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value)
            current = datetime.now(timezone.utc)
            if parsed.tzinfo is None or not current < parsed <= current + timedelta(days=90):
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("Expiration must be timezone-aware, in the future and within 90 days.") from None
        return parsed.astimezone(timezone.utc).isoformat()


def session_factory():
    from backend.main import Session
    return Session()


def safe_metadata(value, depth=0):
    if depth > 5:
        return "[bounded]"
    if isinstance(value, dict):
        return {str(key)[:80]: "[redacted]" if str(key).lower() in SENSITIVE else safe_metadata(item, depth+1)
            for key,item in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [safe_metadata(item, depth+1) for item in value[:50]]
    if isinstance(value, str):
        return redact(value)[:1000]
    return value if value is None or isinstance(value, (bool, int, float)) else "[unavailable]"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def admin_user(db, request, permission=None, *, mutation=False, team_id=None):
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '10s'"))
    elif db.get_bind().dialect.name=="sqlite":
        # Client aborts do not stop SQLite statements. Bound metadata query work
        # on the server too; pool check-in clears this request's handler.
        deadline=time.monotonic()+ADMIN_QUERY_SECONDS
        connection=db.connection().connection.driver_connection
        connection.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
    user, token = authenticate(db, request, mutation, edit=False)
    if permission:
        require_permission(db, user, permission, team_id=team_id)
    elif not (set(ROLE_PERMISSIONS.get(user.role, ())) - SELF_SERVICE_PERMISSIONS or team_ids(db,user,administered=True) or user.platform_role):
        raise HTTPException(403, "Administration is not available to this account.")
    return user, token


def scoped_team(db, user, team_id, *, permission="teams.read"):
    team = db.get(Team, team_id)
    if not team or team.organization_id != user.organization_id:
        raise HTTPException(404, "Team is unavailable in your administrative scope.")
    require_permission(db,user,permission,team_id=team_id)
    if not permitted(db,user,"users.read") and not permitted(db,user,"audit.read") and team_id not in team_ids(db,user,administered=True):
        raise HTTPException(404, "Team is unavailable in your administrative scope.")
    return team


def scoped_member(db, user, user_id):
    member = db.get(OrganizationMembership,(user.organization_id,user_id),populate_existing=True)
    target = db.get(User,user_id)
    if not member or not target:
        raise HTTPException(404, "Member is unavailable in this organization.")
    return member,target


def ensure_primary_membership(db, user):
    row = db.get(OrganizationMembership,(user.organization_id,user.id))
    if row is None:
        identity = db.get(User,user.id)
        if not identity or identity.organization_id != user.organization_id:
            raise HTTPException(403,"An explicit organization membership is required.")
        row = OrganizationMembership(organization_id=user.organization_id,user_id=user.id,role=user.role)
        db.add(row)
        db.flush()
    return row


def check_version(row, expected):
    if expected != (row.version if row else 0):
        raise HTTPException(409, "This record changed. Refresh and review the current version before retrying.")


def fresh_authentication(db, token):
    context = db.get(SessionContext,token.digest)
    if not context or not context.reauthenticated_at or time.time()-context.reauthenticated_at > 300 or context.assurance == "DEMO":
        raise HTTPException(403,{"code":"REAUTHENTICATION_REQUIRED","message":"Reauthenticate before this sensitive operation."})


def lock_scope(db, organization_id):
    # Same short lock order as the existing tenant audit chain; no graph scans.
    db.execute(update(Organization).where(Organization.id==organization_id).values(name=Organization.name))


def bump_revision(db, organization_id):
    row = db.get(GovernanceRevision,organization_id,populate_existing=True)
    if row is None:
        row=GovernanceRevision(scope_key=organization_id,revision=0)
        db.add(row)
        db.flush()
    row.revision+=1
    db.flush()
    return row.revision


def command(db, user, body, permission, action, target_id, apply, *, team_id=None, token=None, sensitive=False, platform=False):
    require_permission(db,user,permission,team_id=team_id)
    if platform:
        # Serialize global policy/approval changes across different operator tenants.
        db.execute(update(GovernanceRevision).where(GovernanceRevision.scope_key=="PLATFORM").values(revision=GovernanceRevision.revision))
    lock_scope(db,user.organization_id)
    user=resolve_principal(db,user,user.organization_id,platform_only=permission.startswith("platform."))
    require_permission(db,user,permission,team_id=team_id)
    if sensitive:
        fresh_authentication(db,token)
    identity=digest({"action":action,"target":target_id,"body":body.model_dump(exclude={"command_id"})})
    previous=db.scalar(select(AdministrativeCommand).where(AdministrativeCommand.organization_id==user.organization_id,
        AdministrativeCommand.actor_id==user.id,AdministrativeCommand.idempotency_key==body.command_id))
    if previous:
        if previous.request_digest != identity:
            raise HTTPException(409,"This command ID was already used with different fields.")
        return {**previous.result,"replayed":True}
    result, change=apply(user)
    db.flush()
    version=bump_revision(db,user.organization_id)
    event=audit(db,user,action,str(target_id)[:100],{"actor_id":user.id,"permission":permission,
        "command_id":body.command_id,"reason":redact(body.reason),"change":safe_metadata(change)})
    response={**result,"audit_event_id":event.id,"governance_revision":version}
    db.add(AdministrativeCommand(id=uid(),organization_id=user.organization_id,actor_id=user.id,
        idempotency_key=body.command_id,request_digest=identity,result=safe_metadata(response)))
    db.commit()
    return response


def page(db, statement, *, offset=0, limit=25):
    total=db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows=list(db.execute(statement.offset(offset).limit(limit)))
    return rows,{"total":total,"offset":offset,"limit":limit,"has_more":offset+len(rows)<total}


def role_assignment(actor, target_id, role):
    allowed={"ENGINEER","VIEWER","REVIEWER","SECURITY_REVIEWER","AUDITOR","TEAM_ADMIN","STANDARD_USER"}
    if actor.role=="ORG_OWNER":
        allowed |= {"ADMIN","SECURITY_ADMIN"}
    if target_id in {actor.id,"demo-engineer"} or role not in allowed:
        raise HTTPException(403,"This role cannot be assigned by this administrator to the selected member.")


def guard_member_change(actor, member):
    if member.user_id==actor.id:
        raise HTTPException(403,"Use a separate authorized administrator to change your own access.")
    if member.role=="ORG_OWNER":
        raise HTTPException(403,"Organization owners require the consented ownership-transfer workflow.")
    if member.role in {"ADMIN","ORG_ADMIN","SECURITY_ADMIN"} and actor.role!="ORG_OWNER":
        raise HTTPException(403,"Only the organization owner can change this elevated membership.")
