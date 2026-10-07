import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from backend import main
from backend.db import AnalysisInput, Record


def account(client):
    registered = client.post(
        "/api/auth/register",
        json={"email": "queue@example.com", "password": "Strong-test-password-123!", "organization": "Queue tests"},
    )
    client.headers["x-csrf-token"] = registered.json()["csrf"]


def queued(client, monkeypatch):
    account(client)
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())
    from workers import tasks

    monkeypatch.setattr(tasks, "Session", main.Session)
    dispatched = []
    monkeypatch.setattr(tasks.celery, "send_task", lambda name, **kwargs: dispatched.append((name, kwargs)))
    return tasks, dispatched


def test_queued_import_encrypts_input_and_worker_persists_stages(client, monkeypatch):
    tasks, sent = queued(client, monkeypatch)
    secret = "SyntheticQueueSecret123456789"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("README.md", "Authentication uses JWT.")
        bundle.writestr("app.py", f'import fastapi\npassword = "{secret}"\n')
    response = client.post(
        "/api/archive/import?name=Queued", content=archive.getvalue(), headers={"content-type": "application/zip"}
    )
    assert response.status_code == 202
    result = response.json()
    assert result["snapshot_id"] is None and result["state"] == "QUEUED"
    assert sent[0][0] == "projecttrace.analyze" and sent[0][1]["args"] == [result["job_id"]]
    with main.Session() as db:
        retained = db.get(AnalysisInput, result["job_id"])
        assert secret not in retained.ciphertext
        assert secret not in json.dumps(db.get(Record, result["job_id"]).data)
    workspace = client.get("/api/workspace").json()
    assert workspace["analysis"]["state"] == "QUEUED" and workspace["repositories"][0]["snapshot"] is None
    tasks.analyze_job.run(result["job_id"])
    output = client.get("/api/workspace").json()
    assert output["repositories"][0]["snapshot"]
    assert secret not in json.dumps(output)
    with main.Session() as db:
        job = db.get(Record, result["job_id"])
        assert job.data["state"] in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}
        assert {"VALIDATING", "PARSING", "ANALYZING", "FINALIZING"} <= {s["stage"] for s in job.data["stages"]}
        assert job.data["queue_wait_ms"] >= 0 and db.get(AnalysisInput, job.id) is None
    tasks.analyze_job.run(result["job_id"])  # Delivery is idempotent.


def test_queued_zip_retains_unsupported_encoding_diagnostics(client, monkeypatch):
    tasks, _ = queued(client, monkeypatch)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("app.py", "def work(): pass".encode("utf-16"))
    response = client.post(
        "/api/archive/import?name=Encoded", content=stream.getvalue(), headers={"content-type": "application/zip"}
    )
    assert response.status_code == 202
    tasks.analyze_job.run(response.json()["job_id"])
    repo_id = response.json()["repository_id"]
    quality = client.get(f"/api/code-quality/{repo_id}/overview").json()
    assert quality["state"] == "PARTIAL" and quality["scope_counts"]["UNSUPPORTED_ENCODING"] == 1


def test_queue_failed_dispatch_cancel_and_tenant_scope(client, monkeypatch):
    tasks, _ = queued(client, monkeypatch)

    def unavailable(*args, **kwargs):
        raise ConnectionError("Synthetic broker outage")

    monkeypatch.setattr(tasks.celery, "send_task", unavailable)
    result = client.post("/api/import", json={"name": "Retained", "files": {"app.py": "import fastapi"}}).json()
    assert result["dispatch"] == "PENDING_RETRY"
    assert client.post(f"/api/jobs/{result['job_id']}/cancel").json()["state"] == "CANCELLED"
    with main.Session() as db:
        assert db.get(AnalysisInput, result["job_id"]) is None
    tasks.analyze_job.run(result["job_id"])
    assert client.get("/api/record/" + result["job_id"]).json()["state"] == "CANCELLED"
    other = client.post(
        "/api/auth/register",
        json={
            "email": "queue-other@example.com",
            "password": "Strong-test-password-123!",
            "organization": "Other queue",
        },
    )
    client.headers["x-csrf-token"] = other.json()["csrf"]
    assert client.get("/api/record/" + result["job_id"]).status_code == 404
    assert client.post(f"/api/jobs/{result['job_id']}/retry").status_code == 404


def test_expired_queued_input_fails_safely(client, monkeypatch):
    tasks, _ = queued(client, monkeypatch)
    result = client.post("/api/import", json={"name": "Expiry", "files": {"app.py": "import fastapi"}}).json()
    with main.Session() as db:
        db.get(AnalysisInput, result["job_id"]).expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        db.commit()
    with pytest.raises(ValueError):
        tasks.analyze_job.run(result["job_id"])
    job = client.get("/api/record/" + result["job_id"]).json()
    assert job["state"] == "FAILED" and job["finished_at"]
    with main.Session() as db:
        assert db.get(AnalysisInput, result["job_id"]) is None


def test_scheduler_purges_expired_inputs_and_marks_stopped_jobs(client, monkeypatch):
    tasks, _ = queued(client, monkeypatch)
    result = client.post("/api/import", json={"name": "Purge", "files": {"app.py": "import fastapi"}}).json()
    with main.Session() as db:
        db.get(AnalysisInput, result["job_id"]).expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        db.commit()
    assert tasks.expire_inputs.run() == {"expired_inputs": 1}
    assert tasks.expire_inputs.run() == {"expired_inputs": 0}
    assert client.get("/api/record/" + result["job_id"]).json()["state"] == "FAILED"


def test_queued_invalid_zip_survives_and_retry_uses_native_task(client, monkeypatch):
    tasks, sent = queued(client, monkeypatch)
    result = client.post("/api/archive/import?name=Invalid", content=b"invalid zip").json()
    with pytest.raises(zipfile.BadZipFile):
        tasks.analyze_job.run(result["job_id"])
    assert client.get("/api/record/" + result["job_id"]).json()["state"] == "FAILED"
    retried = client.post(f"/api/jobs/{result['job_id']}/retry")
    assert retried.status_code == 200 and sent[-1][0] == "projecttrace.analyze"
