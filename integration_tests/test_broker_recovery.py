"""Real Redis 7 / PostgreSQL 17 / Celery prefork failure acceptance.

Requires the explicit owned GitHub CI services. No FLUSH, arbitrary target,
production data, accelerated database lease expiry or mocked broker is used.
"""

import io
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import redis
from celery import Celery
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


def eventually(read, *, timeout=30, label):
    deadline, report = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        value = read()
        if value:
            return value
        if time.monotonic() >= report:
            print(json.dumps({"waiting": label}), flush=True)
            report = time.monotonic() + 20
        time.sleep(0.2)
    raise AssertionError(f"Owned acceptance deadline: {label}")


class Harness:
    def __init__(self, factory, app, runtime, env, container):
        self.factory, self.app, self.runtime, self.env, self.container = factory, app, runtime, env, container
        self.worker = None
        self.logs = []
        self.broker_stopped = False

    def start(self, cut=""):
        assert self.worker is None
        stream = (self.runtime / f"worker-{len(self.logs)}.log").open("w")
        self.logs.append(stream)
        self.worker = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "integration_tests.broker_app:celery", "worker",
             "--pool=prefork", "--concurrency=1", "--queues=native,large,celery", "--loglevel=INFO",
             "--without-gossip", "--without-mingle", "--without-heartbeat"],
            env={**self.env, "PROJECTTRACE_BROKER_CUT": cut}, stdout=stream, stderr=stream, start_new_session=True,
        )
        self.call("projecttrace.expire_inputs")  # Real broker round trip proves readiness.

    def stop(self, *, crash=False):
        if self.worker is None:
            return
        os.killpg(self.worker.pid, signal.SIGKILL if crash else signal.SIGTERM)
        try:
            self.worker.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(self.worker.pid, signal.SIGKILL)
            self.worker.wait(timeout=5)
            if not crash:
                raise AssertionError("Owned worker did not shut down gracefully") from None
        finally:
            self.worker = None

    def event(self, identifier):
        path = self.runtime / "task-events.jsonl"
        if not path.exists():
            return None
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue  # A child may be appending its final line.
            if row["task_id"] == identifier:
                return row
        return None

    def call(self, name, args=None):
        identifier = "probe-" + uuid.uuid4().hex
        self.app.send_task(name, args=args or [], task_id=identifier, retry=False)
        event = eventually(lambda: self.event(identifier), label=name)
        assert event["state"] == "SUCCESS", event
        return event.get("result", {})

    def broker(self, running):
        # Container identity/image were checked before any destructive operation.
        subprocess.run(["docker", "start" if running else "stop", self.container],
                       check=True, capture_output=True, timeout=25)
        self.broker_stopped = not running
        if running:
            def ready():
                try:
                    return redis.Redis.from_url(self.env["REDIS_URL"], socket_timeout=1).ping()
                except redis.RedisError:
                    return False
            eventually(ready, label="owned Redis restarted")

    def job(self, identifier):
        from backend.db import Record
        with self.factory() as db:
            return dict(db.get(Record, identifier).data)

    def published(self, identifier):
        data = self.job(identifier)
        return data if data.get("snapshot_id") and data["state"] in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"} else None

    def snapshots(self, repository):
        from backend.db import Record
        with self.factory() as db:
            return db.scalar(select(func.count()).select_from(Record).where(
                Record.repository_id == repository, Record.kind == "snapshot"))

    def wait_for_expiry(self, identifier):
        from backend.db import QueueEntry
        with self.factory() as db:
            expiry = datetime.fromisoformat(db.get(QueueEntry, identifier).lease_expires_at)
        eventually(lambda: datetime.now(timezone.utc) >= expiry, timeout=180, label="natural worker lease expiry")


@pytest.fixture
def broker(tmp_path, monkeypatch):
    if os.getenv("PROJECTTRACE_BROKER_TESTS") != "owned-ci":
        pytest.skip("Requires explicit disposable Redis/PostgreSQL GitHub CI infrastructure.")
    assert os.getenv("GITHUB_ACTIONS") == "true"
    container = os.environ["PROJECTTRACE_BROKER_CONTAINER"]
    assert re.fullmatch(r"[a-f0-9]{64}", container)
    details = json.loads(subprocess.check_output(["docker", "inspect", container], timeout=10))[0]
    assert details["Id"] == container and details["Config"]["Image"] == "redis:7-alpine"
    assert os.environ["REDIS_URL"] == "redis://127.0.0.1:16379/15"
    url = make_url(os.environ["PROJECTTRACE_BROKER_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and url.port == 15432 and url.database == "projecttrace_broker_test"
    schema = "pt_broker_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    database = url.update_query_dict({"options": "-csearch_path=" + schema})
    values = {
        "APP_ENV": "demo", "JOB_MODE": "celery", "OSV_ENABLED": "0",
        "DATABASE_URL": database.render_as_string(hide_password=False),
        "ANALYSIS_INPUT_KEY": Fernet.generate_key().decode(),
        "SOURCE_BLOB_DIR": str(tmp_path / "blobs"), "SOURCE_UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROJECTTRACE_BROKER_PREFIX": schema + ":", "PROJECTTRACE_BROKER_RUNTIME": str(tmp_path),
        "REPOSITORY_ANALYSIS_SECONDS": "120",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    env = os.environ.copy()
    with (tmp_path / "migrations.log").open("w") as log:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env,
                       check=True, stdout=log, stderr=log, timeout=60)
    from backend import main
    from backend.db import make_engine
    from workers import tasks

    engine = make_engine(database.render_as_string(hide_password=False))
    factory = sessionmaker(engine, expire_on_commit=False)
    app = Celery("owned-broker-acceptance", broker=env["REDIS_URL"])
    app.conf.update(dict(tasks.celery.conf))
    app.conf.broker_transport_options = {**app.conf.broker_transport_options, "global_keyprefix": schema + ":"}
    monkeypatch.setattr(tasks, "celery", app)
    monkeypatch.setattr(tasks, "Session", factory)
    monkeypatch.setattr(main, "Session", factory)
    main.rate_windows.clear()
    harness = Harness(factory, app, tmp_path, env, container)
    try:
        with TestClient(main.app) as client:
            client.headers["origin"] = "http://127.0.0.1:5173"
            result = client.post("/api/auth/register", json={
                "email": "owned-" + uuid.uuid4().hex + "@projecttrace.test",
                "password": "Disposable-broker-acceptance-123!", "organization": "Owned broker acceptance",
            })
            assert result.status_code == 200
            client.headers["x-csrf-token"] = result.json()["csrf"]
            harness.client = client
            yield harness
    finally:
        if harness.broker_stopped:
            harness.broker(True)
        harness.stop()
        for stream in harness.logs:
            stream.close()
        # Only sanitized logs/journals are copied. Never upload runtime DB/keys/source.
        output = Path(os.environ["PROJECTTRACE_BROKER_EVIDENCE"]) / schema
        output.mkdir(parents=True, exist_ok=True)
        for pattern in ("*.log", "task-events.jsonl"):
            for path in tmp_path.glob(pattern):
                (output / path.name).write_bytes(path.read_bytes())
        app.close()
        engine.dispose()
        assert re.fullmatch(r"pt_broker_[a-f0-9]{32}", schema)
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def upload(harness):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("README.md", "Backend uses FastAPI.\n")
        bundle.writestr("app.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    response = harness.client.post("/api/archive/import?name=Owned", content=archive.getvalue(),
                                   headers={"content-type": "application/zip"})
    assert response.status_code == 202
    return response.json()


def test_real_broker_outage_retains_and_recovers_an_accepted_import(broker):
    from backend.db import AnalysisInput
    broker.broker(False)
    receipt = upload(broker)
    identifier = receipt["job_id"]
    assert broker.job(identifier)["dispatch"] == "PENDING_RETRY"
    with broker.factory() as db:
        retained = db.get(AnalysisInput, identifier)
        assert retained and "FastAPI" not in retained.ciphertext
    broker.broker(True)
    broker.start()
    dispatched = datetime.fromisoformat(broker.job(identifier)["last_dispatched_at"])
    eventually(lambda: (datetime.now(timezone.utc) - dispatched).total_seconds() >= 60,
               timeout=65, label="normal lost-dispatch retry interval")
    broker.call("projecttrace.recover_jobs")
    eventually(lambda: broker.published(identifier), label="broker outage recovery publication")
    eventually(lambda: broker.event(identifier), label="recovered import finished")
    assert broker.snapshots(receipt["repository_id"]) == 1
    broker.call("projecttrace.analyze_inventory", [identifier])
    assert broker.snapshots(receipt["repository_id"]) == 1


@pytest.mark.parametrize("boundary", ["BEFORE_ANALYSIS", "AFTER_PUBLICATION"])
def test_real_prefork_loss_preserves_fencing_and_one_publication(broker, boundary):
    from backend.db import AnalysisInput, QueueEntry
    from backend.generation_models import AnalysisGeneration, PublishedGeneration
    broker.start(boundary)
    receipt = upload(broker)
    identifier = receipt["job_id"]
    marker = broker.runtime / "boundary.json"
    eventually(lambda: marker.exists() and marker.stat().st_size, label=boundary)
    cut = json.loads(marker.read_text())
    assert cut["job_id"] == identifier
    before = broker.job(identifier)
    assert broker.snapshots(receipt["repository_id"]) == (1 if boundary == "AFTER_PUBLICATION" else 0)
    with broker.factory() as db:
        assert db.get(AnalysisInput, identifier)
        assert db.get(QueueEntry, identifier).state == "RUNNING"
    broker.stop(crash=True)
    broker.start()  # Entire real prefork worker restarted; no task implementation replaced.
    broker.call("projecttrace.analyze_inventory", [identifier])
    assert broker.job(identifier) == before
    broker.wait_for_expiry(identifier)
    result = broker.call("projecttrace.recover_jobs")
    assert result["recovered_jobs"] == (0 if boundary == "AFTER_PUBLICATION" else 1)
    output = eventually(lambda: broker.published(identifier), label="worker loss publication")
    if boundary == "AFTER_PUBLICATION":
        assert output == before
    else:
        assert output["worker_token"] != cut["token"] and output["recovery_attempts"] == 1
        eventually(lambda: broker.event(identifier), label="new worker finished retained input")
    with broker.factory() as db:
        entry = db.get(QueueEntry, identifier)
        assert entry.state == output["state"] and entry.worker_token is None and entry.lease_expires_at is None
        generations = list(db.scalars(select(AnalysisGeneration).where(AnalysisGeneration.job_id == identifier)))
        assert len(generations) == 1 and generations[0].state == "PUBLISHED"
        pointer = db.get(PublishedGeneration, (entry.organization_id, entry.repository_id, "main"))
        assert pointer.generation_id == generations[0].id and generations[0].snapshot_id == output["snapshot_id"]
    broker.call("projecttrace.analyze_inventory", [identifier])
    assert broker.job(identifier) == output
    assert broker.snapshots(receipt["repository_id"]) == 1


def test_real_worker_rechecks_revocation_and_tenant_job_visibility(broker):
    from backend.db import AnalysisInput, QueueEntry, Record, User
    receipt = upload(broker)
    identifier = receipt["job_id"]
    with broker.factory() as db:
        actor = db.get(User, db.get(Record, identifier).data["user_id"])
        actor.enabled = False
        db.commit()
    with TestClient(broker.client.app) as other:
        other.headers["origin"] = "http://127.0.0.1:5173"
        registered = other.post("/api/auth/register", json={
            "email": "other-" + uuid.uuid4().hex + "@projecttrace.test",
            "password": "Disposable-broker-acceptance-123!", "organization": "Other broker tenant",
        })
        assert registered.status_code == 200
        other.headers["x-csrf-token"] = registered.json()["csrf"]
        assert other.get("/api/record/" + identifier).status_code == 404
        assert other.post(f"/api/jobs/{identifier}/retry").status_code == 404
        broker.start()
        event = eventually(lambda: broker.event(identifier), label="worker rejected revoked actor")
        assert event["state"] == "FAILURE"
        assert other.get("/api/record/" + identifier).status_code == 404
    with broker.factory() as db:
        assert db.get(Record, identifier).data["state"] == "FAILED"
        assert db.get(QueueEntry, identifier).state == "FAILED"
        assert db.get(AnalysisInput, identifier)
    assert broker.snapshots(receipt["repository_id"]) == 0
