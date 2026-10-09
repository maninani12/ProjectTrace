# OpenMetadata real-world recovery validation — 2026-10-08

> Historical observations from the earlier authentication/recovery runtime. For the subsequent ZIP/public intake implementation, SQLite writer repair, current service state and final OpenMetadata outcomes, use [Import reliability validation](IMPORT_RELIABILITY_VALIDATION.md). Process IDs and retry counts below describe their recorded observation time.

**Current outcome: authentication PASS; OpenMetadata FAILED, no snapshot.** Owner browser login and repository visibility are confirmed. The first authorized retry captured all 21,636 entries and reached native analysis, which exceeded its 900-second budget. A subsequent authorized retry hit a transient provider transport failure and reached the job's two-retry limit. The complete inventory, original accounts, connection, source digests and job history are preserved. See [the authentication recovery report](AUTH_RECOVERY_VALIDATION.md) for current evidence and fixes.

## Latest observed continuation after login repair

- API core PID 16564 owns loopback 8011; the existing UI remains on 5181. Account options and session/workspace/logout checks pass through both direct API and UI proxy; no new database-lock errors followed the refresh. The owner confirmed browser login and `maninani12/OpenMetadata` visibility.
- The actual cause of authentication 500s was SQLite rollback-journal writer contention during the 653,722.04 ms source capture. WAL plus bounded, fenced capture commits now release the writer before provider I/O. No authentication or source-safety guard was weakened.
- Inventory `f32cd086-21c1-4713-b9fb-922623f077c4` is CAPTURED, with 21,636 entries / 330,420,155 declared bytes and 21,566 encrypted retained payloads. Intake groups: 21,269 UTF-8 text; 189 BINARY; 108 other raw-byte entries; 38 UNSUPPORTED links; 32 SKIPPED_SIZE_LIMIT. These are not final analysis coverage.
- Job `b0856d98-2bd3-41a2-b103-4d88e21a9075` reached native ANALYZING and then failed at a partition checkpoint: `TimeoutError`, 961,153.41 ms measured analysis versus the unchanged 900-second budget. Zero snapshots/findings/claims were published by this job.
- The later owner-authorized retry failed at FETCHING, 14:53:03 IST, with `TransportError` during GitHub installation-token acquisition. Fresh subsequent stored-connection checks succeeded: token minted; installation repositories, exact commit and untruncated tree HTTP 200; actor/grant/connection/mapping checks passed. The wrapper did not retain the underlying network cause. Current retry count is 2; the existing protected cap is intact. Its empty incomplete capture remains ineligible for analysis.
- Exact target remains `maninani12/OpenMetadata`, branch `refs/heads/projecttrace-snapshot-test`, commit `b1fab2bc21c63335dead4daaaa28194c9878e9bf`. No GitHub commit, source modification or imported-code execution occurred. Native partition performance and a supported further authorized attempt are the remaining analysis gates; missing original webhook-secret injection still blocks future signed webhook deliveries.
- Authentication repair validation: 108 unique backend test cases passed across focused auth/store, security/scheduling/queue/GHES/webhook/migration and provider suites; Ruff/diff checks passed. Existing frontend results below are historical, not rerun for this backend repair.

## Earlier recovery observations (historical; superseded by the continuation above)

| Requested item | Verified result |
| --- | --- |
| 1. Final status | BLOCKED; no successful real job ingestion/analysis is claimed. |
| 2. GitHub webhook | User reported actual ping/push HTTP 200 and the original durable job confirms push intake. This task did not replay another push. The existing private key was restored in the current API environment without displaying/persisting it. API still lacks the original `SCM_GITHUB_WEBHOOK`; future delivery verification is configuration-blocked until trusted operator injection is restored. Historical webhook checks are separate evidence. |
| 3. Redis | Docker Desktop engine started; official `redis:7-alpine`, `projecttrace-redis`, `unless-stopped`, binding only `127.0.0.1:6379`. `redis-cli ping` returned PONG; Windows listener confirmed. |
| 4. Worker | Refreshed worker ready and pingable, Windows solo, queues `native,large,scm,advisory,celery`. Private key inherited in memory; same local database as API. Existing Beat retained. |
| 5. Queued-job recovery | `projecttrace.recover_jobs` requested. Existing job `b0856d98-2bd3-41a2-b103-4d88e21a9075` dispatched and ran; it is now terminal FAILED, not still stranded QUEUED. |
| 6. Snapshot | None created; zero persisted source inventories for the real repository. |
| 7. Commit | Target/read-only probes: `b1fab2bc21c63335dead4daaaa28194c9878e9bf`, `refs/heads/projecttrace-snapshot-test`, `maninani12/OpenMetadata`. No commit has been analyzed into a real snapshot. |
| 8. Files/inventory | Full read-only connector probe passed all 21,636 entries: 21,566 verified byte payloads, 38 UNSUPPORTED links and 32 SKIPPED_SIZE_LIMIT files. 176,232,026 raw bytes verified; 330,420,155 declared bytes counted. Tree is not truncated. Persisted inventory count remains zero. |
| 9. Analysis | FAILED at FETCHING; no static analysis result. Started `2026-10-07T20:45:45.652599+00:00`, finished `2026-10-07T20:45:48.357260+00:00`. These are job/fetch timestamps, not successful analysis timestamps. |
| 10. Claims/findings | No real OpenMetadata analysis snapshot and no result generated by this job. Existing demo findings are not OpenMetadata results. |
| 11. Coverage limits | Links will be explicit UNSUPPORTED without following targets; files above 512,000 bytes are SKIPPED_SIZE_LIMIT. Binary, generated/vendor, unsupported-language and parser/resource coverage must be inspected after actual inventory/analysis; no clean or full semantic coverage is claimed. |
| 12. Errors | Missing Redis initially; SCM rejected the first symbolic link; original per-blob REST design would require more than 21,000 requests; provider UTF-16 text differed from raw blob bytes; ZIP rejected symbolic links; protected retry unavailable in demo session; original API webhook-secret reference absent. |
| 13. Root causes fixed | Redis restored; connector explicitly inventories unsupported links and batches large GitHub.com source reads within fixed bounds, with verified raw fallback for transcoded text; coverage classifies unsupported entries truthfully; repository-card protected retry added; explicit full local development bootstrap added; existing API private-key environment restored. |
| 14. Changed source | Listed below; changes remain uncommitted. |
| 15. Tests | Combined focused backend regression/startup run: 94 passed; final startup-only run: 4 passed (3 overlap, 95 unique backend tests overall). Full frontend suite 30 passed; frontend typecheck/build/prerender passed. Ruff, Python compilation, PowerShell syntax and diff checks passed. |
| 16. Remaining blockers | Sign into ProjectTrace as the account owning this repository before retry. Restore the original webhook secret through trusted operator injection for future webhook deliveries. A clean full-development launch and actual post-fix job result remain unverified. |
| 17. Next step | Owner signs in; execute **Retry analysis** on this existing job, monitor DB/API/log/UI through source capture and analysis, then inspect coverage and evidence before assessing accuracy. No new GitHub commit is needed. |

Repository ID: `cf4ceb64-f4c7-4166-a462-309920d4e24b`. Connection: `480730b9-b545-4636-b181-1f934b66ce23`. App: `ProjectTrace-Mani-Test` / `5227425`, installation `168967276`. Secret values and installation tokens are not included in this report.

## Continuation check of the reported FETCHING failure

The later continuation request showed the same original failure timestamps (Oct 8, 02:15 AM IST). Fresh read-only database checks confirm the same job ID, FAILED/FETCHING state, original timestamps, no retry count, no inventories, no snapshots and no native analysis stages. It is not evidence of a new failure after the connector repair.

The persisted exception type is `ValueError`. The stored reason is the generic **Provider scope changed, analysis stopped, or provider request failed**; there is no structured error-code field. Current API/worker log tails do not retain the original task traceback, and the app-terminal connector is unavailable. The precise symbolic-link error was established by the earlier live reproduction using the original connector against this exact commit: **Symlinks and submodules require explicit separate intake and are not ingested**, before the first emitted entry. This distinction matters: the report does not claim the generic database reason contains that exact exception text.

Fresh provider checks used the currently running worker's approved environment and the actual stored connection through `workers.github.configured_app`, not hardcoded replacement credentials. App 5227425 and installation 168967276 still mint an installation token; installation repository discovery, the exact Git commit, and its recursive tree each returned **HTTP 200**. `maninani12/OpenMetadata` is still authorized; the installation contains one repository; the exact returned commit SHA matches. The tree has 25,770 total entries / 21,636 files, is not truncated, and declares 330,420,155 bytes. REST rate headers show a limit of 5,000 and 4,997 remaining after these checks. No 401/403/404/409/422/429 response occurred in this check. Connection/mapping enabled state, worker actor enabled/same-tenant state, and its repository grant were also verified through the existing read-only access checks.

Those counts fit the unchanged 100,000-file / 2,000,000,000-byte inventory limits and the 200,000-entry recursive metadata bound. The 38 links and 32 files exceeding 512,000 bytes are explicit per-entry coverage limitations. The earlier entire source stream passed after repair; no provider-authentication, commit/ref, installation-pagination or whole-inventory-budget failure is demonstrated here. The corrected adapter and classifier were already loaded in the worker, so this continuation did not make another application-source change or repeat a push.

Fresh continuation tests: `pytest tests/test_scm_batch.py tests/test_scm_streaming.py tests/test_repository_store.py tests/test_ghes.py -q` — **52 passed**, 115.03 seconds, with the existing Starlette/httpx warning. An isolated test database/source/key path was used; a JUnit receipt is retained in the private task workspace. These are repeated regression checks, not additional unique tests added to the earlier total.

The controlled browser's actual Repositories view still identifies **Northstar Labs / Demo engineer / DEMO WORKSPACE** and does not contain OpenMetadata. The OpenMetadata owner page reported by the user is in another session that this browser connector cannot control. The user was asked to perform exactly one native **Retry analysis** in that already signed-in page, or sign into the owner account in the controllable in-app browser. A read-only watch observed no retry or state transition. No session was forged, password reset, repository grant changed, failed job rewritten, or direct worker invocation used to bypass the protected retry endpoint.

This is a real buyer-pilot product gap: an unsupported individual Git entry previously aborted the entire source intake, and generic persisted errors made diagnosis difficult. The intake behavior now has full live source-reading evidence and regression checks. Clear privacy-safe failure codes and post-fix source-to-analysis/UI evidence remain required; infrastructure/process readiness and a read-only source probe do not establish completed analysis or accuracy.

## Architecture audit

Supported execution modes are `sync` and `celery`. Bounded local uploads support intentional synchronous execution; a SCM webhook does not have an intended inline source-processing mode. Its task route is `scm`, so the existing durable Celery job used Redis/Celery rather than an invented bypass. API dispatch/retry requires `JOB_MODE=celery`; API and worker must agree on database, encrypted storage, operator configuration and broker. `recover_jobs` redispatches stranded queued Celery jobs after its bounded waiting interval and handles expired fenced leases. It does not reset failed terminal jobs. Beat schedules recurring recovery but is not needed for one immediate recovery.

Process ownership was verified before changes. Frontend PID 14088 on 5181 was retained; Docker backend owns the loopback Redis listener. The verified idle worker was replaced to load connector fixes; current core PID 35004, launcher 32180, node `projecttrace-validation@LAPTOP-I8MJR81P`, was verified ready and pingable. Verified API PID 11564 was refreshed with retained settings and the existing worker's approved private key in memory; current API PID 32244, launcher 35340, owns 8011. Accounts, snapshots, connection metadata, encrypted blobs and the encryption key matched the before/after fingerprints. These PIDs are observations, not durable startup configuration. API `/health` returned ok; `/ready` returned database reachable and explicitly `worker: not_checked`. Worker health was checked independently.

## Source repair and limits

The old modern streaming adapter aborted on the first symbolic link, before yielding any source. The fix records link/submodule metadata as UNSUPPORTED and never fetches or follows a target. Coverage preserves that state and records why no source parser ran. Global path validation, duplicate checks, inventory count and declared byte quotas remain enforced.

For complete large GitHub.com trees, source reads use fixed read-only GraphQL queries on the same allowlisted, pinned TLS transport. Each batch has at most 100 paths and 2 MB declared source; no imported queries, mutations, URLs or executable content are accepted. Provider object identity and byte size are checked, then received bytes must match the Git blob hash from the exact-commit tree. Binary/truncated text falls back to the original verified REST blob read. A full-source probe found a UTF-16 `DataModelSchema` blob: GitHub text encoded to 26,250 UTF-8 bytes while the raw blob was 52,496 bytes. The raw blob's UTF-16LE BOM and Git integrity were independently verified. Text failing byte size/hash verification is now discarded and falls back to raw REST bytes, which must also pass both checks; corrupt raw fallback still fails closed. GHES/small-tree behavior retains REST. No quota was expanded to make the repository pass. See the official [GraphQL Blob contract](https://docs.github.com/en/graphql/reference/git#blob) for the provider text/binary fields.

An initial live read-only sample yielded 150 entries: 116 verified source byte payloads, 32 UNSUPPORTED links and 2 SKIPPED_SIZE_LIMIT files. The post-fix full-source probe then **passed all 21,636 entries in 350.45 seconds**: 21,566 byte payloads verified against the Git tree, 38 UNSUPPORTED links, 32 SKIPPED_SIZE_LIMIT files, 176,232,026 verified raw bytes and 330,420,155 declared bytes counted. Of the fetched payloads, 21,272 decoded as UTF-8 and 294 did not; these are byte-format counts, not parser coverage classifications. The probe held only bounded batches, discarded source payloads after counting, and wrote a count-only receipt in the private task workspace. Neither probe created an inventory, retried a job or executed repository code. Neither is an analysis result. Full content-addressed capture, static analysis, result accuracy and authorized UI inspection remain unverified until owner retry.

## ZIP rejection

`OpenMetadata-main.zip` is 157,126,481 compressed bytes, with 25,771 directory entries, 21,636 files and 330,420,155 declared uncompressed bytes. It has 32 files above the per-file limit and 38 symbolic links. No compression-ratio violation above 200 was found.

Streaming intake defaults are 100,000 files, 2,000,000,000 declared bytes, 512,000,000 archive bytes and 512,000 bytes per file. The archive passes the numeric aggregate budgets; its exact fresh failure is **Archive symbolic links are forbidden**, before the first emitted entry. That maps to the generic invalid/budget error. Legacy whole-ZIP intake has smaller 10 MB/1,000-file budgets and is unsuitable for this archive independently. Archive symbolic-link safety was preserved; the archive/source was not modified or stripped of files.

Large ZIP support should use the existing bounded streaming/content-addressed intake, explicit partial coverage and actionable rejection reasons. Supporting archive links as metadata requires a separate design/review; this test did not relax that policy. The GitHub SCM path remains the primary validation path.

## Changes and executed validation

Current-task source changes:

- `integrations/github/connector.py`: bounded verified blob batches and unsupported link/submodule metadata.
- `analyzers/code_quality/classification.py`: truthful UNSUPPORTED inventory classification.
- `frontend/src/WorkspaceApp.tsx`: native repository-card action for the existing scoped retry API.
- `scripts/start.ps1`, `scripts/dev_workers.py`: explicit local development infrastructure/preflight.
- `tests/test_scm_batch.py`, `tests/test_scm_streaming.py`, `tests/test_repository_store.py`, `tests/test_dev_workers.py`, `frontend/src/RepositoryRecovery.test.tsx`: relevant tests.
- `README.md`, `docs/operations.md`, `docs/github-integration.md`, this report: operation and measured-status documentation.

Earlier uncommitted webhook repair files (`backend/scm_webhook.py`, `tests/test_scm_webhook.py`, `docs/GITHUB_WEBHOOK_REGRESSION_VALIDATION.md`) were preserved. The webhook tests were included in the fresh regression run. An unrelated pre-existing untracked `wq` file was left untouched. HEAD remains `312156abd0d11b1008ce9385cd494087ba6dbf70`; no ProjectTrace commit/push or OpenMetadata write/push was performed.

Fresh commands/results:

- `pytest tests/test_scm_batch.py tests/test_scm_streaming.py tests/test_repository_store.py tests/test_ghes.py tests/test_scm_webhook.py tests/test_queue.py tests/test_fair_scheduling.py -q`: **89 passed**, 184.87 seconds, isolated source/key/test paths. JUnit receipt retained in the private task workspace.
- `pytest tests/test_dev_workers.py -q`: **3 passed**; rerun after import sorting also passed.
- Final post-encoding-fix run, the same seven backend suites plus `tests/test_dev_workers.py`: **94 passed**, 191.79 seconds, including UTF-16/transcoded text and corrupt raw fallback checks. Earlier runs are not added to this count.
- Final startup guard check, `pytest tests/test_dev_workers.py -q`: **4 passed**, including refusal to duplicate a busy solo worker that cannot answer control ping. Three tests overlap the combined run; **95 unique backend tests** were exercised overall. Bootstrap verifies this project's Windows launcher before depending on broker ping.
- `npm.cmd test -- --run src/RepositoryRecovery.test.tsx`: **4 passed**; subsequent complete `npm.cmd test -- --run`: **30 passed across 7 files**, including those four.
- `npm.cmd run build`: **passed**, including TypeScript checks and 41 prerendered public routes.
- Ruff on changed Python implementation/tests: **passed**; compileall on changed Python implementations: **passed**.
- PowerShell AST parse of `scripts/start.ps1`: **zero syntax errors**; `git diff --check`: **passed** (normal Windows line-ending notices only).
- Configuration-only worker preflight: **correctly refused** missing configured SCM references in the fresh tool environment; no secret values displayed or services launched by that check. This is not a successful clean full-stack launch.

The tests emitted an existing Starlette/httpx deprecation warning. Full backend, production-container, sustained-load, live GHES and analyst-accuracy validation were not run. No OpenMetadata installer, build, package lifecycle, script, container, Terraform, or tests were executed.

## Buyer-pilot answer

**No, not yet demonstrated by this installation.** A customer of a managed deployment should not need to start Redis/Celery themselves; those are operator responsibilities. This local run exposed incomplete startup and recovery visibility, and the real post-fix source-to-analysis workflow is still blocked.

Before a buyer pilot: deploy and monitor the API/worker/broker stack with durable operator-secret injection; surface worker/queue readiness separately from API liveness; automatically capture the initial authorized repository snapshot on connect; give actionable fetch/quota/archive diagnostics and a visible scoped retry path; verify bounded large-repository capture and truthful coverage with this actual job; then inspect claims/evidence and measure analyzer accuracy. The retry button and local bootstrap now have automated checks, but their complete real owner workflow and a clean full-stack launch remain to be exercised. Existing partial language semantics, installation pagination/grant synchronization, sustained queue load and private-deployment/GHES testing remain product gates rather than implied enterprise readiness.
