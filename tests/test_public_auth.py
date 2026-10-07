from backend import main


def test_public_options_expose_only_authentication_and_available_actions(client, monkeypatch):
    expected = {"authenticated": False, "local_registration": True, "demo_available": True}
    assert client.get("/api/auth/options").json() == expected
    client.cookies.set("pt_session", "invalid-session")
    assert client.get("/api/auth/options").json() == expected
    response = client.post("/api/auth/demo", json={})
    assert response.status_code == 200
    assert client.get("/api/auth/options").json() == {**expected, "authenticated": True}
    monkeypatch.setattr(main, "PRODUCTION", True)
    monkeypatch.setattr(main, "APP_ENV", "production")
    # This test isolates production auth availability from Redis admission;
    # distributed admission has its own fail-closed tests and real-service proof.
    local_allow = main.rate_limit.allow
    monkeypatch.setattr(main.rate_limit, "allow", lambda identity, policy, *, distributed=False: local_allow(identity, policy))
    assert client.get("/api/auth/options").json() == {"authenticated": True, "local_registration": False, "demo_available": False}
    assert client.post("/api/auth/demo", json={}).status_code == 404
    assert client.post("/api/auth/register", json={"email": "new@example.com", "password": "Long-test-password-123!", "organization": "new"}).status_code == 404
