# Fenced broker/worker recovery milestone

## Scope and acceptance criteria

Base: PR #1 head `15f38216aaeb1de14d152928b2c9fa4a5f3807c2`. New branch: `codex/broker-recovery-hardening`. Preserve PR #1 unmerged; the new draft PR is stacked on its branch. No schema or frontend changes are required.

The milestone is accepted only when its current-head checks pass, including the dedicated real-service job. Local unit passes or mocked dispatch cannot close real broker acceptance.

| Criterion | Required observation |
|---|---|
| REC-01 terminal outcome | Recovery never rewrites/requeues COMPLETED, COMPLETED_NO_FINDINGS, PARTIAL, FAILED or CANCELLED after a cleanup crash; only stale queue bookkeeping is reconciled |
| REC-02 one lease authority | Renewed/locked scheduler entries cannot be overridden by older job JSON or legacy fallback |
| REC-03 adapter ownership | Celery maintenance does not recover LOCAL jobs; legacy jobs without QueueEntry retain recovery compatibility |
| REC-04 bounded recovery | Two resumptions, then explicit terminal failure/history; missing/expired input fails safely with a sanitized actionable code |
| REC-05 broker interruption | Actual Redis stop causes accepted input to remain encrypted/durable with PENDING_RETRY; Redis restart and the actual recovery task publish exactly one snapshot |
| REC-06 worker restart/fencing | Kill the actual prefork process group after claim and before analysis; no output is published; wait for natural lease expiry, run the real recovery task, then publish once under a new token |
| REC-07 post-publication loss | Kill after actual generation/pointer/job commit but before cleanup/ACK; recovery retains the same terminal job, generation and snapshot, with no new attempt |
| REC-08 duplicate/revocation isolation | Explicit duplicate real broker deliveries do not duplicate snapshots or alter terminal metadata; a revoked actor cannot publish and another tenant cannot read/retry the job |
| REC-09 regressions | Full existing CI, PostgreSQL race/preservation tests, browser/auth drift, audits and both image builds remain successful |

## Failure evidence and implementation

`tests/test_recovery_boundaries.py` initially produced seven failures on the baseline. Its first five states were all reopened; JSON fallback overrode a renewed QueueEntry; Celery scanned LOCAL work. `backend/scheduling.py` now refreshes and reconciles terminal jobs under queue/job locks and exposes failure codes. `workers/tasks.py` filters recovery by CELERY and confines legacy fallback to jobs without QueueEntry. PostgreSQL `test_recovery_postgresql.py` holds an uncommitted renewal lock while recovery runs in another connection; recovery must skip it.

Portable tests deliberately expire owned model leases to check state-machine transitions. These are unit/database regressions, not real broker claims. The real-service job does not edit expiry timestamps or shorten recovery polling intervals.

## Real-service CI harness and safety boundaries

The `broker-recovery` Actions job owns fresh PostgreSQL 17 and Redis 7 containers. It requires the explicit `owned-ci` flag, GitHub Actions marker, exact loopback service URLs and a validated 64-hex Docker container ID whose inspected image is `redis:7-alpine`. It stops/starts only that container. Each case creates its own UUID PostgreSQL schema, encrypted source locations, key and Redis key prefix. No FLUSH command or customer database is used. Cleanup drops only the schema created by that fixture and terminates only its own worker process group. This is isolated test cleanup, not application/database deletion.

The API is the actual FastAPI app with the fixture Session, actual registration/session/CSRF calls and actual ZIP ingestion. Workers run the real Celery task implementations with a prefork pool/concurrency one. The bootstrap only namespaces broker keys, records sanitized completion events and pauses at BEFORE_ANALYSIS or AFTER_PUBLICATION until the controller kills the real process group. It fabricates no API response, claim, analysis result, lease, publication or finding. It is outside the Docker COPY paths and production worker entry point.

The allowed inventory execution budget is explicitly 120 seconds in this fixture, yielding a natural approximately 150-second database lease; the normal application default remains 900 seconds. Soft/hard limits, late ACK, worker-loss handling, default broker visibility timeout and two-recovery policy remain the actual application settings. Recovery tasks are explicitly submitted through Redis; this tests the production handler/transport rather than certifying a separate beat scheduler deployment. Explicit duplicate messages are also sent through Redis and verified as consumed with completion events. The suite does not wait for the default long Redis visibility-timeout redelivery.

The fixture uses APP_ENV=demo for owned loopback infrastructure, so it does not assert production TLS or Redis-backed API admission availability during outage. The broker-failure test proves durability after acceptance; production admission remains fail closed and requires verified TLS. Imported ZIP contents are inert static fixtures; their application code is never run.

Only JUnit, worker/migration logs and sanitized task-ID/status/counter journals are uploaded for seven days. Encryption keys, databases, raw source objects, worker tokens, API credentials/cookies/CSRF values and boundary marker files are excluded. Raw arbitrary exception return values are excluded from journals.

## Execution and evidence

Portable selection:

```bash
pytest -q tests/test_recovery_boundaries.py tests/test_recovery_postgresql.py tests/test_fair_scheduling.py tests/test_lease_renewal_race.py tests/test_queue.py tests/test_worker_failure.py
```

The PostgreSQL race requires the existing explicit disposable PROJECTTRACE_TEST_POSTGRES_URL. Dedicated CI invokes `pytest -q integration_tests/test_broker_recovery.py` with its owned service environment and retains `broker-evidence-<run_id>`. It is intentionally separate from the default portable `tests` tree: default pytest is not permission to stop an arbitrary Redis instance. CI explicitly runs both suites. Manually invoking the integration file without the owned environment skips it rather than touching another service; those skips are not broker validation.

Ruff/compilation include the integration harness. The existing browser job preserves its ten fixture-dependent skips and runs authentication drift. Main CI retains audits, migration round trip/seed, frontend tests/build/type checks and Docker builds. Final measured totals, run/head identifiers, artifacts and intermediate failures are recorded in the draft PR description so a documentation-only result update does not invalidate the tested commit.

Local infrastructure currently lacks Redis, PostgreSQL and Docker binaries, and Chromium downloads were previously invalid. Do not relabel those local checks as passed; dedicated GitHub runner evidence supplies the infrastructure results only after it actually succeeds. Local Python is 3.12; CI's required Python remains 3.14.

## Remaining gates

This milestone does not close parser filesystem/network isolation, SCALE-001 global memory, representative analyzer precision, shared-NAT capacity, private Administration/Learning and large-account/static browser fixtures, or production backup/TLS/provider/object-store qualification. Broker follow-ons include default visibility-timeout redelivery timing, beat scheduling under outage, long-running SCM/advisory failure, sustained multi-worker fairness, Redis persistence/failover and production recovery SLOs. All remain explicit; neither historical VM notes nor a green suite establish complete production readiness.
