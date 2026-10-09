"""API authentication stays usable while the local SCM worker captures sources."""

import pytest
from cryptography.fernet import Fernet

from backend import main
from backend.db import Repository
from backend.repository_store import RepositoryFiles, capture
from backend.security import require_repo


def test_account_options_remain_readable_during_worker_write(client):
    with main.Session() as worker:
        repository = worker.get(Repository, "clean")
        repository.owner = "Uncommitted worker update"
        worker.flush()
        response = client.get("/api/auth/options")
        assert response.status_code == 200
        assert response.json()["demo_available"] is True
        worker.rollback()


@pytest.mark.parametrize("count,payload,checkpoints", [
    (201, b"VALUE = 1\n", (0, 100, 200)),
    (9, b"#" + b"x" * 499_999, (0, 4, 8)),
], ids=["file-count-bound", "byte-count-bound"])
def test_real_login_and_csrf_session_creation_between_source_batches(client, tmp_path, monkeypatch, count, payload, checkpoints):
    monkeypatch.setenv("SOURCE_BLOB_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())
    with main.Session() as worker:
        repository = worker.get(Repository, "clean")
        actor = worker.get(main.User, "viewer")
        checks = []

        def authorized():
            require_repo(worker, actor, repository.id)

        def slow_provider():
            for index in range(count):
                # Provider I/O occurs here. A session INSERT must finish without
                # waiting for capture to complete, including after the first batch.
                if index in checkpoints:
                    require_repo(worker, actor, repository.id)  # Open a fencing read before another writer commits.
                    response = client.post("/api/auth/login", json={
                        "email": "viewer@example.com", "password": "Strong-test-password-123!",
                    })
                    assert response.status_code == 200
                    client.headers["x-csrf-token"] = response.json()["csrf"]
                    assert client.get("/api/auth/options").json()["authenticated"] is True
                    assert client.get("/api/auth/me").status_code == 200
                    assert client.post("/api/auth/logout", json={}).status_code == 200
                    checks.append(index)
                yield f"src/file{index:03}.py", payload

        inventory = capture(worker, actor.organization_id, repository, slow_provider(), checkpoint=authorized)
        worker.commit()
        assert checks == list(checkpoints)
        assert len(RepositoryFiles(worker, actor.organization_id, repository.id, inventory.id)) == count
