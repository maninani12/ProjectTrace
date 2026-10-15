# Durable global-computation checkpoint: implementation and qualification

Status: partial implementation of Priority 1. This is not the final product handoff. The full resumable pipeline and Developer Onboarding & Knowledge Transfer remain incomplete. Pilot release remains BLOCKED.

## Implemented

Migration 0021 adds private `analysis_checkpoints` and a unique scoped-record index. A composite foreign key binds every checkpoint to its job, organization and repository. These receipts are not Records and cannot be selected through the generic domain-record API. They contain an authenticated encrypted envelope and SHA-256 digest. They expire no later than 72 hours or the retained analysis input. Existing expiry maintenance removes expired receipts; successful publication deletes the receipt in the publication transaction.

`execute_analysis` now provides checkpoint load/save callbacks to `persist_analysis`. Once global analysis returns, the result is checkpointed before BUILDING_EVIDENCE. A retry recomputes the source/configuration signature and may load only the same job's matching receipt. Signature inputs include tenant, repository, branch, content digest, analyzer/parser versions, quality profile, base snapshot, advisory cache, Git revision and source inventory identity. Changed signatures rerun computation. File identities are stored as paths, not serialized live RepositoryFiles objects; publication reads source from the original authorized inventory.

Checkpoint writes renew/check the worker lease and verify scope before commit. The existing lease fixes are preserved. A configurable serialization ceiling (default 64 MB, allowed 1–256 MB) bounds the receipt buffer. Oversized results fall back to the existing atomic execution and increment an explicit oversize metric; they are never truncated into valid receipts. This fallback does NOT establish large-repository resumability. Corrupt/envelope-mismatched receipts fail closed. No customer source is executed.

The receipt commit contains completed analysis only. Evidence/graph output remains in the original output transaction: an exception rolls back the snapshot and graph, leaving the completed computation available for retry. This implementation resumes completed global computation; it does not yet checkpoint individual correlation/evidence/graph units or resume partly constructed graph output.

## Root causes corrected during implementation

- Global analyzer results included live RepositoryFiles objects. Serializing that object failed. Store only ordered file paths; retain original source inventory separately.
- Looking up retained input after adding an incomplete receipt caused SQLAlchemy autoflush with missing required fields. Lookup now precedes construction of the receipt. The restart/real-pipeline tests exercise this ordering.
- ORM-only scope validation would not protect a direct SQL insert. A composite database foreign key now rejects tenant substitution.
- Failed synchronous analyses have no AnalysisInput row to drive cleanup. Independent checkpoint expiry permits receipt maintenance without that row.

## Spring PetClinic real-source recovery

Input: spring-projects/spring-petclinic, commit `500158f732419217507c7656904b8e6aa1bcc0d6`; ZIP SHA-256 `160c4b3eec1cdda42e6821a8e1a3e8d9b446c52423bd1d8ef14d19a8ee5e770f`. No source modules were removed or executed.

Capture inventory: 132 entries; 121 retained text entries; 70 received native scans; 50/91 source files parsed within declared scope. Result: PARTIAL. The result contains 8 claims, 16 findings, 35 dependencies, 70 evidence records, 309 graph nodes and 533 edges. These are actual analyzer outputs, not independently validated accuracy claims.

A controlled interruption at the final snapshot-projection boundary rolled back the incomplete snapshot. A fresh database session resumed with the native/global analyzer patched to fail if called; publication succeeded without calling it. Exactly one snapshot was published, and its checkpoint was deleted. Cold capture/analysis through interrupted publication: 4.9288 s. Retry publication: 1.0987 s. Peak memory was not measured. This is a small repository test, not OpenMetadata scale qualification or a process-kill/Redis recovery test.

Two GitHub Actions YAML files reported infrastructure parsing limits; unsupported/partial quality scope was disclosed. Full details and exact identities are in `petclinic-recovery-result.json`. A SQLite online backup was reopened independently, passed integrity_check and matched the source database record count. This does not qualify PostgreSQL disaster recovery.

## Migration and rollback

No live/user database was migrated. Tests create disposable databases and upgrade/downgrade them. The previous populated-snapshot preservation test continues to check existing records survive upgrade. The migration head expectation changes from 0020 to 0021 because a legitimate additive migration was introduced. Existing migrations are untouched.

Before upgrading a deployed environment, back up database/source objects/keys, pause workers, apply `alembic upgrade head`, then deploy API/workers together. Downgrading 0021 drops only private computation receipts and its supporting index; published snapshots remain intact. Downgrade after pausing jobs loses receipt-based retry acceleration. Do not run a downgrade against a live environment without authorization.

## Remaining gates

1. Durable stage/work-unit DAG and fencing receipts for all required logical stages.
2. Bounded evidence/graph staging with safe public reader isolation and atomic generation promotion.
3. Bounded global correlation memory and full cold OpenMetadata qualification.
4. Real PostgreSQL concurrency and Redis worker loss/recovery. No Docker, PostgreSQL or Redis executables were found on PATH; no disposable PostgreSQL connection was supplied.
5. OS filesystem/network isolation and complete tenant controls beyond these new receipt constraints.
6. Both onboarding modes, integrated backend/frontend, permission/assessment/refresh workflows.
7. Six old browser cases: three administration-volume fixtures and three historical current-record-mirror cases. The historical test hardcodes repository/snapshot IDs, counts 21,269/183 and specific diagnostics. Their original mirror is absent. Those numbers must not be fabricated to make the test pass; the test fixture contract needs migration to newly pinned real inputs, keeping equivalent assertions.
8. Live OIDC/GHES/cloud/storage, sustained load and final release qualification.

## Source changes

backend/db.py; backend/domain.py; backend/jobs.py; backend/queue.py; new backend/analysis_checkpoints.py; new backend/migrations/versions/0021_analysis_checkpoints.py; new tests/test_analysis_checkpoints.py; tests/test_migrations.py; this implementation record. No frontend source or dependency manifest changed. No commit or push was made. A pre-change continuation source backup is retained under work/continuation-backup/source.zip in the Codex workspace, in addition to the original milestone backup.

## Validation commands and current evidence

From the supplied ProjectTrace directory, using the isolated workspace virtual-environment Python and a disposable DATABASE_URL:

- `python -m pytest tests/test_analysis_checkpoints.py -q --tb=short`: 7 passed, 1 deprecation warning, 5.81 s. Tests cover a new-session restart without analyzer recomputation, signature mismatch, scope/digest rejection, size ceiling, stale-writer rejection, direct-SQL tenant substitution, expiry cleanup and historical publication rollback.
- `python -m pytest tests/test_analysis_checkpoints.py tests/test_migrations.py tests/test_lease_renewal_race.py -q --tb=short`: earlier focused selection 12 passed, 1 warning, 34.10 s; the historical preservation test was added afterward and passed in the final checkpoint suite.
- `python -m pytest tests/test_timeout_recovery.py tests/test_administration_workers.py tests/test_local_jobs.py tests/test_worker_failure.py -q --tb=short`: 12 passed, 1 warning, 33.81 s.
- `python -m pytest tests/test_analysis_checkpoints.py tests/test_real_pipeline.py tests/test_queue.py tests/test_migrations.py tests/test_lease_renewal_race.py -q --tb=short`: an intermediate implementation run passed 18 tests; final full-suite evidence supersedes that intermediate run.
- `python work/qualify_petclinic.py` from the Codex workspace: pinned PetClinic capture, controlled rollback, new-session recovery, snapshot counts and an independent SQLite backup check. Source download and analysis scripts are retained with the evidence. No Gradle/Maven/npm/customer scripts were run.

The full backend regression is also executed and its final outcome is recorded below. Frontend source is unchanged; this milestone does not claim newly rerun frontend/browser acceptance. Previous frontend/browser evidence remains in the earlier report. Deployed databases remain on their existing migration until an operator performs a backed-up upgrade; no live schema was modified.

Second pinned-source recovery input: the pre-change continuation backup of the supplied ProjectTrace directory, identified by its archive SHA-256 in `projecttrace-recovery-result.json`. Its controlled interrupted run took 84.8532 s through first publication attempt; retry publication in a fresh session took 15.3050 s without rerunning global analysis. It published exactly one PARTIAL snapshot with 450 claims, 587 findings, 309 dependencies, 440 evidence records, 4,135 graph nodes and 9,158 edges. These outputs are analyzer observations, not independently verified detection accuracy. Both source recovery experiments used new isolated local databases and never executed imported source. The test exercises transaction rollback and session restart, not an OS-killed Celery task or staged graph resumption.

Measured repeat on the same preserved ProjectTrace archive, with a new database and shared encrypted source-object directory: 88.2173 s through controlled interruption; 17.0867 s for resumed publication. Parent-process peak working set: 303,955,968 bytes (289.88 MiB); parent peak commit: 290,787,328 bytes. Windows GetProcessMemoryInfo supplied these measurements. Parser child memory is not included or measured. Counts and PARTIAL status matched the first run. The repeated input has 465 captured entries and 461 retained text entries. Because encrypted source blobs were reused, these timings are not a fully cold storage benchmark. No production throughput claim follows from them.

## Final validation result for this increment

Runs span 14–15 October 2026 in Asia/Kolkata. Full backend regression: **528 passed, 9 skipped, 0 failed, 1 deprecation warning in 932.27 s** (`python -m pytest -q --tb=short --junitxml=<outputs>/continuation-full-tests.xml`). The seven-test final checkpoint suite passed in 4.52 s after the final serialization/foreign-key assertion changes and historical preservation test were finalized. The full run began before those final focused adjustments; these results are overlapping evidence and are not summed as unique tests. Changed-file Ruff checks passed. Full-suite logs/XML and final focused logs are retained in outputs. Existing opt-in PostgreSQL skips remain unqualified, not converted to passes.

Tests ran alongside the real-source qualification processes, so the suite duration and repository timings reflect that local load rather than an isolated production benchmark. The initial implementation test failures and their fixes are documented above; the final reported runs have no failures.

The original continuation backup contains all earlier files, including incidental development caches. Preservation comparison found no missing original file and verified backend/scheduling.py is byte-identical to the pre-continuation backup, preserving both earlier lease fixes. Only the listed source files and generated development caches changed; added files are listed in this record and patch. No commits, pushes, public services, paid resources or production operations were performed.

**Release verdict: BLOCKED.** This increment does not complete Priority 1 or the overall assignment. Bounded resumable graph/evidence stages remain implementation work, independently of the missing external qualification resources. Onboarding has not been started because those P0 invariants remain unresolved. No finished-product or onboarding demonstration is claimed.
