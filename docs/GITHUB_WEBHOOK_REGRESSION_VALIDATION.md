# GitHub App webhook regression validation — 2026-10-08

## Real-world finding

ProjectTrace rejected GitHub App ping deliveries because webhook installation validation was performed before ping-event handling. Signed ping events without installation.id returned SCM webhook installation scope is invalid. Repository-affecting events must remain installation-scoped.

The user previously established authentication and repository discovery for `ProjectTrace-Mani-Test` (App `5227425`, installation `168967276`) and `maninani12/OpenMetadata`. The reported pre-fix checks were 422 for a signed ping without installation and 200 when installation was supplied. These are previously reported observations, not newly executed authentication/discovery tests in this repair.

The connection is `480730b9-b545-4636-b181-1f934b66ce23`. The local API is `http://127.0.0.1:8011`; UI is `http://127.0.0.1:5181`.

## Minimal implementation

`backend/scm_webhook.py` still looks up the configured connection, resolves its operator secret reference, and verifies the unchanged HMAC SHA-256 implementation before parsing JSON. Parsing now requires a JSON object and returns 422 for malformed or non-object input. The event is read before conditional installation validation.

Only exact event `ping` may omit installation. Every other event, including `installation`, `installation_repositories`, and unsupported events, must match the configured installation ID. The bounded delivery identifier remains mandatory. Non-ping installation checks occur before duplicate lookup so replaying an accepted ping identifier as a push cannot bypass scope validation. Connection-scoped deduplication and the original duplicate response remain intact.

Ping uses the existing enabled-connection, enabled-owner, owner-organization, audit, and delivery-persistence path. Repository events retain connection/organization/provider-ID mapping, revocation checks, commit validation, repository grants, and existing worker processing. No customer code is executed.

## Newly executed automated validation

Used the project's existing `.venv\Scripts\python.exe`. Test database, source blobs, uploads, and encryption key were isolated under the chat workspace's `work\webhook` directory; tests did not use live SCM secrets.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scm_webhook.py tests/test_ghes.py tests/test_github.py tests/test_scm_streaming.py -q --basetemp 'C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\webhook\focused-final' --junitxml 'C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\webhook\focused-final.xml'
.\.venv\Scripts\python.exe -m ruff check backend/scm_webhook.py tests/test_scm_webhook.py
.\.venv\Scripts\python.exe -m compileall -q backend/scm_webhook.py tests/test_scm_webhook.py
git diff --check
```

Final result: **46 passed in 79.64 seconds**. Ruff, compilation, and whitespace checks passed. Pytest emitted an existing Starlette/httpx deprecation warning.

The new regressions cover signed ping without installation, invalid signature, valid push and PR enqueueing, incorrect/missing installation for all non-ping events, malformed/non-object JSON, missing/oversized delivery IDs, the 100-character boundary, duplicate behavior, replay scope, ignored unsupported events, disabled connection/owner, and an owner from another tenant. Existing tests additionally exercise repository scope, fork handling, revocation, cross-tenant access, worker snapshot processing, and provider streaming/transport contracts using controlled adapters.

The first run had 45 passes and one new test setup failure: attempting to reassign a user's tenant was rejected by the existing immutable-tenant guard. The test was corrected to reference an existing owner from another tenant. No security guard or prior test was weakened. The final results above were freshly executed after that correction. Earlier broad validation results elsewhere in this repository were not rerun and are not evidence for this repair.

## Newly executed live local validation

Credentials were checked for presence only. The original API listener PID `19996`, its ProjectTrace venv launcher, working directory, and port were verified before stopping it. Approved application settings and SCM credentials were retained transiently from the verified process environment; after the first script failure, the independently verified original PowerShell launcher supplied the same credential references in memory. No key, webhook secret, signature, or token value was printed or persisted.

`& .\scripts\start.ps1` was attempted from that credential-bearing PowerShell environment and rejected by Windows script execution policy. After the script failed, the allowed fallback started the existing venv's `uvicorn backend.main:app --host 127.0.0.1 --port 8011` with the retained environment. No execution policy was changed. The verified new listener is PID `17356`; `/health` returns 200. Existing UI remains on port 5181, PID `14088`.

Signed local requests used fresh random delivery IDs and the real configured connection. Validation completed at `2026-10-07T19:47:07Z` (2026-10-08 IST).

| Request | HTTP | Result |
| --- | --- | --- |
| Ping `{"zen":"projecttrace-real-ping-shape-test"}`, no installation | 200 | `RECEIVED`, `NOT_APPLICABLE` |
| Same signed ping delivery repeated | 200 | `DUPLICATE` |
| Signed push, installation `999999999` | 422 | `SCM webhook installation scope is invalid.` |
| Signed push, missing installation | 422 | `SCM webhook installation scope is invalid.` |
| Ping with invalid signature | 401 | `SCM webhook signature is invalid.` |

Preservation comparisons passed for existing password hashes, snapshot records, SCM connection metadata, source blob contents, and the analysis encryption key. These comparisons record only booleans in the private receipt.

Private reproducibility artifacts are `work\webhook\runtime_validation.py`, `runtime-receipt.json`, `public_validation.py`, `public-receipt.json`, and `focused-final.xml` in the chat workspace. They contain no live secret values. No commit or push was performed.

## External verification: PENDING MANUAL ACTION

The already-running cloudflared process was verified as exposing only the API URL. Its current host was obtained from its local metrics endpoint, rather than an old tunnel URL. A signed real-shape ping through the current HTTPS tunnel returned 200 and `RECEIVED`/`NOT_APPLICABLE` at `2026-10-07T19:50:27Z`.

The temporary webhook URL active at that time is:

`https://null-bread-scales-attempted.trycloudflare.com/api/github/webhook/480730b9-b545-4636-b181-1f934b66ce23`

This proves tunnel delivery from the local test client, **not an actual GitHub delivery**. The GitHub App Advanced page redirected to account sign-in; account authentication was not automated and credentials were not stored. The sign-in page has been left open for the user.

Next manual action: sign in to GitHub, confirm the App's webhook URL is the current tunnel endpoint, then go to Settings → Developer settings → GitHub Apps → ProjectTrace-Mani-Test → Advanced → Recent deliveries → Redeliver the ping. Expected result: 2xx. Recheck the active host if the tunnel restarts.

## OpenMetadata source ingestion

Fresh read-only database inspection before and after the local checks found: **connected YES; snapshots 0; source inventories 0; jobs 0; analysis started NO**. The existing runtime uses `JOB_MODE=sync`.

The existing legitimate push workflow is:

1. Verify signature, exact installation, bounded delivery, and configured tenant/repository mapping by provider repository ID.
2. Validate the payload's head commit SHA and durably enqueue the scoped GitHub analysis job.
3. In `JOB_MODE=celery`, dispatch `projecttrace.github_delivery` through the existing queue.
4. The worker rechecks the actor's repository grant, connection version/enabled state, mapping revocation, organization, and fenced job lease.
5. The GitHub App obtains an installation token and streams the installed repository's tree and SHA-verified blobs at that commit through the bounded encrypted source store into a persisted inventory. Imported source is data, never a build or executable.
6. The existing analysis pipeline consumes that inventory and persists the commit-bound snapshot and job result. PRs can also capture or reuse their authorized base snapshot. Publishing checks additionally requires the existing tenant opt-in policy.

No existing backend action that fetches a connected repository immediately was found. `/api/repositories/{id}/analyze` analyzes explicitly supplied files; it does not fetch GitHub source. Connecting a repository establishes its mapping and grant without enqueuing source capture. The existing job retry action requires Redis/Celery and a retained job. No separate Analyze Now feature was added, no fabricated successful OpenMetadata push was sent, and no imported repository commands were run.

After real ping redelivery, source capture requires a legitimate scoped push/PR delivery and the existing Redis/Celery provider worker configured with the same operator credential references. In the current sync runtime, a successful push receipt would remain queued without provider dispatch. Real OpenMetadata snapshot ingestion, its analysis, actual GitHub redelivery, live check publication, broader GHES operation, and enterprise readiness remain unverified by this repair.
