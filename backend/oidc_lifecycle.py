"""Organization controls for explicit OIDC membership and bounded group provisioning."""

import re
import secrets

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import delete, select

from backend.db import Grant, OIDCSubject, Record, SessionToken, User
from backend.domain import add, audit, uid
from backend.security import authenticate, passwords, require_repo


class RoleMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern=r"^(VIEWER|ENGINEER|REVIEWER|SECURITY_REVIEWER|ADMIN)$")
    repositories: list[str] = Field(default_factory=list, max_length=100)


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    label: str = Field(default="Organization SSO", min_length=1, max_length=80)
    state: str = Field(default="ENABLED", pattern=r"^(ENABLED|DISABLED|REMOVED)$")
    jit_enabled: StrictBool = False
    require_mapped_group: StrictBool = True
    allow_admin_roles: StrictBool = False
    groups_claim: str = Field(default="groups", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    role_mappings: dict[str, RoleMapping] = Field(default_factory=dict, max_length=100)


def provider(db, organization_id, issuer):
    return db.scalar(
        select(Record)
        .where(Record.organization_id == organization_id, Record.kind == "oidc_provider", Record.natural_key == issuer)
        .with_for_update()
    )


def revoke_provider_sessions(db, organization_id, issuer):
    bindings = select(OIDCSubject.id).where(
        OIDCSubject.organization_id == organization_id, OIDCSubject.issuer == issuer
    )
    db.execute(delete(SessionToken).where(SessionToken.oidc_subject_id.in_(bindings)))


def membership_for_claims(db, cfg, claims, organization_id=None):
    binding = db.scalar(
        select(OIDCSubject)
        .where(OIDCSubject.issuer == claims["iss"], OIDCSubject.subject == claims["sub"])
        .with_for_update()
    )
    if binding and (not binding.enabled or organization_id and binding.organization_id != organization_id):
        raise HTTPException(403, "OIDC subject is disabled or outside the selected organization.")
    selected_org = binding.organization_id if binding else organization_id
    configured = provider(db, selected_org, cfg["issuer"]) if selected_org else None
    if configured and configured.data.get("state") != "ENABLED":
        raise HTTPException(403, "OIDC provider is disabled or removed.")
    settings = configured.data if configured else {}
    groups = claims.get(settings.get("groups_claim", "groups"), [])
    if not isinstance(groups, list) or len(groups) > 500 or any(not isinstance(g, str) or len(g) > 250 for g in groups):
        raise HTTPException(403, "OIDC group claims are outside the supported bounds.")
    mapped = [m for g, m in settings.get("role_mappings", {}).items() if g in groups]
    if configured and settings.get("require_mapped_group", True) and not mapped:
        raise HTTPException(403, "No configured OIDC group membership permits this login.")
    roles = ["VIEWER", "ENGINEER", "REVIEWER", "SECURITY_REVIEWER", "ADMIN"]
    role = max((m["role"] for m in mapped), key=roles.index) if mapped else None
    if role == "ADMIN" and not settings.get("allow_admin_roles"):
        raise HTTPException(403, "OIDC administrator mapping is not authorized.")
    user = db.get(User, binding.user_id) if binding else None
    if binding and (not user or not user.enabled or user.organization_id != binding.organization_id):
        raise HTTPException(403, "OIDC member is disabled or unavailable.")
    if not user:
        if not configured or not settings.get("jit_enabled") or not mapped:
            raise HTTPException(403, "This OIDC subject has no explicit enabled membership.")
        email = claims.get("email")
        if (
            claims.get("email_verified") is not True
            or not isinstance(email, str)
            or len(email) > 200
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            raise HTTPException(403, "Controlled OIDC provisioning requires a verified email and mapped group.")
        if db.scalar(select(User.id).where(User.email == email.lower())):
            raise HTTPException(403, "Existing email requires an administrator's explicit subject binding.")
        user = User(
            id=uid(),
            organization_id=selected_org,
            email=email.lower(),
            role=role,
            password_hash=passwords.hash(secrets.token_urlsafe(64)),
            enabled=True,
            local_login_allowed=False,
        )
        db.add(user)
        db.flush()
        binding = OIDCSubject(
            id=uid(),
            issuer=claims["iss"],
            subject=claims["sub"],
            organization_id=selected_org,
            user_id=user.id,
            enabled=True,
        )
        db.add(binding)
        db.flush()
        audit(
            db,
            user,
            "OIDC_JIT_MEMBER_CREATED",
            user.id,
            {
                "provider_id": configured.id,
                "subject_binding_id": binding.id,
                "role": role,
                "local_login_allowed": False,
            },
        )
    if role and user.role != "ORG_OWNER" and user.role != role:
        previous_role = user.role
        user.role = role
        db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
        audit(db, user, "OIDC_GROUP_ROLE_CHANGED", user.id, {"before": previous_role, "after": role})
    # Group-managed access is explicit. Previously granted repositories remain explicit grants;
    # administrators revoke them independently rather than guessing their original provenance.
    for repository_id in {rid for m in mapped for rid in m.get("repositories", [])}:
        from backend.db import Repository

        repository = db.get(Repository, repository_id)
        if not repository or repository.organization_id != user.organization_id:
            raise HTTPException(403, "OIDC repository mapping is outside the organization.")
        if not db.get(Grant, (user.id, repository_id)):
            db.add(Grant(user_id=user.id, repository_id=repository_id))
            audit(
                db, user, "OIDC_GROUP_REPOSITORY_GRANTED", repository_id, {"provider_id": configured.id}, repository_id
            )
    return binding, user


def register(router):
    from backend.oidc import session

    @router.get("/provider")
    def inspect_provider(request: Request):
        with session() as db:
            user, _ = authenticate(db, request)
            if user.role not in {"ORG_OWNER", "ADMIN"}:
                raise HTTPException(403, "Only administrators inspect organization OIDC configuration.")
            rows = list(
                db.scalars(
                    select(Record)
                    .where(Record.organization_id == user.organization_id, Record.kind == "oidc_provider")
                    .limit(2)
                )
            )
            row = rows[0] if rows else None
            return {
                "id": row.id if row else None,
                "version": row.version if row else 0,
                "configured": bool(row),
                **(row.data if row else {}),
            }

    @router.post("/provider")
    def update_provider(body: ProviderSettings, request: Request):
        from backend.oidc import config

        cfg = config()  # Endpoints and client secrets remain operator-owned.
        with session() as db:
            user, _ = authenticate(db, request, True)
            if user.role not in {"ORG_OWNER", "ADMIN"}:
                raise HTTPException(403, "Only organization administrators configure OIDC.")
            if body.allow_admin_roles and user.role != "ORG_OWNER":
                raise HTTPException(403, "Only the organization owner authorizes group administrator mappings.")
            if any(not group.strip() or len(group) > 250 for group in body.role_mappings):
                raise HTTPException(422, "Use bounded, nonempty group identifiers.")
            if any(m.role == "ADMIN" for m in body.role_mappings.values()) and not body.allow_admin_roles:
                raise HTTPException(422, "Administrator group mapping requires explicit owner authorization.")
            for mapping in body.role_mappings.values():
                for repository_id in mapping.repositories:
                    require_repo(db, user, repository_id)
            row = provider(db, user.organization_id, cfg["issuer"])
            if body.expected_version != (row.version if row else 0):
                raise HTTPException(409, "OIDC configuration changed; refresh its version.")
            data = {**body.model_dump(exclude={"expected_version"}), "issuer": cfg["issuer"]}
            if row:
                row.data = data
            else:
                row = add(db, user.organization_id, None, "oidc_provider", data, natural_key=cfg["issuer"])
            db.flush()
            revoke_provider_sessions(db, user.organization_id, cfg["issuer"])
            audit(db, user, "OIDC_PROVIDER_UPDATED", row.id, {"version": row.version, **data})
            db.commit()
            return {"id": row.id, "version": row.version, **data}

    @router.get("/members")
    def members(request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        with session() as db:
            user, _ = authenticate(db, request)
            if user.role not in {"ORG_OWNER", "ADMIN"}:
                raise HTTPException(403, "Only administrators inspect organization membership.")
            rows = db.scalars(
                select(User)
                .where(User.organization_id == user.organization_id)
                .order_by(User.id)
                .offset(offset)
                .limit(limit + 1)
            ).all()
            return {
                "has_more": len(rows) > limit,
                "items": [
                    {
                        "id": r.id,
                        "email": r.email,
                        "role": r.role,
                        "enabled": r.enabled,
                        "local_login_allowed": r.local_login_allowed,
                        "bindings": [
                            {"subject": b.subject, "issuer": b.issuer, "enabled": b.enabled}
                            for b in db.scalars(
                                select(OIDCSubject).where(
                                    OIDCSubject.user_id == r.id, OIDCSubject.organization_id == user.organization_id
                                )
                            )
                        ],
                    }
                    for r in rows[:limit]
                ],
            }

    class MemberControl(BaseModel):
        model_config = ConfigDict(extra="forbid")
        enabled: StrictBool

    @router.post("/members/{user_id}")
    def member_control(user_id: str, body: MemberControl, request: Request):
        with session() as db:
            actor, _ = authenticate(db, request, True)
            if actor.role not in {"ORG_OWNER", "ADMIN"}:
                raise HTTPException(403, "Only administrators manage account availability.")
            target = db.scalar(
                select(User).where(User.id == user_id, User.organization_id == actor.organization_id).with_for_update()
            )
            if not target:
                raise HTTPException(404, "Member unavailable in this organization.")
            if target.id == actor.id and not body.enabled:
                raise HTTPException(409, "Use another authorized administrator to disable this account.")
            if target.role == "ORG_OWNER" and actor.role != "ORG_OWNER":
                raise HTTPException(403, "Owner availability requires an organization owner.")
            target.enabled = body.enabled
            db.execute(delete(SessionToken).where(SessionToken.user_id == target.id))
            audit(db, actor, "MEMBER_AVAILABILITY_CHANGED", target.id, {"enabled": body.enabled})
            db.commit()
            return {"id": target.id, "enabled": target.enabled}
