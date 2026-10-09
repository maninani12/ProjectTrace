import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from backend import main
from backend.db import Record, Repository
from scripts.dev_runtime import load_config
from tests.test_public_github import public_fixture
from tests.test_streaming_import import private_storage, zipped


def account(client):
    response = client.post("/api/auth/register", json={"email": "reliability@example.com", "password": "Strong-test-password-123!", "organization": "Reliability"})
    client.headers["x-csrf-token"] = response.json()["csrf"]


def test_zip_duplicate_requests_are_serialized_and_conflicts_do_not_create_repositories(client, monkeypatch, tmp_path):
    private_storage(monkeypatch, tmp_path)
    account(client)
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setattr("backend.queue.dispatch", lambda db, job: None)
    path = "/api/archive/import?name=Duplicate&request_key=zip-request-001"
    content = zipped({"app.py": "def unsafe(value):\n    return eval(value)\n"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(path, content=content), range(2)))
    assert all(r.status_code in {202, 409} for r in responses), [r.text for r in responses]
    first = next(r for r in responses if r.status_code == 202).json()
    duplicate = client.post(path, content=content)
    assert duplicate.status_code == 202 and duplicate.json()["job_id"] == first["job_id"]
    assert duplicate.json()["duplicate"] is True
    assert client.post(path, content=zipped({"app.py": "changed"})).status_code == 409
    with main.Session() as db:
        assert db.scalar(select(func.count()).select_from(Repository).where(Repository.name == "Duplicate")) == 1


def test_public_failed_analysis_retry_reuses_exact_inventory_without_provider_io(client, monkeypatch, tmp_path):
    from workers import public_github
    private_storage(monkeypatch, tmp_path)
    calls = public_fixture(monkeypatch)
    account(client)
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setattr("backend.queue.dispatch", lambda db, job: None)
    job_id = client.post("/api/github/public/import", json={"url": "https://github.com/owner/repo", "request_key": "retained-public-001"}).json()["job_id"]
    monkeypatch.setattr(public_github, "Session", main.Session)
    original = public_github.execute_analysis
    monkeypatch.setattr(public_github, "execute_analysis", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Synthetic parser interruption")))
    with pytest.raises(RuntimeError):
        public_github.public_github_job.run(job_id)
    with main.Session() as db:
        before = db.get(Record, job_id).data["inventory_id"]
    assert client.post(f"/api/jobs/{job_id}/retry", json={}).status_code == 200
    monkeypatch.setattr(public_github, "execute_analysis", original)
    public_github.public_github_job.run(job_id)
    with main.Session() as db:
        job = db.get(Record, job_id)
        assert job.data["inventory_id"] == before and job.data["snapshot_id"]
        assert db.get(Record, job.data["snapshot_id"]).data["commit"] == "a" * 40
    assert len(calls) == 3


def test_corrupt_zip_payload_has_precise_error_without_a_snapshot(client, monkeypatch, tmp_path):
    private_storage(monkeypatch, tmp_path)
    account(client)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED) as z:
        z.writestr("app.py", "VALUE = 1\n")
    raw = stream.getvalue().replace(b"VALUE = 1", b"VALUE = 2")
    response = client.post("/api/archive/import?name=Corrupt", content=raw)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ARCHIVE_ENTRY_CORRUPT"
    with main.Session() as db:
        assert not db.scalar(select(Record).where(Record.kind == "snapshot", Record.repository_id.in_(select(Repository.id).where(Repository.name == "Corrupt"))))


def test_local_config_is_data_only_rejects_secrets_and_defaults_to_local(tmp_path):
    assert load_config(None, {})["JOB_MODE"] == "local"
    config = tmp_path / "runtime.json"
    for value in ({"SCM_GITHUB_KEY": "secret"}, {"COMMAND": "execute"}, {"JOB_MODE": "sync"}, {"APP_ENV": "production"}):
        config.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            load_config(config, {})
    config.write_text(json.dumps({"JOB_MODE": "local"}))
    assert load_config(config, {})["JOB_MODE"] == "local"


def test_repeated_analysis_retains_original_snapshot_job_provenance(client):
    account(client)
    files = {"app.py": "def work(value):\n    return value\n"}
    first = client.post("/api/import", json={"name": "Immutable capture", "files": files}).json()
    captured = client.get("/api/record/" + first["snapshot_id"]).json()
    repeated = client.post(f"/api/repositories/{first['repository_id']}/analyze", json={"files": files})
    assert repeated.status_code == 200 and repeated.json()["id"] == first["snapshot_id"]
    assert client.get("/api/record/" + first["snapshot_id"]).json() == captured
    assert captured["job_id"] == first["job_id"]


def test_local_zip_admission_exposes_active_writer_without_creating_a_repository(client, monkeypatch, tmp_path):
    from backend.scheduling import claim
    private_storage(monkeypatch, tmp_path)
    account(client)
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setattr("workers.tasks.celery.send_task", lambda *a, **kw: None)
    first = client.post("/api/import", json={"name": "Running", "files": {"app.py": "pass\n"}}).json()
    with main.Session() as db:
        assert claim(db, db.get(Record, first["job_id"]), 120)["state"] == "CLAIMED"
    response = client.post("/api/archive/import?name=Blocked", content=zipped({"app.py": "pass\n"}))
    assert response.status_code == 503 and response.json()["detail"]["code"] == "LOCAL_CAPTURE_BUSY"
    assert response.headers["retry-after"] == "2"
    assert [r["name"] for r in client.get("/api/workspace").json()["repositories"]] == ["Running"]


def test_sqlite_busy_is_a_safe_retryable_response_and_never_discloses_sql(client, monkeypatch):
    import sqlite3

    from sqlalchemy.exc import OperationalError
    original = sqlite3.OperationalError("database is locked")
    original.sqlite_errorcode = 5
    def unavailable(*a, **kw):
        raise OperationalError("Sensitive SQL", {"secret": "synthetic-private-value"}, original)
    monkeypatch.setattr(main, "authenticate", unavailable)
    response = client.get("/api/workspace")
    assert response.status_code == 503 and response.json()["detail"]["code"] == "LOCAL_DATABASE_BUSY"
    assert "Sensitive SQL" not in response.text and "synthetic-private-value" not in response.text


def test_zip_backpressure_and_duplicate_receipt_remain_readable_during_publication(client, monkeypatch, tmp_path):
    from sqlalchemy import text

    from backend.scheduling import claim

    private_storage(monkeypatch, tmp_path)
    account(client)
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setattr("backend.queue.dispatch", lambda db, job: None)
    payload = zipped({"app.py": "pass\n"})
    path = "/api/archive/import?name=Active&request_key=active-zip-001"
    response = client.post(path, content=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    with main.Session() as db:
        assert claim(db, db.get(Record, job_id), 120)["state"] == "CLAIMED"
    engine = main.Session.kw["bind"]
    with engine.connect() as writer:
        writer.execute(text("UPDATE queue_cursor SET revision=revision+1 WHERE id='native'"))
        duplicate = client.post(path, content=payload)
        assert duplicate.status_code == 202 and duplicate.json()["job_id"] == job_id
        assert duplicate.json()["duplicate"] is True
        blocked = client.post("/api/archive/import?name=Blocked&request_key=blocked-zip-001", content=payload)
        assert blocked.status_code == 503 and blocked.json()["detail"]["code"] == "LOCAL_CAPTURE_BUSY"
        assert blocked.headers["retry-after"] == "2"
        writer.rollback()
    assert [r["name"] for r in client.get("/api/workspace").json()["repositories"]] == ["Active"]


def test_repaired_scm_retry_is_finite_scoped_and_preserves_attempt_history(client, monkeypatch):
    account(client)
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr("workers.tasks.celery.send_task", lambda *a, **kw: None)
    job_id = client.post("/api/import", json={"name": "SCM retry fixture", "files": {"app.py": "pass\n"}}).json()["job_id"]
    with main.Session() as db:
        job = db.get(Record, job_id)
        job.data = {**job.data, "state": "FAILED", "source": "GITHUB", "retry_count": 3,
            "repair_retry_revision": "safe-intake-2026-10-08", "error_code": "SCM_TRANSPORT", "head_sha": "a" * 40}
        db.commit()
    response = client.post(f"/api/jobs/{job_id}/retry", json={})
    assert response.status_code == 200
    assert response.json()["retry_count"] == 4 and response.json()["head_sha"] == "a" * 40
    assert response.json()["attempt_history"][-1]["retry_count"] == 3
    with main.Session() as db:
        job = db.get(Record, job_id)
        job.data = {**job.data, "state": "FAILED", "error_code": "SCM_TRANSPORT"}
        db.commit()
    assert client.post(f"/api/jobs/{job_id}/retry", json={}).status_code == 409
