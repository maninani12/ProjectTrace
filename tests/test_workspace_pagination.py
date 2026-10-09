"""A large graph must never displace claims, findings or authorized summaries."""
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, insert, select

from backend import main
from backend.db import Record, SnapshotView
from backend.workspace_read import project_snapshot
from tests.test_code_quality import import_repo


def current_scope(signed):
    data = signed.get("/api/workspace").json()
    repo = next(repo for repo in data["repositories"] if repo["id"] == "identity")
    return repo, data


def test_historical_pages_are_complete_and_require_snapshot_and_repository_grants(signed):
    repo, base = import_repo(signed, {"README.md": "# Component\nThis service uses session authentication.\n", "old.py": "def old(value):\n    return value\n"})
    head = signed.post(f"/api/repositories/{repo}/analyze", json={"base_id":base,"files":{"new.py":"def changed(value):\n    return value\n"}}).json()["id"]
    page = signed.get("/api/workspace/records", params={"view":"Evidence","snapshot_id":base,"repository_id":repo,"limit":1}).json()
    assert page["scope"] == "SELECTED_PUBLISHED_SNAPSHOT" and page["snapshot_ids"] == {repo:base}
    assert all(item["scope"]["snapshot_id"] == base for item in page["items"])
    assert signed.get("/api/workspace/records", params={"view":"Evidence","snapshot_id":head,"repository_id":"identity"}).status_code == 404
    signed.post("/api/auth/login", json={"email":"outside@example.com","password":"Strong-test-password-123!"})
    assert signed.get("/api/workspace/records", params={"view":"Evidence","snapshot_id":base}).status_code == 404


def test_large_graph_cannot_truncate_summary_or_paginated_claims(signed):
    repo, before = current_scope(signed)
    sid = repo["snapshot"]["id"]
    with main.Session() as db:
        db.execute(insert(Record), [
            {"id": f"large-graph-{i:05}", "organization_id": "northstar", "repository_id": "identity",
             "kind": "graph_node", "natural_key": f"large-graph-{i}", "created_at": "2099-01-01", "version": 1,
             "data": {"scope": {"repository_id": "identity", "snapshot_id": sid}, "class": "FUNCTION", "title": "Inert graph fixture"}}
            for i in range(6000)
        ])
        expected = db.scalar(select(func.count()).select_from(Record).where(Record.kind == "claim", Record.repository_id == "identity", Record.data["scope"]["snapshot_id"].as_string() == sid))
        db.commit()
    response = signed.get("/api/workspace?summary=1&repository_id=identity")
    assert response.status_code == 200
    data = response.json()
    assert not data["analysis"]["truncated"]
    assert data["counts"]["complete"] and data["counts"]["totals"]["claim"] == expected > 0
    assert data["graph_node"] == [] and len(data["claim"]) <= 5
    assert len(response.content) < 100_000
    ids = []
    for offset in range(0, expected, 2):
        page = signed.get(f"/api/workspace/records?view=Claim%20Ledger&repository_id=identity&offset={offset}&limit=2").json()
        assert page["total"] == expected and page["snapshot_ids"] == {"identity": sid}
        ids.extend(item["id"] for item in page["items"])
    assert len(ids) == len(set(ids)) == expected


def test_summary_is_partial_when_published_snapshot_is_partial(signed):
    repo, _ = current_scope(signed)
    with main.Session() as db:
        row = db.get(Record, repo["snapshot"]["id"])
        row.data = {**row.data, "status": "PARTIAL"}
        project_snapshot(db, row)
        db.commit()
    data = signed.get("/api/workspace?summary=1&repository_id=identity").json()
    assert data["analysis"]["state"] == "PARTIAL" and data["counts"]["totals"]["claim"] > 0


def test_projection_rejects_stale_versions_and_is_transactional(signed):
    repo, _ = current_scope(signed)
    with main.Session() as db:
        snapshot = db.get(Record, repo["snapshot"]["id"])
        projection = db.get(SnapshotView, snapshot.id)
        assert projection.source_version == snapshot.version
        projection.data = {**projection.data, "status": "INCORRECT_STALE_STATE"}
        projection.source_version -= 1
        db.commit()
    data = signed.get("/api/workspace?summary=1&repository_id=identity").json()
    assert data["repositories"][0]["snapshot"]["status"] != "INCORRECT_STALE_STATE"
    with main.Session() as db:
        snapshot = db.get(Record, repo["snapshot"]["id"])
        original = snapshot.data["status"]
        snapshot.data = {**snapshot.data, "status": "PARTIAL"}
        project_snapshot(db, snapshot)
        db.rollback()
    assert signed.get("/api/workspace?summary=1&repository_id=identity").json()["repositories"][0]["snapshot"]["status"] == original


def test_paging_search_status_grants_and_bounds(signed):
    signed.post("/api/auth/login", json={"email": "viewer@example.com", "password": "Strong-test-password-123!"})
    assert signed.get("/api/workspace/records?view=Claim%20Ledger&repository_id=identity").status_code == 404
    data = signed.get("/api/workspace?summary=1").json()
    assert [r["id"] for r in data["repositories"]] == ["clean"]
    assert signed.get("/api/workspace/records?view=Evidence&limit=201").status_code == 422
    assert signed.get("/api/workspace/records?view=Unknown").status_code == 422
    assert signed.get("/api/workspace/records?view=Evidence&offset=-1").status_code == 422
    assert signed.get("/api/workspace/records?view=Claim%20Ledger&search=%25").json()["total"] == 0
    signed.post("/api/auth/demo", json={})
    rows = signed.get("/api/workspace/records?view=Claim%20Ledger&state=CONTRADICTED").json()
    assert rows["total"] > 0 and all(row["status"] == "CONTRADICTED" for row in rows["items"])
    evidence = signed.get("/api/workspace/records?view=Evidence").json()
    assert all("source" not in item and "source_blob_digest" not in item for item in evidence["items"])


def test_concurrent_scoped_summary_reads_are_consistent(signed):
    def read(_):
        response = signed.get("/api/workspace?summary=1&repository_id=identity")
        assert response.status_code == 200
        return response.json()["counts"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, range(8)))
    assert all(result == results[0] for result in results)
