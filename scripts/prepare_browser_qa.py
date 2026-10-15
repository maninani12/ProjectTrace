"""Build a NEW disposable browser QA instance from digest-pinned inert ZIP inputs.

This tool never opens an existing QA directory or a configured production database.
Credentials stay in private .secret files; volume identities/activity are labelled fixtures.
"""
import argparse
import hashlib
import json
import os
import secrets
import sys
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--petclinic", type=Path, required=True)
    parser.add_argument("--petclinic-sha256", required=True)
    parser.add_argument("--projecttrace", type=Path, required=True)
    parser.add_argument("--projecttrace-sha256", required=True)
    args = parser.parse_args()
    inputs = [("spring petclinic", args.petclinic.resolve(), args.petclinic_sha256),
              ("ProjectTrace source", args.projecttrace.resolve(), args.projecttrace_sha256)]
    for _, archive, expected in inputs:
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise ValueError("Pinned source archive digest mismatch.")
    qa = args.directory.resolve()
    qa.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ.update(DATABASE_URL="sqlite:///" + str(qa / "qa.db").replace("\\", "/"),
        ANALYSIS_KEY_FILE=str(qa / "input.key"), SOURCE_BLOB_DIR=str(qa / "blobs"),
        SOURCE_UPLOAD_DIR=str(qa / "uploads"), APP_ENV="demo", JOB_MODE="sync")
    os.chdir(root)
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from backend import main as application
    from backend.admin_models import ActivityEvent, OrganizationMembership
    from backend.db import Grant, Record, User
    from backend.security import passwords

    command.upgrade(Config("alembic.ini"), "head")
    password, email = secrets.token_urlsafe(32), "browser-owner@example.test"
    repositories = []
    with TestClient(application.app) as client:
        client.headers["origin"] = "http://127.0.0.1:5181"
        response = client.post("/api/auth/register", json={"email": email, "password": password,
                                                          "organization": "Reproducible browser QA"})
        response.raise_for_status()
        client.headers["x-csrf-token"] = response.json()["csrf"]
        for label, archive, digest in inputs:
            response = client.post("/api/archive/import", params={"name": label}, content=archive.read_bytes(),
                                   headers={"content-type": "application/zip"})
            response.raise_for_status()
            receipt = response.json()
            with application.Session() as db:
                snapshot = db.get(Record, receipt.get("snapshot_id") or receipt["id"])
                data = snapshot.data
                summary = data["analysis_coverage"]["summary"]
                repositories.append({"name": label, "id": snapshot.repository_id, "snapshot_id": snapshot.id,
                    "file_count": data["file_count"], "warning_count": len(data["warnings"]),
                    "parsed_files": summary["source_files_parsed"], "source_files": summary["source_files"],
                    "evidence_count": db.scalar(select(func.count()).select_from(Record).where(
                        Record.kind == "evidence", Record.repository_id == snapshot.repository_id)),
                    "archive_sha256": digest})
    viewer_email, viewer_password = "repository-viewer@example.test", secrets.token_urlsafe(32)
    with application.Session() as db:
        owner = db.scalar(select(User).where(User.email == email))
        org = owner.organization_id
        synthetic_hash = passwords.hash(secrets.token_urlsafe(32))
        for n in range(1000):
            db.add(User(id="qa-volume-" + str(n), organization_id=org, email=f"qa-volume-{n}@example.test",
                        password_hash=synthetic_hash, role="VIEWER"))
        viewer_id = uuid.uuid4().hex
        db.add(User(id=viewer_id, organization_id=org, email=viewer_email,
                    password_hash=passwords.hash(viewer_password), role="VIEWER"))
        db.flush()
        for n in range(1000):
            db.add(OrganizationMembership(organization_id=org, user_id="qa-volume-" + str(n), role="VIEWER", state="ACTIVE"))
            db.add(ActivityEvent(id="qa-activity-" + str(n), organization_id=org, actor_id=owner.id,
                action="BENCHMARK_DENIED" if n % 2 else "BENCHMARK_ACCEPTED", category="ADMINISTRATION",
                outcome="DENIED" if n % 2 else "SUCCEEDED", data={"fixture": "synthetic volume acceptance"}))
        db.add(OrganizationMembership(organization_id=org, user_id=viewer_id, role="VIEWER", state="ACTIVE"))
        for repository in repositories:
            db.add(Grant(user_id=viewer_id, repository_id=repository["id"]))
        db.commit()
    for name, account_email, account_password in [("qa-account.secret", email, password),
                                                 ("repository-account.secret", viewer_email, viewer_password)]:
        target = qa / name
        target.write_text(json.dumps({"fixture_schema": "projecttrace-browser-qa-v1", "email": account_email,
                                      "password": account_password, "repositories": repositories}), encoding="utf-8")
        target.chmod(0o600)
    (qa / "runtime.json").write_text(json.dumps({name: os.environ[name] for name in (
        "DATABASE_URL", "ANALYSIS_KEY_FILE", "SOURCE_BLOB_DIR", "SOURCE_UPLOAD_DIR", "APP_ENV", "JOB_MODE")}), encoding="utf-8")
    (qa / "fixture-public.json").write_text(json.dumps({"repositories": repositories, "synthetic_users": 1000,
        "synthetic_activity_events": 1000, "source_code_executed": False}, indent=2), encoding="utf-8")
    print("Prepared isolated browser QA directory: " + str(qa))


if __name__ == "__main__":
    main()
