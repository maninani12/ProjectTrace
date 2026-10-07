from sqlalchemy import select

from backend import main
from backend.db import Audit, Record
from tests.test_code_quality import import_repo


def advance(client, repository, base, files):
    response = client.post(f"/api/repositories/{repository}/analyze", json={"base_id": base, "files": files})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_correlated_changes_use_explicit_baseline_graph_and_authorized_history(signed):
    files = {"app.py": "def work(value):\n    return value\n", "requirements.txt": "requests==2.30.0\n",
             "compose.yaml": "services:\n  app: {image: fixture:v1}\n"}
    repo, base = import_repo(signed, files)
    assert signed.get(f"/api/engineering-changes?repository_id={repo}").json()["total"] == 0
    head = advance(signed, repo, base, {**files, "app.py": "def work(value):\n    if value:\n        return eval(value)\n    return None\n",
        "requirements.txt": "requests==2.31.0\n", "compose.yaml": "services:\n  app: {image: fixture:v1, privileged: true}\n"})
    listed = signed.get(f"/api/engineering-changes?repository_id={repo}&limit=1").json()
    assert listed["total"] == 1
    assert "changes" not in listed["items"][0] and "files" not in listed["items"][0]
    identifier = listed["items"][0]["id"]
    data = signed.get("/api/engineering-changes/" + identifier).json()
    assert data["base_snapshot_id"] == base and data["head_snapshot_id"] == head
    assert {"IMPLEMENTATION_CHANGE", "QUALITY_REGRESSION", "SECURITY_CHANGE", "DEPENDENCY_CHANGE", "INFRASTRUCTURE_CHANGE"} <= data["counts"].keys()
    assert data["priority_factors"] and not data["analysis_model_changed"]
    assert data["actor_basis"] == "ANALYSIS_INITIATOR_NOT_COMMIT_AUTHOR" and data["runtime_evidence"] == "UNOBSERVED"
    assert data["linked_record_ids"]
    with main.Session() as db:
        assert all(db.get(Record, rid).repository_id == repo for rid in data["linked_record_ids"])
        assert db.scalar(select(Audit).where(Audit.target == identifier, Audit.action == "ENGINEERING_CHANGE_CAPTURED"))
    assert signed.get("/api/engineering-changes?repository_id=private").status_code == 404
    assert signed.get("/api/engineering-changes?limit=101").status_code == 422
    assert signed.get("/api/engineering-changes?days=0").status_code == 422
    signed.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"})
    assert signed.get("/api/engineering-changes/" + identifier).status_code == 404
    assert signed.get("/api/engineering-changes").json()["total"] == 0


def test_claim_transitions_and_model_reevaluation_have_distinct_priority(signed):
    files = {"README.md": "# Storage\nProduction storage is private.\n", "main.tf": 'resource "aws_s3_bucket" "production" { acl = "private" }'}
    repo, base = import_repo(signed, files)
    changed = {**files, "main.tf": 'resource "aws_s3_bucket" "production" { acl = "public-read" }'}
    head = advance(signed, repo, base, changed)
    first = signed.get(f"/api/engineering-changes?repository_id={repo}").json()["items"][0]
    data = signed.get("/api/engineering-changes/" + first["id"]).json()
    assert any(c["category"] == "CLAIM_STATUS_CHANGE" and c["after"] == "CONTRADICTED" for c in data["changes"])
    assert any(f["weight"] == 40 for f in data["priority_factors"])
    with main.Session() as db:
        row = db.get(Record, head)
        row.data = {**row.data, "parser_signature": "fixture-prior-analyzer"}
        db.commit()
    reevaluated = advance(signed, repo, head, changed)
    listing = signed.get(f"/api/engineering-changes?repository_id={repo}").json()
    item = next(r for r in listing["items"] if r["head_snapshot_id"] == reevaluated)
    assert item["analysis_model_changed"] and item["priority"] == 1
    observed = signed.get("/api/engineering-changes/" + item["id"]).json()
    assert observed["counts"]["ANALYZER_CHANGE"] == 1 and not observed["files"]
