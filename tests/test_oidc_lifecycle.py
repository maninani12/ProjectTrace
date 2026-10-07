import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from sqlalchemy import select

from backend import main, oidc
from backend.db import Grant, OIDCAttempt, OIDCSubject, SessionToken, User
from backend.oidc_lifecycle import membership_for_claims
from backend.security import token_hash
from tests.test_enterprise_trust import identity_provider as shared_identity_provider
from tests.test_enterprise_trust import owner


@pytest.fixture
def identity_provider(monkeypatch):
    return shared_identity_provider.__wrapped__(monkeypatch)


def configure(client, mappings=None, **patch):
    response = client.post("/api/auth/oidc/provider", json={"expected_version": 0, "jit_enabled": True,
        "role_mappings": mappings or {"engineering": {"role": "ENGINEER", "repositories": []}}, **patch})
    assert response.status_code == 200, response.text
    return response.json()


def authorization(client, cfg, key, jwk, monkeypatch, org, **claims):
    start = client.get(f"/api/auth/oidc/start?organization_id={org}", follow_redirects=False)
    assert start.status_code == 307, start.text
    params = parse_qs(urlsplit(start.headers["location"]).query)
    assert params["scope"] == ["openid email profile"]
    token = jwt.encode({"iss": cfg["issuer"], "aud": cfg["client_id"], "sub": "new-member",
        "nonce": params["nonce"][0], "iat": time.time(), "exp": time.time() + 300,
        "email": "new-member@example.com", "email_verified": True, "groups": ["engineering"], **claims},
        key, algorithm="RS256", headers={"kid": "fixture-key"})

    def exchange(method, url, **kwargs):
        if method == "GET":
            return {"keys": [jwk]}
        assert kwargs["data"]["code_verifier"] and kwargs["data"]["redirect_uri"] == cfg["redirect_uri"]
        return {"id_token": token}

    monkeypatch.setattr(oidc, "fetch_json", exchange)
    return "/api/auth/oidc/callback?" + f"state={params['state'][0]}&code=controlled-code"


def organization():
    with main.Session() as db:
        return db.scalar(select(User.organization_id).where(User.email == "enterprise-owner@example.com"))


def test_controlled_jit_verified_group_grant_and_provider_removal(client, identity_provider, monkeypatch):
    client = owner(client)
    cfg, key, jwk = identity_provider
    repo = client.post("/api/import", json={"name": "OIDC repository", "files": {"app.py": "pass\n"}}).json()["repository_id"]
    policy = configure(client, {"engineering": {"role": "ENGINEER", "repositories": [repo]}})
    org = organization()
    assert client.get("/api/auth/oidc/options").json()["organizations"][0]["id"] == org
    callback = authorization(client, cfg, key, jwk, monkeypatch, org)
    assert client.get(callback, follow_redirects=False).status_code == 303
    token = client.cookies.get("pt_session")
    assert client.get("/api/auth/me").json()["role"] == "ENGINEER"
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == "new-member@example.com"))
        assert not user.local_login_allowed and user.enabled
        assert db.get(Grant, (user.id, repo))
    assert client.post("/api/auth/login", json={"email": "new-member@example.com", "password": "anything"}).status_code == 401
    login = client.post("/api/auth/login", json={"email": "enterprise-owner@example.com", "password": "Enterprise-test-password-123!"}).json()
    client.headers["x-csrf-token"] = login["csrf"]
    update = client.post("/api/auth/oidc/provider", json={"expected_version": policy["version"], "state": "REMOVED"})
    assert update.status_code == 200 and update.json()["state"] == "REMOVED"
    with main.Session() as db:
        assert db.get(SessionToken, token_hash(token)) is None
    assert client.get(f"/api/auth/oidc/start?organization_id={org}", follow_redirects=False).status_code == 503


@pytest.mark.parametrize("claims", [
    {"email_verified": False}, {"groups": ["unmapped"]}, {"groups": "engineering"},
    {"email": "enterprise-owner@example.com"}, {"groups": [{"role": "ADMIN"}]},
])
def test_jit_rejects_unsafe_membership_and_does_not_resurrect_or_link_email(client, identity_provider, monkeypatch, claims):
    client = owner(client)
    cfg, key, jwk = identity_provider
    configure(client)
    callback = authorization(client, cfg, key, jwk, monkeypatch, organization(), **claims)
    assert client.get(callback, follow_redirects=False).status_code == 403
    with main.Session() as db:
        assert db.scalar(select(OIDCSubject).where(OIDCSubject.subject == "new-member")) is None


def test_oidc_provider_version_change_invalidates_pending_attempt_before_exchange(client, identity_provider, monkeypatch):
    client = owner(client)
    cfg, key, jwk = identity_provider
    saved = configure(client)
    callback = authorization(client, cfg, key, jwk, monkeypatch, organization())
    assert client.post("/api/auth/oidc/provider", json={"expected_version": saved["version"], "state": "DISABLED"}).status_code == 200
    monkeypatch.setattr(oidc, "fetch_json", lambda *a, **k: pytest.fail("An invalidated login must not exchange its code"))
    assert client.get(callback, follow_redirects=False).status_code == 400
    with main.Session() as db:
        assert not list(db.scalars(select(OIDCAttempt)))


def test_provider_group_admin_permissions_scope_stale_and_disabled_users(client, identity_provider):
    client = owner(client)
    cfg, _, _ = identity_provider
    assert client.post("/api/auth/oidc/provider", json={"expected_version": 0, "role_mappings": {"admin": {"role": "ADMIN"}}}).status_code == 422
    assert client.post("/api/auth/oidc/provider", json={"expected_version": 0, "role_mappings": {"group": {"role": "VIEWER", "repositories": ["private"]}}}).status_code == 404
    policy = configure(client)
    assert client.post("/api/auth/oidc/provider", json={"expected_version": 0}).status_code == 409
    assert client.get("/api/auth/oidc/members?limit=101").status_code == 422
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == "enterprise-owner@example.com"))
        subject = OIDCSubject(id="disabled-subject", issuer=cfg["issuer"], subject="disabled-user",
            organization_id=user.organization_id, user_id=user.id, enabled=True)
        db.add(subject)
        db.flush()
        user.enabled = False
        with pytest.raises(Exception) as error:
            membership_for_claims(db, cfg, {"iss": cfg["issuer"], "sub": "disabled-user", "groups": ["engineering"]}, user.organization_id)
        assert error.value.status_code == 403
        db.rollback()
    assert policy["version"] == 1
