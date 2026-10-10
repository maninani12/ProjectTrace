# ProjectTrace Administration & Control Center - final validation

Date: 2026-10-10. **Final verdict: ADMIN_FEATURE_READY_FOR_DEMO for the documented local administration scope. Complete product/pilot readiness remains BLOCKED.** Additive migrations 0019 and 0020 are applied to the original installation, and preservation is verified. ProjectTrace is running at `http://127.0.0.1:5181/administration`. Sign in with an existing authorized organization account. No customer password was reset, account elevated, database seeded, commit created or code pushed.

## Implementation and architecture

The existing product is extended, not rebuilt. Shared User, Organization, Grant, Record, inventory, snapshots, findings, Claim Ledger, Evidence Graph, review and audit stores remain authoritative. Additive migration 0019 introduces 22 governance tables and backfills existing primary memberships and session contexts. Migration 0020 adds an activity outcome index without modifying payloads. A selected SessionContext resolves explicit organization membership separately from the identity's immutable primary organization.

Central authorization in `backend/governance.py` derives granular role permissions, current membership/global restrictions, active delegated teams, explicit repository grants/inheritance minus denials, and effective feature access. It denies unknown roles/features and never gives platform operators automatic source access. The existing request, intake, dispatch, workers, OIDC lifecycle, trust, profiles and review controls use the shared decisions. Existing snapshot scope and organization isolation remain enforced.

Administrative commands require CSRF, bounded strict fields, a reason, an idempotency key, expected versions where applicable, and fresh supported assurance for sensitive actions. Short serialized transactions recheck authority and atomically store the mutation, audit chain, activity mirror and command receipt. Stale versions return 409; audit failure rolls back. Platform emergency release and operator changes require a distinct current super administrator. Ownership requires designated target consent. Expiration participates in the browser's access decision version; protected caches clear on changes or 401/403.

Implemented UI includes paginated members/invitations/teams/repositories/jobs/activity/audit/notices, minimal scoped record lookup, team operational views, feature preview/history/new-revision restoration, ownership consent, security/health metadata and usage reports. Administration loads independently of the engineering graph. APIs retain the 15-second client deadline and honest loading/error/empty/partial states. Local password reauthentication is not labeled MFA.

The [operator guide](docs/ADMINISTRATION_GUIDE.md) explains lifecycle, feature precedence, privacy, retention, bootstrap and recovery. The [exact role matrix](docs/ADMINISTRATION_PERMISSIONS.md) lists implemented permission keys. The [baseline architecture plan](docs/ADMINISTRATION_ARCHITECTURE_AND_PLAN.md) records the initial audit and implementation order.

## Demonstrated defects and corrections

- PostgreSQL aggregation repeated JSON expressions with different bind identities in SELECT/GROUP BY and raised GroupingError. Reusing the same state/day/source expression objects fixes the generated SQL; an actual PostgreSQL API regression verifies dashboard/usage/actor results.
- New activity mirroring assumed every audit actor had a user ID and broke the existing filesystem-operator retained-analysis retry. Unauthenticated maintenance activity now has no fabricated user ID; the original audit identity is preserved. Its authorization, retained inventory and attempt-history regression passes.
- High-volume denied-event counts lacked a covering outcome index and scanned tenant activity payloads. Profiling recorded 5.5851 seconds and 2.2812 API-process CPU seconds for this count. The outcome index enables a covering tenant/outcome/time range.
- Activity/audit timelines ordered timestamp DESC and ID ASC against indexes whose keys have matching direction. SQLite built a temporary B-tree for tied timestamps. Ordering both keys DESC removes that sort while keeping stable, exact scoped pagination. Actual API query-plan and disjoint-page tests verify the behavior.
- A browser abort alone did not stop a SQLite metadata statement. Administration now installs a ten-second server query-work budget and returns sanitized DATABASE_BUDGET/503 on interruption. Pool check-in clears the handler so repository workers never inherit an expired administrative deadline. PostgreSQL retains five-second lock/ten-second statement budgets. This cannot promise an absolute wall deadline under an unresponsive OS/storage scheduler.
- Existing analyzer fixtures omitted explicit source grants and now correctly failed central authorization. The fixtures and owned benchmark setup now grant their own repositories; authorization was not weakened. A redundant test grant was removed. Cross-tenant audit assertions now distinguish a legitimate own LOGIN_SUCCEEDED event from other-tenant events.
- Legacy frontend identity fixtures needed compatibility guards. Accessible exact field labels, invitation/notice mutation deadlines, own notifications, inline-sign-in identity refresh and restricted-account invitation CSRF recovery were completed. Browser assertions now wait for submitted authentication to finish rather than abort it through navigation. Guide assertions include the new 35th topic. Screenshots wait for the mobile drawer transition; they do not declare a transient frame a layout result.

## Preservation and migration evidence

A verified recovery bundle contains the complete 10.3 GB SQLite database and 67,561 decrypted/hash-verified encrypted blobs, with keys separately retained. It took 4,145.1353 wall seconds. No customer reset or source execution occurred.

On a full copy, 0019 upgrade, untouched-governance downgrade and repeat upgrade preserved 81 users, 81 organizations, 77 repositories, 77 direct grants, 149 sessions, 1,788,253 Records, 67,561 blob records, 134,344 inventory-file records, 8,139 audit events, 6,135 audit links and all 181 raw snapshot hashes/credential state. Full quick_check and all foreign-key checks passed. Total qualification took 1,112.5121 seconds. Migration 0019 SHA256 is `131da2a2f24ad5bd70a72d0ce62a47d3985b6277f1d91d4ae5052389a6e8fb1c`.

0020 was separately qualified on that preserved full copy through upgrade/downgrade/repeat upgrade, all-table count/snapshot/credential comparisons and affected-table integrity/FK checks. It took 436.4121 seconds; migration operations were 2.0709, 1.7074 and 1.9116 seconds. The copy's whole-database integrity had already passed; the only later change is the additive index. 0020 SHA256 is `38923927cb81980988c3e2286982707357f5c7842e59ea63025048941511002f`.

The private QA API/UI clean restart at 0020 preserves all table counts, snapshot hashes, credential digest and complete existing audit-row hash. The original API/UI was then gracefully stopped with no queued/running jobs, the existing operator settings were loaded, and additive head 0020 was applied during managed startup. The original before/after comparison passed: every pre-existing table count, all 181 raw snapshot payload hashes, credential digest and complete existing audit-row hash are identical. Backfills contain 81 organization memberships and 149 session contexts. Before/after proof took 60.064650 / 41.200553 wall seconds. Original platform bootstrap has not been run; no customer account has been elevated or password reset.

After rollout, three repeated checks each passed API readiness, proxied auth options and the Administration HTML (200), while anonymous administration dashboard requests returned 401. Maximum readiness check was 0.111857 seconds; maximum auth-options check 0.036244; maximum HTML check 0.019224. HTML timings do not measure authenticated data loading. The owned managed API/UI process identities were verified. Original customer interactive authentication was not performed: browser acceptance used explicitly authorized private fixture accounts, not customer impersonation. Separate QA API/UI and the task-owned PostgreSQL container were stopped after completed tests, preserving their data. The original 8011/5181 services remain running.

## Performance evidence and limits

Hardware: Windows 11 Home build 26300, Intel Core 5 120U (10 cores/12 logical processors), approximately 16.8 GB physical RAM, Python 3.14.3, SQLite 3.50.4, SQLAlchemy 2.1.3. The test database contains 500,000 synthetic activity rows across two tenants, 1,000 disabled-local-login fixture members, 10,000 synthetic jobs and 80 initial teams, plus actual private browser-analysis fixtures. Imported source fixtures are only read as text. They are never executed.

A measurement-only repeat after the query fixes and clean restart includes 39 serial reads across 13 endpoints followed by 40 reads across eight concurrent readers: **79/79 passed within 15 seconds**, maximum **6.381756 seconds**. First process access maximum: 6.381756; warm repeat maxima: 0.516846 and 0.447165; eight-reader maximum: 1.258849. Total request measurement wall time: 19.874619 seconds. API process-tree CPU: 18.875 seconds. Sum of separate process lifetime memory peaks: 487,489,536 bytes; this is not a simultaneous high-water or per-job memory measurement. OS caches were not flushed. No application aggregate cache was added.

Earlier measurements are retained: first population maximum 5.26213 seconds; restart maximum 4.531339 seconds. The first resource sampling incorrectly measured only the Windows venv launcher; its CPU/memory values are invalid and excluded. Corrected runs enumerate the actual owned API process tree.

A cold stress run during full-copy scans and backend regression **failed**: 18 reads exceeded or failed the deadline, maximum client observation 15.030985 seconds. Query profiling observed server waits up to 208 seconds with much less CPU time. At observation, this PC had roughly 1.3 GB available RAM and 32 GB committed. These are actual failed measurements, not passing runs, and complete archive scans are outside the claimed passing workload. The query corrections and server work budget mitigate demonstrated SQL costs and abandoned work; no unconditional 15-second SLA under system/storage exhaustion is claimed. Production hardware, sustained multi-host traffic and analyzer memory remain unqualified.

## Tests and release gates

Receipts/logs and private proofs are retained outside the product tree in this chat's `work/admin-control-center` directory. They contain synthetic account data and recovery metadata and are not public downloads. Completed receipts are not overwritten. Tests use isolated SQLite files/disposable PostgreSQL UUID schemas, never the original customer's database.

Completed gates so far: initial auth/API/OIDC/queue/migration baseline 36 passed; administration lifecycle/feature/worker/operations suite 36 passed; metadata-budget, query-plan, recovery/queue/repository/migration suite 46 passed; actual PostgreSQL administration/concurrency/tenant isolation test 1 passed; frontend 41 unit tests passed; production/SSR build passed and prerendered 42 public routes; administration browser critical path 3 passed after restart. The full backend regression passed 526 tests in 1,297.36 test seconds / 1,304.9001 wall seconds, including actual disposable PostgreSQL integration. It began before the final SQLite administration deadline/pool guard was added; the separate 46-test budget/recovery suite validates that subsequent correction. Frontend unit tests passed 41, build passed with 42 public routes, final administration browser tests passed 3 (including mobile layout), and the repeated broader browser suite passed 15 with 3 explicitly skipped cases in 196.9266 wall seconds. Lint and git diff whitespace checks pass. Counts across overlapping suites are not added as unique tests.

Retained failed runs exposed the defects/test-assumption changes listed above. One full run before the maintenance-actor correction had 522 passed/1 failed. The next private repeat was explicitly stopped to apply measured query/index corrections; it is ABORTED, not PASS. The corrected full suite passed 526 tests; subsequent metadata-deadline/pool changes have their separate passing 46-test suite. Browser suites explicitly skip large-customer-mirror and production-static-server cases when those fixtures are not configured; skipped cases do not count as passes.

## Supported administration scope versus remaining limitations

Implemented: organization and delegated-team lifecycle, manual single-use invitations, role/version/session controls, explicit repository grants/denials, eight workflow feature policies, scoped admission quotas, fenced job cancel/retry, command audit rollback/idempotence, prospective team attribution, bounded SQL analytics/activity/audit exports, private in-app notices, metadata-only platform operations, offline two-credential bootstrap and bounded owner-confirmed routine retention.

Partial/unavailable: automatic invitation/email/SMS delivery, selectable per-analyzer controls, resource limits without enforcement/measurements, automatic anomaly detection, comprehensive worker heartbeats/CPU/memory metrics, immutable external compliance archive, customer source-support elevation, historical team reconstruction, full IdP/GHES/provider production/browser qualification, database RLS defense, complete helper sandbox and sustained production throughput. The routine activity buffer is bounded/best-effort and can drop; required governance audits remain transactional. No original retention deletion occurred.

The actual original OpenMetadata and Spring PetClinic published results remain PARTIAL for the documented parser/unsupported/claim-cap/coverage reasons in [repository reliability validation](REPOSITORY_ANALYSIS_RELIABILITY_FINAL.md). Administration preserves their snapshots and diagnostics. No fresh unchanged large analysis has been declared complete by this feature delivery. Cold large analysis, memory envelope and representative semantic coverage remain whole-product release blockers. Existing native quality/security/cloud capabilities do not depend on SonarQube or Wiz.

## Acceptance coverage and provenance

PASS applies only to the listed implementation and test scope. PARTIAL means implemented subsets with disclosed limits; NOT_TESTED means this delivery provides no new acceptance evidence for that item.

| Area | Result | Actual evidence / boundary |
| --- | --- | --- |
| Identity, organization switching and role enforcement | PASS in private fixtures | Authenticated owner/admin/delegated/standard/auditor tests; selected-membership context; cross-tenant rejection; versioned changes and last-owner safeguards. Original customer interactive login NOT_TESTED. |
| User lifecycle, invitations and scoped session revocation | PASS for manual invitations | Single-use matching-identity acceptance, suspension/reactivation/removal, unrelated membership isolation and revocation tests; browser invitation/reactivation walkthrough. Automatic message delivery unavailable. |
| Teams and repository access | PASS in qualified control paths | Team delegation, inherited grants and explicit denial; unrelated team/tenant negative tests; browser cache revocation and team management. Platform roles receive no source grant. |
| Features, expiration and worker authorization | PASS for eight catalog features | API/dispatch/worker denial and expiration tests; browser direct ZIP denial, preview and restoration. Per-analyzer toggles unavailable. |
| Platform safety, ownership and bootstrap | PASS for private API/security tests; browser PARTIAL | Distinct-operator approval, designated-owner consent, mandatory deny and offline two-credential bootstrap tests. No original bootstrap and no full platform-role browser walkthrough. |
| Quotas, job cancellation/retry and recovery | PASS for supported admission/job controls | Bounded org/team/user pending/daily quotas, concurrency, fresh authority and finite fenced recovery; original inventory/history retained. Configurable CPU/memory SLA controls unavailable. |
| Activity, audit and privacy | PASS for scoped documented metadata | Actor attribution, redaction, indexed filtering/disjoint pagination, transactional audit rollback and controlled exports; real browser filtering/export. Required governance audits are durable; routine telemetry is best-effort. External immutable archive unavailable. |
| Usage, operational graphs and health | PARTIAL | SQL counts/trends, wall-time/queue-wait when recorded and organization storage provenance are tested. Worker heartbeat, CPU and memory values remain unavailable; no fabricated business data. |
| Volume and concurrent read workload | PASS for stated local fixture workload | 500,000 activity events; 79 reads, including eight concurrent readers, all within 15 seconds. Simultaneous archive-scan stress FAILED; no unrestricted SLA. |
| Schema and clean restart preservation | PASS | Full-copy upgrade/downgrade/re-upgrade qualification; original 0018 to 0020 rollout preserves all old counts, 181 raw snapshots, credentials and audit hash; QA restart preservation verified. |
| Existing source/evidence workflows | PASS for current private small fixtures; large scope PARTIAL | Browser ZIP analysis, claims/source evidence, review/findings/drift/trust/scope plus existing regression suite. Customer large snapshots and diagnostics preserved; no fresh cold full large analysis in this delivery. |
| Provider and deployment qualification | PARTIAL / NOT_TESTED | Existing local OIDC/SCM worker regressions and actual disposable PostgreSQL tests pass. Full IdP/GHES, production multi-host services, database RLS defense and complete helper sandbox remain unqualified. |

The final administration browser suite executes three real workflows: (1) authenticated volume dashboard/activity filters, server pagination, sanitized export and mobile layout; (2) matching-identity invitation, team delegation, direct feature denial, repository-cache revocation and membership reactivation; (3) new source-fixture import/analysis with scoped claims/evidence and administrative job metadata. It does not substitute a pre-imported demonstration for intake. The broader final browser suite executes 15 workflows and explicitly skips three missing customer/static fixtures.

| Completed run | Actual result | Wall seconds |
| --- | --- | ---: |
| Full backend `backend-release` | 526 passed, 1,297.36 test seconds; before the last SQLite deadline/pool guard | 1,304.900144 |
| Latest budget/query-plan/recovery `administration-budget-final` | 46 passed, 134.39 test seconds; covers the subsequent guard and pool recovery | 140.630 |
| Actual PostgreSQL `postgres-release` | 1 passed, including concurrent updates and tenant isolation | 21.854 |
| Frontend `frontend-unit-release` | 41 passed | 51.916 |
| Production/SSR `frontend-build-release` | Build passed; 42 public routes / 35 Guide topics | 34.756143 |
| Final administration browser `browser-admin-visual-final` | 3 passed, 36.7 test seconds; responsive screenshots inspected | 39.287919 |
| Final broader browser `browser-existing-final` | 15 passed / 3 explicitly skipped | 196.926635 |
| Latest lint `lint-final` | Passed | 0.251178 |

These suites overlap; their counts are not summed as unique tests. The last global backend suite was not rerun after the narrowly scoped SQLite budget correction; its current-state evidence is the separate passing budget/queue/repository/migration suite. No skipped, aborted or failed receipt is labeled PASS. No independent security assessment or legal-compliance qualification is claimed.

## Final decision

**ADMIN_FEATURE_READY_FOR_DEMO:** the implemented local organization/delegated administration scope has actual backend, PostgreSQL, concurrency, browser, volume, failure-recovery and restart/preservation evidence. The original installation is at 0020 and ready; qualified local controls can be demonstrated using existing authorized memberships. Platform controls have private API/security tests and a documented two-credential bootstrap, but no original operator was created. This is not a claim that every master-prompt capability is complete.

**Complete ProjectTrace product/pilot gate: BLOCKED.** Fresh cold large-repository analysis, sustained memory/throughput, independent semantic coverage, complete production provider qualification and the security/operations limitations below remain open. The failed stress measurement is retained. Original interactive owner acceptance and the three skipped customer/static mirror browser cases are NOT_TESTED by this delivery. No commit or push has been made.

## Files changed

The working tree is uncommitted. Shared enforcement changes are in authentication/governance, OIDC/SCM, queue/workers and tenant persistence. New administration modules supply controls; migrations are additive; frontend routes reuse the existing application. Tests/benchmarks grant only their own fixtures. Complete current change list:

```text
backend/db.py
backend/domain.py
backend/jobs.py
backend/main.py
backend/native.py
backend/oidc.py
backend/oidc_lifecycle.py
backend/quality_api.py
backend/queue.py
backend/repository_read.py
backend/scm_connections.py
backend/security.py
backend/trust.py
backend/trust_api.py
docs/RELEASE.md
frontend/e2e/public-site.spec.ts
frontend/e2e/real-import.spec.ts
frontend/src/App.tsx
frontend/src/WorkspaceApp.tsx
frontend/src/api.ts
frontend/src/public/guideContent.ts
frontend/src/routes.ts
scripts/admin.py
scripts/benchmark_repository_analysis.py
scripts/benchmark_repository_scale.py
tests/test_analysis_performance.py
tests/test_api.py
tests/test_migrations.py
tests/test_postgresql_integration.py
tests/test_repository_store.py
workers/advisories.py
workers/github.py
workers/public_github.py
workers/tasks.py
ADMINISTRATION_CONTROL_CENTER_VALIDATION.md
backend/activity.py
backend/admin_api.py
backend/admin_common.py
backend/admin_features.py
backend/admin_models.py
backend/admin_operations.py
backend/admin_people.py
backend/admin_platform.py
backend/admin_quotas.py
backend/governance.py
backend/job_control.py
backend/migrations/versions/0019_administration.py
backend/migrations/versions/0020_activity_outcome_index.py
docs/ADMINISTRATION_ARCHITECTURE_AND_PLAN.md
docs/ADMINISTRATION_GUIDE.md
docs/ADMINISTRATION_PERMISSIONS.md
frontend/e2e/administration.spec.ts
frontend/src/Administration.test.tsx
frontend/src/Administration.tsx
frontend/src/Invitation.tsx
frontend/src/administration.css
scripts/bootstrap_platform.py
scripts/retain_activity.py
tests/test_administration.py
tests/test_administration_acceptance.py
tests/test_administration_api.py
tests/test_administration_features.py
tests/test_administration_operations.py
tests/test_administration_postgresql.py
tests/test_administration_workers.py
```

## Executed validation commands

The receipt runner sets isolated SQLite paths, keys/blob roots, distinct pytest basetemp/XML paths, and an explicitly owned disposable PostgreSQL URL. No test command points at the customer's database. Exact core commands:

```text
python -m pytest -q --durations=15
python -m pytest -q tests/test_administration.py tests/test_administration_api.py tests/test_administration_features.py tests/test_administration_workers.py tests/test_administration_operations.py tests/test_administration_acceptance.py
python -m pytest -q tests/test_administration_acceptance.py tests/test_administration_operations.py tests/test_queue.py tests/test_repository_store.py tests/test_migrations.py
python -m pytest -q tests/test_administration_postgresql.py
python -m ruff check backend analyzers tests workers scripts integrations
npm test
npm run build
npx playwright test administration.spec.ts
npx playwright test --grep-invert "administration|current ZIPs|rate-limited identity"
git diff --check
```

The browser suites use the private QA API/UI on 8014/5184. Broad browser skips are: exact large snapshot mirror, production static server without JavaScript, and current-customer repository failure-recovery mirror. These are NOT_TESTED by this administration run; prior repository-reliability receipts remain historical evidence.

Private backup/copy qualification, measurement-only benchmark and preservation commands use receipt-producing helpers in this chat's work directory. Managed original rollout uses `python -m scripts.dev_runtime stop` / `start` with existing local settings; it never seeds or resets data.
