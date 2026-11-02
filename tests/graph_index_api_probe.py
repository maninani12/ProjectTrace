"""Exact authorized HTTP response comparison on identical disposable copies."""

import hashlib
import json
from http.cookies import SimpleCookie
from pathlib import Path


def read_api(path, mode):
    from fastapi import Response
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from backend import main
    from backend.db import Grant, Organization, Record, Repository, User, make_engine
    from backend.generation_models import AnalysisGeneration, GenerationRecord
    from backend.security import create_session
    from tests.graph_index_prototype import install, listen_for_guards, mark

    engine = make_engine("sqlite:///" + str(path))
    factory = sessionmaker(engine, expire_on_commit=False)
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        mark(path)
        install(raw, mode)
    with factory() as db:
        user = db.get(User, "owned-eq")
        response = Response()
        create_session(db, user, response)
        cookie = SimpleCookie(response.headers["set-cookie"])["pt_session"].value
        db.add(Organization(id="proto-api-other", name="Other controlled tenant"))
        db.flush()
        db.add(
            Repository(
                id="proto-api-other",
                organization_id="proto-api-other",
                name="Other",
                system="Other",
                component="Other",
                owner="Other",
                provider="LOCAL",
            )
        )
        db.add(
            User(
                id="proto-api-other",
                organization_id="proto-api-other",
                email="other@owned.invalid",
                password_hash="unused",
                role="ORG_OWNER",
            )
        )
        db.flush()
        db.add(Grant(user_id="proto-api-other", repository_id="proto-api-other"))
        other_response = Response()
        create_session(db, db.get(User, "proto-api-other"), other_response)
        other_cookie = SimpleCookie(other_response.headers["set-cookie"])["pt_session"].value
        public_snapshot = db.scalar(select(Record.id).where(Record.kind == "snapshot").order_by(Record.id))
        node = db.scalar(
            select(Record)
            .where(Record.kind == "graph_node", Record.data["scope"]["snapshot_id"].as_string() == public_snapshot)
            .order_by(Record.id)
        )
        old = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.snapshot_id == public_snapshot))
        for identity, kind, data in (
            ("proto-private-job", "job", {"user_id": user.id, "state": "RUNNING", "source": "INVENTORY"}),
            ("proto-private-snapshot", "snapshot", {"branch": "prototype-private", "status": "PARTIAL"}),
            (
                "proto-private-node",
                "graph_node",
                {"scope": {"snapshot_id": "proto-private-snapshot"}, "class": "FUNCTION"},
            ),
        ):
            db.add(
                Record(
                    id=identity,
                    organization_id=user.organization_id,
                    repository_id="owned-eq",
                    kind=kind,
                    natural_key=identity,
                    data=data,
                )
            )
        db.flush()
        db.add(
            AnalysisGeneration(
                id="proto-private-generation",
                job_id="proto-private-job",
                organization_id=user.organization_id,
                repository_id="owned-eq",
                signature="a" * 64,
                content_key="b" * 64,
                inventory_id=old.inventory_id,
                branch="prototype-private",
                expected_pointer_revision=0,
                state="STAGING",
                expires_at="2099-01-01",
                snapshot_id="proto-private-snapshot",
            )
        )
        db.flush()
        for ordinal, identity in enumerate(("proto-private-snapshot", "proto-private-node")):
            db.add(
                GenerationRecord(
                    record_id=identity,
                    generation_id="proto-private-generation",
                    organization_id=user.organization_id,
                    repository_id="owned-eq",
                    stage="SNAPSHOT",
                    ordinal=ordinal,
                )
            )
        db.commit()
    original_session = main.Session
    main.Session = factory
    main.rate_windows.clear()
    release = listen_for_guards(engine) if mode == "validated_partial" else lambda: None

    class Captures(list):
        def append(self, item):
            item["body_sha256"] = hashlib.sha256(response.content).hexdigest()
            item["content_type"] = response.headers.get("content-type")
            super().append(item)

    results = Captures()
    try:
        with TestClient(main.app, raise_server_exceptions=False) as client:
            client.headers["origin"] = "http://127.0.0.1:5173"
            response = client.get("/api/graph/nodes", params={"repository_id": "owned-eq"})
            results.append({"case": "anonymous", "status": response.status_code, "body": response.json()})
            client.cookies.set("pt_session", cookie)
            for offset in (0, 1, 7, 100):
                response = client.get(
                    "/api/graph/nodes",
                    params={"repository_id": "owned-eq", "snapshot_id": public_snapshot, "offset": offset, "limit": 7},
                )
                results.append(
                    {"case": "nodes-" + str(offset), "status": response.status_code, "body": response.json()}
                )
            for parameter in (
                {"node_class": "FUNCTION"},
                {"node_class": "COMPONENT"},
                {"search": "%"},
                {"search": "app.py"},
            ):
                response = client.get(
                    "/api/graph/nodes",
                    params={"repository_id": "owned-eq", "snapshot_id": public_snapshot, **parameter},
                )
                results.append(
                    {"case": "filter-" + json.dumps(parameter), "status": response.status_code, "body": response.json()}
                )
            for offset in (0, 1, 7):
                response = client.get(
                    "/api/graph/neighborhood", params={"node_id": node.id, "limit": 7, "offset": offset}
                )
                results.append(
                    {"case": "neighbors-" + str(offset), "status": response.status_code, "body": response.json()}
                )
            for name, route, parameters in (
                (
                    "private-snapshot",
                    "/api/graph/nodes",
                    {"repository_id": "owned-eq", "snapshot_id": "proto-private-snapshot"},
                ),
                ("private-node", "/api/graph/neighborhood", {"node_id": "proto-private-node"}),
                ("private-record", "/api/record/proto-private-snapshot", {}),
                (
                    "wrong-repository",
                    "/api/graph/nodes",
                    {"repository_id": "forbidden", "snapshot_id": public_snapshot},
                ),
            ):
                response = client.get(route, params=parameters)
                results.append({"case": name, "status": response.status_code, "body": response.json()})
            client.cookies.set("pt_session", other_cookie)
            for name, route, parameters in (
                (
                    "cross-tenant-repository",
                    "/api/graph/nodes",
                    {"repository_id": "owned-eq", "snapshot_id": public_snapshot},
                ),
                ("cross-tenant-node", "/api/graph/neighborhood", {"node_id": node.id}),
            ):
                response = client.get(route, params=parameters)
                results.append({"case": name, "status": response.status_code, "body": response.json()})
            with factory() as db:
                db.delete(db.get(Grant, ("owned-eq", "owned-eq")))
                db.commit()
            client.cookies.set("pt_session", cookie)
            for name, route, parameters in (
                (
                    "revoked-repository",
                    "/api/graph/nodes",
                    {"repository_id": "owned-eq", "snapshot_id": public_snapshot},
                ),
                ("revoked-node", "/api/graph/neighborhood", {"node_id": node.id}),
            ):
                response = client.get(route, params=parameters)
                results.append({"case": name, "status": response.status_code, "body": response.json()})
    finally:
        release()
        main.Session = original_session
        engine.dispose()
    assert results[0]["status"] == 401
    assert all(
        row["status"] == 404
        for row in results
        if row["case"].startswith(("private-", "cross-tenant-", "revoked-")) or row["case"] == "wrong-repository"
    )
    assert all(
        row["status"] == 200 for row in results[1:] if row["case"].startswith(("nodes-", "filter-", "neighbors-"))
    )
    return results


if __name__ == "__main__":
    import argparse

    from tests.graph_index_prototype import clone

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    args.root.mkdir()
    results = {
        mode: read_api(clone(args.source, args.root / (mode + ".db")), mode)
        for mode in ("baseline", "validated_partial")
    }
    (args.root / "result.json").write_text(json.dumps(results, indent=2))
    differences = [a["case"] for a, b in zip(results["baseline"], results["validated_partial"]) if a != b]
    print(json.dumps({"requests_per_mode": len(results["baseline"]), "differences": differences}))
    if differences:
        raise SystemExit(1)
