# Operations

Native startup uses ports 8011/5181 and the local data/projecttrace.db adapter. /health is process liveness; /ready checks database access and local-runner liveness when configured; production Celery readiness is separate. Provider state is separate from database readiness.

Review API errors by request ID without logging source or credentials. Signed webhook receipts are retained even when dispatch fails. Inspect job records through authorized record endpoints. Retry/cancel operations are scoped and do not silently delete source evidence. Celery has late acknowledgement, single-task prefetch and time limits. A real private Linux child-crash/expired-lease recovery drill and PostgreSQL duplicate-claim/dispatch-race tests passed on 2026-10-09; sustained recovery, dead-letter automation and tenant-fairness throughput remain unqualified. See the [current product audit](../PROJECTTRACE_PRODUCT_AUDIT_AND_READINESS.md) for exact scope.

The startup script records API/UI logs under data. Stop only processes identified as this project's API/UI; do not kill other projects occupying default ports. Back up retained data before schema changes. See backup-recovery.md and RELEASE.md for verified/unverified operations.

## Authentication under local source capture

SQLite connections use WAL so native capture cannot block account reads through rollback-journal cache spill. SCM capture buffers fixed 100-entry / 2 MB batches outside write transactions, then validates authorization and the worker lease before committing each incomplete batch. Only a completed CAPTURED inventory can be analyzed. The default non-checkpointed capture and snapshot publication retain atomic behavior; foreign keys, source limits, permissions and cancellation fencing remain enforced. This local concurrency repair does not replace the production PostgreSQL adapter.

The 2026-10-08 failure was an actual `database is locked` traceback on authentication, despite a running API. Before/after checks preserved accounts, organizations, repository grants, SCM records, prior job IDs, captured source metadata and the encryption key. Normal owner browser login and OpenMetadata visibility were confirmed by the user after the repair. See [authentication validation](AUTH_RECOVERY_VALIDATION.md) for executed tests and current service/job observations.

## Managed local startup and shutdown

Run `scripts/start.ps1` on an installed workspace. The default local runner uses the same durable encrypted inputs, scoped worker authorization, queue admission and lease fencing as production jobs. No Redis, App credential, webhook tunnel or infrastructure install is needed for ZIP/public snapshots. `scripts/stop.ps1` signals the owned API wrapper to drain its active local analysis and stops only the recorded UI process after checking PID, creation time and command line. Queued inputs, database, accounts and keys remain. Independent Celery/Redis services remain running. A forced OS/process crash recovers through the existing bounded expired-lease mechanism; it cannot publish a stale snapshot.

Only JSON data is loaded from optional `data/local-settings.json` or `-Config`. Raw secret keys and shell directives are rejected. Approved `*_FILE` references must be existing absolute operator files. Noncredentialed loopback Redis is allowed for private SCM dispatch; source archives never configure launch settings. Health checks verify API/database and the UI `/api/auth/options` proxy before reporting success. Already healthy listeners are reused; unrelated or unhealthy occupied ports are never killed automatically. Startup does not reseed existing users.

`-FullDevelopment` explicitly requests the optional Celery worker/Beat setup. `-DockerRedis` is a separate opt-in and only reuses/starts installed infrastructure. Existing workers are detected even when a busy Windows solo worker cannot answer ping. Missing App/webhook references are actionable SCM limitations, not ZIP/public prerequisites. `scripts/dev_workers.py --check-only --require-scm` performs the strict reference-presence check without displaying values. The original missing webhook secret must be restored by the operator; never replace it with a newly generated secret.

Repository job cards use the protected retry endpoint. Retry admission and QUEUED job state commit together before dispatch, so unavailable dispatch remains recoverable. Failed jobs retain source for 72 hours. PARTIAL jobs retain input for review/retry. Public retries use the already resolved commit and complete scoped inventory; App retries reuse only an inventory with matching recorded commit provenance. Two normal retries remain bounded. Two finite server repair revisions apply only to the diagnosed exhausted GitHub failures: `safe-intake-2026-10-08` permits retry 3 after the original transport/time failure; `serialized-transport-2026-10-08` permits retry 4 only after that revision failed with `SCM_TRANSPORT`. Counts and attempt history are retained; there is no fifth retry allowance or client-controlled reset.

The SQLite adapter admits one active analysis job across the local runner and Celery. Local admission ignores unavailable queued Celery jobs when choosing its next candidate, while counting all active writers. Checkpointed capture takes a short immediate write transaction only after fetching its bounded batch; parser cache writes similarly release preceding read snapshots before CPU/provider work. This prevents WAL read-to-write upgrade failures when another worker publishes results. PostgreSQL retains configured concurrency. A ZIP capture attempted while an analysis writer is active receives `LOCAL_CAPTURE_BUSY` with Retry-After; SQLite busy errors receive a sanitized retryable 503 instead of exposing SQL or returning a mysterious 500.

Provider transport validates every DNS result before connection, tries at most four approved addresses within one connect budget and preserves original-host TLS verification. Installation-token minting retries at most three transient transport failures. Certificate, address-policy and provider HTTP refusals are not retried or bypassed. Public GitHub intake uses the configured bounded archive response budget; ordinary provider metadata responses retain their smaller transport cap.

See [current import validation](IMPORT_RELIABILITY_VALIDATION.md) for live outcomes and remaining scale/browser limits. Older reports describe the earlier runtime and are historical, not proof of current ingestion success.

## Repository analysis performance

Jobs retain `performance` with stage wall seconds, helper/cache/aggregation component timings, current-attempt counters and at most 40 slow file operations. Component timers overlap and cannot be summed as wall runtime. `source_blob_reads` and `source_cache_hits` describe bounded parsing partitions; publication and global source reads are outside those counters. A cache reuse timer is the cost of reusing that artifact in this attempt, not its historical parser runtime. Failed attempts keep their performance metadata in retry history.

The default repository analysis deadline remains 900 seconds. Native source caching is capped at 2 MB per partition, and at most two owned syntax/IaC helpers run concurrently under their original CPU, memory, timeout and output caps. Publication checks its deadline and lease every 250 record/computation steps or at the next iteration after one second, and uses bounded writes in the original atomic snapshot transaction. Checks are cooperative between bounded operations. A failure retains completed parser cache entries and scoped file-local diagnostic records while rolling back unfinished graph output. Inventory exclusions/skipped rows are never turned into successful parser coverage.

After global static analysis completes, the job retains `completed_analysis` with its inventory ID, measured counts and coverage summary. `publication_state=UNPUBLISHED` means evidence/correlation/snapshot publication has not succeeded; it must not be presented as a completed snapshot or passing gate. Only successful publication sets PUBLISHED and links the snapshot ID. The original inventory and parser diagnostic records retain the detailed skipped/failed paths. Retry history preserves prior summaries and performance.

An installed local filesystem operator may run `.venv\Scripts\python.exe scripts/retry_retained_analysis.py --job-id <existing-id>` with the already configured local runtime environment. The command only accepts a retained LOCAL/INVENTORY job, verifies its original enabled submitter and repository grant, uses its existing complete encrypted inventory, and enforces the normal two-retry ceiling. It preserves attempt history and audits `LOCAL_FILESYSTEM_OPERATOR`; it does not log in as the owner, change accounts, fetch a provider repository or accept production/private SCM jobs. Prefer the existing authenticated retry UI for ordinary user operations.

See [OpenMetadata performance validation](OPENMETADATA_PERFORMANCE_VALIDATION.md) for measured files, stages, tests, unchanged-source provenance and the current retry outcome. Reload the relevant API/worker process to activate code changes; cache keys remain tied to parser/rule/configuration semantics.

The matched 900.31-second incident and subsequent recovery are documented in
[repository timeout root cause and recovery](../REPOSITORY_TIMEOUT_ROOT_CAUSE_AND_RECOVERY.md).
Migration 0014 adds a tenant-plus-artifact-ID lookup index; it preserves cache
payloads and avoids scanning a tenant's full cache for every partition. History
projections prefetch and flush at most 250 identities/occurrences at a time,
retaining normal tenant and immediate foreign-key checks. Completed native
partitions commit their immutable cache entries and file diagnostics before
the following progress deadline check, so that check cannot discard a completed
partition. Unfinished global snapshot output still rolls back atomically.

For isolated performance work, run `scripts/benchmark_repository_analysis.py`
with a new empty `--output` directory and bounded `--files` / `--functions`.
Optional `--archive` plus `--component` selects authorized ZIP text as data.
The script records separate cold, warm and one-file-change attempts, resource
measurements, cache/SQL counters and coverage. It never executes fixture or
imported repository code. Cold denotes an empty application cache, not a
cleared operating-system cache; do not turn a passing small fixture into an
unsupported whole-repository performance claim.

Graph writers keep deadline/lease checks separate from flush scheduling: deferred
artifact/function graph work fills explicit batches of at most 250 rows, then
drains at projection boundaries within the original atomic snapshot transaction.
Ordinary publication/update checkpoints retain their flush behavior. SQLite uses
a 32 MiB page-cache target per connection (`cache_size=-32768`); this is not a
hard process memory ceiling, and pooled connections can consume multiple targets.
WAL, foreign keys, durability and the 900-second budget remain enforced.

See [final correlation validation](../CORRELATION_PERFORMANCE_FINAL_VALIDATION.md)
for unchanged OpenMetadata pipeline publication in 330.51 seconds on an isolated
copy and 481.23 seconds through the installed fenced worker. Both retain PARTIAL
coverage and all declared analyzers. These are awake-host, existing-parser-cache
measurements; cold full-repository and maximum-scale capacity remain unverified.
Standby-interrupted failures are retained separately in that report. Use full call
wall time for headroom: the legacy stored job duration excludes final commit.

## Current reliability qualification

Idle lease recovery uses a read-only, execution-scoped preflight before acquiring a writer lock and rechecks expired work under the lock. ZIP duplicate receipts and local capture backpressure likewise preflight and recheck under serialized admission. PostgreSQL claims take the scheduler lock before refreshing/locking the job row so dispatch metadata cannot cause a stale-version claim; all native claimants use that lock order. Expired recovery preserves the prior attempt's stages, performance and unpublished summary before requeuing. Idempotent reuse links the later job to its snapshot without rewriting the original snapshot's job provenance.

Native cache checkpoints are not a durably resumable global pipeline. Aggregate verification, graph/history construction and final snapshot publication still run in one task and one atomic output transaction. Committing that transaction piecemeal would expose incomplete records through existing reads. The current master audit therefore retains a BLOCKED readiness verdict until a scoped unpublished generation/work-unit architecture, visibility checks, failure recovery and representative resource/performance qualification are implemented.

The Docker gateway now accepts the same default 512,000,000-byte archive cap as the API; a lower configured API quota still applies. Directory redirects remain relative so the public origin/port survives container/ingress mapping. Actual gateway body validation and production static-page browser checks passed; large synchronous upload/capture through that gateway remains unqualified. No response timeout was raised to obtain a pass.
