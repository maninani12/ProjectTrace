import hashlib
import secrets
import time
import uuid
from datetime import datetime, timezone

from argon2 import PasswordHasher
from fastapi import HTTPException, Request
from sqlalchemy import select

from backend.admin_models import OrganizationMembership, SessionContext
from backend.db import OIDCSubject, Record, Repository, SessionToken, User
from backend.governance import enforce_request, expired, permitted, repository_condition, resolve_principal

passwords = PasswordHasher()
EDIT_ROLES = {"ORG_OWNER", "ADMIN", "ENGINEER", "SECURITY_REVIEWER", "REVIEWER"}


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, user, response, production=False, previous_token=None, oidc_subject_id=None):
    principal = resolve_principal(db, user)
    if not principal.enabled and not oidc_subject_id:
        choices = db.scalars(select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == user.id, OrganizationMembership.state.in_(["ACTIVE","SUSPENDED"])).order_by(
                OrganizationMembership.organization_id).limit(100))
        principal = next((candidate for org in choices if (candidate := resolve_principal(db, user, org)).enabled), principal)
    if not principal.enabled:
        raise HTTPException(403, "No active organization membership is available. Contact your administrator.")
    if previous_token:
        previous = db.get(SessionToken, token_hash(previous_token))
        if previous:
            db.delete(previous)
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        SessionToken(
            digest=token_hash(token),
            user_id=user.id,
            csrf=csrf,
            expires=time.time() + 8 * 3600,
            oidc_subject_id=oidc_subject_id,
        )
    )
    db.flush()
    db.add(SessionContext(digest=token_hash(token), public_id=str(uuid.uuid4()), organization_id=principal.organization_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        reauthenticated_at=time.time(), assurance="DEMO" if user.id == "demo-engineer" else "OIDC" if oidc_subject_id else "PASSWORD"))
    response.set_cookie(
        "pt_session", token, httponly=True, secure=production, samesite="strict", max_age=8 * 3600, path="/"
    )
    return csrf


def authenticate(db, request: Request, mutation=False, edit=True):
    token = request.cookies.get("pt_session", "")
    session = db.get(SessionToken, token_hash(token))
    if not session or session.expires < time.time():
        raise HTTPException(401, "Sign in to access engineering evidence.")
    user = db.get(User, session.user_id)
    if not user or not user.enabled:
        raise HTTPException(401, "Session member is unavailable.")
    from backend.admin_models import AccountControl
    restriction=db.get(AccountControl,user.id,populate_existing=True)
    if restriction and restriction.state!="ACTIVE" and not (restriction.state=="SUSPENDED" and expired(restriction.expires_at)):
        raise HTTPException(403,"Account access is restricted by the platform. Contact the service operator.")
    context = db.get(SessionContext, session.digest)
    user = resolve_principal(db, user, context.organization_id if context else user.organization_id,
        platform_only=request.url.path.startswith("/api/admin/platform/"))
    platform_metadata=bool(user.platform_role and request.url.path in {"/api/auth/me","/api/auth/access","/api/admin/context"})
    if not user.enabled and not platform_metadata and request.url.path not in {"/api/auth/organizations", "/api/auth/organization", "/api/auth/logout", "/api/auth/invitations/accept", "/api/notifications"}:
        raise HTTPException(403, "Organization access is suspended or removed. Choose another permitted workspace or contact your administrator.")
    if session.oidc_subject_id:
        subject = db.get(OIDCSubject, session.oidc_subject_id)
        if (
            not subject
            or not subject.enabled
            or subject.user_id != user.id
            or subject.organization_id != user.organization_id
        ):
            raise HTTPException(401, "OIDC membership is revoked or unavailable.")
        provider = db.scalar(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.kind == "oidc_provider",
                Record.natural_key == subject.issuer,
            )
        )
        if provider and provider.data.get("state") != "ENABLED":
            raise HTTPException(401, "OIDC provider is disabled or removed.")
    if mutation:
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
            raise HTTPException(403, "CSRF token is missing or invalid.")
        if edit and not permitted(db, user, "engineering.write"):
            raise HTTPException(403, "Your role cannot modify engineering records.")
    request.state.principal_id = user.id
    request.state.organization_id = user.organization_id
    enforce_request(db, user, request)
    return user, session


def allowed_repositories(db, user):
    # Owner roles do not bypass source permissions; every repository requires a grant.
    user = resolve_principal(db, user, user.organization_id)
    if not user.enabled:
        raise HTTPException(403, "Organization membership is unavailable.")
    return list(
        db.scalars(
            select(Repository)
            .where(repository_condition(user))
        )
    )


def require_repo(db, user, repo_id):
    if not user or not user.enabled:
        raise HTTPException(401, "Repository member is disabled or unavailable.")
    user = resolve_principal(db, user, user.organization_id)
    repo = db.scalar(select(Repository).where(Repository.id == repo_id, repository_condition(user))) if user.enabled else None
    if not repo:
        raise HTTPException(404, "Repository is not available in your authorized scope.")
    return repo
