from sqlalchemy import select

from backend import main
from backend.advisories import run_checks
from backend.db import Record, Repository, User
from backend.domain import add


def test_exact_advisory_coverage_cache_failure_and_tenant_isolation(client):
    registered = client.post("/api/auth/register", json={"email": "advisory@example.com", "password": "Strong-test-password-123!", "organization": "Advisory tests"})
    client.headers["x-csrf-token"] = registered.json()["csrf"]
    policy = client.get("/api/trust/policy").json()
    assert client.post("/api/trust/policy", json={**policy, "package_coordinate_advisories": True}).status_code == 200
    imported = client.post("/api/import", json={"name": "Packages", "files": {
        "package.json": '{"dependencies":{"alpha":"1.0.0","beta":"2.0.0","gamma":"3.0.0","range":"^1.0.0"}}'}}).json()
    calls = []
    def provider(ecosystem, name, version):
        calls.append(name)
        if name == "gamma":
            raise TimeoutError("Synthetic provider outage")
        return [{"id": "TEST-2026-1", "modified": "2026-10-01T00:00:00Z", "summary": "Synthetic test advisory", "database_specific": {"severity": "HIGH"}}] if name == "alpha" else []
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == "advisory@example.com"))
        repo, snapshot = db.get(Repository, imported["repository_id"]), db.get(Record, imported["snapshot_id"])
        for _ in range(2):
            job = add(db, user.organization_id, repo.id, "job", {"state": "QUEUED"})
            run_checks(db, user, repo, snapshot, job, provider)
        assert calls.count("alpha") == 1 and calls.count("beta") == 1
        assert job.data["state"] == "PARTIAL" and job.data["engines"]["OSV"]["cache_hits"] == 2
        deps = {d["name"]: d for d in snapshot.data["dependencies"]}
        assert deps["alpha"]["vulnerability_status"] == "VULNERABLE"
        assert deps["beta"]["vulnerability_status"] == "CHECKED_NO_KNOWN_ADVISORY"
        assert deps["gamma"]["vulnerability_status"] == "CHECK_FAILED"
        assert deps["range"]["vulnerability_status"] == "UNKNOWN_VERSION"
        assert len([f for f in snapshot.data["findings"] if f.get("provider") == "OSV"]) == 1
        cache_ids = list(db.scalars(select(Record.id).where(Record.kind == "advisory_cache")))
    other = client.post("/api/auth/register", json={"email": "advisory-other@example.com", "password": "Strong-test-password-123!", "organization": "Other advisories"})
    client.headers["x-csrf-token"] = other.json()["csrf"]
    assert client.post(f"/api/snapshots/{imported['snapshot_id']}/advisories").status_code == 503
    for cache_id in cache_ids:
        assert client.get("/api/record/" + cache_id).status_code == 404
