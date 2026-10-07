import hashlib
import secrets
import time

from argon2 import PasswordHasher
from fastapi import HTTPException, Request
from sqlalchemy import select

from backend.db import Grant, OIDCSubject, Record, Repository, SessionToken, User

passwords = PasswordHasher()
EDIT_ROLES = {"ORG_OWNER", "ADMIN", "ENGINEER", "SECURITY_REVIEWER", "REVIEWER"}


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, user, response, production=False, previous_token=None, oidc_subject_id=None):
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
        if edit and user.role not in EDIT_ROLES:
            raise HTTPException(403, "Your role cannot modify engineering records.")
    return user, session


def allowed_repositories(db, user):
    # Owner roles do not bypass source permissions; every repository requires a grant.
    return list(
        db.scalars(
            select(Repository)
            .join(Grant, Repository.id == Grant.repository_id)
            .where(Repository.organization_id == user.organization_id, Grant.user_id == user.id)
        )
    )


def require_repo(db, user, repo_id):
    if not user or not user.enabled:
        raise HTTPException(401, "Repository member is disabled or unavailable.")
    repo = db.get(Repository, repo_id)
    grant = db.get(Grant, (user.id, repo_id))
    if not repo or repo.organization_id != user.organization_id or not grant:
        raise HTTPException(404, "Repository is not available in your authorized scope.")
    return repo
