"""100 real signed local webhook requests and native analyses over owned inert fixtures."""

# ruff: noqa: E402
import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from celery.exceptions import Retry
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import (
    Base,
    Delivery,
    Grant,
    Organization,
    QueueCursor,
    QueueEntry,
    Record,
    Repository,
    SourceInventory,
    User,
    make_engine,
)
from backend.domain import add
from backend.process_limits import self_limits
from backend.scheduling import eligible, recover_expired
from workers import github

SECRET = "owned-load-fixture-webhook-secret"


class OwnedAdapter:
    def iter_snapshot(self, name, commit):
        # The parsed fixture varies per immutable head; it is never executed.
        yield "service.py", f"def transform(value):\n    return value + {int(commit[-6:], 16)}\n".encode()
        yield "README.md", b"# Owned load fixture\n"
        yield "package.json", b'{"name":"owned-load-fixture"}'

    def publish_check(self, *args):
        raise AssertionError("The load benchmark must not publish outside this process.")


def percentile(values, fraction):
    return round(sorted(values)[int((len(values) - 1) * fraction)], 3) if values else None


def run(args):
    root = args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "pr-load.db"
    if path.exists():
        raise ValueError("Use a fresh owned benchmark directory.")
    key = Fernet.generate_key()
    with (root / "private-load.key").open("xb") as stream:
        stream.write(key)
    (root / "private-load.key").chmod(0o600)
    os.environ["ANALYSIS_INPUT_KEY"] = key.decode()
    os.environ["SOURCE_BLOB_BACKEND"] = "local"
    os.environ["SOURCE_BLOB_DIR"] = str(root / "blobs")
    os.environ["SOURCE_UPLOAD_DIR"] = str(root / "uploads")
    guard = self_limits(768 * 1024 * 1024, 600)
    engine = make_engine("sqlite:///" + str(path))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    main.Session = github.Session = factory
    github.configured_app = lambda connection=None: OwnedAdapter()
    os.environ["SCM_LOAD_WEBHOOK"] = SECRET
    os.environ["JOB_MODE"] = "sync"  # signed receipt remains queued; controlled workers drain it below
    main.rate_windows.clear()
    with factory() as db:
        for org in ("alpha", "beta"):
            db.add(Organization(id=org, name="Owned load " + org))
            db.flush()
            user = User(
                id=org, organization_id=org, email=org + "@invalid.example", password_hash="unused", role="ORG_OWNER"
            )
            db.add(user)
            db.flush()
            add(
                db,
                org,
                None,
                "scm_connection",
                {
                    "owner_id": org,
                    "installation_id": "1",
                    "webhook_secret_ref": "ENV:SCM_LOAD_WEBHOOK",
                    "enabled": True,
                },
                "load-connection",
            )
            connection = db.scalar(select(Record).where(Record.organization_id == org, Record.kind == "scm_connection"))
            add(db, org, None, "integration", {"owner_id": org, "checks_enabled": False}, "github:" + connection.id)
            for number in (0, 1):
                identifier = org + str(number)
                db.add(
                    Repository(
                        id=identifier,
                        organization_id=org,
                        name="owned/" + identifier,
                        system="Owned",
                        component="Owned",
                        owner="Owned",
                        provider="GHES",
                        provider_id=identifier,
                    )
                )
                db.flush()
                db.add(Grant(user_id=org, repository_id=identifier))
                add(
                    db,
                    org,
                    identifier,
                    "repository_scm",
                    {"connection_id": connection.id, "provider_repository_id": str(number + 7), "enabled": True},
                )
        db.commit()
        connections = {
            r.organization_id: r.id for r in db.scalars(select(Record).where(Record.kind == "scm_connection"))
        }
    receipts, acceptance, analysis, waits, failures, retries, busy, peak_busy, started = (
        [],
        [],
        [],
        [],
        [],
        [],
        0,
        0,
        time.perf_counter(),
    )
    mutex = threading.Lock()
    with TestClient(main.app) as client:

        def send(index, delivery=None):
            org = ("alpha", "beta")[index % 2]
            number = (index // 2) % 2
            pr_number = index // 4 + 1 if index < 80 else (index - 80) // 4 + 1
            payload = {
                "installation": {"id": 1},
                "repository": {"id": number + 7},
                "action": "synchronize",
                "pull_request": {
                    "number": pr_number,
                    "head": {"sha": f"{index + 1:040x}", "ref": "load", "repo": {"id": number + 7}},
                },
            }
            raw = json.dumps(payload).encode()
            before = time.perf_counter()
            response = client.post(
                "/api/github/webhook/" + connections[org],
                content=raw,
                headers={
                    "x-hub-signature-256": "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest(),
                    "x-github-event": "pull_request",
                    "x-github-delivery": delivery or "owned-" + str(index),
                },
            )
            acceptance.append((time.perf_counter() - before) * 1000)
            if response.status_code != 200:
                raise ValueError(f"Signed owned event {index} failed: HTTP {response.status_code}")
            receipts.append(response.json()["status"])

        for index in range(100):
            send(index)
        for index in range(10):
            send(index)  # delivery replay
        for index in range(95, 100):
            send(index, "new-delivery-same-sha-" + str(index))
    with factory() as db:
        first = eligible(db)[0].job_id
    crash_code = """import os,sys
from sqlalchemy.orm import sessionmaker
from backend.db import make_engine,Record
from backend.scheduling import claim
with sessionmaker(make_engine('sqlite:///'+sys.argv[1]),expire_on_commit=False)() as db:
 result=claim(db,db.get(Record,sys.argv[2]),120)
 if result['state']!='CLAIMED': raise RuntimeError('Crash fixture did not claim work')
os._exit(73)
"""
    crashed = subprocess.run([sys.executable, "-c", crash_code, str(path), first], cwd=ROOT, check=False)
    if crashed.returncode != 73:
        raise ValueError("Owned worker-crash fixture did not exit as intended.")
    with factory() as db:
        db.get(QueueEntry, first).lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
        recovered = recover_expired(db)
        if recovered != [first]:
            raise ValueError("Crashed owned worker lease did not recover.")
    deadline = time.monotonic() + 600

    def worker(_):
        nonlocal busy, peak_busy
        while time.monotonic() < deadline:
            with factory() as db:
                candidates = eligible(db)
                pending = db.scalar(
                    select(func.count()).select_from(QueueEntry).where(QueueEntry.state.in_(["QUEUED", "RUNNING"]))
                )
                cursor = db.get(QueueCursor, "native")
                selected = next((row for row in candidates if row.organization_id > (cursor.last_tenant if cursor else "")), candidates[0] if candidates else None)
                identifier = selected.job_id if selected else None
            if not pending:
                return
            if not identifier:
                time.sleep(0.02)
                continue
            begin = time.perf_counter()
            with mutex:
                busy += 1
                peak_busy = max(busy, peak_busy)
            try:
                github.github_delivery.run(identifier)
            except Retry:
                with mutex:
                    retries.append(identifier)
            except Exception as error:
                with mutex:
                    failures.append({"job_id": identifier, "error_type": type(error).__name__})
            finally:
                with mutex:
                    busy -= 1
                    analysis.append((time.perf_counter() - begin) * 1000)
            time.sleep(0.005)
        raise TimeoutError("Owned load benchmark did not drain within its bounded budget.")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(4)))
    with factory() as db:
        jobs = list(db.scalars(select(Record).where(Record.kind == "job")))
        snapshots = list(db.scalars(select(Record).where(Record.kind == "snapshot")))
        scoped = all(r.repository_id.startswith(r.organization_id) for r in snapshots)
        states = {
            state: sum(j.data.get("state") == state for j in jobs) for state in {j.data.get("state") for j in jobs}
        }
        waits = [j.data["queue_wait_ms"] for j in jobs if "queue_wait_ms" in j.data]
        tenant_completed = {org: sum(s.organization_id == org for s in snapshots) for org in ("alpha", "beta")}
        streaming_snapshots = sum(bool(row.data.get("source_inventory_id")) for row in snapshots)
        report = {
            "state": "MEASURED_CONTROLLED_LOCAL"
            if not failures and scoped and len(snapshots) == streaming_snapshots == 80
            else "FAILED",
            "database": "LOCAL_SQLITE",
            "source_adapter": "OWNED_STREAMING_ITERATOR_TENANT_ENCRYPTED_CAPTURE",
            "streaming_snapshots": streaming_snapshots,
            "captured_inventories": db.scalar(select(func.count()).select_from(SourceInventory)),
            "resource_guard": guard,
            "implementation_hashes": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in [
                    "backend/domain.py", "backend/jobs.py", "backend/repository_store.py", "backend/scheduling.py",
                    "backend/snapshot_context.py", "backend/quality_domain.py", "backend/engineering_changes.py",
                    "workers/github.py", "scripts/benchmark_pr_load.py",
                ]
            },
            "queue_adapter": "FOUR_CONTROLLED_THREADS_USING_PRODUCTION_CLAIMS_AND_GHES_WORKER",
            "broker_qualification": "UNMEASURED_REDIS_CELERY_POSTGRESQL",
            "primary_pr_events": 100,
            "http_requests": len(receipts),
            "duplicate_delivery_responses": receipts.count("DUPLICATE"),
            "retained_delivery_receipts": db.scalar(select(func.count()).select_from(Delivery)),
            "jobs": len(jobs),
            "job_states": states,
            "snapshots": len(snapshots),
            "tenant_completed": tenant_completed,
            "tenant_scope_verified": scoped,
            "owned_worker_exit_code": crashed.returncode,
            "recovered_jobs": len(recovered),
            "lease_expiry_advanced_for_crash_test": True,
            "webhook_p50_ms": percentile(acceptance, 0.5),
            "webhook_p95_ms": percentile(acceptance, 0.95),
            "webhook_p99_ms": percentile(acceptance, 0.99),
            "worker_attempt_p50_ms": percentile(analysis, 0.5),
            "worker_attempt_p95_ms": percentile(analysis, 0.95),
            "queue_wait_p50_ms": percentile(waits, 0.5),
            "queue_wait_p95_ms": percentile(waits, 0.95),
            "worker_threads": 4,
            "peak_busy_threads": peak_busy,
            "deferred_attempts": len(retries),
            "failures": failures,
            "wall_seconds": round(time.perf_counter() - started, 3),
            "customer_code_executed": False,
            "limitations": [
                "Local HTTP TestClient excludes network/TLS latency; adapter serves owned inert source.",
                "Lease expiry was advanced after an actual owned subprocess exit; production crash timing is unmeasured.",
                "Busy threads include database lock waits and deferred deliveries; CPU saturation is unmeasured.",
            ],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    if report["state"] == "FAILED":
        raise ValueError("Owned PR load invariants failed; inspect the retained report.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    run(parser.parse_args())
