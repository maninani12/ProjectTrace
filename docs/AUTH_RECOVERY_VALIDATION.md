# Authentication recovery validation — 2026-10-08

> This report records the earlier authentication repair. [Import reliability validation](IMPORT_RELIABILITY_VALIDATION.md) records the subsequent writer-collision repair, managed local startup and current import outcomes. Runtime IDs and later-job conclusions below are historical observations.

**AUTH STATUS: PASS. Database preserved: YES. Browser login verified: YES, confirmed by the repository owner.** The owner refreshed the existing login page, signed in using the existing account and confirmed that `maninani12/OpenMetadata` is visible. Browser automation itself was blocked by the browser tool's local-tab URL policy; this report distinguishes the user's browser confirmation from automated HTTP checks.

## Exact cause and runtime

The actual API traceback was `sqlite3.OperationalError: database is locked`, propagated as a SQLAlchemy `OperationalError` during account-options/user lookups and sign-in. One intended API listener was verified on loopback port 8011, with the correct ProjectTrace working directory and database. The database schema and Alembic head were both `0013`. Redis, CSRF, password hashes and missing migrations were not the cause.

The API and Celery worker shared `data/projecttrace.db` in SQLite rollback-journal mode (`delete`). Source capture flushed inventory rows and renewed the worker lease within one write transaction, while continuing provider requests and encrypted blob writes. The real OpenMetadata capture took 653,722.04 ms. A sufficiently large rollback-journal writer blocked account reads; sign-in also needs a session INSERT and therefore cannot be fixed merely by enabling concurrent reads.

The original verified API PID was 28440. Once the existing job was terminal and no scheduler entries were RUNNING, only the verified API and idle worker were refreshed, retaining their approved configuration in memory. Current API core PID **16564** owns `127.0.0.1:8011`; worker core PID **25300** was verified ready, using the existing Redis and Beat. These are observed process IDs, not permanent configuration. `APP_ENV=demo`, `JOB_MODE=celery`, the loopback broker reference, CORS settings and the existing SCM key-file reference were preserved. Sessions are database-backed opaque tokens; no absent signing secret caused this failure. The original webhook-secret reference remains unavailable for future signed deliveries.

## Minimal fix

- `backend/db.py`: enable SQLite WAL on connections, retaining foreign-key enforcement and the existing bounded write-lock timeout. PostgreSQL behavior is unchanged.
- `backend/repository_store.py`: optional checkpointed capture buffers at most 100 entries / 2,000,000 raw bytes before writing. It commits permission-checked batches before requesting further provider bytes and batches component-assignment updates. Default captures remain atomic. A partially committed inventory remains incomplete and `RepositoryFiles` refuses to analyze it.
- `workers/github.py`: commit the initial authorization/lease renewal before provider I/O, retain read-only cancellation/fencing checks while pulling entries, and validate actor, grant, connection version and repository mapping before capture checkpoints. Snapshot/graph publication remains atomic.
- `tests/test_auth_during_capture.py`, `tests/test_repository_store.py`: concurrent account lookup; real password login/session INSERT/CSRF logout between both file-count and byte-count batches; quota failure and permission revocation cannot produce analyzable inventories.
- This report, `docs/OPENMETADATA_REAL_WORLD_VALIDATION.md`, `docs/operations.md`: measured results and startup recommendations.

No account, password, grant, secret or repository was reset or regenerated. No source safety quota was raised. No GitHub commit/push or OpenMetadata source execution occurred.

## Preservation evidence

Before changing the database journal mode, SQLite's online backup API saved a private backup outside the repository. Its `quick_check` returned `ok`. Before/after fingerprints matched all users (including password hashes and enabled/login settings), organizations, repositories, grants, SCM connection/integration/mapping records and the existing encryption key. Every previous job ID remains present. The captured inventory and every captured source-file metadata/digest row also matched the backup.

Job data/audit/session changes made by normal owner login and the subsequent owner-authorized retry are expected and retained. Neither a raw copy of a live journal nor a database replacement/reseed was used. Migration version remains `0013`; journal mode is now `wal`. No database-lock traceback was recorded after the refreshed API started.

## Tests actually run

**108 unique backend test cases passed across these runs** (overlapping reruns are not added):

| Run | Result |
| --- | --- |
| `pytest tests/test_auth_during_capture.py tests/test_public_auth.py tests/test_repository_store.py -q` | 22 passed, 500.09 s; before adding the byte-count parameter case |
| `pytest tests/test_auth_during_capture.py -q` after byte-bound case | 3 passed, 5.72 s; two overlap the preceding run |
| `pytest tests/test_security_hardening.py tests/test_fair_scheduling.py tests/test_queue.py tests/test_ghes.py tests/test_scm_webhook.py tests/test_migrations.py -q` | 61 passed, 131.95 s |
| `pytest tests/test_scm_batch.py tests/test_scm_streaming.py -q` | 24 passed, 1.43 s |

The first attempts encountered test-harness filesystem errors: the default Windows pytest temporary directory was inaccessible; a new explicit temporary directory initially lacked its parent; and a large parameter value required a short explicit test ID. These setup failures were corrected and affected suites rerun successfully. Isolated database/source/key paths were used. The existing Starlette/httpx deprecation warning remains. JUnit receipts are retained in the private task workspace. Ruff and `git diff --check` passed; no frontend code changed in this authentication repair.

Automated live checks passed against both `http://127.0.0.1:8011` and the frontend proxy at `http://127.0.0.1:5181`:

| Route/action | HTTP |
| --- | --- |
| Account options | 200 |
| Invalid normal login | 401, with no server exception |
| Existing public demo-session creation | 200 |
| Authenticated account lookup | 200 |
| Authorized workspace | 200 |
| Demo session attempting the real owner's job | 404 |
| CSRF-protected logout | 200 |

The synthetic test account exercised successful normal password login during capture; no real owner password was printed or guessed. Live demo-session checks prove session persistence but do not establish owner access. Owner access/browser login was separately confirmed by the user.

## OpenMetadata continuation

The same repository, branch and exact commit remain connected: `maninani12/OpenMetadata`, `refs/heads/projecttrace-snapshot-test`, `b1fab2bc21c63335dead4daaaa28194c9878e9bf`. The original job is `b0856d98-2bd3-41a2-b103-4d88e21a9075`.

The first owner-authorized retry/recovery **captured all 21,636 entries**, retained 21,566 encrypted byte payloads and reached actual native ANALYZING. Inventory `f32cd086-21c1-4713-b9fb-922623f077c4` is CAPTURED: 330,420,155 declared bytes, 21,269 UTF-8 text entries, 189 BINARY, 108 other raw-byte entries, 38 UNSUPPORTED links and 32 SKIPPED_SIZE_LIMIT files. Those are intake states, not semantic coverage. Capture took 653,722.04 ms. No imported code was executed.

Native analysis then failed with `TimeoutError: Analysis exceeded its configured execution time budget.` The measured analysis duration was 961,153.41 ms against the unchanged 900-second configured budget. Failure was detected at a partition progress checkpoint; no snapshot was published. The traceback identifies native partition parsing, but does not establish a particular slow file or justify increasing limits.

After login was restored, a second owner-authorized retry reached FETCHING and failed on a provider `TransportError` during installation-token acquisition (14:53:03 IST). It left an empty incomplete inventory; that inventory is not eligible for analysis. A subsequent fresh bounded check using the stored connection/current worker environment minted an installation token, and repository discovery, the exact Git commit and full recursive tree each returned HTTP 200. Enabled actor, organization, grant, connection and mapping checks passed. The transport failure was transient in these observations; its underlying DNS/TLS/network cause was not retained by the privacy-safe exception wrapper and is not invented here.

**Current OpenMetadata status: FAILED/FETCHING; no snapshot.** The complete earlier inventory remains intact. The existing job now has `retry_count=2`, reaching its protected retry limit. No failed job was rewritten, no limit was expanded and no direct worker invocation bypassed owner authorization. Further successful validation requires a supported authorized analysis attempt after diagnosing the native partition-time bottleneck; current evidence does not establish full coverage, findings/claims accuracy or enterprise readiness.

## Local development experience

This is a verified startup/DX defect: liveness/readiness alone did not exercise authentication while a source job was writing, and relaunching required retaining a shared API/worker environment. Keep the existing full-development mode; a focused next improvement should load operator-owned configuration references through one explicit launch entry point, report actual listener/worker PIDs, check `/api/auth/options` through the frontend proxy after startup, and distinguish database/auth, queue/worker and SCM readiness. Preserve existing database/account initialization on restarts and provide actionable missing-reference diagnostics without displaying secrets. A complete startup redesign was not performed in this repair.
