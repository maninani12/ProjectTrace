# Import reliability validation — 2026-10-08

**Readiness: BLOCKED for the complete OpenMetadata acceptance gate.** Small and medium ZIP imports publish real results; public GitHub URL import publishes a provenance-aware PARTIAL snapshot. The unchanged OpenMetadata ZIP is now safely captured but exceeds the unchanged 900-second native analysis budget. The latest private-worker repair is ready for one final owner-session retry; a successful private snapshot is not yet verified. Browser automation was blocked by its local-tab URL policy. Owner login/repository visibility and the first retry were manually confirmed by the user.

The subsequent [performance investigation](OPENMETADATA_PERFORMANCE_VALIDATION.md) records unchanged-ZIP retries, per-file/stage measurements, optimizations, retained diagnostics and the later isolated validation outcome. This document's observations describe the earlier intake repair; the performance report does not validate the private GitHub path.

## Root causes and fixes

### Unchanged OpenMetadata ZIP rejection

The original validator rejected the first symbolic link with `ValueError("Archive symbolic links are forbidden.")`, before emitting any entry. The UI converted that into a generic archive/budget message. It was not a 512 KB whole-archive limit. The attachment has 38 links, 32 oversized parser inputs, no encrypted/unsafe entries and no entry over the compression-ratio limit. Its 157,126,481 compressed bytes and 330,420,155 declared expanded bytes are below configured aggregate intake limits.

The streaming routes now use an encrypted seekable spool and metadata preflight. Symbolic links are recorded UNSUPPORTED and never followed/read/extracted. Oversized files are SKIPPED_SIZE_LIMIT; binary and undecodable retained bytes remain explicit. Unsafe/duplicate paths, encrypted entries, special file modes, corrupt payloads, multi-disk archives and decompression bombs fail safely. Central-directory metadata is bounded before allocating the ZIP directory. Unsupported compression is recorded without attempting decompression. All applicable hard-limit errors expose code, budget name, actual, maximum and remediation. Legacy archive import routes share this bounded pipeline.

No imported application, script, package installer, Maven command, Dockerfile or hook was executed. Static IaC parsing uses bounded owned helper processes, not repository executables.

### Private GitHub FETCHING and concurrency failures

The existing repository and job were preserved:

| Identity | Value |
| --- | --- |
| Repository | `maninani12/OpenMetadata` |
| Repository ID | `cf4ceb64-f4c7-4166-a462-309920d4e24b` |
| Existing job | `b0856d98-2bd3-41a2-b103-4d88e21a9075` |
| Connection | `480730b9-b545-4636-b181-1f934b66ce23` |
| Branch | `refs/heads/projecttrace-snapshot-test` |
| Exact commit | `b1fab2bc21c63335dead4daaaa28194c9878e9bf` |

The first full capture completed in 653,722.04 ms, retaining all 21,636 inventory entries. Native analysis then failed at 961,153.41 ms versus 900 seconds; it published no snapshot. Earlier authentication 500s came from a rollback-journal SQLite writer held during long capture. WAL and bounded fenced capture commits repaired account reads and login/session writes; the owner confirmed login and repository visibility.

The later FETCHING failure was a `TransportError` during installation-token POST. The old transport wrapper discarded its underlying DNS/TLS/network classification; the historical cause cannot be asserted more precisely. Read-only probes using the verified worker configuration minted a token and returned HTTP 200 for installation repository authorization, the exact commit and its full untruncated tree. Actor, grant, tenant, connection and mapping checks all passed.

The owner's next repair retry actually fetched 600 entries, then collided with concurrent public analysis publication: SQLite raised `database is locked` during capture flush and failure-state persistence. Cleanup raised `PendingRollbackError`, leaving the job for expired-lease recovery. Recovery later hit another token transport error. The incomplete 600-entry and empty recovery inventories remain CAPTURING and cannot be analyzed.

The final repair serializes active SQLite analysis jobs, releases capture/cache read snapshots before obtaining bounded immediate write transactions and rolls back before worker cleanup. PostgreSQL keeps configured concurrency. Local dispatch commits the queued state before waking its worker and performs no stale versioned write after that wake; Celery dispatch merges refreshed metadata without resending a task. Local jobs cannot be starved by an older queued job belonging to unavailable Celery infrastructure. API busy errors are sanitized 503 responses.

HTTPS transport now validates all DNS addresses, tries up to four prevalidated destinations within the original connect deadline, retains TLS hostname/certificate checks and reports safe failure categories. Only transient installation-token transport failures receive at most three bounded attempts; policy/certificate/HTTP refusals are not bypassed. Two finite server repair revisions preserve original retry counts and attempt history, culminating in retry 4; there is no unlimited retry reset.

## Actual live outcomes

Tests used normal authenticated registration in isolated validation organizations. Existing repository-owner credentials were not read, changed or impersonated. Time values below are measured observations on this PC, not performance promises. Pipeline COMPLETED does not imply full semantic coverage.

| Input | Inventory | Result / snapshot | Findings / evidence / claims | Measured duration |
| --- | --- | --- | --- | --- |
| Small realistic ZIP, refreshed final runtime | 5 TEXT; CAPTURED | COMPLETED, `b727262b-48c5-498d-a5ab-e5aeb3e4b132` | 3 / 5 / 6 | Intake 0.28 s; native 565.02 ms; end-to-end 3.36 s |
| Medium ZIP, 8 service directories / 256 files | 256 TEXT; CAPTURED | COMPLETED, `419163d3-d293-4679-b4a2-e107bb9ad2e9` | 256 / 256 / 8 | Intake 1.34 s; native 1,574.73 ms; end-to-end 7.42 s |
| Unchanged industry OpenMetadata ZIP | 21,636 entries; CAPTURED | FAILED / ANALYZING; **no snapshot** | **0 published / 0 / 0** | Intake 119.93 s; native failure 901.44 s; end-to-end 1,022.96 s |
| Public `pallets/flask`, refreshed final runtime | 231 TEXT + 5 BINARY; CAPTURED | PARTIAL, `58273e64-d815-487b-8f89-6e4c97738c5d` | 58 / 117 / 376 | Intake 0.08 s; native 7,251.41 ms; end-to-end 21.26 s |

Small ZIP inventory: `9cc1136c-dfd7-4abd-8c52-ba8e1c2d4e83`; job `510b294e-38c8-4070-8903-2c1589f28a28`; repository `7c143cb4-c95f-4189-b4de-d9248779c46c`. Its five coverage rows are PARTIAL because the native static analyzers have stated semantic limitations.

Medium inventory: `f386833e-a071-4f5d-9c9a-2b0fd3484313`; job `50186227-c064-42fd-8015-02819d5451e7`; separate repository `5fbc7947-3fe3-40c9-a67e-a005ee59e378`. Its 256 coverage rows are PARTIAL. Three partitions completed. The eight fixture service directories do not declare package component boundaries; runtime membership remains unobserved.

Public Flask inventory: `4d4372a4-4e06-48ea-91b3-1b4b62d3cf6d`; job `b03ac515-56ca-41fc-95f6-ab140e79c7bf`; repository `c3e79eb6-bb60-43c0-9e0a-03e8c68ff0f8`. Coverage: **116 PARTIAL, 87 UNSUPPORTED, 28 IGNORED_BY_POLICY, 5 BINARY**. There were 117 native candidate inputs, two partitions, 132 dependency records and 1,971 graph nodes. Provenance pins `main` to Git SHA `d086db856be187255b8ec61ef409357393020f32`, verified through GitHub API. Archive: 847,948 bytes, SHA-256 `d6c2b7322644872bd7e4fa44b4abd1711c1a06b5aaaa27661994652595922746`. Public intake did not use App credentials or webhooks.

### Exact unchanged OpenMetadata ZIP outcome

Input: `C:\Users\sai krishna\Downloads\OpenMetadata-main.zip`; SHA-256 `027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`. It was not edited/repacked. The 25,771 directory entries include directories; the file inventory is 21,636.

Separate ZIP repository: `8ab5f0b7-7c0d-43c6-98cc-cbd64df2ef3e`; job `e3986c27-737f-447b-a2d4-197beedffaa5`; complete inventory `821307d0-f546-4ef6-bca8-e2789855742a`. Intake states: **21,269 TEXT; 189 BINARY; 108 RAW_BYTES; 38 UNSUPPORTED symbolic links; 32 SKIPPED_SIZE_LIMIT**. Inventory declares 330,420,155 bytes. The same tree counts were independently verified on the private exact commit.

Native analysis has 18,859 candidate paths and a planned 199 partitions. Durable parser progress reached approximately 160 updates by 850 seconds, then exceeded `REPOSITORY_ANALYSIS_SECONDS`: actual **901.44**, maximum **900**, code **ANALYSIS_TIME_BUDGET**. Batched bounded IaC helpers reduced repeated process startup, but this cold full-repository run still exceeded the safe budget. Parser cache/inventory are retained; partial observations are not published as successful findings or fabricated snapshot coverage. The unchanged ZIP therefore has **snapshot ID null**, and only its job record was published in the analysis-record table.

The earlier private CAPTURED inventory `f32cd086-21c1-4713-b9fb-922623f077c4` also retains all 21,636 entries. The first current repair's 600-entry inventory `265077f1-6ef8-4486-a41d-157c36cf21e4` and later empty recovery inventory `0db88201-469d-4fff-ba52-36973b71303e` remain incomplete. Complete source intake and final analysis coverage are distinct. At the latest observation, the original private job is FAILED / FETCHING, retry count 3, `SCM_TRANSPORT`, with no snapshot. Earlier native duration/stages retained on that job describe the prior analysis attempt, not the subsequent token request.

## Tests actually run

| Verification | Executed result |
| --- | --- |
| Full backend baseline after main implementation | **420 passed, 1 failed**, 1,532.80 s. The sole failure asserted the obsolete bad-ZIP behavior of persisting a failed repository; metadata preflight now rejects before repository creation. The assertion was corrected and rerun below. This run is not represented as an all-green full suite. |
| API / transport / GitHub / SCM / public / import reliability after that correction | **74 passed**, 45.67 s |
| Final affected scheduling / auth-during-capture / store / streaming / public / local-runner / reliability / transport / queue tests | **68 passed**, 73.85 s, after final concurrency, dispatch and finite retry changes |
| Frontend suites | **32 tests across 8 files passed**, 51.33 s; production TypeScript/Vite build passed |
| Archive safety and streaming focused checks | **12 passed**; subsequent archive/public checks **30 passed** |
| Targeted final Ruff | All checks passed |
| Live API/database | Small/medium/unchanged industry ZIP plus real public GitHub; exact outcomes above |
| Managed services | Graceful stop/start exercised; API/database and UI auth proxy ready at 8011/5181; local mode; independent SCM worker retained/refreshed |
| Existing database preservation | Original accounts, organizations, repositories, grants, SCM records and prior job IDs preserved; SQLite quick_check `ok` |
| Browser | Existing owner login/repository visibility and retry confirmed manually; automated local browser access blocked by URL policy; no browser PASS invented |

Focused test groups overlap; their counts are not added together as distinct test cases. The full backend suite was not repeated after the last focused fixes. The Starlette/httpx test-client deprecation warning is recorded; dependency migration was outside this repair.

Coverage includes auth/CSRF and tenant boundaries; duplicate/conflicting request keys; no extra repository on rejection; corrupt CRC/metadata; unsafe paths, symbolic links, binary/oversized entries and hard quotas; public URL/ref/host/redirect/private/rate/transport failures; pinned retry inventory and commit; unavailable local/worker dispatch; fenced cancellation, stale recovery, writer contention; encryption/snapshot integrity; and bounded token/address retries. Production PostgreSQL/Celery load, OS sleep/crash soak and multi-host deployment were not validated.

## Files changed in this repair

| Area | Main files |
| --- | --- |
| Intake and source safety | `backend/intake_errors.py`, `backend/encrypted_archive.py`, `backend/repository_store.py`, `backend/main.py` |
| Native parsing and truthful output | `analyzers/engine.py`, `analyzers/infrastructure.py`, `analyzers/iac_worker.py`, `backend/partitioned_analysis.py`, `backend/domain.py`, `backend/jobs.py` |
| Durable local and private/public workers | `backend/local_jobs.py`, `backend/queue.py`, `backend/scheduling.py`, `workers/tasks.py`, `workers/github.py`, `workers/public_github.py` |
| Public URL and provider transport | `integrations/github/public.py`, `integrations/github/connector.py`, `integrations/secure_http.py` |
| Managed development runtime | `scripts/start.ps1`, `scripts/stop.ps1`, `scripts/dev_runtime.py`, `scripts/local_api.py`, `scripts/dev_workers.py` |
| Existing interface | `frontend/src/WorkspaceApp.tsx`, `frontend/src/api.ts`, `frontend/src/ImportFlow.test.tsx`, `frontend/src/RepositoryRecovery.test.tsx` |
| Regression tests and docs | `tests/test_archive_safety.py`, `tests/test_public_github.py`, `tests/test_streaming_import.py`, `tests/test_local_jobs.py`, `tests/test_import_reliability.py`, `tests/test_transport_reliability.py`, `tests/test_iac_partitions.py`, updated store/API/queue/scheduling/auth tests; README, operations, login/import guide and this report |

Existing authentication/webhook repairs and unrelated untracked work were retained. This is the existing ProjectTrace codebase, not a replacement. No commit/push was made.

Final comparison against the private pre-repair online backup confirmed all original **75 users, 75 organizations, 67 repositories, 67 grants and 3 SCM connection/integration/mapping records** unchanged. All **116 prior job IDs** remain; normal authorized retry/session/audit updates are retained. The original complete private inventory and its source metadata/digests are unchanged; the input-encryption key fingerprint matches. SQLite quick_check returned `ok`, journal mode `wal`, migration `0013`. Final `/ready` and UI `/api/auth/options` checks returned HTTP 200. Newly registered validation accounts/repositories are additive; they do not replace existing rows.

## User flows and startup

From `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`, run:

```powershell
.\scripts\start.ps1
```

Open `http://127.0.0.1:5181/repositories` with the existing owner login. Choose **Import repository** → **Upload ZIP** → a new name/file → submit. ZIP/local repositories also support **Upload new snapshot** without mixing private GitHub history. Choose **Public GitHub URL** and paste `https://github.com/owner/repository`; optional ref is separate. Choose **Connect private GitHub** for existing App-backed Connections. Job cards display real queued/fetching/parsing/analysis/evidence/final stages and structured errors. **Trust & Coverage** exposes partial/unsupported/binary/policy/oversized states. No fake progress percentages are supplied.

Graceful stop:

```powershell
.\scripts\stop.ps1
```

The installed local workflow defaults to the durable local runner, checks database plus UI auth proxy, reuses healthy owned listeners and does not seed/reset accounts or silently install infrastructure. Optional `-Config` loads approved JSON data and absolute existing secret-file references only. Private jobs can use the retained loopback Redis/SCM worker. `-FullDevelopment` explicitly requests optional Celery/Beat setup; `-DockerRedis` is separate opt-in. Production continues to use its configured worker architecture.

## Safe limits and remaining gates

Default bounds remain: **100,000 files/directory entries; 2,000,000,000 expanded bytes; 512,000,000 compressed bytes; 64,000,000 central-directory metadata bytes; compression ratio 200; 512,000 bytes per parser input; partitions at most 100 files / 2,000,000 bytes; native repository analysis 900 seconds**. IaC helpers retain bounded time/output/memory/CPU. Retained failed/partial job input has a 72-hour policy. These limits were not raised to force OpenMetadata success.

The outstanding acceptance gates are a successful final owner-triggered private job under the refreshed worker, full OpenMetadata native analysis within bounded resources, and live browser interaction where browser policy permits it. The original webhook-secret reference is still missing; future signed App webhook delivery requires restoring that original operator reference. ZIP/public snapshots require neither that reference nor webhook tunneling. Static findings and claims remain subject to explicit parser/semantic limitations and unobserved runtime behavior. The app is running and useful for the verified ZIP/public flows, but the complete requested private/full-industry gate is **BLOCKED**, not PILOT CANDIDATE.
