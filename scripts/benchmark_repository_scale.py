"""Measure owned inert fixtures through encrypted intake and the persisted native pipeline."""
# ruff: noqa: E402

import argparse
import ctypes
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.fernet import Fernet
from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from analyzers.engine import PARSER_SIGNATURE, VERSION
from backend.db import (
    Base,
    Grant,
    Organization,
    ParserArtifact,
    Record,
    Repository,
    SourceInventory,
    SourceInventoryFile,
    User,
    make_engine,
)
from backend.execution_clock import active_time
from backend.jobs import execute_analysis
from backend.process_limits import self_limits
from backend.repository_store import BlobStore, RepositoryFiles, capture


def peak_memory():
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("page_faults", wintypes.DWORD),
                *[
                    (name, ctypes.c_size_t)
                    for name in [
                        "peak_working_set",
                        "working_set",
                        "peak_paged_pool",
                        "paged_pool",
                        "peak_nonpaged_pool",
                        "nonpaged_pool",
                        "pagefile",
                        "peak_pagefile",
                    ]
                ],
            ]

        value = Counters()
        value.cb = ctypes.sizeof(value)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(value), value.cb):
            raise OSError("Peak working-set measurement failed.")
        return value.peak_working_set
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)


def source(index, lines, changed=False):
    body = [f"def transform_{index}(value):", f"    return value + {index + (999999 if changed else 0)}"]
    body.extend(f"CONFIG_{index}_{line} = {line}" for line in range(lines - 2))
    return ("\n".join(body) + "\n").encode()


def fixture(index, args, changed=False):
    if args.fixture == "python":
        return f"services/part{index // 1000}/module{index:06}.py", source(index, args.lines, changed)
    if index == 0:
        return ".projecttrace/components.json", json.dumps(
            {
                "version": 1,
                "components": [
                    {"root": "services/" + language, "name": language} for language in ("py", "js", "ts", "tsx", "java")
                ],
            }
        ).encode()
    language = ("py", "js", "ts", "tsx", "java")[(index - 1) % 5]
    value = index + (999999 if changed else 0)
    if language == "py":
        raw = source(index, args.lines, changed)
    elif language == "java":
        body = [f"class Module{index} {{", f"  int transform(int value) {{ return value + {value}; }}"]
        body.extend(f"  static final int CONFIG_{line} = {line};" for line in range(args.lines - 3))
        raw = ("\n".join(body + ["}"]) + "\n").encode()
    else:
        signature = "value: number" if language in {"ts", "tsx"} else "value"
        body = [f"export function transform{index}({signature}) {{", f"  return value + {value};", "}"]
        body.extend(f"export const CONFIG_{line} = {line};" for line in range(args.lines - 3))
        raw = ("\n".join(body) + "\n").encode()
    return f"services/{language}/Module{index:06}.{language}", raw


def recover_owned_head(db, args, report):
    """Reuse an owned failed HEAD capture, preserving the measured initial report."""
    previous = json.loads(args.initial_report.read_text(encoding="utf-8"))
    if (
        previous.get("fixture") != "OWNED_SYNTHETIC_FIRST_PARTY_STYLE_INERT"
        or previous.get("customer_code_executed") is not False
        or previous.get("files_requested") != args.files
        or previous.get("fixture_kind") != args.fixture
        or previous.get("physical_lines_requested") != args.files * args.lines
        or previous.get("parser_signature") != PARSER_SIGNATURE
        or len(previous.get("phases", [])) != 1
    ):
        raise ValueError("HEAD recovery requires a matching owned successful initial-phase report.")
    user, repo = db.get(User, "benchmark-user"), db.get(Repository, "benchmark-repo")
    if (
        not user or not repo or user.email != "fixture@invalid.example"
        or user.organization_id != "benchmark" or repo.organization_id != "benchmark"
        or db.scalar(select(func.count()).select_from(User)) != 1
        or db.scalar(select(func.count()).select_from(Repository)) != 1
        or db.scalar(select(func.count()).select_from(Organization)) != 1
    ):
        raise ValueError("HEAD recovery accepts only the isolated script-owned fixture database.")
    snapshots = db.execute(select(Record.id, Record.data["source_inventory_id"].as_string()).where(
        Record.kind == "snapshot", Record.organization_id == "benchmark", Record.repository_id == repo.id
    )).all()
    initial = previous["phases"][0]
    if (
        len(snapshots) != 1 or snapshots[0].id != initial.get("snapshot_id")
        or initial.get("state") not in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}
        or initial.get("files_discovered") != args.files
        or initial.get("physical_lines") != args.files * args.lines
    ):
        raise ValueError("HEAD recovery requires exactly the reported committed initial snapshot.")
    jobs = list(db.scalars(select(Record).where(Record.kind == "job")))
    completed = [j for j in jobs if j.data.get("state") in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}]
    if (
        not 2 <= len(jobs) <= 10 or len(completed) != 1
        or completed[0].data.get("snapshot_id") != snapshots[0].id
        or any(j.organization_id != "benchmark" or j.repository_id != repo.id
               or j.data.get("source") != "INVENTORY"
               or j.data.get("state") not in {"FAILED", "INTERRUPTED", "COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}
               for j in jobs)
        or db.scalar(select(func.count()).select_from(Record)) != initial["persisted_records"]
        + len(jobs) - len(previous.get("retained_prior_attempts", [])) - 1
    ):
        raise ValueError("HEAD recovery requires retained terminal attempts without extra committed output.")
    inventories = list(db.scalars(select(SourceInventory)))
    if len(inventories) != 2 or any(
        (row.organization_id, row.repository_id) != ("benchmark", repo.id)
        or row.data.get("source") != "OWNED_BENCHMARK" or row.data.get("files") != args.files
        for row in inventories
    ):
        raise ValueError("HEAD recovery requires exactly the owned BASE and failed HEAD inventories.")
    head = next(row for row in inventories if row.id != snapshots[0][1])
    for inventory in inventories:
        expected = dict(db.execute(select(SourceInventoryFile.path, SourceInventoryFile.digest).where(
            SourceInventoryFile.inventory_id == inventory.id
        )).all())
        regenerated = {path: hashlib.sha256(raw).hexdigest() for path, raw in (
            fixture(i, args, inventory.id == head.id and 0 < i <= 8) for i in range(args.files)
        )}
        if expected != regenerated:
            raise ValueError("Every captured BASE/HEAD path and hash must match the generated owned fixture.")
    # Control the eight-file experiment in this isolated fixture only. Retain all
    # prior jobs/output and all unchanged artifacts; expose the eviction count.
    changed_hashes = [hashlib.sha256(fixture(i, args, True)[1]).hexdigest() for i in range(1, 9)]
    predicate = (ParserArtifact.organization_id == "benchmark",
                 ParserArtifact.content_hash.in_(changed_hashes), ParserArtifact.parser_version == PARSER_SIGNATURE)
    removed = db.scalar(select(func.count()).select_from(ParserArtifact).where(*predicate))
    if not 0 <= removed <= 8:
        raise ValueError("Unexpected changed-artifact scope in owned HEAD recovery.")
    db.execute(delete(ParserArtifact).where(*predicate))
    initial = {**initial, "implementation_hashes": previous["implementation_hashes"],
               "implementation_scope": "HISTORICAL_SUCCESSFUL_INITIAL_PHASE_RETAINED_UNCHANGED"}
    report["phases"].append(initial)
    report["implementation_hash_scope"] = "CURRENT_RECOVERED_HEAD_ONLY_INITIAL_HAS_OWN_HISTORICAL_HASHES"
    report["retained_prior_attempts"] = [{"state": j.data.get("state"), "error_type": j.data.get("error_type")} for j in jobs]
    report["owned_changed_artifacts_removed_for_eight_file_experiment"] = removed
    report["retained_head_capture_seconds_historical"] = head.data["inventory_ms"] / 1000
    report["recovery_baseline_database_bytes"] = (args.work_dir / "benchmark.db").stat().st_size
    report["limitations"].append(
        "Initial timing retains its original implementation hashes. HEAD reuses the failed attempt's fully hash-validated capture; near-zero intake is reference reuse, not capture throughput. Only the eight owned changed-file artifacts are evicted to measure 49,992 unchanged hits/eight misses. Earlier failed attempts remain stored. Cold completion throughput is UNMEASURED."
    )
    db.commit()
    return user, repo, snapshots[0].id, head


def measure(args):
    workspace = args.work_dir.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    database = workspace / "benchmark.db"
    recovering = args.resume_initial or args.resume_captured or args.resume_head_captured
    if database.exists() and not recovering:
        raise ValueError("Use a fresh benchmark directory; existing results are preserved.")
    if args.resume_head_captured and not database.exists():
        raise ValueError("A persisted owned BASE/HEAD fixture is required for recovery.")
    if args.resume_initial and not database.exists():
        raise ValueError("A persisted owned initial benchmark is required for recovery.")
    if args.resume_captured and not database.exists():
        raise ValueError("An interrupted owned captured inventory is required for recovery.")
    os.environ["SOURCE_BLOB_DIR"] = str(workspace / ("recovered-blobs" if args.resume_initial else "blobs"))
    os.environ["SOURCE_UPLOAD_DIR"] = str(workspace / "uploads")
    key_path = workspace / "private-benchmark.key"
    if recovering and not key_path.is_file():
        raise ValueError("Owned recovery requires its retained private benchmark key.")
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
        key_path.chmod(0o600)
    os.environ["ANALYSIS_INPUT_KEY"] = key_path.read_text().strip()
    os.environ["REPOSITORY_ANALYSIS_SECONDS"] = "3600"
    engine = make_engine("sqlite:///" + str(database))
    if not recovering:
        Base.metadata.create_all(engine)
    guard = self_limits(args.memory_mb * 1024 * 1024, 7200)
    report = {
        "state": "RUNNING",
        "recovered_initial_report": args.resume_initial or args.resume_head_captured,
        "recovered_captured_inventory": args.resume_captured or args.resume_head_captured,
        "analyzer_version": VERSION,
        "parser_signature": PARSER_SIGNATURE,
        "fixture": "OWNED_SYNTHETIC_FIRST_PARTY_STYLE_INERT",
        "files_requested": args.files,
        "fixture_languages": ["Python"]
        if args.fixture == "python"
        else ["Python", "JavaScript", "TypeScript", "TSX", "Java"],
        "fixture_kind": args.fixture,
        "physical_lines_requested": args.files * args.lines,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "implementation_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in [
                "backend/domain.py",
                "backend/jobs.py",
                "backend/repository_store.py",
                "backend/partitioned_analysis.py",
                "analyzers/engine.py",
                "backend/db.py",
                "scripts/benchmark_repository_scale.py",
                "backend/snapshot_context.py", "backend/quality_domain.py", "backend/engineering_changes.py",
            ]
        },
        "active_clock": "WINDOWS_UNBIASED_INTERRUPT_TIME_PRECISE" if os.name == "nt" else "PLATFORM_MONOTONIC",
        "database": "LOCAL_SQLITE",
        "resource_guard": guard,
        "execution_budget_seconds": 3600,
        "execution_budget_clock": "OWNED_BENCHMARK_ACTIVE_SYSTEM_TIME_PRODUCTION_UNCHANGED",
        "customer_code_executed": False,
        "external_llm_used": False,
        "phases": [],
        "limitations": [
            "Generated benchmark fixture is not a representative customer repository or production precision corpus.",
            "No live PostgreSQL/Redis/Celery/TLS staging; synchronous pipeline timings are measured separately from queue load.",
            "Memory is OS-reported process lifetime peak working set; source and observation growth are not extrapolated.",
        ],
    }

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    with sessionmaker(engine, expire_on_commit=False)() as db:
        base = None
        recovered_inventory = None
        recovered_base_id = None
        if args.resume_head_captured:
            user, repo, recovered_base_id, recovered_inventory = recover_owned_head(db, args, report)
            save()
        elif args.resume_captured:
            user, repo = db.get(User, "benchmark-user"), db.get(Repository, "benchmark-repo")
            if not user or not repo or repo.organization_id != "benchmark" or user.email != "fixture@invalid.example":
                raise ValueError("Recovery is restricted to an isolated owned benchmark.")
            inventories = list(
                db.scalars(select(SourceInventory).where(SourceInventory.organization_id == "benchmark"))
            )
            jobs = list(db.scalars(select(Record).where(Record.kind == "job", Record.organization_id == "benchmark")))
            if (
                len(inventories) != 1
                or not 1 <= len(jobs) <= 10
                or db.scalar(select(func.count()).select_from(Record)) != len(jobs)
            ):
                raise ValueError("Captured recovery requires interrupted owned jobs and no committed snapshot output.")
            recovered_inventory = inventories[0]
            if (
                recovered_inventory.data.get("source") != "OWNED_BENCHMARK"
                or recovered_inventory.data.get("files") != args.files
            ):
                raise ValueError("Captured recovery dimensions do not match the owned fixture.")
            expected = dict(
                db.execute(
                    select(SourceInventoryFile.path, SourceInventoryFile.digest).where(
                        SourceInventoryFile.inventory_id == recovered_inventory.id,
                    )
                ).all()
            )
            generated = {
                path: hashlib.sha256(raw).hexdigest() for path, raw in (fixture(i, args) for i in range(args.files))
            }
            if expected != generated:
                raise ValueError("Captured recovery content does not match every owned fixture hash.")
            for previous_job in jobs:
                if previous_job.repository_id != repo.id or previous_job.data.get("source") != "INVENTORY":
                    raise ValueError("Captured recovery jobs must belong to the isolated owned inventory.")
                if previous_job.data.get("state") not in {"FAILED", "INTERRUPTED"}:
                    raise ValueError("Only terminal failed/interrupted owned jobs can be recovered.")
            report["retained_prior_attempts"] = [
                {"state": row.data.get("state"), "error_type": row.data.get("error_type")}
                for row in jobs
            ]
            report["recovery_baseline_database_bytes"] = database.stat().st_size
            db.commit()
            report["limitations"].append(
                "The cold initial attempt was interrupted before snapshot commit. INITIAL_RECOVERY_CACHE_WARM measures a new persisted analysis using the retained encrypted inventory and compatible parser artifacts. Original cold intake/parsing/persistence totals are UNMEASURED; no interrupted timing is treated as a pass."
            )
            save()
        elif args.resume_initial:
            user, repo = db.get(User, "benchmark-user"), db.get(Repository, "benchmark-repo")
            if not user or not repo or repo.organization_id != "benchmark" or user.email != "fixture@invalid.example":
                raise ValueError("Recovery is restricted to this script's isolated owned fixture.")
            completed = list(
                db.scalars(select(Record).where(Record.kind == "job", Record.organization_id == "benchmark"))
            )
            if len(completed) != 1 or completed[0].data.get("state") not in {
                "COMPLETED",
                "COMPLETED_NO_FINDINGS",
                "PARTIAL",
            }:
                raise ValueError("Recovery requires exactly one completed owned initial job.")
            previous_job = completed[0]
            base = db.get(Record, previous_job.data["snapshot_id"])
            inventory = db.get(SourceInventory, base.data["source_inventory_id"])
            if inventory.data.get("source") != "OWNED_BENCHMARK" or inventory.data.get("files") != args.files:
                raise ValueError("Recorded inventory does not match the owned benchmark dimensions.")
            expected = dict(
                db.execute(
                    select(SourceInventoryFile.path, SourceInventoryFile.digest).where(
                        SourceInventoryFile.inventory_id == inventory.id
                    )
                ).all()
            )
            restored = time.perf_counter()

            for index in range(args.files):
                path, raw = fixture(index, args)
                if hashlib.sha256(raw).hexdigest() != expected.get(path):
                    raise ValueError("Regenerated fixture does not match the retained initial content hash.")
                BlobStore().put(db, "benchmark", raw)
            db.commit()
            report["owned_fixture_reencryption_seconds"] = round(time.perf_counter() - restored, 3)
            report["limitations"].append(
                "The original reporter failed after initial persistence; initial CPU and peak memory are unavailable. Owned fixture recovery verified every regenerated blob against its retained initial hash."
            )
            report["phases"].append(
                {
                    "phase": "INITIAL",
                    "files_discovered": inventory.data["files"],
                    "physical_lines": args.files * args.lines,
                    "inventory_seconds": inventory.data["inventory_ms"] / 1000,
                    "pipeline_seconds": previous_job.data["duration_ms"] / 1000,
                    "wall_seconds": None,
                    "cpu_seconds": None,
                    "peak_working_set_bytes": None,
                    "database_bytes": database.stat().st_size,
                    "persisted_records": db.scalar(select(func.count()).select_from(Record)),
                    "source_storage": base.data.get("source_storage"),
                    "state": base.data["status"],
                    "changed_files": len(base.data["changed_files"]),
                    "gate": base.data["gate"]["overall"],
                    "snapshot_id": base.id,
                    "coverage": base.data["analysis_coverage"]["summary"],
                    "stages": previous_job.data["stages"],
                }
            )
            save()
            print(
                json.dumps({"phase": "INITIAL_RECOVERED", "pipeline_seconds": previous_job.data["duration_ms"] / 1000}),
                flush=True,
            )
        else:
            db.add(Organization(id="benchmark", name="Owned benchmark"))
            db.flush()
            user = User(
                id="benchmark-user",
                organization_id="benchmark",
                email="fixture@invalid.example",
                password_hash="unused",
                role="ORG_OWNER",
            )
            repo = Repository(
                id="benchmark-repo",
                organization_id="benchmark",
                name="Scale fixture",
                system="Benchmark",
                component="Owned module",
                owner="Benchmark",
                provider="LOCAL",
            )
            db.add_all([user, repo])
            db.flush()
            db.add(Grant(user_id=user.id,repository_id=repo.id))
            db.commit()
        if isinstance(base, Record):
            db.expunge(base)
            base = SimpleNamespace(id=base.id)
        phases = ["EIGHT_FILE_HEAD"] if args.resume_initial else ["INITIAL", "EIGHT_FILE_HEAD"]
        if args.resume_captured:
            phases = ["INITIAL_RECOVERY_CACHE_WARM", "EIGHT_FILE_HEAD"]
        if args.resume_head_captured:
            phases = ["EIGHT_FILE_HEAD_RECOVERY_CAPTURED"]
        for phase in phases:
            started, cpu, active_started = time.perf_counter(), time.process_time(), active_time()
            inventory = (
                recovered_inventory
                if phase in {"INITIAL_RECOVERY_CACHE_WARM", "EIGHT_FILE_HEAD_RECOVERY_CAPTURED"}
                else capture(
                    db,
                    user.organization_id,
                    repo,
                    (
                        fixture(index, args, phase == "EIGHT_FILE_HEAD" and 0 < index <= 8)
                        for index in range(args.files)
                    ),
                    source="OWNED_BENCHMARK",
                )
            )
            intake_seconds = time.perf_counter() - started
            active_intake_seconds = active_time() - active_started
            pipeline_active_started = active_time()
            pipeline_wall_started = time.perf_counter()
            files = RepositoryFiles(db, user.organization_id, repo.id, inventory.id)
            snapshot, job = execute_analysis(
                db, user, repo, files, base_id=recovered_base_id or (base.id if base else None), _elapsed_clock=active_time
            )
            details = {
                "phase": phase,
                "files_discovered": inventory.data["files"],
                "physical_lines": sum(
                    row[0].get("physical_lines") or 0
                    for row in db.execute(
                        select(SourceInventoryFile.data).where(SourceInventoryFile.inventory_id == inventory.id)
                    )
                ),
                "inventory_seconds": round(intake_seconds, 3),
                "inventory_active_seconds": round(active_intake_seconds, 3),
                "pipeline_active_seconds": round(active_time() - pipeline_active_started, 3),
                "active_wall_seconds": round(active_time() - active_started, 3),
                "system_suspend_seconds": round(
                    max(0, (time.perf_counter() - started) - (active_time() - active_started)), 3
                ),
                "pipeline_seconds": round(time.perf_counter() - pipeline_wall_started, 3),
                "wall_seconds": round(time.perf_counter() - started, 3),
                "cpu_seconds": round(time.process_time() - cpu, 3),
                "peak_working_set_bytes": peak_memory(),
                "database_bytes": database.stat().st_size,
                "persisted_records": db.scalar(select(func.count()).select_from(Record)),
                "source_storage": snapshot.data.get("source_storage"),
                "state": snapshot.data["status"],
                "changed_files": len(snapshot.data["changed_files"]),
                "claims": snapshot.data["claim_extraction"],
                "gate": snapshot.data["gate"]["overall"],
                "snapshot_id": snapshot.id,
                "coverage": snapshot.data["analysis_coverage"]["summary"],
                "stages": job.data["stages"],
                "execution_workers": 1,
                "queue_delay_seconds": None,
                "helper_cpu_seconds": None,
            }
            report["phases"].append(details)
            save()
            print(
                json.dumps(
                    {
                        "phase": phase,
                        "wall_seconds": details["wall_seconds"],
                        "peak_bytes": details["peak_working_set_bytes"],
                        "cache": details["source_storage"],
                    }
                ),
                flush=True,
            )
            base = SimpleNamespace(id=snapshot.id)
            db.expunge(snapshot)
            del snapshot, job, files
        report["state"] = "MEASURED_SYNTHETIC_LOCAL"
        save()
    engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, required=True)
    parser.add_argument("--lines", type=int, default=10)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-initial", action="store_true")
    parser.add_argument("--resume-captured", action="store_true")
    parser.add_argument("--resume-head-captured", action="store_true")
    parser.add_argument("--initial-report", type=Path)
    parser.add_argument("--memory-mb", type=int, default=1536)
    parser.add_argument("--fixture", choices=("python", "mixed"), default="python")
    args = parser.parse_args()
    if sum((args.resume_initial, args.resume_captured, args.resume_head_captured)) > 1:
        parser.error("Choose only one owned recovery mode.")
    if args.resume_head_captured and (not args.initial_report or not args.initial_report.is_file()):
        parser.error("Captured HEAD recovery requires --initial-report with the preserved owned measurement.")
    if not 8 <= args.files <= 100000 or not 2 <= args.lines <= 1000:
        parser.error("Fixture dimensions exceed their owned benchmark budget.")
    attempt_wall_started, attempt_active_started, attempt_cpu_started = (
        time.perf_counter(), active_time(), time.process_time()
    )
    try:
        measure(args)
    except Exception as error:
        if args.output.exists():
            failed = json.loads(args.output.read_text(encoding="utf-8"))
            failed.update(
                state="FAILED",
                error_type=type(error).__name__,
                failed_attempt_wall_seconds=round(time.perf_counter() - attempt_wall_started, 3),
                failed_attempt_active_seconds=round(active_time() - attempt_active_started, 3),
                failed_attempt_cpu_seconds=round(time.process_time() - attempt_cpu_started, 3),
                failed_attempt_peak_working_set_bytes=peak_memory(),
            )
            args.output.write_text(json.dumps(failed, indent=2), encoding="utf-8")
        raise
