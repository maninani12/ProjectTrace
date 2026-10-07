from backend import main
from backend.db import Record
from tests.test_code_quality import import_repo
from tests.test_enterprise_trust import owner


def test_captured_formats_versions_and_snapshot_scope(signed):
    repo, snapshot = import_repo(signed, {
        "compose.yaml": "services:\n  web: {image: fixture:v1, ports: ['8080:80']}\n",
        "app.go": "package main", "broken.py": "def broken(:",
    })
    url = f"/api/trust/coverage?repository_id={repo}&snapshot_id={snapshot}"
    data = signed.get(url).json()
    assert data["quality_gate_version"] and data["ruleset_version"]
    formats = {r["format"]: r for r in data["infrastructure"]}
    assert formats["COMPOSE"]["files"] == 1 and formats["COMPOSE"]["resources"] >= 1
    assert formats["TERRAFORM"]["files"] == 0
    assert data["summary"]["states"]["PARSE_FAILED"] == 1
    choices = signed.get(f"/api/trust/snapshots?repository_id={repo}&limit=1").json()
    assert choices["items"][0]["id"] == snapshot and "files" not in str(choices)
    assert signed.get("/api/trust/snapshots?repository_id=private").status_code == 404
    assert signed.get("/api/trust/snapshots?limit=101").status_code == 422


def test_exception_inventory_scope_filter_and_lifecycle(client):
    client = owner(client)
    repo, snapshot = import_repo(client, {"compose.yaml": "services:\n  app: {privileged: true}\n"})
    issue = next(r for r in client.get("/api/workspace").json()["finding"] if r["rule"] == "PT-IAC-001")
    assert client.post(f"/api/record/{issue['id']}/review", json={
        "action": "CREATE_EXCEPTION", "reason": "Controlled temporary test exception", "expires_days": 7,
        "expected_version": issue["version"],
    }).status_code == 200
    url = f"/api/trust/exceptions?repository_id={repo}"
    active = client.get(url + "&state=ACTIVE").json()
    assert active["total"] == 1 and active["items"][0]["state"] == "ACTIVE"
    exception = active["items"][0]
    assert client.get(url + "&state=EXPIRED").json()["total"] == 0
    assert client.post(f"/api/trust/exceptions/{exception['id']}", json={
        "action": "REVOKE", "expected_version": exception["version"], "reason": "Revoking controlled test exception",
    }).status_code == 200
    assert client.get(url + "&state=REVOKED").json()["total"] == 1
    assert client.get(url + "&state=ACTIVE").json()["total"] == 0
    assert client.get(url + "&offset=-1").status_code == 422
    identity = client.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"}).json()
    client.headers["x-csrf-token"] = identity["csrf"]
    assert client.get(url).status_code == 404
    assert not client.get("/api/trust/exceptions").json()["items"]
    with main.Session() as db:
        assert db.get(Record, snapshot).data["analysis_coverage"]


def test_infrastructure_policy_is_versioned_and_rejects_unknown_rules(client):
    client = owner(client)
    body = {"version": 0, "infrastructure": {"environment": "PRODUCTION", "require_healthcheck": True}}
    assert client.post("/api/native/profile", json={**body, "version": 6}).status_code == 409
    assert client.post("/api/native/profile", json={**body, "infrastructure": {"rules": {"PT-IAC-999": {"enabled": False}}}}).status_code == 422
    first = client.post("/api/native/profile", json=body)
    assert first.status_code == 200 and first.json()["infrastructure"]["require_healthcheck"]
    assert client.post("/api/native/profile", json=body).status_code == 409
    with main.Session() as db:
        assert any(r.data["configuration"].get("environment") == "PRODUCTION" for r in db.query(Record).filter(Record.kind == "infrastructure_profile_version"))
