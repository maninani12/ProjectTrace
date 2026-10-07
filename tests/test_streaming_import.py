import io
import json
import zipfile

from cryptography.fernet import Fernet
from sqlalchemy import select

from backend import main
from backend.db import AnalysisInput, Record, SnapshotInventory
from backend.queue import load_input
from backend.repository_store import RepositoryFiles
from tests.test_code_quality import import_repo


def zipped(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, text in files.items():
            archive.writestr(path, text)
    return output.getvalue()


def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_BLOB_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("SOURCE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())


def test_streaming_existing_repository_retains_baseline_and_lazy_authorized_evidence(signed, monkeypatch, tmp_path):
    private_storage(monkeypatch, tmp_path)
    repo, base = import_repo(signed, {"app.py": "VALUE = 1\n"})
    response = signed.post(
        f"/api/repositories/{repo}/source-archive",
        content=zipped({"app.py": "VALUE = 2\n"}),
        headers={"content-type": "application/zip"},
    )
    assert response.status_code == 200, response.text
    head = response.json()["snapshot_id"]
    with main.Session() as db:
        assert db.get(Record, head).data["base_id"] == base
        assert db.get(SnapshotInventory, head)
        evidence = next(
            r
            for r in db.scalars(select(Record).where(Record.kind == "evidence"))
            if r.data.get("scope", {}).get("snapshot_id") == head
        )
        assert "source" not in evidence.data
        identifier = evidence.id
    assert signed.get("/api/record/" + identifier).json()["source"] == "VALUE = 2\n"
    assert not list((tmp_path / "uploads").iterdir())
    assert signed.post(f"/api/repositories/{repo}/source-archive", content=b"invalid").status_code == 422
    assert (
        signed.post(
            f"/api/repositories/{repo}/source-archive", content=b"", headers={"content-length": "9999999999"}
        ).status_code
        == 413
    )
    login = signed.post(
        "/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"}
    )
    signed.headers["x-csrf-token"] = login.json()["csrf"]
    assert signed.get("/api/record/" + identifier).status_code == 404
    assert signed.post(f"/api/repositories/{repo}/source-archive", content=b"invalid").status_code == 404


def test_streaming_new_import_and_reference_only_queue(signed, monkeypatch, tmp_path):
    private_storage(monkeypatch, tmp_path)
    import_repo(signed, {"app.py": "pass\n"})
    response = signed.post(
        "/api/archive/stream/import?name=NewSource", content=zipped({"app.py": "pass\n", "other.go": "package main\n"})
    )
    assert response.status_code == 200, response.text
    repo = response.json()["repository_id"]
    coverage = signed.get(f"/api/trust/coverage?repository_id={repo}")
    assert coverage.status_code == 200
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setattr("backend.queue.dispatch", lambda db, job: None)
    queued = signed.post(f"/api/repositories/{repo}/source-archive", content=zipped({"app.py": "VALUE = 9\n"}))
    assert queued.status_code == 202, queued.text
    with main.Session() as db:
        job = db.get(Record, queued.json()["job_id"])
        retained = db.get(AnalysisInput, job.id)
        import backend.queue

        decoded = json.loads(backend.queue.cipher().decrypt(retained.ciphertext.encode()))
        assert set(decoded) == {"inventory_id"}
        assert isinstance(load_input(db, job), RepositoryFiles)
        assert load_input(db, job)["app.py"] == "VALUE = 9\n"


def test_component_corrections_authorized_versioned_and_future_only(signed):
    repo, _ = import_repo(signed, {"app.py": "pass\n"})
    url = f"/api/repositories/{repo}/components"
    current = signed.get(url).json()
    assert current["version"] is None
    body = {"version": None, "configuration": {"version": 1, "components": [{"root": ".", "name": "Reviewed"}]}}
    response = signed.post(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["applies_to"] == "FUTURE_INVENTORIES"
    assert signed.post(url, json=body).status_code == 409
    body["version"] = response.json()["version"]
    body["configuration"]["components"][0]["root"] = "../escape"
    assert signed.post(url, json=body).status_code == 422
