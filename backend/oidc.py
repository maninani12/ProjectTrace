"""Authorization Code + PKCE; explicit issuer/subject membership, no email JIT."""

import base64
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import socket
import time
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import delete, select

from backend.db import OIDCAttempt, OIDCSubject, SessionToken, User
from backend.domain import audit, uid
from backend.oidc_lifecycle import register as register_lifecycle
from backend.queue import cipher
from backend.security import authenticate, create_session, token_hash

router = APIRouter(prefix="/api/auth/oidc", tags=["OIDC"])


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(
                value.split("?", 1)[0] + "?[redacted]"
                if isinstance(value, str) and "/api/auth/oidc/callback?" in value
                else value
                for value in record.args
            )
        return True


logging.getLogger("uvicorn.access").addFilter(CallbackLogFilter())


def session():
    from backend.main import Session

    return Session()


def config():
    keys = ("issuer", "authorization_url", "token_url", "jwks_url", "client_id", "redirect_uri", "frontend_url")
    result = {key: os.getenv("OIDC_" + key.upper(), "") for key in keys}
    if not all(result.values()):
        raise HTTPException(503, "OIDC is not configured by the deployment operator.")
    for key in ("issuer", "authorization_url", "token_url", "jwks_url"):
        approved_url(result[key])
    callback, frontend = urlsplit(result["redirect_uri"]), urlsplit(result["frontend_url"])
    from backend.main import ORIGINS, PRODUCTION

    if (
        callback.path != "/api/auth/oidc/callback"
        or callback.query
        or callback.fragment
        or frontend.path not in {"", "/"}
        or frontend.query
        or frontend.fragment
        or result["frontend_url"].rstrip("/") not in ORIGINS
        or (PRODUCTION and (callback.scheme != "https" or frontend.scheme != "https"))
    ):
        raise HTTPException(503, "OIDC callback/frontend configuration is invalid.")
    return result


def configuration_hash(cfg, provider_row=None):
    return token_hash(
        json.dumps(
            {**cfg, "organization_provider_version": provider_row.version if provider_row else None}, sort_keys=True
        )
    )


def approved_url(value):
    parsed = urlsplit(value)
    approved = {h.strip().lower() for h in os.getenv("OIDC_ALLOWED_HOSTS", "").split(",") if h.strip()}
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in approved
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
    ):
        raise HTTPException(503, "OIDC endpoint is not an approved HTTPS destination.")
    try:
        networks = [
            ipaddress.ip_network(c.strip(), strict=True)
            for c in os.getenv("OIDC_ALLOWED_PRIVATE_CIDRS", "").split(",")
            if c.strip()
        ]
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError()
        for row in addresses:
            address = ipaddress.ip_address(row[4][0])
            address = getattr(address, "ipv4_mapped", None) or address
            if (
                address.is_loopback
                or address.is_link_local
                or address.is_unspecified
                or address.is_multicast
                or (not address.is_global and not any(address in network for network in networks))
            ):
                raise ValueError()
    except (OSError, ValueError):
        raise HTTPException(503, "OIDC endpoint DNS/address is not approved.") from None


def fetch_json(method, url, **kwargs):
    approved_url(url)
    from integrations.secure_http import PinnedTransport

    hosts = {h.strip().lower() for h in os.getenv("OIDC_ALLOWED_HOSTS", "").split(",") if h.strip()}
    networks = [c.strip() for c in os.getenv("OIDC_ALLOWED_PRIVATE_CIDRS", "").split(",") if c.strip()]
    transport = PinnedTransport(url, hosts, networks, os.getenv("OIDC_CA_BUNDLE_FILE") or None)
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False, transport=transport) as client:
        with client.stream(method, url, **kwargs) as response:
            if response.status_code != 200:
                raise ValueError("OIDC endpoint rejected request")
            value = bytearray()
            for chunk in response.iter_bytes():
                value.extend(chunk)
                if len(value) > 262144:
                    raise ValueError("OIDC response budget exceeded")
            return json.loads(value)


def validate_token(token, cfg, nonce_hash):
    if not isinstance(token, str) or len(token) > 32768:
        raise ValueError("ID token budget exceeded")
    header = jwt.get_unverified_header(token)
    if header.get("alg") not in {"RS256", "ES256"} or not isinstance(header.get("kid"), str):
        raise ValueError("Unsupported token signature")
    jwks = fetch_json("GET", cfg["jwks_url"])
    matches = [
        key
        for key in jwks.get("keys", [])
        if key.get("kid") == header["kid"]
        and key.get("use", "sig") == "sig"
        and key.get("alg", header["alg"]) == header["alg"]
    ]
    if len(matches) != 1:
        raise ValueError("Signing key unavailable or ambiguous")
    key = jwt.PyJWK.from_dict(matches[0], algorithm=header["alg"])
    claims = jwt.decode(
        token,
        key.key,
        algorithms=[header["alg"]],
        audience=cfg["client_id"],
        issuer=cfg["issuer"],
        options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        leeway=30,
    )
    if not isinstance(claims["sub"], str) or not claims["sub"] or len(claims["sub"]) > 250:
        raise ValueError("Invalid subject")
    if not isinstance(claims["nonce"], str) or not secrets.compare_digest(token_hash(claims["nonce"]), nonce_hash):
        raise ValueError("Nonce mismatch")
    aud = claims["aud"]
    if (
        isinstance(aud, list)
        and len(aud) > 1
        and claims.get("azp") != cfg["client_id"]
        or "azp" in claims
        and claims["azp"] != cfg["client_id"]
    ):
        raise ValueError("Authorized party mismatch")
    if time.time() - claims["iat"] > 600:
        raise ValueError("ID token is too old for this login")
    return claims


@router.get("/options")
def options():
    try:
        cfg = config()
        from backend.db import Record

        with session() as db:
            providers = db.scalars(
                select(Record)
                .where(
                    Record.kind == "oidc_provider",
                    Record.natural_key == cfg["issuer"],
                    Record.data["state"].as_string() == "ENABLED",
                )
                .limit(100)
            )
            return {
                "enabled": True,
                "issuer": cfg["issuer"],
                "flow": "CODE_PKCE",
                "jit": False,
                "organizations": [{"id": r.organization_id, "label": r.data["label"]} for r in providers],
            }
    except HTTPException:
        return {"enabled": False, "flow": "CODE_PKCE", "jit": False}


@router.get("/start")
def start(organization_id: str | None = None):
    cfg = config()
    state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    with session() as db:
        from backend.oidc_lifecycle import provider

        configured = provider(db, organization_id, cfg["issuer"]) if organization_id else None
        if organization_id and (not configured or configured.data.get("state") != "ENABLED"):
            raise HTTPException(503, "Organization OIDC is unavailable.")
        db.execute(delete(OIDCAttempt).where(OIDCAttempt.expires < time.time()))
        db.add(
            OIDCAttempt(
                state_hash=token_hash(state),
                browser_hash=token_hash(browser),
                nonce_hash=token_hash(nonce),
                verifier_ciphertext=cipher().encrypt(verifier.encode()).decode(),
                expires=time.time() + 300,
                organization_id=organization_id,
                configuration_hash=configuration_hash(cfg, configured),
            )
        )
        db.commit()
    response = RedirectResponse(
        cfg["authorization_url"]
        + "?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": cfg["client_id"],
                "redirect_uri": cfg["redirect_uri"],
                "scope": "openid email profile" if configured and configured.data.get("jit_enabled") else "openid",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    from backend.main import PRODUCTION

    response.set_cookie(
        "pt_oidc_browser", browser, httponly=True, secure=PRODUCTION, samesite="lax", max_age=300, path="/api/auth/oidc"
    )
    return response


@router.get("/callback")
def callback(request: Request, state: str = "", code: str = ""):
    cfg = config()
    if not state or len(state) > 200 or not code or len(code) > 4096:
        raise HTTPException(400, "OIDC callback is invalid.")
    with session() as db:
        attempt = db.scalar(select(OIDCAttempt).where(OIDCAttempt.state_hash == token_hash(state)).with_for_update())
        if (
            not attempt
            or attempt.expires < time.time()
            or not secrets.compare_digest(attempt.browser_hash, token_hash(request.cookies.get("pt_oidc_browser", "")))
        ):
            raise HTTPException(400, "OIDC state/browser binding is invalid or expired.")
        nonce_hash, ciphertext = attempt.nonce_hash, attempt.verifier_ciphertext
        from backend.oidc_lifecycle import membership_for_claims, provider

        organization_id = attempt.organization_id
        configured = provider(db, organization_id, cfg["issuer"]) if organization_id else None
        if (
            organization_id
            and (not configured or configured.data.get("state") != "ENABLED")
            or attempt.configuration_hash
            and attempt.configuration_hash != configuration_hash(cfg, configured)
        ):
            db.delete(attempt)
            db.commit()
            raise HTTPException(400, "OIDC configuration changed during login; start again.")
        db.delete(attempt)
        db.commit()  # Consume state before the exchange; failed attempts cannot be replayed.
        try:
            body = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg["redirect_uri"],
                "client_id": cfg["client_id"],
                "code_verifier": cipher().decrypt(ciphertext.encode()).decode(),
            }
            secret = os.getenv("OIDC_CLIENT_SECRET")
            if secret:
                body["client_secret"] = secret
            token = fetch_json("POST", cfg["token_url"], data=body)
            claims = validate_token(token.get("id_token"), cfg, nonce_hash)
        except Exception:
            raise HTTPException(400, "OIDC token validation failed.") from None
        subject, user = membership_for_claims(db, cfg, claims, organization_id)
        from backend.governance import resolve_principal
        user=resolve_principal(db,user,subject.organization_id)
        from backend.main import PRODUCTION

        response = RedirectResponse(cfg["frontend_url"].rstrip("/") + "/overview", status_code=303)
        create_session(db, user, response, PRODUCTION, request.cookies.get("pt_session"), oidc_subject_id=subject.id)
        response.delete_cookie("pt_oidc_browser", path="/api/auth/oidc")
        audit(db, user, "OIDC_LOGIN", user.id, {"issuer": claims["iss"], "membership_id": subject.id})
        db.commit()
        return response


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=250)
    enabled: StrictBool = True


@router.post("/membership")
def membership(body: Membership, request: Request):
    cfg = config()
    with session() as db:
        actor, _ = authenticate(db, request, True)
        from backend.governance import require_permission, resolve_principal
        require_permission(db,actor,"organization.settings.manage")
        user = db.get(User, body.user_id)
        if not user or not resolve_principal(db,user,actor.organization_id).enabled:
            raise HTTPException(404, "Member unavailable in this organization.")
        row = db.scalar(
            select(OIDCSubject)
            .where(OIDCSubject.issuer == cfg["issuer"], OIDCSubject.subject == body.subject)
            .with_for_update()
        )
        if row and (row.organization_id != actor.organization_id or row.user_id != user.id):
            raise HTTPException(409, "Subject is already assigned; explicit reassignment is required.")
        if not row:
            row = OIDCSubject(
                id=uid(),
                issuer=cfg["issuer"],
                subject=body.subject,
                organization_id=actor.organization_id,
                user_id=user.id,
                enabled=body.enabled,
            )
            db.add(row)
        row.enabled = body.enabled
        if not body.enabled:
            db.execute(delete(SessionToken).where(SessionToken.oidc_subject_id == row.id))
        audit(db, actor, "OIDC_MEMBERSHIP_UPDATED", user.id, {"enabled": body.enabled, "membership_id": row.id})
        db.commit()
        return {"id": row.id, "enabled": row.enabled}


register_lifecycle(router)
