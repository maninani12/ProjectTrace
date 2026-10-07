"""Real workspace graph lineage and bounded, evidence-backed change impact."""

from datetime import datetime, timedelta, timezone

import pytest

from backend import main
from backend.db import Record
from backend.domain import policy_gate, scoped_snapshot_records


def workspace(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "graph@example.com", "password": "Strong-test-password-123!", "organization": "Graph fixture"},
    )
    assert response.status_code == 200, response.text
    client.headers["x-csrf-token"] = response.json()["csrf"]
    return client


def import_files(client, files):
    response = client.post("/api/import", json={"name": "Graph fixture", "files": files})
    assert response.status_code == 200, response.text
    result = response.json()
    return result, client.get("/api/record/" + result["snapshot_id"]).json()


def next_snapshot(client, imported, base, files):
    response = client.post(
        f"/api/repositories/{imported['repository_id']}/analyze", json={"files": files, "base_id": base["id"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def doc_claim(snapshot, expected):
    return next(c for c in snapshot["claims"] if c["origin"] == "DOCUMENTATION" and c["expected"] == expected)


def test_removed_support_reaches_unchanged_documentation_and_tracks_lineage(client):
    client = workspace(client)
    base_files = {
        "README.md": "Authentication uses JWT. Backend uses FastAPI.",
        "auth.py": "import jwt\njwt.decode(token, key)\n",
        "api.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    }
    imported, base = import_files(client, base_files)
    assert base["impact"]["initial_baseline"] and not base["impact"]["affected_claims"]
    assert not base["drifts"]
    auth_base = doc_claim(base, "jwt")
    assert auth_base["status"] == "VERIFIED"
    head_files = {p: t for p, t in base_files.items() if p != "auth.py"}
    head = next_snapshot(client, imported, base, head_files)
    auth_head = doc_claim(head, "jwt")
    assert auth_head["status"] == "UNVERIFIED"
    assert auth_head["identity_id"] == auth_base["identity_id"]
    assert auth_head["id"] != auth_base["id"]
    assert auth_head["previous_version_id"] == auth_base["id"]
    assert auth_head["claim_version"] == auth_base["claim_version"] + 1
    assert [h["status"] for h in auth_head["history"]] == ["VERIFIED", "STALE", "UNVERIFIED"]
    impact = head["impact"]
    assert impact["changed_files"] == ["auth.py"]
    assert auth_head["id"] in impact["affected_claims"]
    assert impact["affected_documentation"] == ["README.md"]
    assert doc_claim(head, "fastapi")["id"] not in impact["affected_claims"]
    assert impact["verification"]["reused"] == 1 and impact["verification"]["reverified"] == 1
    assert any(n["class"] == "FILE_EVIDENCE" and n["snapshot_id"] == base["id"] for n in impact["affected_nodes"])
    edges = {e["id"] for e in client.get("/api/records/edge?limit=200").json()}
    assert all(set(n["via"]) <= edges for n in impact["affected_nodes"])


@pytest.mark.parametrize("changed_model", ["version", "parser"])
def test_analyzer_rule_upgrade_is_not_software_drift(client, changed_model):
    client = workspace(client)
    files = {"README.md": "Backend uses FastAPI.", "app.py": "from fastapi import FastAPI\napp=FastAPI()\n"}
    imported, base = import_files(client, files)
    with main.Session() as db:
        stored = db.get(Record, base["id"])
        claims = [{**c, "status": "UNVERIFIED"} for c in stored.data["claims"]]
        model = (
            {"analyzer_version": "legacy-test"} if changed_model == "version" else {"parser_signature": "legacy-parser"}
        )
        stored.data = {**stored.data, **model, "claims": claims}
        db.commit()
    head = next_snapshot(client, imported, base, files)
    assert head["changed_files"] == [] and head["drifts"] == []
    assert head["comparison"]["analysis_model_changed"]
    changes = client.get("/api/records/analysis_change").json()
    assert len(changes) == 1 and changes[0]["snapshot_id"] == head["id"]
    assert any(a["action"] == "ANALYSIS_RULES_CHANGED" for a in client.get("/api/audit").json())


def test_policy_and_api_impact_are_derived_from_real_graph_edges(client):
    client = workspace(client)
    files = {
        "README.md": "Authentication uses JWT. The API exposes /health.",
        "app.py": "import jwt\nfrom fastapi import FastAPI\napp=FastAPI()\njwt.decode(token, key)\n@app.get('/health')\ndef health(): return True\n",
    }
    imported, base = import_files(client, files)
    head_files = {
        **files,
        "app.py": "from fastapi import FastAPI\nfrom starlette.middleware.sessions import SessionMiddleware\napp=FastAPI()\napp.add_middleware(SessionMiddleware, secret_key='fixture_not_live_123456789')\n@app.get('/health')\ndef health(): return True\n",
    }
    head = next_snapshot(client, imported, base, head_files)
    claim = doc_claim(head, "jwt")
    assert claim["status"] == "CONTRADICTED"
    assert [h["status"] for h in claim["history"]] == ["VERIFIED", "STALE", "CONTRADICTED"]
    impact = head["impact"]
    assert impact["affected_findings"] and impact["affected_policies"]
    assert impact["affected_api"] and impact["affected_architecture"]
    current = client.get("/api/workspace").json()
    nodes = {n["id"]: n for n in current["graph_node"]}
    assert all(nodes[identifier]["class"] == "POLICY" for identifier in impact["affected_policies"])
    assert all(nodes[identifier]["class"] == "API_ENDPOINT" for identifier in impact["affected_api"])
    assert all(n.get("provenance") == "METADATA" for n in nodes.values() if n["class"] in {"SYSTEM", "COMPONENT"})
    all_ids = {n["id"] for kind in ["claim", "finding", "evidence", "dependency", "graph_node"] for n in current[kind]}
    assert all(e["source"] in all_ids and e["target"] in all_ids for e in current["edge"])
    assert all(f["risk_factors"]["runtime_reachability"] == "UNOBSERVED" for f in current["finding"])
    # A historical snapshot keeps its own original claim verdict and evidence.
    assert doc_claim(client.get("/api/record/" + base["id"]).json(), "jwt")["status"] == "VERIFIED"


def test_equivalent_declaration_and_review_continuity_are_versioned_safely(client):
    client = workspace(client)
    files = {"README.md": "Backend uses FastAPI.", "app.py": "from fastapi import FastAPI\napp=FastAPI()\n"}
    imported, base = import_files(client, files)
    before = doc_claim(base, "fastapi")
    reviewed = client.post(
        f"/api/record/{before['id']}/review",
        json={"action": "CONFIRM", "reason": "Reviewed static source evidence.", "expected_version": 1},
    )
    assert reviewed.status_code == 200
    unchanged = next_snapshot(client, imported, base, {**files, "notes.txt": "Unrelated change."})
    after = doc_claim(unchanged, "fastapi")
    assert after["identity_id"] == before["identity_id"] and after["review_status"] == "CONFIRMED"
    assert after["review_reason"] == "Reviewed static source evidence."
    assert unchanged["impact"]["verification"]["reused"] == 1
    changed = next_snapshot(
        client,
        imported,
        unchanged,
        {**files, "README.md": "\nThe application is built with FastAPI.", "notes.txt": "Unrelated change."},
    )
    final = doc_claim(changed, "fastapi")
    assert final["identity_id"] == before["identity_id"]
    assert final["claim_version"] == 3 and final["review_status"] == "OPEN"
    assert final["review_identity_id"] != after["review_identity_id"]
    assert not any(d["type"] == "CLAIM_REMOVED" and d["path"] == "README.md" for d in changed["drifts"])


def test_graph_snapshot_query_and_impact_never_cross_tenant_or_repository(client):
    client = workspace(client)
    imported, base = import_files(client, {"README.md": "Backend uses FastAPI.", "app.py": "import fastapi"})
    with main.Session() as db:
        snapshot = db.get(Record, base["id"])
        assert scoped_snapshot_records(db, "northstar", imported["repository_id"], snapshot.id) == []
        assert scoped_snapshot_records(db, snapshot.organization_id, "clean", snapshot.id) == []
        assert scoped_snapshot_records(db, snapshot.organization_id, imported["repository_id"], snapshot.id)
    response = client.post(
        "/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"}
    )
    client.headers["x-csrf-token"] = response.json()["csrf"]
    assert client.get("/api/record/" + base["id"]).status_code == 404
    assert client.get("/api/workspace?repository_id=" + imported["repository_id"]).status_code == 404
    assert client.get("/api/records/graph_node").json() == []


def test_finding_exception_follows_only_unchanged_evidence(client):
    client = workspace(client)
    files = {"compose.yaml": "services:\n  fixture:\n    privileged: true\n"}
    imported, base = import_files(client, files)
    finding = next(f for f in base["findings"] if f["category"] == "IAC")
    current = client.get("/api/record/" + finding["id"]).json()
    accepted = client.post(
        f"/api/record/{finding['id']}/review",
        json={
            "action": "CREATE_EXCEPTION",
            "reason": "Bounded fixture exception.",
            "expected_version": current["version"],
            "expires_days": 1,
        },
    )
    assert accepted.status_code == 200
    assert client.get("/api/gate/" + base["id"]).json()["overall"] == "PASS"
    unchanged = next_snapshot(client, imported, base, {**files, "notes.txt": "Unrelated edit."})
    same = next(f for f in unchanged["findings"] if f["category"] == "IAC")
    assert same["identity_id"] == finding["identity_id"]
    assert same["first_seen"] == finding["first_seen"]
    assert client.get("/api/gate/" + unchanged["id"]).json()["overall"] == "PASS"
    changed = next_snapshot(
        client, imported, unchanged, {**files, "compose.yaml": files["compose.yaml"] + '    ports: ["8080:80"]\n'}
    )
    fresh = next(f for f in changed["findings"] if f["category"] == "IAC")
    assert fresh["identity_id"] == finding["identity_id"]
    assert fresh["review_identity_id"] != same["review_identity_id"]
    assert client.get("/api/gate/" + changed["id"]).json()["overall"] == "REVIEW_REQUIRED"


def test_exception_identity_expiry_and_changed_evidence_fail_closed():
    finding = {
        "id": "new-version",
        "review_identity_id": "same-reviewed-evidence",
        "severity": "CRITICAL",
        "confidence": "HIGH",
        "blocking_eligible": True,  # Explicit qualified synthetic gate condition.
        "title": "Fixture",
    }
    expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    exception = {"target": "old-version", "identity_id": "same-reviewed-evidence", "expires_at": expiry}
    assert policy_gate([], [finding], [exception])["overall"] == "PASS"
    changed = {**finding, "review_identity_id": "changed-evidence"}
    assert policy_gate([], [changed], [exception])["overall"] == "FAIL"
    for invalid in ["not-a-date", "2099-01-01T00:00:00", None]:
        assert policy_gate([], [finding], [{**exception, "expires_at": invalid}])["overall"] == "FAIL"
    assert policy_gate([], [finding], [{"target": None, "expires_at": expiry}])["overall"] == "FAIL"
