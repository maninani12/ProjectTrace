import pytest

from backend import main
from backend.db import Record


def test_worker_scope_error_is_persisted(client, monkeypatch):
    created = client.post(
        "/api/auth/register",
        json={"email": "worker@example.com", "password": "Strong-test-password-123!", "organization": "Worker test"},
    )
    client.headers["x-csrf-token"] = created.json()["csrf"]
    imported = client.post("/api/import", json={"name": "worker", "files": {"app.py": "import fastapi"}})
    job_id = imported.json()["job_id"]
    with main.Session() as db:
        job = db.get(Record, job_id)
        job.data = {**job.data, "state": "QUEUED", "files": {"app.py": "import fastapi"}, "user_id": "missing"}
        db.commit()
    from workers import tasks

    monkeypatch.setattr(tasks, "Session", main.Session)
    with pytest.raises(ValueError):
        tasks.analyze_job.run(job_id)
    with main.Session() as db:
        job = db.get(Record, job_id)
        assert job.data["state"] == "FAILED" and job.data["error_type"] == "ValueError"
        assert "files" not in job.data and job.data["finished_at"]
