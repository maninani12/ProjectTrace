import time

from sqlalchemy import select

from backend import main
from backend.db import Record, Repository
from backend.local_jobs import LocalJobs
from tests.test_streaming_import import private_storage, zipped


def test_local_zip_runs_without_redis_app_or_webhook_and_retains_real_snapshot(client, monkeypatch, tmp_path):
    private_storage(monkeypatch, tmp_path)
    reply = client.post("/api/auth/register", json={"email": "local-test@example.com", "password": "Strong-test-password-123!", "organization": "Local tests"})
    client.headers["x-csrf-token"] = reply.json()["csrf"]
    monkeypatch.setenv("JOB_MODE", "local")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr("workers.tasks.celery.send_task", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Local ZIP must not use Redis")))
    # An unavailable older SCM queue must not starve infrastructure-free imports.
    from backend.domain import add
    from backend.scheduling import register
    with main.Session() as db:
        user = db.scalar(select(main.User).where(main.User.email == "local-test@example.com"))
        repo = Repository(id="unavailable-scm", organization_id=user.organization_id, name="Unavailable SCM", system="Test", component="Test", owner="Owner", provider="GITHUB")
        db.add(repo)
        db.flush()
        older = add(db, user.organization_id, repo.id, "job", {"state": "QUEUED", "execution": "CELERY", "source": "GITHUB"})
        register(db, older)
        db.commit()
    runner = LocalJobs(main.Session)
    runner.start()
    try:
        response = client.post("/api/archive/import?name=LocalZip", content=zipped({"app.py": "def unsafe(value):\n    return eval(value)\n"}))
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with main.Session() as db:
                job = db.get(Record, job_id)
                if job.data.get("finished_at"):
                    break
            time.sleep(0.05)
        with main.Session() as db:
            job = db.get(Record, job_id)
            assert job.data["state"] in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}, job.data
            snapshot = db.get(Record, job.data["snapshot_id"])
            assert snapshot.data["source_provenance"]["source"] == "ZIP"
            assert db.get(Repository, job.repository_id).provider == "ZIP"
            assert db.scalar(select(Record).where(Record.kind == "finding", Record.repository_id == job.repository_id))
    finally:
        runner.stop()


def test_bad_zip_leaves_no_repository_and_api_error_identifies_safety_failure(client):
    reply = client.post("/api/auth/register", json={"email": "invalid-local@example.com", "password": "Strong-test-password-123!", "organization": "Invalid tests"})
    client.headers["x-csrf-token"] = reply.json()["csrf"]
    response = client.post("/api/archive/import?name=Invalid", content=b"invalid zip")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ARCHIVE_INVALID"
    assert client.get("/api/workspace").json()["repositories"] == []
