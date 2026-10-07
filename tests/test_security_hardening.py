import hashlib
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import select

from analyzers.verifiers import extract_documentation
from backend import main, oidc
from backend.db import Audit, AuditHead, AuditLink, User
from backend.domain import audit
from backend.trust import canonical, integrity
from tests.test_enterprise_trust import owner


def test_retained_checkpoint_detects_privileged_whole_chain_rewrite(client, monkeypatch):
    monkeypatch.setenv("AUDIT_CHECKPOINT_KEY", "controlled-checkpoint-key-at-least-32-characters")
    client = owner(client)
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == "enterprise-owner@example.com"))
        org = user.organization_id
        audit(db, user, "OWNED_CHECKPOINT_FIXTURE", org, {"reason": "original"})
        db.commit()
    proof = client.get("/api/trust/audit-integrity").json()
    checkpoint = proof["checkpoint"]
    assert (
        client.post("/api/trust/audit-checkpoint/verify", json=checkpoint).json()["state"]
        == "VERIFIED_AGAINST_RETAINED_CHECKPOINT"
    )
    with main.Session() as db:
        links = list(db.scalars(select(AuditLink).where(AuditLink.organization_id == org).order_by(AuditLink.sequence)))
        event = db.get(Audit, links[-1].event_id)
        event.data = {"reason": "privileged rewrite"}
        previous = "0" * 64
        for link in links:
            link.previous_digest = previous
            link.digest = hashlib.sha256(
                canonical(db.get(Audit, link.event_id), link.sequence, previous).encode()
            ).hexdigest()
            previous = link.digest
        db.get(AuditHead, org).digest = previous
        db.commit()
        assert integrity(db, org)["state"] == "VERIFIED"
    result = client.post("/api/trust/audit-checkpoint/verify", json=checkpoint)
    assert result.json()["state"] == "CHECKPOINT_MISMATCH"
    assert not result.json()["immutable_archive"]
    assert (
        client.post("/api/trust/audit-checkpoint/verify", json={**checkpoint, "signature": "0" * 64}).status_code == 422
    )


def test_concurrent_audit_appends_keep_one_contiguous_chain(client):
    owner(client)
    with main.Session() as db:
        identifier = db.scalar(select(User.id).where(User.email == "enterprise-owner@example.com"))

    def append(index):
        with main.Session() as db:
            user = db.get(User, identifier)
            audit(db, user, "OWNED_CONCURRENT_FIXTURE", str(index), {})
            db.commit()
            return user.organization_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        orgs = list(pool.map(append, range(12)))
    with main.Session() as db:
        proof = integrity(db, orgs[0])
        assert proof["state"] == "VERIFIED" and proof["linked_events"] >= 12


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254"]
)
def test_oidc_internal_allowlist_cannot_allow_metadata_or_loopback(monkeypatch, address):
    monkeypatch.setenv("OIDC_ALLOWED_HOSTS", "identity.example")
    monkeypatch.setenv("OIDC_PRIVATE_HOSTS", "identity.example")
    monkeypatch.setenv("OIDC_ALLOWED_PRIVATE_CIDRS", "0.0.0.0/0,::/0")
    monkeypatch.setattr(oidc.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(Exception):
        oidc.approved_url("https://identity.example/keys")


def test_oidc_fetch_uses_pinned_transport_without_proxy_or_redirect(monkeypatch):
    from integrations.secure_http import PinnedTransport

    original_client = httpx.Client
    received = []
    monkeypatch.setenv("OIDC_ALLOWED_HOSTS", "identity.example")
    monkeypatch.setattr(oidc.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])

    def controlled_client(**kwargs):
        assert isinstance(kwargs["transport"], PinnedTransport)
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        kwargs["transport"].close()
        kwargs["transport"] = httpx.MockTransport(
            lambda request: received.append(request) or httpx.Response(200, json={"keys": []})
        )
        return original_client(**kwargs)

    monkeypatch.setattr(oidc.httpx, "Client", controlled_client)
    assert oidc.fetch_json("GET", "https://identity.example/keys") == {"keys": []}
    assert received[0].url.host == "identity.example"


def test_documentation_work_limits_are_explicit_and_source_is_inert():
    diagnostics = []
    claims = extract_documentation(
        {f"doc{i}.md": "Backend uses FastAPI.\n" for i in range(1600)}, diagnostics=diagnostics
    )
    assert len(claims) == 1501 and diagnostics[-1]["state"] == "PARTIAL"
    diagnostics = []
    assert not extract_documentation({"long.md": "x" * 33000 + "Backend uses JWT."}, diagnostics=diagnostics)
    assert diagnostics[0]["code"] == "DOCUMENTATION_LINE_BUDGET"
    diagnostics = []
    assert not extract_documentation({f"empty{i}.md": "# inert\n" for i in range(2001)}, diagnostics=diagnostics)
    assert diagnostics[0]["code"] == "DOCUMENTATION_WORK_BUDGET"
