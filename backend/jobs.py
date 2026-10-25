"""Durable local analysis lifecycle. No raw source or exception text is logged."""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from backend.db import Record, now
from backend.domain import add, audit, persist_analysis
from backend.intake_errors import IntakeError

STATES = {
    "NO_REPOSITORY",
    "READY",
    "QUEUED",
    "FETCHING",
    "VALIDATING",
    "PARSING",
    "ANALYZING",
    "BUILDING_EVIDENCE",
    "EXTRACTING_CLAIMS",
    "VERIFYING",
    "CORRELATING",
    "FINALIZING",
    "COMPLETED",
    "COMPLETED_NO_FINDINGS",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
}
TERMINAL = {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL", "FAILED", "CANCELLED"}
log = logging.getLogger("projecttrace.pipeline")


def inventory_time_budget():
    seconds = int(os.getenv("REPOSITORY_ANALYSIS_SECONDS", "900"))
    if not 120 <= seconds <= 3600:
        raise ValueError("Repository analysis time budget must be between 120 and 3600 seconds.")
    return seconds


def job_time_budget(job):
    return inventory_time_budget() if job.data.get("source") in {"INVENTORY", "GITHUB", "PUBLIC_GITHUB"} else 120


def execute_analysis(db, user, repo, files, *, request_id=None, job=None, _elapsed_clock=None, **options):
    from backend.repository_store import RepositoryFiles

    inventory_input = isinstance(files, RepositoryFiles)
    if job is None:
        from backend.queue import check_capacity
        check_capacity(db,user,repo,source="INVENTORY" if inventory_input else "FILES")
    job = job or add(
        db,
        user.organization_id,
        repo.id,
        "job",
        {
            "state": "QUEUED",
            "stage": "QUEUED",
            "started_at": now(),
            "finished_at": None,
            "user_id": user.id,
            "request_id": request_id,
            "branch": options.get("branch", "main"),
            "warnings": [],
            "errors": [],
            "stages": [],
            "execution": "PARTITIONED_SYNCHRONOUS" if inventory_input else "BOUNDED_SYNCHRONOUS",
            "source": "INVENTORY" if inventory_input else "FILES",
        },
    )
    db.commit()  # Repository + job survive a failed analysis; snapshot output remains atomic.
    job_id, organization_id, repository_id = job.id, user.organization_id, repo.id
    owned_token = job.data.get("worker_token")
    clock = _elapsed_clock or time.perf_counter
    stages, started = [], clock()
    output_started, completed_analysis = False, None
    from analyzers.performance import Performance
    performance = Performance()
    job.data = {
        **{k: v for k, v in job.data.items() if k != "completed_analysis"},
        "started_at": now(),
        "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=job_time_budget(job) + 30)).isoformat(),
    }

    def check_current():
        from backend.scheduling import ensure_current
        elapsed = round((clock() - started) * 1000, 2)
        if elapsed > job_time_budget(job) * 1000:
            raise TimeoutError("Analysis exceeded its configured execution time budget.")
        # A budget/lease check must not implicitly flush all dirty correlation
        # rows. Explicit publication batches retain the transaction's ordering.
        with db.no_autoflush:
            ensure_current(db, job, renew_seconds=job_time_budget(job))
        return elapsed

    def retain_completed_analysis(result, content):
        nonlocal completed_analysis
        coverage = result.get("analysis_coverage", {})
        completed_analysis = {
            "schema": "projecttrace-completed-analysis-v1",
            "result_scope": "COMPLETED_STATIC_ANALYSIS_SUMMARY",
            "publication_state": "UNPUBLISHED",
            "source_inventory_id": getattr(content, "inventory_id", None),
            "analysis_seconds": round(clock() - started, 6),
            "analyzer_results": {
                "files": len(content), "claims": len(result["claims"]),
                "native_findings": len(result["findings"]), "dependencies": len(result["dependencies"]),
                "reused_files": result["reused_files"], "warning_count": len(result["warnings"]),
            },
            # Generated counts only. The original inventory retains every path,
            # exclusion and diagnostic; no source or unfinished graph is copied.
            "coverage": {
                "schema": coverage.get("schema"), "summary": coverage.get("summary", {}),
                "languages": coverage.get("languages", [])[:100],
                "languages_truncated": len(coverage.get("languages", [])) > 100,
                "runtime_evidence": "UNOBSERVED", "customer_code_executed": False,
            },
        }
        job.data = {**job.data, "completed_analysis": completed_analysis}

    def stage(state):
        nonlocal output_started
        elapsed = check_current()
        performance.switch(state)
        stages.append({"stage": state, "at": now(), "elapsed_ms": elapsed})
        job.data = {
            **job.data,
            "state": state,
            "stage": state,
            "stages": stages[:],
            "performance": performance.snapshot(),
            "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=job_time_budget(job) + 30)).isoformat(),
        }
        # Publish native stages durably without committing partial graph output.
        if not output_started:
            db.commit()
        if state == "BUILDING_EVIDENCE":
            output_started = True
            # Deadline/lease checks continue inside long publication loops.
            # They do not commit the partially built graph.
            db.info["analysis_output_checkpoint"] = check_current
        log.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "job_id": job_id,
                    "organization_id": organization_id,
                    "repository_id": repository_id,
                    "snapshot_id": job.data.get("snapshot_id"),
                    "analyzer": "ProjectTrace native",
                    "duration_ms": elapsed,
                    "status": state,
                }
            )
        )

    stage.performance = performance
    check_current.performance = performance
    stage.job_id = job_id
    stage.retain_completed_analysis = retain_completed_analysis
    def load_checkpoint(signature):
        from backend.analysis_checkpoints import load
        check_current()
        result = load(db, job_id, organization_id, repository_id, signature)
        if result is not None:
            performance.count("global_analysis_checkpoint_hits")
        return result

    def save_checkpoint(signature, result):
        from backend.analysis_checkpoints import save
        saved = save(db, job_id, organization_id, repository_id, signature, result, check_current)
        performance.count("global_analysis_checkpoints_saved" if saved else "global_analysis_checkpoints_oversize")
        if not saved and inventory_input and os.getenv("PROJECTTRACE_GENERATION_PUBLICATION", "1") == "1":
            raise IntakeError("GLOBAL_CHECKPOINT_BUDGET", "Completed analysis exceeds the durable checkpoint byte budget.",
                              budget="ANALYSIS_CHECKPOINT_MAX_BYTES", maximum=int(os.getenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "64000000")),
                              remediation="Inspect analysis volume and stage storage; retained source inventory remains available.")

    stage.load_analysis_checkpoint = load_checkpoint
    stage.save_analysis_checkpoint = save_checkpoint
    def prepare_publication(files, signature, result):
        from backend.publication_units import prepare
        return prepare(db, job_id, files, signature, result, check_current)

    stage.prepare_publication = prepare_publication
    def begin_generation(signature, *, branch="main", inventory_id, content_key):
        from backend.generations import Generation
        return Generation(db, job_id, organization_id, repository_id, signature, check_current,
                          branch=branch, inventory_id=inventory_id, content_key=content_key)

    stage.begin_generation = begin_generation
    try:
        stage("VALIDATING")
        content = files() if callable(files) else files
        snapshot = persist_analysis(db, user, repo, content, progress=stage, job_id=job.id, **options)
        state = snapshot.data["status"]
        output_started = True
        stage("FINALIZING")
        generation = db.info.get("analysis_generation")
        if generation:
            generation.validate(snapshot)
        stage(state)
        job.data = {
            **job.data,
            "snapshot_id": snapshot.id,
            "state": state,
            "stage": state,
            "finished_at": now(),
            "duration_ms": round((clock() - started) * 1000, 2),
            "warnings": snapshot.data.get("warnings", []),
            "errors": [],
            "analyzer_results": snapshot.data.get("analyzer_results", {}),
            "engines": snapshot.data.get("engines", {}),
            "performance": performance.snapshot(),
            "claim_extraction": snapshot.data.get("claim_extraction", {}),
            **({"completed_analysis": {**completed_analysis, "publication_state": "PUBLISHED", "snapshot_id": snapshot.id}}
               if completed_analysis else {}),
        }
        from backend.db import AnalysisCheckpoint
        retained_checkpoint = db.get(AnalysisCheckpoint, job_id)
        if retained_checkpoint:
            db.delete(retained_checkpoint)
        from sqlalchemy import delete

        from backend.db import PublicationUnit
        db.execute(delete(PublicationUnit).where(PublicationUnit.job_id == job_id,
                   PublicationUnit.organization_id == organization_id, PublicationUnit.repository_id == repository_id))
        if generation:
            generation.promote(snapshot)
            job.data = {**job.data, "generation_id": generation.row.id,
                        "generation_receipts_reused": generation.reused,
                        "generation_batches": generation.batches,
                        "generation_maximum_batch_rows": generation.maximum_batch_rows}
        db.commit()
        if generation:
            generation.published = True
        return snapshot, job
    except Exception as error:
        interrupted_generation = db.info.get("analysis_generation")
        interrupted_generation_id = interrupted_generation.generation_id if interrupted_generation else None
        from backend.generations import clear as clear_generation
        clear_generation(db)
        from backend.analysis_budget import clear
        clear(db)
        from backend.scheduling import JobCancelled, owns
        db.rollback()
        if interrupted_generation_id:
            from backend.generation_models import AnalysisGeneration
            published = db.get(AnalysisGeneration, interrupted_generation_id)
            terminal_job = db.get(Record, job_id)
            if published and published.state == "PUBLISHED" and terminal_job.data.get("snapshot_id") == published.snapshot_id and terminal_job.data.get("state") in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}:
                # A lost commit acknowledgement cannot turn a committed,
                # consistent generation into a fabricated FAILED job.
                return db.get(Record, published.snapshot_id), terminal_job
        if not owns(db, job_id, owned_token):
            raise JobCancelled("Worker lease was replaced; this attempt cannot modify the job.") from None
        job = db.get(Record, job_id)
        from analyzers.observation_store import ObservationBudgetExceeded
        from analyzers.sandbox import SandboxFailure
        failure = error if isinstance(error, IntakeError) else (
            IntakeError("PARSER_ISOLATION_" + error.code, "Required parser isolation failed; unfinished analysis was not published.",
                        remediation="Verify Linux Landlock ABI 3+, libseccomp, allowed container syscalls and immutable parser runtime; inspect SEC-002 operations guidance.")
            if isinstance(error, SandboxFailure) else
            (
            IntakeError("ANALYSIS_TIME_BUDGET", "Analysis exceeded its configured execution time budget.",
                        budget="REPOSITORY_ANALYSIS_SECONDS", actual=round(clock() - started, 2), maximum=job_time_budget(job),
                        remediation="Inspect partial parser diagnostics and import a smaller source component; retained inventory remains available.")
            if isinstance(error, TimeoutError) else None
            )
        )
        if isinstance(error, ObservationBudgetExceeded):
            failure = IntakeError("ANALYSIS_OBSERVATION_BUDGET",
                "Analysis exceeded its encrypted observation spill budget; unfinished output was not published.",
                remediation="Inspect per-stage observation volume and provision bounded scratch storage; retain the source inventory for retry.")
        job.data = {
            **{k: v for k, v in job.data.items() if k != "files"},
            "state": "CANCELLED" if isinstance(error, JobCancelled) else "FAILED",
            "performance": performance.snapshot(),
            **({"completed_analysis": completed_analysis} if completed_analysis else {}),
            "stage": stages[-1]["stage"] if stages else "PARSING",
            "stages": stages,
            "finished_at": now(),
            "error_type": type(error).__name__,
            **({"error_code": failure.code, "error_detail": failure.detail()} if failure else {}),
            "errors": [
                failure.message if failure else "Analysis failed. Check supported input limits; consult the request/job IDs for diagnostics."
            ],
            "duration_ms": round((clock() - started) * 1000, 2),
        }
        audit(
            db, user, "ANALYSIS_FAILED", job.id, {"error_type": type(error).__name__, "request_id": request_id}, repo.id
        )
        db.commit()
        log.error(
            json.dumps(
                {
                    "request_id": request_id,
                    "job_id": job_id,
                    "organization_id": organization_id,
                    "repository_id": repository_id,
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                }
            )
        )
        raise
    finally:
        from backend.generations import clear as clear_generation
        clear_generation(db)
        from backend.analysis_budget import clear
        clear(db)
