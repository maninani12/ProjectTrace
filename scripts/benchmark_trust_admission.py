"""Separate local admission measurements; neither large-repo nor concurrent-worker proof."""

import argparse
import hashlib
import hmac
import json
import os
import tempfile
import time
import tracemalloc
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from analyzers.engine import VERSION, validate_files
from backend import main
from backend.db import Base, Delivery, Organization, Record, Repository, make_engine


def large_admission():
    tracemalloc.start()
    started = time.perf_counter()
    source = "x = 0\n" * 3_000_000
    try:
        validate_files({"generated.py": source}, keep_excluded=True)
        status = "ACCEPTED"
    except ValueError:
        status = "REJECTED_BY_BOUNDED_INTAKE"
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "version": VERSION,
        "method": "SYNTHETIC_ADMISSION_ONLY",
        "lines": 3_000_000,
        "bytes": len(source),
        "status": status,
        "elapsed_ms": round(1000 * (time.perf_counter() - started), 3),
        "python_traced_peak_bytes": peak,
        "analysis_throughput": None,
        "limitations": [
            "This validates rejection at the current 512KB/file and 10MB total bounds; it does not analyze a 3M-line repository.",
            "Streaming/CAS/sharding and successful large-repository measurements are deferred.",
        ],
    }


def receipts():
    previous = main.Session
    previous_env = {key: os.environ.get(key) for key in ("GITHUB_WEBHOOK_SECRET", "JOB_MODE")}
    secret = "Synthetic-local-receipt-benchmark-secret"
    os.environ.update(GITHUB_WEBHOOK_SECRET=secret, JOB_MODE="sync")
    try:
        with tempfile.TemporaryDirectory(prefix="projecttrace-receipts-") as directory:
            engine = make_engine("sqlite:///" + str(Path(directory) / "benchmark.db").replace("\\", "/"))
            Base.metadata.create_all(engine)
            factory = sessionmaker(engine, expire_on_commit=False)
            main.Session = factory
            main.rate_windows.clear()
            with factory() as db:
                db.add(Organization(id="benchmark-org", name="Synthetic benchmark"))
                db.flush()
                db.add(
                    Repository(
                        id="benchmark-repo",
                        organization_id="benchmark-org",
                        name="fixture/repo",
                        system="Fixture",
                        component="Fixture",
                        owner="Fixture",
                        provider="GITHUB",
                        provider_id="987654321",
                    )
                )
                db.commit()
            durations, codes = [], []
            started = time.perf_counter()
            with TestClient(main.app) as client:
                for number in range(100):
                    body = json.dumps(
                        {
                            "repository": {"id": 987654321},
                            "pull_request": {
                                "number": number + 1,
                                "title": "Synthetic PR",
                                "head": {"sha": hashlib.sha1(str(number).encode()).hexdigest(), "ref": "fixture"},
                                "base": {"sha": "a" * 40},
                            },
                        }
                    ).encode()
                    headers = {
                        "x-github-event": "pull_request",
                        "x-github-delivery": "synthetic-benchmark-" + str(number),
                        "x-hub-signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
                    }
                    tick = time.perf_counter()
                    result = client.post("/api/github/webhook", content=body, headers=headers)
                    durations.append(1000 * (time.perf_counter() - tick))
                    codes.append(result.status_code)
                replay = client.post("/api/github/webhook", content=body, headers=headers)
            elapsed = time.perf_counter() - started
            with factory() as db:
                deliveries = db.scalar(select(func.count()).select_from(Delivery))
                jobs = db.scalar(select(func.count()).select_from(Record).where(Record.kind == "job"))
            engine.dispose()
            ordered = sorted(durations)
            return {
                "version": VERSION,
                "method": "100_SEQUENTIAL_SIGNED_HTTP_RECEIPTS_LOCAL_SQLITE",
                "concurrency": 1,
                "requests": 100,
                "accepted": codes.count(200),
                "durable_deliveries": deliveries,
                "durable_jobs": jobs,
                "replay_status": replay.json().get("status"),
                "receipt_latency_ms": {"p50": ordered[49], "p95": ordered[94], "p99": ordered[98]},
                "elapsed_seconds": round(elapsed, 3),
                "receipts_per_second": round(100 / elapsed, 3),
                "analysis_throughput": None,
                "queue_wait_ms": None,
                "tenant_fairness": "UNMEASURED",
                "limitations": [
                    "Sequential receipt retention/idempotency only, not 100 concurrent PR analysis.",
                    "No live provider, Redis workers, fairness, supersession or end-to-end SLA is validated.",
                ],
            }
    finally:
        main.Session = previous
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for name, report in (
        ("enterprise-large-admission-1.6.0.json", large_admission()),
        ("enterprise-receipts-1.6.0.json", receipts()),
    ):
        (args.output_directory / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"report": name, "method": report["method"], "analysis_throughput": report["analysis_throughput"]}
            )
        )
