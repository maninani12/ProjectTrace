import base64
import hashlib
import hmac
import json
import ssl

import httpcore
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from backend import main
from backend.db import Record
from integrations.github.connector import GitHubApp
from integrations.secure_http import PinnedBackend, PinnedTransport
from tests.test_enterprise_trust import owner


def body(**patch):
    return {"provider_type": "GHES", "label": "Controlled GHES", "web_url": "https://ghes.example",
        "api_base_url": "https://ghes.example/api/v3", "app_id": "1", "installation_id": "2",
        "private_key_ref": "ENV:SCM_FIXTURE_KEY", "webhook_secret_ref": "ENV:SCM_FIXTURE_WEBHOOK", **patch}


def configure(client, monkeypatch):
    monkeypatch.setenv("GHES_ALLOWED_HOSTS", "ghes.example")
    monkeypatch.setenv("SCM_FIXTURE_WEBHOOK", "controlled-webhook-secret")
    result = client.post("/api/github/connections", json=body())
    assert result.status_code == 200, result.text
    return result.json()


class FixtureAdapter:
    def repositories(self):
        return [{"id": 7, "name": "repo", "full_name": "org/repo", "private": True}]

    def fetch_snapshot(self, name, commit):
        assert name == "org/repo"
        return {"app.py": "def work():\n    return 1\n"}

    def publish_check(self, *args):
        pytest.fail("Checks require explicit tenant policy")


def connected(client, monkeypatch):
    client = owner(client)
    saved = configure(client, monkeypatch)
    from workers import github

    monkeypatch.setattr(github, "configured_app", lambda connection: FixtureAdapter())
    discovery = client.get(f"/api/github/connections/{saved['id']}/repositories")
    assert discovery.status_code == 200 and discovery.json()["source_fetched"] is False
    result = client.post("/api/github/connect", json={"connection_id": saved["id"], "repository_id": 7,
        "system": "Controlled system", "owner": "Fixture team", "checks_enabled": True})
    assert result.status_code == 200, result.text
    return saved, result.json()["repository_id"]


def deliver(client, connection_id, payload, event="push", delivery="fixture-delivery"):
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"controlled-webhook-secret", raw, hashlib.sha256).hexdigest()
    return client.post("/api/github/webhook/" + connection_id, content=raw, headers={
        "x-hub-signature-256": signature, "x-github-event": event, "x-github-delivery": delivery})


def test_ghes_metadata_scoped_discovery_webhook_worker_and_neutral_egress(client, monkeypatch):
    saved, repository = connected(client, monkeypatch)
    identifier = saved["id"]
    payload = {"installation": {"id": 2}, "repository": {"id": 7}, "after": "a" * 40, "ref": "refs/heads/main"}
    assert deliver(client, identifier, payload).status_code == 200
    assert deliver(client, identifier, payload).json()["status"] == "DUPLICATE"
    from workers import github

    monkeypatch.setattr(github, "Session", main.Session)
    with main.Session() as db:
        job = db.scalar(select(Record).where(Record.kind == "job", Record.repository_id == repository))
        job_id = job.id
    github.github_delivery.run(job_id)
    with main.Session() as db:
        job = db.get(Record, job_id)
        assert job.data["snapshot_id"] and job.data["check_published"] is False
        assert job.data["check_status"] == "BLOCKED_BY_TENANT_POLICY"
    assert deliver(client, identifier, {**payload, "installation": {"id": 99}}, delivery="bad-install").status_code == 422
    assert deliver(client, identifier, {**payload, "repository": {"id": 99}}, delivery="bad-repo").status_code == 404
    assert client.post("/api/github/webhook/" + identifier, content=json.dumps(payload), headers={"x-hub-signature-256": "invalid"}).status_code == 401


def test_installation_repository_revocation_removal_and_fork_scope(client, monkeypatch):
    saved, _ = connected(client, monkeypatch)
    identifier = saved["id"]
    fork = {"installation": {"id": 2}, "repository": {"id": 7}, "action": "opened",
        "pull_request": {"number": 11, "head": {"sha": "a" * 40, "repo": {"id": 99}}, "base": {"sha": "b" * 40}}}
    assert deliver(client, identifier, fork, event="pull_request").json()["analysis"] == "PARTIAL"
    removed = {"installation": {"id": 2}, "action": "removed", "repositories_removed": [{"id": 7}]}
    assert deliver(client, identifier, removed, event="installation_repositories", delivery="removed-repo").status_code == 200
    push = {"installation": {"id": 2}, "repository": {"id": 7}, "after": "a" * 40}
    assert deliver(client, identifier, push, delivery="after-revoke").status_code == 410
    assert deliver(client, identifier, {"installation": {"id": 2}, "action": "deleted"}, event="installation", delivery="removed-install").json()["status"] == "REVOKED"
    assert deliver(client, identifier, push, delivery="after-remove").status_code == 410


@pytest.mark.parametrize("patch", [{"web_url": "http://ghes.example"}, {"api_base_url": "https://evil.example/api/v3"},
    {"api_base_url": "https://ghes.example/metadata"}, {"web_url": "https://user:pass@ghes.example"},
    {"api_base_url": "https://ghes.example/api/v3?redirect=metadata"}, {"private_key_ref": "ENV:DATABASE_URL"}])
def test_scm_rejects_unapproved_endpoints_or_sensitive_reference_domains(client, monkeypatch, patch):
    client = owner(client)
    monkeypatch.setenv("GHES_ALLOWED_HOSTS", "ghes.example")
    assert client.post("/api/github/connections", json=body(**patch)).status_code == 422


def test_connected_provider_identity_is_not_reassigned_and_cross_tenant_reads_fail(client, monkeypatch):
    saved, _ = connected(client, monkeypatch)
    current = client.get("/api/github/connections").json()["items"][0]
    assert client.post("/api/github/connections", json=body(connection_id=saved["id"], expected_version=current["version"], installation_id="3")).status_code == 409
    client.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"})
    assert client.get("/api/github/connections").json()["items"] == []
    assert client.get(f"/api/github/connections/{saved['id']}/repositories").status_code == 404
    assert client.get("/api/record/" + saved["id"]).status_code == 404


def test_network_destination_is_pinned_and_metadata_loopback_or_dns_mixture_rejected(monkeypatch):
    from integrations import secure_http

    calls = []
    monkeypatch.setattr(secure_http.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    backend = PinnedBackend("ghes.example", 443)
    monkeypatch.setattr(backend.delegate, "connect_tcp", lambda *a, **k: calls.append(a) or object())
    backend.connect_tcp("ghes.example", 443)
    assert calls[0][0] == "93.184.216.34"
    transport = PinnedTransport("https://ghes.example/api/v3", {"ghes.example"})
    assert transport.context.check_hostname and transport.context.verify_mode == ssl.CERT_REQUIRED
    with pytest.raises(httpx.TransportError):
        transport.handle_request(httpx.Request("GET", "https://evil.example/api/v3"))
    for address in ["127.0.0.1", "169.254.169.254", "::1", "10.1.2.3"]:
        monkeypatch.setattr(secure_http.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 443))])
        with pytest.raises(httpcore.ConnectError):
            backend.connect_tcp("ghes.example", 443)
    private = PinnedBackend("ghes.example", 443, ["10.0.0.0/8"])
    monkeypatch.setattr(private.delegate, "connect_tcp", lambda *a, **k: calls.append(a) or object())
    private.connect_tcp("ghes.example", 443)
    assert calls[-1][0] == "10.1.2.3"
    transport.close()


def test_ghes_transport_preserves_api_prefix_and_refreshes_installation_tokens(monkeypatch):
    calls = []
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app = GitHubApp("1", key, "2", api_base_url="https://ghes.example/api/v3", allowed_hosts={"ghes.example"})

    def handler(request):
        calls.append(request.url.path)
        assert request.url.host == "ghes.example" and request.url.path.startswith("/api/v3/")
        if request.url.path.endswith("access_tokens"):
            return httpx.Response(201, json={"token": "fixture-installation-token"})
        if request.url.path.endswith("repositories"):
            return httpx.Response(200, json={"total_count": 1, "repositories": [{"id": 7}]})
        if "/trees/" in request.url.path:
            return httpx.Response(200, json={"tree": [{"path": "app.py", "sha": "b" * 40, "type": "blob", "mode": "100644", "size": 5}]})
        return httpx.Response(200, json={"encoding": "base64", "content": base64.b64encode(b"pass\n").decode()})

    monkeypatch.setattr(app, "client", lambda headers=None: httpx.Client(base_url=app.api_base_url, transport=httpx.MockTransport(handler), follow_redirects=False, headers=headers))
    assert app.repositories()[0]["id"] == 7
    assert app.fetch_snapshot("org/repo", "a" * 40)["app.py"] == "pass\n"
    assert sum(p.endswith("access_tokens") for p in calls) == 2
