# ProjectTrace final stability and release validation

Date: 2026-10-09. Product directory: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`.

**Readiness verdict: BLOCKED for a complete production release.** The Overview/count/pagination defects and the current retained-input OpenMetadata timeout have been corrected and validated locally. The measured local acceptance scope passes; large cold analysis, the configured 1 GiB worker resource envelope, durable global-correlation continuation, and live enterprise integrations remain unqualified. These limitations prevent a whole-product PASS.

The installation remains available at http://127.0.0.1:5181. No user database was reset, no owner password was changed or disclosed, no imported code/build/install script was executed, and no code was committed or pushed. Existing unrelated changes were preserved.

## Environment and evidence

Windows 11 Home Single Language 10.0.26300; Intel Core 5 120U, 12 logical processors; 16,806,244,352 bytes RAM; Python 3.14.3; SQLite 3.50.4; SQLAlchemy 2.1.3. Installed API/UI ports are 8011/5181. The current repository incident uses the local queue; a separate Celery solo worker and Beat were refreshed after verifying their queues were idle. SQLite retains WAL, foreign keys, durability settings, one admitted analysis writer and the existing 32 MiB connection-cache target. Parser helper concurrency remains bounded at two; the measured large runs observed one active helper and 23 helper launches.

Additive schema migrations 0015–0018 are installed. The 900-second analysis budget, parser/node limits, claim cap, archive protections, retries and tenant fences remain enabled. The desktop workload and OS file cache were not controlled. At one point the host reached about 95% memory utilization while tests and a broad integrity scan overlapped; later suites ran without that overlap. No deployment SLA is inferred from these local measurements.

Private raw receipts, logs, JUnit and Playwright results are retained in:

`C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\release-stability`

Important receipts: `before.json`, `pages-union-final.json`, `pages-final-covering.json`, `record-key-benchmark.json`, `measured-retry-1.json`, `measured-retry-2.json`, `measured-full-repeat.json`, `actual-imports-final.json`, `actual-imports-clean-repeat.json`, `crash-recovery.json`, `preservation-final.json`, `installed-integrity.json`, `typed-publication-consistency.json`, `backend-acceptance.xml`, and the two final browser result/proof directories. Private account and connection files are deliberately excluded from this report.

Historical reports are not fresh qualification. The previous correlation report is preserved byte-for-byte under `docs/history/CORRELATION_PERFORMANCE_FINAL_VALIDATION_before_release_2026-10-09.md`; its SHA-256 is `ea6966ffef823ca2d6abbebc3911e25b0c586c4317787ac501f571d05f3eb539`. The current correlation report identifies the separate current incident and measurements.

## Root causes and corrections

1. **Overview consumed a capped global record list.** On the actual large tenant, the legacy workspace read took 12.843888 seconds and serialized 5,178,971 bytes. The latest 5,000 records were predominantly graph records; claims and findings were absent from that slice. A prior summary path still loaded large snapshot payloads and supplied empty arrays, which the UI treated as zero. Thus the zero dashboard was not a genuine zero-result scan. Repository authorization/filtering also needed to occur before latest-snapshot ranking.

   The modern UI now uses complete, authorized latest-snapshot counts and a small preview, independent of detailed arrays. A version-checked `snapshot_views` projection is published in the same transaction as its snapshot. Covering indexes support snapshot selection, claim states, finding severity and review aggregates. Counts carry an explicit complete-scope contract; missing/failed contracts become visible errors. PARTIAL, failed-with-retained-results, active, empty and completed states are distinct.

2. **Large detail views lacked authoritative server pagination.** `/api/workspace/records` now supplies stable pages, totals, server search/state filters, repository scoping and authorized historical-snapshot selection. UI pages use 50 rows; the API enforces 1–200, bounded search/state lengths and a maximum offset of one million. Source content is loaded separately when inspecting a record. Repository selection resets page offsets. Page-only statistics are labelled accordingly. The legacy bulk endpoint still explicitly reports its 5,000-row truncation; it is not used as the modern dashboard's complete evidence source.

3. **Graph queries missed expression indexes and an OR selected an expensive plan.** Developer-owned literal JSON paths match the indexed expression; request values remain bound parameters. Indexed source/target edge queries now use a distinct UNION, preserving all 118 measured relationships and self-edge behavior. Before reads measured components 14.5727 seconds and neighborhood 27.3639 seconds. A literal-path-only intermediate OR plan regressed neighborhood to 118.4444 seconds; it was rejected. The final read-only probe measured components 0.0351 seconds and neighborhood 0.7343 seconds. These probes and browser HTTP results have different cache/observer conditions and are not a universal speedup ratio.

4. **The remaining correlation cost was predominantly SQLite graph insertion.** After the earlier safe batching/cache/history repairs, a fresh original retry still failed at a stored 900.74175 seconds. Function graph construction had not finished; leaf SQL insertion samples and flush timing dominated. The controlled experiment and minimal storage-identity correction are detailed in `CORRELATION_PERFORMANCE_FINAL_VALIDATION.md`. New Record storage IDs use UUIDv7; an implicit natural key reuses that ID instead of introducing a second random key. Explicit semantic keys, stable finding fingerprints, existing IDs, tenant/FK guards and atomic publication are preserved. No analyzer was disabled and no graph was truncated to pass.

5. **Reads could leave indefinite loading or misleading account policy.** GET requests have a 15-second deadline covering response and JSON decoding. Overview does not automatically retry indefinitely and presents a manual Retry with a visible error. POST/import requests are not cancelled by this read deadline. Browser acceptance exposed shared-IP rate exhaustion on auth-option reads, which was incorrectly presented as disabled registration/demo. Those reads now have a separate bounded 240/minute bucket, retaining the previous per-endpoint allowance and stricter login/import/analysis limits. A 60/minute prototype failed the Guide sweep and was corrected. Unknown policy is shown as an error, not an asserted policy decision.

6. **Shutdown previously waited on disconnected HTTP traffic.** The managed local API drains HTTP for 30 seconds. Local background analysis retains its existing 900+30-second shutdown allowance and durable lease recovery. API, private UI, worker and Beat restarts were exercised using verified owned process identities and unchanged keys/database/broker configuration.

ZIP/public GitHub intake, encrypted inventories, bounded parser isolation, history batching, fenced job recovery and transaction publication fixes already present in the codebase were retained and retested rather than replaced. Native quality, SAST, secrets, SCA and IaC continue to run within their declared support; no SonarQube/Wiz dependency was introduced.

## Files changed in this stabilization pass

This list identifies the current corrections, not every pre-existing dirty file in the repository:

- Backend queries/storage: `backend/workspace_read.py`, `backend/json_query.py`, `backend/record_identity.py`, `backend/main.py`, `backend/db.py`, `backend/domain.py`, `backend/graph_api.py`, `backend/rate_limit.py`.
- Additive migrations: `backend/migrations/versions/0015_snapshot_views.py`, `0016_graph_class.py`, `0017_snapshot_identity.py`, `0018_summary_counts.py`.
- Service lifecycle: `scripts/local_api.py`.
- UI/read contracts: `frontend/src/WorkspaceApp.tsx`, `api.ts`, `status.ts`, `App.tsx`, `public/AuthPage.tsx`.
- Automated tests: `tests/test_workspace_pagination.py`, `test_indexed_workspace_queries.py`, `test_record_identity.py`, `test_rate_policy.py`, `test_code_quality.py`, `test_migrations.py`, `test_postgresql_integration.py`; `frontend/src/WorkspaceSummary.test.tsx`, `App.test.tsx`, `public/Public.test.tsx`; `frontend/e2e/large-workspace.spec.ts`, `release-stability.spec.ts`.
- Reports: this file, the current correlation report, its preserved historical copy, and the current qualification link in `docs/RELEASE.md`. Trusted private harnesses/receipts are outside the product directory. Earlier parser/cache/history/intake/worker changes listed in the historical investigation remain in place.

## Actual repository and UI results

Current incident: tenant `c1d9f579-bdd2-4d2b-b22f-a2020aa4a2dc`, repository `4f7304f9-c355-467f-8799-785e74b83cdf` (`data`), job `03382b0a-2de5-4d9b-a8dc-3097c129616e`, retained inventory `98db76fd-aadf-4522-99d8-46a5b36ab5e3`.

OpenMetadata archive: SHA-256 `027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`, 157,126,481 compressed bytes, 330,420,155 expanded bytes, 21,636 discovered files. The unchanged installed retry completed and published **PARTIAL in 663.671952 seconds**. An independent pre-repair database replay actually rebuilt/published the full graph in **288.691365 seconds**. Both kept the 900-second budget and passed the 720-second headroom target. Neither was an existing-snapshot shortcut. Both were warm retained-parser-cache runs: 18,756 hits and 103 misses. The original retry count remains bounded at two; an older exhausted job was not reset.

Installed snapshot: `01a12093-bcc9-7dbc-9ac8-320abfb01c18`; independent snapshot: `01a1209d-c8cb-7295-bb43-6a728adcca92`.

| Published scope | Actual value |
| --- | ---: |
| Claims | 1,500: 934 verified, 559 inferred, 7 unverified |
| Findings | 7,904: 182 critical, 1,186 high, 6,140 medium, 396 low |
| Material findings | 1,368 |
| Evidence files / dependencies | 18,859 / 2,090 |
| Graph nodes / edges | 231,228 / 289,745 |
| Source files parsed / discovered source | 14,567 / 15,669 (92.967005%) |
| Warnings | 105 |

Coverage retains 1,083 unsupported, 17,671 partial, 1,475 policy-ignored, 32 size-skipped, 1,058 generated, 33 parse-failed, 189 binary and 95 vendor files. These states sum to all 21,636 entries. The 1,500 claim cap itself makes claim extraction partial. Runtime evidence is UNOBSERVED; parser completion is not proof of full semantic/security coverage or measured precision.

The actual installed scoped summary returned in 2.741537 seconds, 71,607 bytes and ten SQL statements. This was a trusted read-only diagnostic with the existing owner's grants, not a fabricated owner browser login. Browser tests used independent QA accounts. The large QA mirror contains the exact earlier snapshot/Record payloads but does not copy original encrypted source blobs or typed quality/history tables. Large counts/pagination/graph UI are qualified there; source inspection, quality review and export are qualified on actual smaller ZIP analyses. Original typed publication was checked independently read-only.

Browser Overview measurements were 2.04 seconds initially, 4.17 seconds after a clean API restart, and 5.11 seconds after restarting both API/UI. The last two summary HTTP measurements were 2.351 and 3.023 seconds. Final repeat claim pages measured 195/128 ms, verified pages 249/178 ms, and findings 218 ms. Those large-view checks recorded no JavaScript errors or result-limit banner and verified complete 1,500/7,904 totals and 934 verified claims. These are observations on this desktop, not latency guarantees under memory saturation.

| Real intake via private HTTP API | State | Full observed wall seconds | Stored analysis seconds |
| --- | --- | ---: | ---: |
| Six-file inert native ZIP | COMPLETED | 2.103843 | 1.328160 |
| User's smart-waste ZIP, 47 files | PARTIAL | 6.890495 | 5.970610 |
| Public `pallets/itsdangerous`, 50 files | PARTIAL | 5.184338 | 2.677760 |
| Same public commit after API restart | PARTIAL | 2.414269 | 1.138660 |

Public GitHub commit was pinned to `672971d66a2ef9f85151e53283113f33d642dabd`; results identify their actual snapshot/commit. Malformed ZIP returned 422 `ARCHIVE_INVALID`, traversal ZIP returned 422 `ARCHIVE_UNSAFE_PATH`, and an unauthorized snapshot returned 404. Login cookie, prior snapshot content and verified audit chain survived the API restart. The smart-waste archive SHA-256 is `293fca0b7f1cf9b42b6726073b3468ae05ba432fe310daa81b93e0f7fd969919`.

After the final browser suites, intake was repeated against the final code and retained private database, followed by another clean API restart. All four real imports passed again: six-file ZIP **COMPLETED, 1.409357 seconds** (analysis 0.873640); smart-waste **PARTIAL, 5.833936 seconds** (analysis 5.211270); public GitHub **PARTIAL, 4.521824 seconds** (analysis 2.366850); public GitHub after restart **PARTIAL, 2.177998 seconds** (analysis 0.977310). The restart took **7.804443 seconds** and again preserved the session, exact prior snapshot and verified audit. Malformed/traversal input and tenant denial again returned 422/422/404. `actual-imports-clean-repeat.json` retains all snapshot IDs and actual provider provenance; nothing was substituted with a mock.

## Regression, restart, consistency and preservation

- Final backend acceptance: **480 passed**, no skips, 620.12 seconds; operator wall 627.225969 seconds. Real PostgreSQL integration cases ran against a private PostgreSQL 17 instance. One upstream Starlette/httpx deprecation warning remains.
- Current frontend: **35 tests passed in nine files**, 12.62 seconds; production build succeeded, operator wall 8.692806 seconds. Final Ruff checks passed.
- First isolated post-restart Chromium acceptance: **15 passed**, operator wall 198.481017 seconds. The subsequent complete clean API/UI restart suite also had **15 passed**, operator wall **257.832151 seconds** (completed 19:08:58 local), with no retries added to obtain that result. Receipts: `browser-restart.json`, `browser-clean-repeat.json` and their result/proof directories.
- Browser coverage includes real login/signup, empty workspace, repository filters, account/organization change and tenant denial, controlled summary failure/retry, ZIP/native analysis, claims/source/evidence/review, quality profiles and SARIF, secrets/SCA/SBOM, drift and historical comparisons, findings/graph pagination, trust/audit, exceptions/gates/PR workflows, Guide, responsive/dark/keyboard behavior and production public HTML without JavaScript. Cloud inventory is exercised only through its credential gate, not through a real cloud account.
- Crash recovery: an owned 500-file static-fixture worker was terminated after durable analysis checkpointing, before publication. Its private lease alone was expired to trigger the normal recovery path. Recovery took 23.489191 seconds, reused all 500 parser artifacts, published exactly one completed snapshot, retained the unpublished checkpoint/attempt history and verified audit. This proves parser/checkpoint/lease recovery, not durable resumption of a half-built global graph.
- Final installed SQLite check: zero foreign-key violations, schema 0018, 179 snapshots, no active/queued jobs; the incident is PARTIAL with retry count two and two retained prior attempts.
- Immutable preservation compared **1,173,595 pre-existing Records** plus old organizations, users, grants, repositories, reviews/exceptions in Records, typed findings/quality/cloud, inputs, inventories, parser artifacts and audit rows: none missing or changed. Only the explicitly authorized incident job lifecycle and normal mutable cursor/session/audit-head/schema state were excluded. All 64,563 old blob files remained; 100 distributed decrypt/hash samples passed; all 21 existing audit heads verified. Old snapshot versions/content were retained.
- Current/replay canonical claim and finding coordinates/hashes match, duplicate current finding fingerprints are zero, and graph endpoints/scope have no missing or foreign rows. Typed current publication contains 8,290 finding occurrences (including historical/resolved occurrences), 6,843 quality occurrences, one quality analysis, 133 cloud assets and one snapshot-inventory link. Occurrence history is not a current-finding count.
- The previous snapshot has one additional `Quality: baseline` policy node because its base is null. The retry references that previous snapshot as its baseline; the analyzer intentionally does not emit that first-baseline node. No other measured graph class/relationship distribution differs between the two new runs. The old graph was preserved unchanged.

Earlier failed receipts remain available: an outdated summary assertion was corrected to the new preview/complete-count contract; two browser attempts exposed and verified the auth-options rate/policy defect; another heavily contended host run missed five-second UI assertions on Overview/profile saving (13 passed, two failed). No stress-success claim is made from rerunning in isolation. A private preservation observer was interrupted after its table checks because repeated path resolution was expensive; blob verification resumed with a bounded directory inventory. That observer interruption was not a product analysis success or hidden product timeout.

One early browser invocation hit the installed UI during mixed-version rollout and created its own isolated QA organization/account/repository/small snapshot. Those additions are retained rather than deleted; they do not belong to the incident owner. The final browser suites use private QA ports 8012/5182 and a static preview at 5183. No claim is made that the installed database gained no test rows.

The private API/UI pair restart took 21.359837 seconds and retained 82 queue entries. Its auxiliary snapshot-count probe used uppercase `SNAPSHOT` although persisted kinds are lowercase; its reported zero is invalid as a snapshot-preservation proof. The harness was corrected. Snapshot preservation instead relies on the actual authenticated restart/import check, immutable comparisons and the exact-snapshot browser assertions before and after restart. This diagnostic mistake is not presented as a genuine empty QA database.

After validation, the owned private QA API/UI/static-preview and private PostgreSQL test instance were stopped; their databases, encrypted sources and receipts were retained. Installed API 8011 and UI 5181 returned HTTP 200; installed worker/Beat/Redis remain available. `final-gate.json` and `final-gate-clean-imports.json` verify the terminal test receipts and measured budget without changing product data or marking PARTIAL scans fully covered.

## Staged performance and remaining blockers

Trusted static Python fixtures have ten functions per file. Cold means no ProjectTrace parser artifacts, not a cleared OS cache. All stages completed and all declared source files parsed; semantic maturity stays explicit.

| Files | Cold wall s | Warm wall s | One-file change wall s | Largest parent RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| 20 | 0.696751 | 0.296651 | 0.481038 | 133.54 |
| 100 | 1.948301 | 3.271518 | 6.304806 | 238.25 |
| 500 | 9.741847 | 6.684950 | 31.222108 | 636.49 |

The changed-file run reused N−1 parser artifacts and read one changed source blob. Global history/graph work is still recomputed; 500-file incremental SQL cost was 15.24025 seconds. Caching is effective without proving end-to-end incremental speedup. CPU, stages and SQL details are in each `benchmark-*/receipt.json`.

Release blockers and realistic next steps:

1. **Resource mismatch:** the large runs peaked at 4.715/5.117 GiB parent RSS; Compose's worker limit remains 1 GiB/2 CPUs. A hard whole-analysis memory envelope is not yet demonstrated. Concurrent large jobs and memory-saturated interactive latency are not qualified. Compact/disk-backed graph state and admission based on a validated memory estimate require engineering and tests before that deployment can pass.
2. **Global continuation:** native artifacts/checkpoints and job fencing recover, but graph correlation/publication still uses one atomic transaction. A crash there rebuilds global work. A safe extension requires deterministic bounded stage units, durable generation IDs, idempotent keys and a fenced atomic published-generation switch, preserving history and tenant references. This pass does not pretend that a SQLite cache/ID change implements that architecture.
3. **Cold and maximum-scale qualification:** no fresh large cold parser-cache or full 157 MB provider/gateway upload SLA was run. Intake maxima are security caps, not validated supported-scale targets. SQLite stalls varied substantially; file-system/antivirus/OneDrive attribution was not independently proven. PostgreSQL offers a realistic large-publication deployment option but these full OpenMetadata runs used SQLite, not PostgreSQL.
4. **Enterprise/live support:** automated authorization/provider regressions passed, but live OIDC, GHES, private GitHub App/webhook delivery, AWS/cloud credentials, object storage and production TLS/ingress were not exercised. Missing operator credentials/configuration remain specific qualification blockers. Native language/advisory/semantic coverage remains declared partial.
5. **Timing telemetry:** stored job duration/FINALIZING is recorded before final transaction commit/cleanup. Full call wall is the acceptance metric; treating 561.88 seconds as the installed completion time would underreport the actual 663.67 seconds. Durable post-commit end-to-end telemetry remains a follow-up.
6. **Inherited security/operations qualifications remain open:** application-level tenant/grant and negative tests pass, but there is no comprehensive PostgreSQL RLS/compound-FK defense for every generic Record relationship or per-job main-process filesystem/network sandbox. Audit verification is not a WORM guarantee; privileged whole-chain rewriting requires an independently retained authenticated checkpoint. Large ZIP capture remains synchronous rather than a durable ingestion work unit. Independently measured accuracy, sustained multi-tenant workload and production disaster-recovery/rotation SLA are not qualified. The prior product audit describes these exact gaps; this pass does not close them by testing only read APIs.

**Final decision:** the current original timeout is **fixed within the measured warm retained-inventory local scope**, and Overview/paging/intake/auth/recovery regressions pass within the stated acceptance scope. The complete production release remains **BLOCKED** until the resource, global-recovery and deployment qualification items above pass actual tests. No broader performance, correctness or integration claim is made.
