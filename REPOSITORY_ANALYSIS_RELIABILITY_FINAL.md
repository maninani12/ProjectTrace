# Repository analysis and workspace reliability final validation

Date: 2026-10-09. Product: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`. Continues the existing database, snapshots and previous investigation; no rebuild, database reset, credential reset, commit or push.

**Decision: PASS for the measured local repository-list deadline, corrected scope/evidence reads, small-import workflow and checkpoint recovery. Complete product/production readiness: BLOCKED.** Both customer repositories remain honestly PARTIAL. A fresh cold full large analysis, deployment memory envelope and unrestricted semantic accuracy are not qualified. Loading the dashboard is not the release gate.

## Environment and evidence boundaries

Windows 11 Home 10.0.26300, Intel Core 5 120U (10 cores / 12 logical processors), 16,806,244,352 bytes physical RAM; Python 3.14.3, FastAPI, SQLAlchemy 2.1.3, SQLite 3.50.4 WAL. This validates the current Python product; it does not claim a separate Java/Spring production backend. Installed APP_ENV=demo / JOB_MODE=local, one admitted local analysis writer, helper maximum two, repository analysis budget **900 seconds**, client GET deadline **15 seconds**, general IP quota **240/minute**. These limits and security checks were retained.

The original database remains in the OneDrive Desktop product directory. An independent storage/sync contribution was not isolated. Available physical RAM varied during validation; the final saved sample was 3,965,956 KiB (about 3.78 GiB), with earlier samples lower. Previous large parent-process peaks were 4.715 and 5.117 GiB, before counting all helpers. Another full large construction was not started under that pressure. No customer project code, dependency installer, build script, Maven goal, infrastructure command or imported test was executed.

Original inspection used read-only SQLite connections and verified owner/repository grants in an isolated diagnostic process. Authenticated HTTP/browser tests used normal, task-owned accounts against a retained private QA database; no customer session or password was impersonated. The original browser was at login, so the final customer-owner browser session itself was not automated. The private current-record mirror includes both exact current snapshots, their Records, projections and current cloud assets. It does not contain all original encrypted source blobs or every typed historical/quality projection. Original source validation and full fresh PetClinic/ZIP runs qualify those aspects separately; a missing source in this mirror is not reported as customer data loss.

Measured final hardware resource snapshot: [environment-final.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/environment-final.json>).

## Exact Repositories deadline root cause

The Repositories page unnecessarily depended on **GET `/api/workspace?summary=1`**. In the installed original database the first measured read took **11.806522 seconds** (10 SQL calls); JSON serialization was only 0.000621 seconds. Two database operations dominated:

| Operation, original query shape | Seconds | Actual SQLite plan problem |
| --- | ---: | --- |
| Finding severity/review aggregate | 5.622624 | `ix_records_finding_summary` sought organization only, followed by temporary grouping B-tree |
| High/critical finding preview | 5.782223 | `sqlite_autoindex_records_2` sought organization/kind only, then temporary ordering and full JSON reads |

An OR across `(repository A, snapshot A)` and `(repository B, snapshot B)` let SQLite choose broad tenant/history scans rather than point seeks. The catalogue waited for these unrelated finding reads. Single-repository reads were 0.669742 seconds for data and 0.016518 for PetClinic; warmed ALL was 0.661702. This proves avoidable work and little initial deadline headroom. The user's intermittent 15-second browser error was not independently captured on the original tab; do not turn an 11.8-second measurement into a fabricated 15-second trace or a proven lock incident. No evidence establishes a parser or database-lock cause for this page.

Correction: independent **GET `/api/repositories`**, default 25 / maximum 100 rows; explicit total, offset, has_more and authorized scope; literal-escaped bounded search. Organization plus repository grant filtering happens before count, search and pagination. It reads version-checked compact snapshot projections and scalar latest-job metadata; it never computes finding/graph aggregates or claims totals. The 100-row filter catalogue uses `include_analysis=false`, with no domain Record queries. Large repository catalogues paginate; absent totals are not displayed as zero. No separate application cache was needed; query/React Query caching remains scoped by identity, filters and pagination. The current two-repository catalogue sorts its small authorized set using a temporary B-tree; no million-row finding/history sort remains on that path. Name-search/offset catalogue scaling beyond the tested 32-repository authorization fixture is not a benchmarked maximum-scale claim.

Workspace summaries still compute complete authorized current-snapshot counts. Per-repository indexed branches use bounded 200-branch UNION ALL chunks; previews first select at most five candidate IDs per repository and fetch only final documents. The first corrected summary profile was 0.994581 seconds, repeat 0.214055. Current installed repository listing direct function reads were **0.030882 first / 0.009017 repeat** with six SQL calls. These are read-only function measurements, separate from authenticated HTTP below.

Final direct installed read also verified both actual snapshot/job states as PARTIAL at their exact IDs; first 0.896892 seconds / repeat 0.005453. This was an isolated read-only function process during the final managed restart, not an authenticated customer session measurement.

Receipts: [before-workspace.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/before-workspace.json>), [corrected summary profile (historical filename)](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/--help.json>), [installed-list-profile.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/installed-list-profile.json>), [installed-stable-list-profile.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/installed-stable-list-profile.json>), [current-diagnostics.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/current-diagnostics.json>).

## A second demonstrated deadline defect: Infrastructure

Post-restart API acceptance also reproduced an actual 15-second driver deadline while querying **GET `/api/trust/infrastructure`**. Original read-only full endpoint timing was **26.473152 seconds**: resource query **19.209691**, finding query **5.497917**. Bound JSON path parameters prevented existing SQLite expression indexes from matching; the selected graph-target index sought only organization/repository/kind and scanned snapshot history.

Using constant, developer-controlled paths through `indexed_text` restored the existing graph-class/snapshot indexes. Same source, scope and result semantics: resource query **0.006653 seconds**, finding query **0.216286**, full endpoint **2.309556** (about 2.008346 seconds remained in snapshot metadata). Private mirror full endpoint was 2.565470; original PetClinic 0.032723. No timeout increase, extra index or migration was used. A new SQL-plan regression requires the graph-class expression index and checks retained resources/findings. The failed first driver attempt is retained, not counted as a pass.

Receipts: [before-infra-installed.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/before-infra-installed.json>), [after-infra-installed.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/after-infra-installed.json>), [before-infra-qa.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/before-infra-qa.json>), [after-infra-qa.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/after-infra-qa.json>).

## Loading time and tested concurrency

Each authenticated HTTP batch had 21 serial and 40 reads across four concurrent readers, same two current snapshots, configured 15-second deadline. All **244 reads** succeeded across four batches. These are measured local workloads, not an unlimited-throughput SLA or a cold operating-system cache claim. The final batch also explicitly verified both latest job previews and snapshots as PARTIAL after correcting the private mutable-job mirror.

| Batch | Reads | First read s | p50 s | p95 s | Maximum s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before clean restart, corrected listing | 61 | 0.049443 | 0.044927 | 0.086764 | 0.121541 |
| After clean restart, corrected Infrastructure | 61 | 0.048031 | 0.048031 | 0.083309 | 0.141314 |
| Final Ask code, after clean restart | 61 | 0.027213 | 0.030374 | 0.044121 | 0.077330 |
| Final scope/job mirror, after clean restart | 61 | 0.096078 | 0.047101 | 0.074813 | 0.096078 |

Each batch also passed 16 explicit repository/snapshot API scope checks covering catalogue, diagnostics, claims, findings, evidence, graph nodes, coverage and Infrastructure. ALL summary totals agreed at **1,505 claims / 7,943 findings**; summary timings were 0.466691, 3.276592, 2.473701 and 3.660821 seconds. Repositories no longer waits for that summary. The final corrected-job batch p95 was 0.074813 and maximum 0.096078 seconds.

Final browser suites each hard-reloaded the two-repository page eight times. Across the final **16 reloads**, maximum useful-page time was **0.868135 seconds**, below 15 seconds. No workspace-summary request was made on that page; stalled summary responses were deliberately injected to verify independence. JavaScript page-error lists were empty. Read failure showed unavailable data and a GET-only Retry, with no invented zero counts, infinite spinner or analysis retry POST.

One earlier attempt ran the API workload concurrently with the browser suite and correctly encountered the existing shared 240/minute quota (429). Later, a fast unpaced whole-suite burst by itself also reached that quota. Neither is evidence of a new SQL timeout. The quota was retained. Final browser qualification runs every test/file in four admission-aware batches, using only task-owned read-only window telemetry to wait for headroom; no limit/window is cleared or bypassed. Batch memberships, admission waits and real results are in the receipts. The final four-reader API benchmark remains a separate concurrent workload. This does not claim unthrottled users behind one NAT can exceed the configured quota. Rate-limited native-profile reads show unknown/unavailable state and manual read Retry rather than a fake profile version.

Receipts: [api-before-restart.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/api-before-restart.json>), [api-final-after-restart.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/api-final-after-restart.json>), [api-release-after-restart.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/api-release-after-restart.json>), [api-validated-scope.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/api-validated-scope.json>), [browser-paced-acceptance-results.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/browser-paced-acceptance-results.json>), [browser-paced-repeat-results.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/browser-paced-repeat-results.json>) and their `*-proof/repository-browser.json` files.

## The two original published PARTIAL results

Organization `c1d9f579-bdd2-4d2b-b22f-a2020aa4a2dc` (`second`). No original job, snapshot or inventory was replaced during this read-reliability investigation.

| Original published result | data / OpenMetadata | spring petclinic |
| --- | --- | --- |
| Repository ID | `4f7304f9-c355-467f-8799-785e74b83cdf` | `684f260f-d5bb-461c-b024-2da4d883eeea` |
| Snapshot ID | `01a12093-bcc9-7dbc-9ac8-320abfb01c18` | `01a120f6-3ebe-7f6d-9854-53e62443f253` |
| Job ID | `03382b0a-2de5-4d9b-a8dc-3097c129616e` | `01a120f6-1561-7c4f-a7e9-92b9c757f7fc` |
| State | PARTIAL, published | PARTIAL, published |
| Captured text files (card) | 21,269 | 183 |
| Inventory discovered | 21,636 | 200 |
| Native scanned / evidence | 18,859 | 140 |
| Declared source parsed / total | 14,567 / 15,669 (92.967005%) | 84 / 119 (70.588235%) |
| Claims | 1,500: 934 verified, 559 inferred, 7 unverified | 5 verified |
| Findings / dependencies | 7,904 / 2,090 | 39 / 131 |
| Graph nodes / edges | 231,228 / 289,745 | 445 / 956 |
| Recorded warnings | 105 | 3 |

These denominators measure different scopes. Captured text file count is not parsed source coverage. The UI label now says **Captured text files**. Inventory initial retention states are also distinct from the final analyzer coverage states below.

**OpenMetadata:** PARSING, QUALITY, SAST, IAC and CLAIMS are PARTIAL. Secrets and dependency inventory completed within their declared static capability; API completed supported checks only. Claim extraction reached its existing 1,500 cap. Legacy `claim_extraction.state=COMPLETED` contradicted `engines.CLAIMS.state=PARTIAL`; diagnostics now expose the effective PARTIAL state without rewriting the snapshot, and future publication records the actual engine state.

Final file states sum to 21,636: UNSUPPORTED 1,083; PARTIAL 17,671; IGNORED_BY_POLICY 1,475; SKIPPED_SIZE_LIMIT 32; EXCLUDED_GENERATED 1,058; PARSE_FAILED 33; BINARY 189; EXCLUDED_VENDOR 95. Warning classes include 83 IaC ValueError, one IaC ScannerError, one JSONDecodeError, ten syntax-node-budget and eight other parsing warnings, plus quality-scope and claim-cap warnings. The 40,000 syntax-node budget and other safety limits remain. Language examples: Java 4,609 / 4,598 parsed; Python 3,054 / 3,037; TypeScript 7,866 / 6,820; JavaScript 112 / 112; SQL 342, Shell 60, Make 3 and unknown source remain unsupported. Generated exclusions and per-file parse warnings account for further gaps. Partial inventory and all completed results remain visible; no omitted scope is promoted to completed.

**PetClinic:** 64 Java and 20 JavaScript files parsed successfully; no source parse failure. The remaining 35 declared source files are SQL 12, Shell 6 and unknown 17. Final states sum to 200: PARTIAL 140, UNSUPPORTED 35, policy ignored 13, binary 12. Seventeen archive entries were not text-retained: 12 classified binary plus five JAR/font entries with no initial retention-state classification; all 200 captured inventory digests matched the actual ZIP. This retention-classification gap is disclosed rather than treated as five parsed files.

Quality is PARTIAL because its declared source scope includes unsupported files; zero supported quality/SAST findings is not proof of repository quality or security. IaC is PARTIAL with 38 findings and two failed GitHub workflow parses. Static reproduction confirmed the conservative YAML guard sees `${{...}}` as an unrendered template and reports unsupported Helm syntax. This overbroad refusal remains a parser capability defect/limitation, not a workflow execution. The third warning is quality scope. Secrets found one static observation; dependencies recorded 131 observations from nine manifests. API is SKIPPED_UNSUPPORTED: the current route verifier does not implement Spring route semantics. Four documentation files were processed and a direct static extraction rerun produced zero recognized documentation claims; Spring/Eureka are mentioned but unsupported by this claim model. It is not lost README data.

Runtime evidence for both is **UNOBSERVED**. Neither PARTIAL state is a failed publication, truncated workspace page or fabricated completion. Both have genuine analyzed, unsupported and skipped scopes.

## Claim/source and graph correctness

Every original claim link was structurally checked: OpenMetadata **2,131 links / 1,319 unique encrypted blobs**, PetClinic **5 links / 5 blobs**. Repository/snapshot scope, source digests and declared lines were inspected. The raw check correctly reported **46 invalid line citations**: all were line 1 on empty `tests/__init__.py` files for path-derived test-file assertions. No foreign scope or digest mismatch explains them.

All **733** implementation test-file claims now display the supported statement **“Repository contains a file under a test path.”**, `evidence_basis=PATH_INVENTORY`, no invented source line, and an explicit reason that implementation/execution/test quality are unobserved. `recorded_text` and `recorded_line` retain legacy values in read output; old persisted IDs, payloads, reviews, exceptions and history remain untouched. New publication applies the same annotation before storing claims. This narrows the claim to actual inventory evidence rather than treating a VERIFIED label as proof of working tests.

PetClinic's five source-backed claims are three Docker declarations and two GitHub Actions configuration-presence declarations. All five sources, lines and hashes checked; all 200 ZIP inventory digests matched. They establish static declarations, not working Spring services, CI success, deployment security or runtime correctness. The other large claims have scope/provenance checks; this is not an independent semantic precision/recall study for 1,500 claims or all findings.

Ask Engineering previously bypassed this annotation by reading embedded snapshot claims and independently resolving the latest snapshot. It now annotates those embedded legacy claims too, accepts bounded authorized `snapshot_ids`, returns the exact map, and the frontend sends the snapshots displayed by its scope. A delayed response is discarded after repository/snapshot selection changes. Its graph neighborhood filters claim endpoints before loading payloads and applies the existing 50-row bound in SQL, rather than loading every snapshot edge and slicing in Python. Tests check old-snapshot selection during new publication, cross-tenant denial, incompatible scope rejection, preserved legacy payloads and SQL-level bounds. This correction does not introduce runtime verification or a new claim model.

Original graph audit found **zero invalid endpoints**, **zero repository-scope mismatches**, **7,904 / 39 unique finding fingerprints**, and zero SQLite FK violations. Exact current snapshot hashes/versions remained unchanged. The exhaustive original read-only graph/FK audit took 178.209944 seconds; that audit is not an interactive page or analysis runtime.

Receipts: [claim-source-validation.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/claim-source-validation.json>), [current-graph-validation.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/current-graph-validation.json>), [petclinic-after-restart.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/petclinic-after-restart.json>).

## Workspace, repository and snapshot scope

Workspace summary counts are the latest published snapshot per authorized repository. Detailed workspace pages send an explicit one-snapshot-per-repository selection from that same summary, avoiding a publication race between summary and record reads. API validation checks organization, repository grants and snapshot kind before returning data, and rejects unknown/foreign/incompatible or duplicate-repository selections. Explicit single historical-snapshot APIs remain supported.

Explore now selects the clicked repository before opening Evidence; its PetClinic page returned exactly its 140 evidence records in bounded 50-row pages. Code Quality, captured coverage and Infrastructure receive the displayed selected repository snapshot; historical selectors intentionally choose an explicitly identified older snapshot. ALL coverage is one explicitly labeled selected snapshot, not an invented global coverage aggregate. Cloud and risk views retain their declared scoped/current semantics; organization-wide policy, profiles and audit integrity are labeled organization controls. Session organization switching clears client queries; identity is part of repository/list/summary query keys. A filter catalogue supports pages beyond its first 100 repositories.

The unpaced demo recovery failure proved another product defect: a 429 from `/api/auth/me` was swallowed and rendered the login form even though the demo session was valid. The API error now retains its HTTP status; only 401 selects login. Other identity-read failures render **Workspace access unavailable**, the sanitized error and GET-only **Retry access**, with no false logout or workspace zeros. The identity effect ignores stale unmounted responses. New unit/browser regressions inject 429, verify session-preserving access retry, and distinguish a real 401.

Regression/browser/API coverage includes all major navigation pages, both exact current repository views, review/evidence interactions, organization switching and explicit current/historical pagination. This is not a claim that every possible endpoint, provider credential flow or every historical typed projection was exhaustively qualified. Production tenant defense-in-depth and live provider qualifications remain below.

## Actual end-to-end PetClinic and large-repository evidence

Fresh authorized PetClinic imports used the exact unchanged ZIP SHA-256 `8e325e137699f497a9e34aebc56cc7a9175ba7e2e3578c4e4241667aa2d0ed39` (1,556,024 compressed bytes). Ordinary authenticated HTTP upload and the durable local queue created new private snapshots; no imported application was executed.

| Fresh exact PetClinic run | Parser-cache cold | Unchanged warm |
| --- | ---: | ---: |
| Whole upload/completion/validation wall seconds | 16.528850 | 7.667149 |
| Stored analysis seconds | 11.210910 | 3.706200 |
| API CPU seconds | 10.359375 | 6.015625 |
| API sampled peak RSS bytes | 160,370,688 | 164,814,848 |
| Cache hits / misses | 0 / 140 | 138 / 2 |
| Result | PARTIAL | PARTIAL |
| Claims / findings / evidence / dependencies | 5 / 39 / 140 / 131 | 5 / 39 / 140 / 131 |

“Cold” means no product parser cache, not cleared OS/storage cache. The two failed GHA parses are reprocessed rather than cached as successful. Sampled descendant maxima 4/2 include Windows virtual-environment launcher/helper processes and are not evidence of four analyzer helpers; the configured analyzer maximum remained two. CPU/RSS above cover the API process, not summed helper memory/CPU. Both runs had identical canonical finding coordinates, engine/coverage/warning results; all five source-backed claims and all 200 coverage rows were checked. Repository list reads during actual analysis peaked at 0.351490 / 0.219027 seconds (16 / 11 samples). After restart, both exact new snapshots retained counts, coverage, caches and verified audit.

| Stored PetClinic stage seconds | Cold | Warm |
| --- | ---: | ---: |
| VALIDATING | 0.051301 | 0.089804 |
| PARSING | 0.023886 | 0.020062 |
| ANALYZING | 6.294190 | 0.841106 |
| EXTRACTING_CLAIMS | 0.115027 | 0.058805 |
| VERIFYING | 0.405796 | 0.377207 |
| BUILDING_EVIDENCE | 0.780201 | 0.411468 |
| CORRELATING | 3.510635 | 1.888583 |
| FINALIZING | 0.008162 | 0.004783 |

Large current installed snapshot is the same unchanged OpenMetadata result qualified in [CORRELATION_PERFORMANCE_FINAL_VALIDATION.md](<C:/Users/sai krishna/OneDrive/Desktop/ProjectTrace/CORRELATION_PERFORMANCE_FINAL_VALIDATION.md>). Previous measured full constructions, same archive/input/options and 900-second budget, completed at **663.671952 seconds installed / 288.691365 seconds independent private repeat**; both below 720 seconds, both genuinely PARTIAL. Cache reuse was 18,756 hits / 103 misses. Parent CPU 223.390625 / 193.250000 seconds; peaks 4.715 / 5.117 GiB. These are **carried prior measured full runs**, not new full executions of the latest read/UI changes. This investigation freshly validates their exact original snapshot, claims, findings, evidence links, coverage, graph and preservation; it does not label that as a fresh cold reanalysis.

Those large stages were respectively VALIDATING 2.083571 / 2.203687; PARSING 0.087511 / 0.082401; ANALYZING 61.982571 / 51.060520; EXTRACTING_CLAIMS 23.726806 / 2.899060; VERIFYING 17.550916 / 12.209077; BUILDING_EVIDENCE 16.397787 / 14.241827; CORRELATING 440.045867 / 192.883544; FINALIZING 0.001623 / 0.000895 seconds. Stored analysis duration (561.884230 / 275.589550) excludes final commit/cleanup; acceptance uses whole-call wall. Full cold large analysis and concurrent large jobs are outstanding, not silently passed.

Receipts: [petclinic-end-to-end.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/petclinic-end-to-end.json>), [petclinic-after-restart.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/petclinic-after-restart.json>); previous large receipts remain under sibling `release-stability/measured-retry-2.json` and `measured-full-repeat.json`, linked from the earlier correlation report.

## Actual imports, failure recovery, concurrency and clean restart

Real current-code private HTTP imports: six-file controlled ZIP COMPLETED 1.214124 seconds; authorized 47-file smart-waste ZIP PARTIAL 4.393549; public `pallets/itsdangerous` 50-file import PARTIAL 3.933157; same public flow after clean API restart PARTIAL 1.691416. Actual provider commit/provenance is in the receipt. Invalid ZIP returned 422 ARCHIVE_INVALID, traversal ZIP 422 ARCHIVE_UNSAFE_PATH, foreign-tenant snapshot 404. The restart retained the signed-in private session, exact snapshot and verified audit. Browser tests independently import fresh ZIPs through the UI and inspect real source/claims/drift rather than using a pre-imported demo as intake proof.

A task-owned 500-file non-executing fixture worker was killed at EVIDENCE_FILES. Its unfinished publication rolled back (zero published snapshots), 500 parser artifacts remained, and the ordinary fenced expired-lease recovery reused **500 hits / zero misses**, published exactly one valid snapshot with no duplicate current fingerprints, and verified audit. Wall 18.517660 seconds. Completed checkpoint diagnostics were retained; no customer lease/job was altered. Recovery still recomputes global graph/publication work; durable mid-global-graph continuation is not claimed.

Latest installed API/UI restart used the managed graceful lifecycle, verified idle ownership and retained configuration/limits. Original counts stayed **1,727,011 Records; 76 repositories; 80 organizations; 80 users; 76 grants; 8,123 audit events; 6,119 audit links; 149 sessions; 19 inventories; 131,554 inventory files; 64,763 source blobs; 75,700 parser artifacts**. All **180 snapshot raw hashes/versions** and the credential-state digest matched before/after. No customer password/hash/secret appears in this report. Earlier preservation checked 1,173,595 old immutable Records individually and 21 audit heads; this turn's count/hash comparisons are not falsely described as another full per-row audit.

The local API-managed analysis runner restarted with the application. Optional retained Celery/Beat processes were not used for these local queue tests and are not a freshly qualified production Celery rollout. Final private test services and the task-owned PostgreSQL container were stopped after validation; their databases and evidence files are retained. Installed API/UI remain healthy at [ProjectTrace](http://127.0.0.1:5181).

Receipts: [actual-imports-release.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/actual-imports-release.json>), [crash-recovery.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/crash-recovery.json>), [installed-access-restart.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/installed-access-restart.json>), [qa-paced-repeat-restart.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/qa-paced-repeat-restart.json>), [private-validation-cleanup.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/private-validation-cleanup.json>).

## Files changed in this investigation

The checkout already contained substantial uncommitted earlier stabilization work. This list identifies the current investigation's edits and additions, not every dirty file in Git:

| Files | Purpose |
| --- | --- |
| `backend/repository_read.py` (new), `backend/main.py` | Authorized independent catalogue, bounded diagnostics, explicit multi-snapshot record/Ask scope |
| `backend/workspace_read.py` | Indexed per-repository aggregate/preview branches and claim read annotation |
| `backend/claim_read.py` (new), `backend/domain.py` | Honest inventory-only claim basis; actual future claim engine state; historical payload preservation |
| `backend/trust_api.py` | Constant JSON paths matching existing Infrastructure expression indexes |
| `frontend/src/WorkspaceApp.tsx`, `frontend/src/api.ts` | Independent paginated listing/catalogue, truthful read errors, snapshot-pinned pages/Ask, correct Explore/import targets, review/Ask response race protection |
| `frontend/src/CodeQuality.tsx`, `EnterpriseTrust.tsx`, `Infrastructure.tsx` | Explicit displayed snapshot and page-reset scope |
| `frontend/src/NativeProfiles.tsx` | Unknown/failure/retry state rather than invented version |
| `frontend/src/status.ts`, `status.test.tsx` | Matching published engine diagnostics when a compact successful job preview omits duplicates; no fallback for active/failed/different jobs |
| `frontend/src/App.test.tsx`, `api.ts`, `WorkspaceApp.tsx` | Preserve HTTP error status, distinguish identity 429/service failure from 401, and retry access without logging out a valid session |
| `tests/test_repository_read.py` (new), `tests/test_indexed_workspace_queries.py` | Pagination, grants, publication race, immutable diagnostics, claim basis, Ask scope/SQL bounds, Infrastructure index plan |
| `frontend/e2e/repository-reliability.spec.ts` (new), `large-workspace.spec.ts`, `workflow.spec.ts` | Both current ZIPs, reload timing, read recovery, exact large snapshot, delayed review/Ask races |
| `frontend/e2e/native-platform.spec.ts` | Synchronize with the actual credential-gate response within 15 seconds and assert 409/missing credentials, then its visible message; record timing |
| This report and `docs/RELEASE.md` | Current evidence and remaining release gate |

The SHA-256 manifest [validated-source-hashes.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/validated-source-hashes.json>) identifies validated source versions. Private benchmark scripts/receipts are in `C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\repository-reliability`; no credentials are linked.

## Tests actually executed and results

| Final check | Actual result |
| --- | --- |
| Full backend `python -m pytest -q` including private real PostgreSQL integrations | **488 passed**, zero failed/errors/skipped; 398.61 test seconds / 402.79 operator seconds |
| Frontend `npm test` | **37 passed / 9 files**, 14.34 operator seconds |
| Frontend `npm run build` | PASS, 9.38 operator seconds |
| Ruff backend/analyzers/tests/workers/scripts/integrations | PASS |
| Chromium full major-workflow suite, final code, four quota-aware batches | **20 passed**, zero skips/flaky/failures; 490.23 seconds wall span including admission waits and the documented observer interruption |
| Same full browser suite after another clean API/UI restart | **20 passed**, zero skips/flaky/failures; 270.51 operator seconds including admission waits |
| Authenticated repository-list four-reader workload | 244/244 reads within 15 seconds, overall maximum 0.141314; final corrected-job batch maximum 0.096078 seconds |
| Original DB/claim/source/graph checks | Both exact snapshots preserved, scopes/digests checked, known legacy claim citations corrected at read, no graph/FK/fingerprint defect |
| Fresh exact PetClinic cold/warm/restart | Valid PARTIAL twice, identical declared results, source/coverage verified |
| Owned worker crash/recovery | One fenced recovery / one snapshot / parser reuse / audit verified |
| ZIP/public GitHub/invalid/traversal/foreign tenant | Actual positive and negative results above |

Failed intermediate attempts remain in receipts: a second-import dialog used an inactive workspace cache (fixed to displayed repositories); the shared quota run returned 429; a delayed review response could reopen a dismissed inspector (fixed to update only the still-selected same record); old Infrastructure indexing exceeded the driver deadline (fixed). Visual QA also caught a stale pre-retry mutable FAILED job in the private mirror: its initial INSERT OR IGNORE refresh copied the new immutable snapshot but retained the old mutable job. Three private job payloads were refreshed from the read-only original; all snapshot payloads stayed unchanged and old private job payloads were archived. The original job had already been PARTIAL. Final browser assertions now require both original-repository snapshots and job previews to be PARTIAL on every reload. Receipt: [private-job-mirror-refresh.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/private-job-mirror-refresh.json>). Compact job previews also no longer falsely imply missing engine diagnostics when the same successfully published snapshot contains them. New controlled tests exposed fixture CSRF/SQL-path assertion mistakes while being developed; these are retained, corrected and superseded by the completed suites, not passed off as product successes. The upstream Starlette/httpx deprecation warning remains, with no test skip or behavior suppression.

The first paced runner was interrupted before batch four when it read private admission telemetry during a non-atomic JSON write. Its first 13 successful child results were preserved. The runner now retries transient telemetry reads and resumes only completed, validated child receipts; it finished the remaining seven tests without rerunning or overwriting those first results. This was a private observer failure, not a failed product test. The first suite's reported wall span includes the interruption and starts at the earliest retained child start time; original runner initialization is unavailable. The post-restart repeat is a separate complete run. Both parent receipts retain actual batch statistics and admission waits.

One later browser run passed 18/19 and failed only because its AWS credential-message assertion expired after five seconds with the POST still in flight; the trace had no response, not a 429. A separate actual authorized unconfigured request returned the expected 409 in 0.014324 seconds, and a fresh trusted SDK-import probe took 0.401751 seconds. These later timings do not isolate the earlier five-second transport/handler delay. The browser test now waits for the actual POST response within 15 seconds, asserts 409 plus sanitized missing-credential detail, then checks the visible message and records its wall time. Final browser gate measurements were 0.314375 and 0.294484 seconds, both 409. No product timeout/resource limit changed and no AWS credential/network call was introduced. This is response synchronization, not a claim that the unexplained earlier delay was a proven parser, SDK or rate-limit defect. See [credential-gate-timing.json](<C:/Users/sai krishna/Documents/Codex/2026-10-04/pr/work/repository-reliability/credential-gate-timing.json>) and final `*-proof/credential-gate.json` receipts. Live cloud success remains unqualified.

## Outstanding release blockers and final disposition

1. **Large-analysis deployable memory and fresh cold scale remain unqualified.** Two prior warm full completions fixed the original local timeout, but 4.715/5.117 GiB parent peaks do not fit the declared 1 GiB Compose worker envelope. Do not raise that envelope or the 900-second limit to claim resolution. Next architecture to measure is compact/disk-backed global graph state, deterministic bounded work units, durable generation checkpoints/idempotent writes, and a fenced atomic publication switch; benchmark a correctly indexed PostgreSQL deployment separately. Atomic global publication currently lacks mid-graph durable continuation.
2. **Analyzer/claim coverage remains PARTIAL by evidence.** SQL/Shell/unknown sources, generated/vendor/policy/size exclusions, bounded parser failures, unsupported Spring route/documentation semantics and the conservative GHA expression refusal remain visible. Test-path presence now has accurate evidence wording, but independent semantic precision/recall, cross-file/runtime verification and full security completeness are not established.
3. **Complete production security/provider/operations qualification remains blocked.** Live OIDC/GHES/private SCM and webhook credentials, cloud/S3/TLS/managed key recovery/WORM/DR, sustained production PostgreSQL/Redis/Celery large workloads, process/helper isolation and tenant database defense-in-depth/RLS are not all qualified by this local SQLite run. See [PROJECTTRACE_FINAL_STABILITY_AND_RELEASE_VALIDATION.md](<C:/Users/sai krishna/OneDrive/Desktop/ProjectTrace/PROJECTTRACE_FINAL_STABILITY_AND_RELEASE_VALIDATION.md>) and [PROJECTTRACE_PRODUCT_AUDIT_AND_READINESS.md](<C:/Users/sai krishna/OneDrive/Desktop/ProjectTrace/PROJECTTRACE_PRODUCT_AUDIT_AND_READINESS.md>) for retained earlier evidence and exact gaps.
4. **Scope of final proof is explicit.** Local catalogue and its four-reader deadline workload, representative browser/API workflows, exact persisted original results, fresh smaller analysis and checkpoint recovery pass. This does not prove every provider, every typed historical view, a fresh final-code large cold construction, arbitrary concurrent large jobs or all possible UI states. These are release qualifications, not fabricated PASS results.

**Final disposition:** Repositories' avoidable summary dependency/query scans are fixed in the tested workload; Infrastructure's demonstrated index mismatch and review/Ask scope races are corrected. The two published analyses are preserved and correctly remain PARTIAL. The earlier original warm large timeout has repeated measured completion evidence; a fresh cold/deployment-scale guarantee remains unresolved. **Do not promote the whole ProjectTrace product as ready.**
