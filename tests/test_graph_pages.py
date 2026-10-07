from sqlalchemy import select

from backend import main
from backend.db import Record
from tests.test_code_quality import import_repo


def test_graph_pages_preserve_scope_and_lazy_evidence(signed):
    repo, snapshot = import_repo(signed, {"app.py": "def run(value):\n    return value\n"})
    url = f"/api/graph/nodes?repository_id={repo}&snapshot_id={snapshot}"
    first = signed.get(url + "&limit=1").json()
    second = signed.get(url + "&limit=1&offset=1").json()
    assert first["total"] > 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    component = signed.get(url + "&node_class=COMPONENT").json()["items"][0]
    links = signed.get("/api/graph/neighborhood?node_id=" + component["id"] + "&limit=1").json()
    assert links["depth"] == 1 and links["total"] > 0 and len(links["edges"]) == 1
    assert all("source" not in item and "source_blob_digest" not in item for item in links["nodes"])
    evidence = signed.get(url + "&search=app.py").json()["items"]
    assert evidence and all("source" not in item for item in evidence)
    assert signed.get(url + "&search=%25").json()["total"] == 0
    assert signed.get(url + "&limit=101").status_code == 422
    with main.Session() as db:
        source_id = db.scalar(select(Record.id).where(Record.repository_id == repo, Record.kind == "evidence"))
    assert signed.get("/api/record/" + source_id).json()["source"].startswith("def run")
    workspace = signed.get("/api/workspace?repository_id=" + repo).json()
    assert "analysis_cache" not in workspace["repositories"][0]["snapshot"]
    assert "quality_metrics" not in workspace["repositories"][0]["snapshot"]
    assert all("source" not in item for item in workspace["evidence"])
    signed.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"})
    assert signed.get(url).status_code == 404
    assert signed.get("/api/graph/neighborhood?node_id=" + component["id"]).status_code == 404


def test_graph_historical_snapshot_and_authorized_cross_repository_refusal(signed):
    repo, base = import_repo(signed, {"old.py": "pass\n"})
    updated = signed.post(
        f"/api/repositories/{repo}/analyze", json={"base_id": base, "files": {"new.py": "pass\n"}}
    ).json()["id"]
    url = f"/api/graph/nodes?repository_id={repo}"
    assert signed.get(url).json()["snapshot_id"] == updated
    assert signed.get(url + "&snapshot_id=" + base).json()["snapshot_id"] == base
    assert signed.get(url + "&snapshot_id=" + base + "&search=new.py").json()["total"] == 0
    assert signed.get("/api/graph/nodes?repository_id=private&snapshot_id=" + base).status_code == 404
