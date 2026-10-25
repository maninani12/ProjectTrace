"""Full authorized ZIP capture/analysis, with receipts even on failure.

Requires Linux parser isolation and a verified cgroup envelope. Does not run
repository scripts, package installers, hooks, builds or tests from the input.
Cold failure blocks all dependent qualification scenarios, without fake passes.
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

from scripts.scale_linux_resources import memory

ORIGIN = "https://github.com/maninani12/OpenMetadata"
COMMIT = "b1fab2bc21c63335dead4daaaa28194c9878e9bf"
ARCHIVE_SHA = "95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257"
HISTORICAL_SHA = "027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914"
LIMIT = 768_000_000


def write(path, value):
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "qualification.json").exists():
        parser.error("Use a fresh qualification directory.")
    with args.archive.open("rb") as stream:
        archive_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    if archive_sha != ARCHIVE_SHA:
        raise ValueError("Qualification archive differs from pinned replacement.")
    if os.environ.get("PROJECTTRACE_PARSER_ISOLATION") != "required":
        raise ValueError("Qualification requires active SEC-002 Linux isolation.")
    initial = memory()
    if not args.manifest_only and (initial.get("memory.max") != LIMIT or initial.get("memory.swap.max") != 0):
        raise ValueError("Qualification requires actual 768000000-byte cgroup with swap disabled.")
    receipt = {"schema": "projecttrace-scale-qualification-v1", "verdict": "BLOCKED", "origin": ORIGIN,
               "source_commit": COMMIT, "archive_sha256": archive_sha, "archive_bytes": args.archive.stat().st_size,
               "historical_archive_sha256": HISTORICAL_SHA, "historical_input_reproduced": False,
               "python": sys.version, "platform": platform.platform(), "initial_memory": initial,
               "service_boundary": "SQLite in same cgroup; PostgreSQL/Redis acceptance separate; not broker recovery qualification",
               "scenarios": {name: "NOT_RUN" for name in ("cold", "warm", "one_file_change", "multi_file_change",
                             "exhaustion_recovery", "cancellation", "fresh_worker_recovery", "concurrent_tenants")}}
    write(output / "qualification.json", receipt)
    os.environ.update(DATABASE_URL="sqlite:///" + str(output / "qualification.db"), APP_ENV="demo", JOB_MODE="sync",
                      REPOSITORY_ANALYSIS_SECONDS="1800", SOURCE_BLOB_DIR=str(output / "blobs"),
                      SOURCE_UPLOAD_DIR=str(output / "uploads"), ANALYSIS_KEY_FILE=str(output / "key"))
    # Never persist this key in public CI artifacts. The encrypted objects and DB
    # also remain private; exported evidence is counts/hashes only.
    from cryptography.fernet import Fernet
    os.environ["ANALYSIS_INPUT_KEY"] = Fernet.generate_key().decode()
    from sqlalchemy import func, select

    from analyzers import sandbox
    from backend.db import Base, Grant, Organization, ParserArtifact, Record, Repository, Session, User, engine
    from backend.jobs import execute_analysis
    from backend.repository_store import RepositoryFiles, archive_items, capture, limits
    sandbox.require_runtime()
    Base.metadata.create_all(engine)
    stage = ["INITIALIZING"]
    stop = threading.Event()
    maxima = {}

    def sample():
        with (output / "memory.jsonl").open("a") as stream:
            while not stop.is_set():
                row = {"elapsed_seconds": round(time.monotonic() - started, 3), "stage": stage[0], **memory()}
                for key in ("coordinator_rss_bytes", "child_rss_bytes", "namespace_rss_bytes", "memory.current", "memory.peak"):
                    value = row.get(key)
                    if isinstance(value, int):
                        maxima[key] = max(maxima.get(key, 0), value)
                stream.write(json.dumps(row) + "\n")
                stream.flush()
                stop.wait(0.25)
    started = time.monotonic()
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    try:
        if args.manifest_only:
            from analyzers.archive_transport import archive_items as isolated_items
            stage[0] = "FULL_ARCHIVE_MANIFEST"
            count, expanded, digest = 0, 0, hashlib.sha256()
            with args.archive.open("rb") as source, (output / "manifest.jsonl").open("w") as target:
                with closing(isolated_items(source, limits(), manifest_only=True)) as rows:
                    for path, data in rows:
                        canonical = json.dumps({"path": path, **data}, sort_keys=True, separators=(",", ":")) + "\n"
                        target.write(canonical)
                        digest.update(canonical.encode())
                        count += 1
                        expanded += data["bytes"]
            receipt["manifest"] = {"files": count, "expanded_bytes": expanded, "sha256": digest.hexdigest(),
                                   "policy": "Every non-directory ZIP member, including link bytes and oversized files; no extraction"}
            if count != 21_636 or expanded != 330_420_155:
                raise ValueError("Pinned workload inventory differs from expected identity.")
            receipt["manifest_state"] = "PASSED"
            # Manifest success is not SCALE qualification.
            receipt["verdict"] = "PARTIALLY QUALIFIED"
            return
        with Session() as db:
            db.add(Organization(id="scale-owned", name="Owned qualification tenant"))
            db.flush()
            user = User(id="scale-owned", organization_id="scale-owned", email="scale@example.invalid",
                        password_hash="unused-owned-fixture", role="ORG_OWNER")
            repo = Repository(id="scale-owned", organization_id="scale-owned", name="Pinned static input",
                              system="Qualification", component="OpenMetadata", owner="Owned qualification", provider="LOCAL")
            db.add_all([user, repo])
            db.flush()
            db.add(Grant(user_id=user.id, repository_id=repo.id))
            db.commit()
            stage[0] = "CAPTURING"
            with args.archive.open("rb") as stream, closing(archive_items(stream, sort_paths=True)) as rows:
                inventory = capture(db, user.organization_id, repo, rows, source="PINNED_AUTHORIZED_COMMIT_ZIP")
            db.commit()
            files = RepositoryFiles(db, user.organization_id, repo.id, inventory.id)
            receipt["inventory"] = {"file_count": len(files.entries), "retained_text": len(files),
                                    "declared_bytes": sum(row["bytes"] for row in files.entries.values())}
            if receipt["inventory"]["file_count"] != 21_636:
                raise ValueError("Capture omitted pinned workload entries.")
            write(output / "qualification.json", receipt)
            # Observe actual production stage transitions without replacing any
            # analyzer, verifier, publication, fence or cancellation callbacks.
            from analyzers.performance import Performance
            original = Performance.switch
            def measured_switch(owner, state):
                stage[0] = state
                return original(owner, state)
            Performance.switch = measured_switch
            try:
                for number, mode in enumerate(("cold", "warm")):
                    receipt["scenarios"][mode] = "RUNNING"
                    write(output / "qualification.json", receipt)
                    snapshot, job = execute_analysis(db, user, repo, files, git_commit=COMMIT,
                                                     branch="qualification-" + mode)
                    receipt["scenarios"][mode] = job.data["state"]
                    receipt.setdefault("outputs", {})[mode] = {
                        "files": snapshot.data["file_count"], "claims": len(snapshot.data.get("claims", [])),
                        "findings": len(snapshot.data.get("findings", [])),
                        "metrics": len(snapshot.data.get("quality_metrics", [])),
                        "parser_artifacts": db.scalar(select(func.count()).select_from(ParserArtifact)),
                        "performance": job.data.get("performance", {}),
                    }
                    write(output / "qualification.json", receipt)
                    del snapshot, job
                    db.expunge_all()
                    import gc
                    gc.collect()
                    user, repo = db.get(User, "scale-owned"), db.get(Repository, "scale-owned")
            finally:
                Performance.switch = original
            # Remaining scenarios must be implemented and verified before this
            # driver can ever award full qualification, even if cold/warm pass.
            receipt["verdict"] = "PARTIALLY QUALIFIED"
            raise RuntimeError("Remaining qualification scenarios are NOT_RUN.")
    except BaseException as error:
        receipt["error_type"] = type(error).__name__  # no source/traceback/key leakage
        receipt["error_code"] = getattr(error, "code", None)
        receipt["failed_stage"] = stage[0]
        try:
            with Session() as db:
                from backend.generation_models import AnalysisGeneration, PublishedGeneration
                receipt["failure_integrity"] = {
                    "published_pointers": db.scalar(select(func.count()).select_from(PublishedGeneration)),
                    "published_generations": db.scalar(select(func.count()).select_from(AnalysisGeneration).where(AnalysisGeneration.state == "PUBLISHED")),
                    "parser_artifacts": db.scalar(select(func.count()).select_from(ParserArtifact)),
                    "jobs": [{"state": r.data.get("state"), "stage": r.data.get("stage"),
                              "error_code": r.data.get("error_code")} for r in db.scalars(select(Record).where(Record.kind == "job"))],
                    "sqlite_integrity": db.connection().exec_driver_sql("PRAGMA integrity_check").scalar(),
                    "foreign_key_violations": len(db.connection().exec_driver_sql("PRAGMA foreign_key_check").all()),
                }
        except Exception:
            receipt["failure_integrity"] = "POST_FAILURE_READ_FAILED"
        raise
    finally:
        stop.set()
        thread.join(timeout=5)
        receipt.update(duration_seconds=round(time.monotonic() - started, 3), sampled_maxima=maxima, final_memory=memory())
        write(output / "qualification.json", receipt)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Sanitized receipt is retained; no imported source/credentials in logs.
        print("SCALE-001 qualification blocked; inspect qualification.json", file=sys.stderr)
        raise SystemExit(1) from None
