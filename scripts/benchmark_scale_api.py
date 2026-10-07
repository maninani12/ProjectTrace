"""Measure authorized read APIs against an isolated owned scale fixture; never use live data."""

# ruff: noqa: E402
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.responses import Response
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import Grant, Record, Repository, User, make_engine
from backend.security import create_session


def run(args):
    root = args.work_dir.resolve()
    os.environ["ANALYSIS_INPUT_KEY"] = (root / "private-benchmark.key").read_text().strip()
    os.environ["SOURCE_BLOB_DIR"] = str(root / "blobs")
    engine = make_engine("sqlite:///" + str(root / "benchmark.db"))
    # Historical owned benchmark DBs may predate the additive graph indexes.
    with engine.connect() as connection:
        existing_indexes = {row[1] for row in connection.exec_driver_sql("PRAGMA index_list(records)")}
    for index in Record.__table__.indexes:
        if index.name.startswith("ix_records_graph_"):
            if index.name not in existing_indexes:
                index.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        user, repo = db.get(User, "benchmark-user"), db.get(Repository, "benchmark-repo")
        if not user or not repo or user.email != "fixture@invalid.example" or repo.organization_id != "benchmark":
            raise ValueError("Only isolated owned scale fixture databases are accepted.")
        if not db.get(Grant, (user.id, repo.id)):
            db.add(Grant(user_id=user.id, repository_id=repo.id))
        response = Response()
        create_session(db, user, response)
        db.commit()
        cookie = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
        evidence = db.scalar(
            select(Record.id).where(Record.organization_id == "benchmark", Record.kind == "evidence").limit(1)
        )
        component = db.scalar(
            select(Record.id)
            .where(
                Record.organization_id == "benchmark",
                Record.kind == "graph_node",
                Record.data["class"].as_string() == "COMPONENT",
            )
            .limit(1)
        )
    main.Session = factory
    result = {
        "state": "MEASURED_LOCAL_TESTCLIENT",
        "database": "ISOLATED_OWNED_SQLITE",
        "network_transport_included": False,
        "samples_per_endpoint": args.samples,
        "endpoints": {},
    }
    endpoints = {
        "graph_nodes_page_50": "/api/graph/nodes?repository_id=benchmark-repo&limit=50",
        "graph_neighborhood_page_50": f"/api/graph/neighborhood?node_id={component}&limit=50",
        "workspace": "/api/workspace?repository_id=benchmark-repo",
        "authorized_evidence": f"/api/record/{evidence}",
    }
    with TestClient(main.app) as client:
        client.cookies.set("pt_session", cookie)
        for label, url in endpoints.items():
            durations, lengths = [], []
            for _ in range(args.samples):
                started = time.perf_counter()
                received = client.get(url)
                durations.append((time.perf_counter() - started) * 1000)
                if received.status_code != 200:
                    raise ValueError(f"Owned API benchmark failed: {label} HTTP {received.status_code}")
                lengths.append(len(received.content))
            ordered = sorted(durations)
            result["endpoints"][label] = {
                "p50_ms": round(ordered[int((len(ordered) - 1) * 0.50)], 3),
                "p95_ms": round(ordered[int((len(ordered) - 1) * 0.95)], 3),
                "max_ms": round(max(ordered), 3),
                "response_max_bytes": max(lengths),
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=10)
    options = parser.parse_args()
    if not 3 <= options.samples <= 100:
        parser.error("Use 3–100 bounded samples.")
    run(options)
