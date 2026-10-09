"""Listing must stay independent of repository-sized workspace aggregates."""
from sqlalchemy import event, select

from backend import main, workspace_read
from backend.db import Grant, Record, Repository, User
from tests.test_code_quality import import_repo


def test_repository_listing_is_paginated_authorized_and_aggregate_independent(signed, monkeypatch):
    with main.Session() as db:
        owner = db.scalar(select(User).where(User.email == "demo@projecttrace.local"))
        for i in range(32):
            rid = f"page-fixture-{i:02}"
            db.add(Repository(id=rid, organization_id="northstar", name=rid, system="fixture", component="fixture",
                owner="Fixture", provider="LOCAL"))
            db.flush()
            db.add(Grant(user_id=owner.id, repository_id=rid))
        db.commit()
    def unavailable(*args, **kwargs):
        raise AssertionError("Workspace aggregation must not run for a repository list.")
    monkeypatch.setattr(workspace_read, "summary_counts", unavailable)
    ids = []
    for offset in (0, 10, 20, 30):
        result = signed.get("/api/repositories", params={"search":"page-fixture", "offset":offset, "limit":10}).json()
        assert result["repository_page"]["total"] == 32
        assert "counts" not in result and result["claim"] == []
        ids += [repo["id"] for repo in result["repositories"]]
    assert len(ids) == len(set(ids)) == 32
    assert signed.get("/api/repositories?search=%25").json()["repository_page"]["total"] == 0
    assert signed.get("/api/repositories?repository_id=private").status_code == 404
    assert signed.get("/api/repositories?limit=101").status_code == 422
    assert signed.get("/api/repositories?offset=-1").status_code == 422
    signed.post("/api/auth/login", json={"email":"viewer@example.com","password":"Strong-test-password-123!"})
    assert [repo["id"] for repo in signed.get("/api/repositories").json()["repositories"]] == ["clean"]
    signed.post("/api/auth/login", json={"email":"outside@example.com","password":"Strong-test-password-123!"})
    assert signed.get("/api/repositories").json()["repository_page"]["total"] == 0


def test_catalogue_has_no_domain_record_queries(signed):
    statements = []
    with main.Session() as db:
        engine = db.bind
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = signed.get("/api/repositories?include_analysis=false").json()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert result["repositories"] and all(repo["snapshot"] is None for repo in result["repositories"])
    assert not any("FROM records" in sql for sql in statements)


def test_record_pages_pin_multiple_published_snapshots_during_new_publication(signed):
    first, base = import_repo(signed, {"old.py":"def old():\n    return 1\n"})
    imported = signed.post("/api/import", json={"name":"Second component", "files":{"other.py":"def other():\n    return 2\n"}}).json()
    second, other = imported["repository_id"], imported["snapshot_id"]

    head = signed.post(f"/api/repositories/{first}/analyze", json={"base_id":base,"files":{"new.py":"def new():\n    return 3\n"}}).json()["id"]
    result = signed.get("/api/workspace/records", params=[("view","Evidence"),("snapshot_ids",base),("snapshot_ids",other)]).json()
    assert result["snapshot_ids"] == {first:base, second:other}
    assert all(item["scope"]["snapshot_id"] in {base,other} for item in result["items"])
    assert signed.get("/api/workspace/records",params=[("view","Evidence"),("snapshot_ids",base),("snapshot_ids",head)]).status_code == 422
    assert signed.get("/api/workspace/records",params=[("view","Evidence"),("repository_id",second),("snapshot_ids",base)]).status_code == 404
    assert signed.get("/api/workspace/records",params={"view":"Evidence","snapshot_id":base,"snapshot_ids":other}).status_code == 422


def test_diagnostics_preserve_partial_claim_state_and_reject_foreign_scopes(signed):
    repo, sid = import_repo(signed, {"README.md":"# Sample\n", "a.py":"x = 1\n"})
    with main.Session() as db:
        snapshot = db.get(Record, sid)
        snapshot.data = {**snapshot.data, "status":"PARTIAL", "claim_extraction":{"state":"COMPLETED"},
            "engines":{"CLAIMS":{"state":"PARTIAL"}}, "warnings":[{"message":"Budget reached"} for _ in range(60)]}
        original = dict(snapshot.data)
        db.commit()
    response = signed.get(f"/api/repositories/{repo}/analysis?snapshot_id={sid}").json()
    assert response["effective_claim_extraction_state"] == "PARTIAL"
    assert response["warning_count"] == 60 and len(response["warnings"]) == 50 and not response["warnings_complete"]
    with main.Session() as db:
        assert db.get(Record, sid).data == original
    assert signed.get(f"/api/repositories/identity/analysis?snapshot_id={sid}").status_code == 404
    signed.post("/api/auth/login", json={"email":"outside@example.com","password":"Strong-test-password-123!"})
    assert signed.get(f"/api/repositories/{repo}/analysis?snapshot_id={sid}").status_code == 404


def test_inventory_claim_does_not_invent_source_lines_or_test_behavior(signed):
    from backend.claim_read import inventory_basis
    stored = {"text":"Repository contains test source files.", "line":1, "origin":"IMPLEMENTATION",
              "expected":"test files", "assertion_family":"source_testing", "status":"VERIFIED"}
    original = dict(stored)
    read = inventory_basis(stored)
    assert stored == original and read["line"] is None and read["recorded_line"] == 1
    assert read["evidence_basis"] == "PATH_INVENTORY" and "unobserved" in read["reason"]
    assert inventory_basis(read) == read
    repo, sid = import_repo(signed, {"tests/__init__.py":""})
    result = signed.get("/api/workspace/records", params={"view":"Claim Ledger","snapshot_id":sid}).json()
    claim = next(item for item in result["items"] if item.get("expected") == "test files")
    assert claim["line"] is None and claim["evidence_ids"] and "test path" in claim["text"]
    with main.Session() as db:
        assert db.get(Record, claim["id"]).data["evidence_basis"] == "PATH_INVENTORY"


def test_investigation_pins_snapshot_and_annotates_legacy_inventory_claims(signed):
    repo, base = import_repo(signed, {"tests/__init__.py":""})
    with main.Session() as db:
        snapshot = db.get(Record, base)
        original_claim = snapshot.data["claims"][0]
        legacy = {**original_claim, "text":"Repository contains test source files.", "line":1}
        legacy.pop("evidence_basis", None)
        snapshot.data = {**snapshot.data, "claims":[legacy]}
        stored = dict(snapshot.data)
        db.commit()
    head = signed.post(f"/api/repositories/{repo}/analyze", json={
        "base_id":base, "files":{"tests/new.py":"def test_new():\n    assert True\n"}}).json()["id"]
    payload = {"question":"test files", "repository_id":repo, "snapshot_ids":[base]}
    result = signed.post("/api/ask", json=payload)
    assert result.status_code == 200
    response = result.json()
    assert response["snapshot_ids"] == {repo:base} and response["scope"] == "SELECTED_PUBLISHED_SNAPSHOT"
    claim = response["claims"][0]
    assert claim["id"] == legacy["id"] and claim["line"] is None
    assert claim["evidence_basis"] == "PATH_INVENTORY" and "unobserved" in response["answer"]
    assert all(item["scope"]["snapshot_id"] == base for item in response["evidence"])
    with main.Session() as db:
        assert db.get(Record, base).data == stored
    assert signed.post("/api/ask", json={**payload, "snapshot_ids":[base,head]}).status_code == 422
    assert signed.post("/api/ask", json={**payload, "repository_id":"identity"}).status_code == 404
    assert signed.post("/api/ask", json={**payload, "snapshot_ids":["x"*81]}).status_code == 422
    assert signed.post("/api/ask", json={"question":"test files", "repository_id":repo}).json()["snapshot_ids"] == {repo:head}
    login = signed.post("/api/auth/login", json={"email":"outside@example.com","password":"Strong-test-password-123!"})
    assert login.status_code == 200
    signed.headers["x-csrf-token"] = login.json()["csrf"]
    assert signed.post("/api/ask", json=payload).status_code == 404


def test_investigation_filters_and_limits_graph_rows_before_loading(signed):
    statements = []
    with main.Session() as db:
        engine = db.bind
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = signed.post("/api/ask", json={"question":"How is authentication implemented?", "repository_id":"identity"})
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert result.status_code == 200
    response = result.json()
    ids = {claim["id"] for claim in response["claims"]}
    edges = response["retrieval"]["graph_neighborhood"]
    assert edges and len(edges) <= 50
    assert all(edge["source"] in ids or edge["target"] in ids for edge in edges)
    matching = [sql for sql in statements if '$."source"' in sql and '$."target"' in sql]
    assert matching and all("LIMIT" in sql and '$."snapshot_id"' in sql for sql in matching)
