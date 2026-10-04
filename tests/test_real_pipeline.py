import io
import json
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import Base, make_engine


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for path, content in files.items():
            z.writestr(path, content)
    return output.getvalue()


def fixture_files():
    return {
        "README.md": "Authentication uses JWT. Database uses PostgreSQL.",
        "app.py": "from fastapi import FastAPI\nfrom starlette.middleware.sessions import SessionMiddleware\napp=FastAPI()\napp.add_middleware(SessionMiddleware, secret_key='fake_fixture_secret_123456789')\nDATABASE_URL='postgresql://user:example@localhost/demo'\n@app.get('/health')\ndef health(): return True\ndef unsafe(db, x): return db.execute(f'SELECT * FROM users WHERE id={x}')\n"
        + "def complex(x):\n"
        + "".join(f"    if x == {n}: x += 1\n" for n in range(12)),
        "requirements.txt": "fastapi>=0.115,<1\npsycopg==3.2.0",
        "package-lock.json": json.dumps(
            {"packages": {"": {"dependencies": {"lodash": "4.17.20"}}, "node_modules/lodash": {"version": "4.17.20"}}}
        ),
        "openapi.json": json.dumps({"openapi": "3.0.0", "paths": {"/missing": {"get": {}}}}),
        "compose.yaml": "services:\n  app:\n    privileged: true\n",
    }


def test_fresh_database_real_end_to_end(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path}/fresh.db")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "Session", sessionmaker(engine, expire_on_commit=False))
    main.rate_windows.clear()
    with TestClient(main.app) as client:
        client.headers["origin"] = "http://127.0.0.1:5181"
        created = client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "Strong-test-password-123!",
                "organization": "Real fixture",
            },
        )
        assert created.status_code == 200
        client.headers["x-csrf-token"] = created.json()["csrf"]
        assert client.get("/api/workspace").json()["analysis"]["state"] == "NO_REPOSITORY"
        client.post("/api/auth/logout", json={})
        login = client.post(
            "/api/auth/login", json={"email": "owner@example.com", "password": "Strong-test-password-123!"}
        )
        client.headers["x-csrf-token"] = login.json()["csrf"]
        imported = client.post("/api/archive/import?name=fixture", content=archive(fixture_files()))
        assert imported.status_code == 200, imported.text
        ids = imported.json()
        data = client.get("/api/workspace").json()
        assert not data["demo"] and len(data["repositories"]) == 1
        assert data["job"][0]["state"] == "COMPLETED"
        assert data["job"][0]["finished_at"]
        assert next(c for c in data["claim"] if c["text"] == "Authentication uses JWT.")["status"] == "CONTRADICTED"
        assert next(c for c in data["claim"] if c["text"] == "Database uses PostgreSQL.")["status"] == "VERIFIED"
        assert not data["drift"]  # Initial contradiction is consistency, not historical change.
        assert {"QUALITY", "SAST", "SECRET", "IAC", "SCA", "CONSISTENCY"} <= {f["category"] for f in data["finding"]}
        assert data["dependency"]
        assert {"REPOSITORY", "SNAPSHOT", "COMPONENT", "ARTIFACT", "API_ENDPOINT"} <= {
            n["class"] for n in data["graph_node"]
        }
        node_ids = {n["id"] for key in ["claim", "finding", "evidence", "dependency", "graph_node"] for n in data[key]}
        assert all(e["source"] in node_ids and e["target"] in node_ids for e in data["edge"])
        assert "fake_fixture_secret" not in json.dumps(data)
        asked = client.post(
            "/api/ask", json={"question": "How is authentication implemented?", "repository_id": ids["repository_id"]}
        )
        assert asked.status_code == 200 and asked.json()["evidence"]
        assert "No language model was called." in asked.json()["limitations"]
        second = fixture_files()
        second["app.py"] = second["app.py"].replace(
            "app.add_middleware(SessionMiddleware, secret_key='fake_fixture_secret_123456789')",
            "import jwt\njwt.decode(token, key)",
        )
        updated = client.post(f"/api/repositories/{ids['repository_id']}/archive/analyze", content=archive(second))
        assert updated.status_code == 200, updated.text
        new = client.get("/api/workspace").json()
        assert new["drift"] and all(d["base_id"] == ids["snapshot_id"] for d in new["drift"])
        assert "ANALYSIS_COMPLETED" in {event["action"] for event in client.get("/api/audit").json()}
        assert client.get("/api/workspace?repository_id=unauthorized").status_code == 404
    engine.dispose()


def test_partial_parse_and_durable_unexpected_error(client, monkeypatch):
    created = client.post(
        "/api/auth/register",
        json={"email": "partial@example.com", "password": "Strong-test-password-123!", "organization": "Partial"},
    )
    client.headers["x-csrf-token"] = created.json()["csrf"]
    result = client.post("/api/import", json={"name": "broken-syntax", "files": {"app.py": "def broken(:"}})
    assert result.status_code == 200 and result.json()["state"] == "PARTIAL"
    assert client.get("/api/workspace").json()["job"][0]["warnings"]
    import backend.jobs as jobs

    def failed(*args, **kwargs):
        raise RuntimeError("private content must never be exposed")

    monkeypatch.setattr(jobs, "persist_analysis", failed)
    response = client.post("/api/import", json={"name": "failed", "files": {"app.py": "import fastapi"}})
    assert response.status_code == 500
    data = client.get("/api/workspace").json()
    assert data["analysis"]["state"] == "FAILED"
    assert "private content" not in json.dumps(data)
    assert len(data["repositories"]) == 2
