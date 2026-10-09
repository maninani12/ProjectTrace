import redis

from backend import rate_limit


def test_separate_policies_and_redis_atomic_admission(monkeypatch):
    assert rate_limit.bucket("/api/auth/login", "POST") == "login"
    assert rate_limit.bucket("/api/auth/options", "GET") == "auth_metadata"
    assert rate_limit.bucket("/api/auth/oidc/options", "GET") == "auth_metadata"
    assert rate_limit.bucket("/api/archive/import", "POST") == "imports"
    assert rate_limit.bucket("/api/ask", "POST") == "ask"
    assert rate_limit.bucket("/api/github/webhook", "POST") == "webhook"
    assert rate_limit.bucket("/api/repositories/x/analyze", "POST") == "analysis"
    calls = []
    class FakeRedis:
        def eval(self, script, count, key):
            calls.append((script, count, key))
            return 16
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: FakeRedis())
    assert not rate_limit.allow("synthetic-client", "login", distributed=True)
    assert calls[0][1] == 1 and "synthetic-client" not in calls[0][2]
    assert "EXPIRE" in calls[0][0]  # The increment and expiration share one server operation.


def test_workspace_burst_cannot_hide_auth_options_and_both_policies_remain_bounded(client):
    # The actual browser incident returned 429 for this cheap configuration read
    # after many authorized workspace reads shared one loopback/NAT address.
    from backend import main
    identity = "testclient"
    assert rate_limit.LIMITS["general"] == 240 and rate_limit.LIMITS["login"] == 15
    assert rate_limit.LIMITS["auth_metadata"] == rate_limit.LIMITS["general"]
    for _ in range(rate_limit.LIMITS["general"]):
        assert rate_limit.allow(identity,"general")
    assert client.get("/api/workspace").status_code == 429
    for _ in range(rate_limit.LIMITS["auth_metadata"]):
        assert client.get("/api/auth/options").status_code == 200
    assert client.get("/api/auth/options").status_code == 429
    assert client.get("/api/auth/oidc/options").status_code == 429
    assert rate_limit.bucket("/api/auth/register","POST") == "login"
    assert main.rate_windows[(identity,"general")]


def test_metrics_never_include_other_organization_jobs(client):
    registered = client.post("/api/auth/register", json={"email": "metrics@example.com", "password": "Strong-test-password-123!", "organization": "Metrics"})
    client.headers["x-csrf-token"] = registered.json()["csrf"]
    imported = client.post("/api/import", json={"name": "Metrics", "files": {"app.py": "import fastapi"}}).json()
    assert client.get("/api/analysis/metrics").json()["samples"] == 1
    second = client.post("/api/auth/register", json={"email": "metrics-other@example.com", "password": "Strong-test-password-123!", "organization": "Other metrics"})
    client.headers["x-csrf-token"] = second.json()["csrf"]
    assert client.get("/api/analysis/metrics").json()["samples"] == 0
    assert client.get("/api/analysis/metrics?repository_id=" + imported["repository_id"]).status_code == 404
