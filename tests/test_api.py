import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from backend import main
from backend.db import Repository
from backend.domain import policy_gate


def test_login_cookie_security(signed):
    response = signed.post("/api/auth/demo", json={})
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]


def test_workspace_consistency(signed):
    data = signed.get("/api/workspace").json()
    assert len(data["repositories"]) == 4
    assert any(c["status"] == "CONTRADICTED" for c in data["claim"])
    ids = {e["id"] for e in data["evidence"]}
    assert all(set(c["evidence_ids"]) <= ids for c in data["claim"])
    assert all(c["scope"]["snapshot_id"] for c in data["claim"])
    assert data["demo"] is True


def test_private_repository_acl_applies_to_every_surface(signed):
    assert signed.post("/api/repositories/private/analyze", json={"files": {"README.md": "hidden"}}).status_code == 404
    data = signed.get("/api/workspace").json()
    assert "private-secret-repository" not in json.dumps(data)
    assert (
        signed.post("/api/ask", json={"question": "How is auth implemented?", "repository_id": "private"}).status_code
        == 404
    )


def test_cross_tenant_idor(signed):
    claim = signed.get("/api/workspace").json()["claim"][0]
    response = signed.post(
        "/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"}
    )
    signed.headers["x-csrf-token"] = response.json()["csrf"]
    assert signed.get("/api/record/" + claim["id"]).status_code == 404
    assert signed.get("/api/sbom/" + claim["scope"]["snapshot_id"]).status_code == 404
    assert signed.get("/api/workspace").json()["repositories"] == []
    assert signed.get("/api/audit").json() == []


def test_viewer_grants_and_mutation_authorization(signed):
    response = signed.post(
        "/api/auth/login", json={"email": "viewer@example.com", "password": "Strong-test-password-123!"}
    )
    signed.headers["x-csrf-token"] = response.json()["csrf"]
    data = signed.get("/api/workspace").json()
    assert {r["id"] for r in data["repositories"]} == {"clean"}
    assert signed.post("/api/import", json={"name": "demo", "files": {"README.md": "example"}}).status_code == 403
    assert signed.post("/api/ask", json={"question": "The API exposes health?"}).status_code == 200


def test_csrf_and_origin(signed):
    signed.headers["x-csrf-token"] = "invalid"
    assert signed.post("/api/import", json={"name": "demo", "files": {"README.md": "example"}}).status_code == 403
    signed.headers["origin"] = "https://evil.example"
    assert signed.post("/api/auth/demo", json={}).status_code == 403


def test_logout_invalidates_session(signed):
    assert signed.post("/api/auth/logout", json={}).status_code == 200
    assert signed.get("/api/workspace").status_code == 401


def test_import_redacts_secrets(signed):
    registered = signed.post(
        "/api/auth/register",
        json={"email": "real@example.com", "password": "Strong-test-password-123!", "organization": "Real workspace"},
    )
    signed.headers["x-csrf-token"] = registered.json()["csrf"]
    response = signed.post(
        "/api/import",
        json={
            "name": "new-repo",
            "files": {
                "config.env": 'api_key = "test_credential_value_1234567"',
                "README.md": "Authentication uses OAuth.",
            },
        },
    )
    assert response.status_code == 200
    serialized = signed.get("/api/workspace").text
    assert "test_credential_value" not in serialized
    assert "[REDACTED SECRET]" in serialized


def test_review_audit_and_optimistic_locking(signed):
    item = signed.get("/api/workspace").json()["claim"][0]
    body = {"action": "CONFIRM", "reason": "Reviewed current source and evidence.", "expected_version": item["version"]}
    response = signed.post(f"/api/record/{item['id']}/review", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == item["status"]
    assert response.json()["review_status"] == "CONFIRMED"
    assert signed.post(f"/api/record/{item['id']}/review", json=body).status_code == 409
    assert signed.get("/api/audit").json()[0]["action"] == "HUMAN_REVIEW"


def test_engineer_cannot_accept_risk(signed):
    item = signed.get("/api/workspace").json()["claim"][0]
    assert (
        signed.post(
            f"/api/record/{item['id']}/review",
            json={
                "action": "CREATE_EXCEPTION",
                "reason": "Accept this risk temporarily.",
                "expected_version": item["version"],
            },
        ).status_code
        == 403
    )


def test_ask_is_grounded(signed):
    answer = signed.post(
        "/api/ask", json={"question": "How is authentication implemented?", "repository_id": "identity"}
    ).json()
    assert "session" in answer["answer"]
    assert answer["evidence"]
    assert answer["provider"] == "Deterministic evidence retrieval"
    assert (
        signed.post("/api/ask", json={"question": "What is the temperature on Jupiter?"}).json()["verification"]
        == "UNVERIFIED"
    )


def test_idempotent_analysis_and_scope(signed):
    body = {"files": {"README.md": "Backend uses FastAPI.", "app.py": "import fastapi"}, "branch": "test"}
    first = signed.post("/api/repositories/clean/analyze", json=body)
    second = signed.post("/api/repositories/clean/analyze", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    base = signed.get("/api/workspace").json()["repositories"][0]["snapshot"]["id"]
    if signed.get("/api/record/" + base).json()["repository_id"] != "clean":
        assert signed.post("/api/repositories/clean/analyze", json={**body, "base_id": base}).status_code == 422


def test_webhook_signature_replay_and_unconfigured(signed, monkeypatch):
    assert signed.post("/api/github/webhook", content="{}").status_code == 503
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    payload = json.dumps({"repository": {"id": 123}}).encode()
    assert signed.post("/api/github/webhook", content=payload).status_code == 401
    with main.Session() as db:
        repo = db.get(Repository, "clean")
        repo.provider = "GITHUB"
        repo.provider_id = "123"
        db.commit()
    signature = "sha256=" + hmac.new(b"test-webhook-secret", payload, hashlib.sha256).hexdigest()
    headers = {"x-hub-signature-256": signature, "x-github-delivery": "test-delivery", "x-github-event": "pull_request"}
    assert signed.post("/api/github/webhook", content=payload, headers=headers).json()["status"] == "RECEIVED"
    assert signed.post("/api/github/webhook", content=payload, headers=headers).json()["status"] == "DUPLICATE"


def test_expired_exceptions_do_not_bypass_gate():
    finding = {"id": "finding", "severity": "CRITICAL", "confidence": "HIGH", "title": "Test"}
    expired = {"target": "finding", "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
    current = {**expired, "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    assert policy_gate([], [finding], [expired])["overall"] == "FAIL"
    assert policy_gate([], [finding], [current])["overall"] == "PASS"


def test_security_headers_and_bad_zip(signed):
    response = signed.get("/api/workspace")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert signed.post("/api/archive/import", content=b"badzip").status_code == 409
    registered = signed.post(
        "/api/auth/register",
        json={"email": "real@example.com", "password": "Strong-test-password-123!", "organization": "Real workspace"},
    )
    signed.headers["x-csrf-token"] = registered.json()["csrf"]
    assert signed.post("/api/archive/import", content=b"badzip").status_code == 422
    data = signed.get("/api/workspace").json()
    assert data["analysis"]["state"] == "FAILED"
    assert data["job"][0]["errors"]


def test_claim_history_tracks_stale_transition(signed):
    data = signed.get("/api/workspace").json()
    claim = next(c for c in data["claim"] if c["status"] == "CONTRADICTED")
    assert [h["status"] for h in claim["history"]] == ["VERIFIED", "STALE", "CONTRADICTED"]


def test_health_readiness_and_provider_truth(signed):
    assert signed.get("/health").status_code == 200
    assert signed.get("/ready").status_code == 200
    assert all(i["status"] == "NOT_CONFIGURED" for i in signed.get("/api/integrations").json())


def test_repeated_bad_login_is_rate_limited(client):
    responses = [
        client.post("/api/auth/login", json={"email": "missing@example.com", "password": "bad"}) for _ in range(16)
    ]
    assert responses[-1].status_code == 429


def test_gate_recomputes_from_reviewed_records(signed):
    item = next(f for f in signed.get("/api/workspace").json()["finding"] if f["category"] == "IAC")
    snapshot_id = item["scope"]["snapshot_id"]
    before = signed.get("/api/gate/" + snapshot_id).json()
    signed.post(
        f"/api/record/{item['id']}/review",
        json={
            "action": "FALSE_POSITIVE",
            "reason": "Fixture is intentionally privileged.",
            "expected_version": item["version"],
        },
    )
    after = signed.get("/api/gate/" + snapshot_id).json()
    assert len(after["results"]) < len(before["results"])
