"""Advisory enrichment remains part of the scoped evidence and policy graph."""

import json

from sqlalchemy import select

from backend import main
from backend.advisories import run_checks
from backend.db import Record, Repository, User
from backend.domain import add


def account(client, files):
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "advisory-graph@example.com",
            "password": "Strong-test-password-123!",
            "organization": "Advisory graph",
        },
    )
    client.headers["x-csrf-token"] = registered.json()["csrf"]
    policy = client.get("/api/trust/policy").json()
    assert client.post("/api/trust/policy", json={**policy, "package_coordinate_advisories": True}).status_code == 200
    response = client.post("/api/import", json={"name": "Packages", "files": files})
    assert response.status_code == 200, response.text
    return response.json()


def execute(imported, provider):
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == "advisory-graph@example.com"))
        repo = db.get(Repository, imported["repository_id"])
        snapshot = db.get(Record, imported["snapshot_id"])
        job = add(db, user.organization_id, repo.id, "job", {"state": "QUEUED"})
        run_checks(db, user, repo, snapshot, job, provider)
        return snapshot.id


def test_async_advisory_merges_manifest_evidence_and_updates_reviewed_policy_graph(client):
    files = {
        "package.json": '{"dependencies":{"alpha":"1.0.0"}}',
        "service/package.json": '{"dependencies":{"alpha":"1.0.0"}}',
    }
    imported = account(client, files)
    calls = []

    def provider(ecosystem, name, version):
        calls.append((ecosystem, name, version))
        return [
            {
                "id": "TEST-2026-ALPHA",
                "modified": "2026-10-01T00:00:00Z",
                "summary": 'Synthetic advisory api_key="SyntheticProviderSecret123456"',
                "database_specific": {"severity": "HIGH"},
            }
        ]

    execute(imported, provider)
    current = client.get("/api/workspace").json()
    assert len(calls) == 1
    finding = next(f for f in current["finding"] if f["category"] == "SCA")
    assert len(finding["evidence_ids"]) == 2 and len(finding["dependency_ids"]) == 2
    assert len(finding["provider_observations"]) == 2
    assert "SyntheticProviderSecret" not in json.dumps(current)
    evidence = {e["id"]: e for e in current["evidence"]}
    assert {evidence[eid]["path"] for eid in finding["evidence_ids"]} == set(files)
    assert {
        e["target"] for e in current["edge"] if e["source"] == finding["id"] and e["relationship"] == "AFFECTS"
    } == set(finding["dependency_ids"])
    policy = next(n for n in current["graph_node"] if n["class"] == "POLICY" and n["result"] == "REVIEW_REQUIRED")
    assert any(e["source"] == policy["id"] and e["target"] == finding["id"] for e in current["edge"])
    accepted = client.post(
        f"/api/record/{finding['id']}/review",
        json={
            "action": "CREATE_EXCEPTION",
            "reason": "Bounded synthetic provider test exception.",
            "expected_version": finding["version"],
            "expires_days": 1,
        },
    )
    assert accepted.status_code == 200
    execute(imported, provider)
    refreshed = client.get("/api/workspace").json()
    assert len(calls) == 1 and len(refreshed["finding"]) == 1
    snapshot = refreshed["repositories"][0]["snapshot"]
    assert snapshot["gate"]["overall"] == "PASS"
    assert all(n["result"] == "PASS" for n in refreshed["graph_node"] if n["class"] == "POLICY")
    assert finding["identity_id"] == refreshed["finding"][0]["identity_id"]


def test_cached_native_sca_and_live_advisory_share_one_issue_per_package(client):
    manifest = '{"dependencies":{"lodash":"4.17.20"}}'
    imported = account(client, {"package.json": manifest, "service/package.json": manifest})
    initial = client.get("/api/workspace").json()
    issues = [f for f in initial["finding"] if f["category"] == "SCA"]
    assert issues and len(issues) == len({f["advisory"]["id"] for f in issues})
    assert all(len(f["evidence_ids"]) == 2 for f in issues)

    def provider(*_):
        return [
            {
                "id": f["advisory"]["id"],
                "summary": f["advisory"].get("summary", ""),
                "modified": "2026-10-04T00:00:00Z",
                "database_specific": {"severity": "HIGH"},
            }
            for f in issues
        ]

    execute(imported, provider)
    current = client.get("/api/workspace").json()
    assert {f["id"] for f in current["finding"]} == {f["id"] for f in issues}
    assert all(len(f["dependency_ids"]) == 2 and len(f["evidence_ids"]) == 2 for f in current["finding"])
    node_ids = {n["id"] for kind in ["claim", "finding", "evidence", "dependency", "graph_node"] for n in current[kind]}
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in current["edge"])


def test_advisory_withdrawal_updates_gate_and_reappearance_requires_review(client):
    imported = account(client, {"package.json": '{"dependencies":{"alpha":"1.0.0"}}'})
    advisory = {"id": "TEST-2026-ALPHA", "summary": "Synthetic fixture", "database_specific": {"severity": "HIGH"}}
    execute(imported, lambda *_: [advisory])
    original = client.get("/api/workspace").json()["finding"][0]
    for returned in [[], [advisory]]:
        with main.Session() as db:
            cache = db.scalar(select(Record).where(Record.kind == "advisory_cache", Record.repository_id.is_(None)))
            cache.data = {**cache.data, "checked_at": "2020-01-01T00:00:00+00:00"}
            db.commit()
        execute(imported, lambda *_: returned)
        current = client.get("/api/workspace").json()
        issue = current["finding"][0]
        assert issue["id"] == original["id"]
        assert current["repositories"][0]["snapshot"]["gate"]["overall"] == ("REVIEW_REQUIRED" if returned else "PASS")
    assert issue["review_status"] == "OPEN" and issue["review_identity_id"] != original["review_identity_id"]
