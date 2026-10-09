# ProjectTrace product audit and readiness

Audit date: 2026-10-09, Asia/Calcutta. Report generated 2026-10-09 12:14:45.
Actual workspace: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`.
Private reproducible receipts: `C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit`.
This report applies to the current uncommitted source; it preserves the earlier timeout/correlation reports as historical evidence.

## A. Executive verdict

**BLOCKED** for the master prompt's complete product/pilot readiness gate.

The installed app is running and its demonstrated local workflows work. This audit repaired measured SQLite contention, a real PostgreSQL dispatch/claim race, immutable snapshot provenance, interruption-history loss, asynchronous test assumptions, and two gateway defects. Final regression tests and actual private staging checks passed. The mandatory complete, durably resumable multi-task pipeline is still absent: native file artifacts survive interruption, but global aggregation and graph/snapshot publication are rebuilt inside one task and one atomic transaction.

The latest exact `data`/`second` incident was retried twice without changing its archive, tenant, inventory, original submitting account, grant or 900-second budget. Final retry state: **PARTIAL**, stage **PARTIAL**, snapshot `9fc9a751-0ef7-4673-b437-93ea40768cfd`. A new snapshot was actually published. This retained-cache completion mitigates the immediate incident; the original large cold/partially warm completion problem remains unresolved. It missed the 720-second headroom target and does not establish multi-task resumability or repeated current-tenant completion. No timeout, analyzer, safety, coverage or retry limit was disabled; there was no third retry or new maintenance job to conceal failure.

| Acceptance gate | Status | Evidence / limit |
| --- | --- | --- |
| Real small ZIP and public GitHub imports | PASS | Linux Celery/PostgreSQL API; actual published results |
| Real authorized smart-waste ZIP | PASS | Pipeline completed with explicitly PARTIAL analysis scope |
| Current full OpenMetadata processing | PASS | Exact current job measured below; historical warm passes are separately identified |
| Repeated full runs at <=720 seconds / cold repository qualification | FAIL | The first current replay failed at 915.34 s; no full cold-cache qualification |
| Native parser checkpoint retention and actual child crash recovery | PASS | 500 cached files survived, no partial snapshot visible, one recovery publication |
| Entire analysis resumed as bounded durable stage tasks | FAIL | Global publication has no durable generation/work-unit state |
| SQLite idle writer contention and ZIP backpressure | PASS | Measured before/after and writer-lock regressions |
| Real PostgreSQL migrations/claim race/scoped publication | PASS | Eight real PG tests; actual stalled public job recovered |
| Production memory/resource envelope for OpenMetadata | NOT_TESTED | Existing 1 GiB compose worker is below previously measured ~4.6 GiB aggregate peak |
| Browser major local workflows and production static pages | PASS | 12 async workflows + actual Nginx static production check |
| GitHub App ref resolution | PASS | Actual authorized provider metadata HTTP 200 |
| End-to-end live App webhook / GHES / OIDC / cloud / object store | NOT_TESTED | Original webhook secret absent; remaining external systems not supplied |
| Fresh private PG database + encrypted-source restore | PASS | Separate restored DB identical; 214 restored ciphertext digests verified |
| Production TLS, sustained load, independent accuracy and disaster recovery SLA | NOT_TESTED | No public deployment or unsupported SLA |

## B. Defects repaired

| Symptom | Proven cause and exact correction | Source / regression evidence | Residual risk |
| --- | --- | --- | --- |
| Idle local recovery waits behind unrelated publication | `recover_expired` acquired the singleton writer lock even when no applicable expired lease existed. Read-only scoped preflight, then lock and recheck only real work. | `backend/scheduling.py`; fair-scheduling writer-lock tests; contention probe | Actual work still serializes intentionally; SQLite admits one analysis writer |
| Busy ZIP request waits ~5.5 s and returns database-busy | Admission acquired the writer lock before checking duplicate receipts/active local analysis. Added authorized read preflight and serialized recheck. | `backend/main.py`; import-reliability duplicate/backpressure tests | Capture itself remains synchronous; native archive limits and grant checks retained |
| Real Linux public job remains QUEUED after dispatch | Worker read Record version, API updated SENT metadata, worker claim committed the stale version before its error handler: actual `StaleDataError`. Claim now locks scheduler first, refreshes/locks job row, then claims; removed inverse Record-first lock in native worker. | `backend/scheduling.py`, `workers/tasks.py`; PG stale-dispatch test; same stalled job `88441ece-1e53-4a21-a2c1-4d59f08583a9` redispatched and published `e9a0dade-d079-42ee-8499-54ac9dd8bcc1` | Concurrency test scope is bounded; sustained production fairness not qualified |
| Idempotent replay changes an existing snapshot's origin job | Existing snapshot reuse overwrote `data.job_id`. Removed the rewrite; later job points to the immutable original snapshot. | `backend/domain.py`; repository-store and real PG provenance tests | Existing historical metadata is preserved, not retroactively rewritten |
| Expired-worker recovery loses attempt stage history | Recovery overwrote current job state without saving attempt history. Preserve prior stages, performance, unpublished summary, errors and counters before bounded recovery. | `backend/scheduling.py`; SQLite/PG recovery tests; actual child interruption | Cache recovery still rebuilds global output; not global stage resume |
| Seven browser tests fail after local async startup | Tests assumed HTTP 200, read job IDs as snapshot IDs, or asserted results before completion. Added bounded authenticated terminal-job polling and actual snapshot validation. | `frontend/e2e/analysis.ts` and seven specs; 12 passed / one static skip later exercised separately | Test harness repair; no product UI rewrite |
| Gateway rejects permitted archive sizes | Actual Nginx returned 413 for 12,582,912 bytes while API default allows 512,000,000. Match gateway byte cap to API default; API enforces smaller operator quotas. | `infrastructure/nginx.conf`; actual 12 MiB probe now 422 `ARCHIVE_INVALID` | Valid 157 MB cold capture through the gateway is not yet qualified; synchronous capture can exceed gateway response timeout |
| Production public pages redirect to unusable internal port | Actual `/guide`, `/trust`, `/docs` redirected to `127.0.0.1:8080` behind published port 8014. Use relative directory redirects in Docker and Kubernetes configurations. | Both Nginx configs; same actual gateway browser test now passes | Kubernetes deployment itself not executed |

No SonarQube, Wiz or external AI runtime was introduced. No customer repository code, package scripts, builds, Terraform, Maven or infrastructure commands were executed. The trusted ProjectTrace app and its own tests/images were built.

## C. Product capabilities

Statuses describe the stated verified scope, not universal semantic coverage.

| Capability | Status | Verified scope / remaining limitation |
| --- | --- | --- |
| Local account creation/login/logout and repository grants | WORKING_AND_VERIFIED | Real browser accounts, API role/tenant negatives; existing customer accounts retained |
| ZIP intake and later source snapshots | WORKING_AND_VERIFIED | Real ZIP → analysis → review/evidence → second snapshot/drift/gates; malicious ZIP rejection |
| Public GitHub snapshot intake | WORKING_AND_VERIFIED | Actual provider commit-pinned repository import on Linux Celery/PG |
| GitHub App source and PR automation | PARTIALLY_IMPLEMENTED | Actual configured ref resolves; local worker/provider/signature regressions pass; exhausted full job and absent webhook secret remain |
| GHES and OIDC lifecycle | IMPLEMENTED_BUT_UNVERIFIED | Provider-policy/lifecycle mock regressions pass; no actual enterprise host/IdP end-to-end |
| Claim Ledger and static verification | WORKING_AND_VERIFIED | Supported documentation/implementation statements, contradictions, evidence citations and review history; runtime UNOBSERVED |
| Evidence storage and graph | WORKING_AND_VERIFIED | Encrypted scoped artifacts, graph paging/relationships and real small/medium output; large resumable publication absent |
| Code Quality | WORKING_AND_VERIFIED | Supported metrics, profiles, new-code/history/coverage views and advisory gates; partial language maturity |
| SAST | PARTIALLY_IMPLEMENTED | Bounded Python models and selected JS/TS/Java syntax checks; no complete interprocedural taint/type resolution |
| Secrets | PARTIALLY_IMPLEMENTED | Static context/pattern detection and redaction; credential validity never tested |
| SCA/SBOM/advisory enrichment | PARTIALLY_IMPLEMENTED | Native pinned/manifests inventory and scoped exports tested; unresolved coordinates and no fresh live advisory feed qualification |
| IaC | PARTIALLY_IMPLEMENTED | Supported Terraform/HCL2, Kube, Compose, CloudFormation and Dockerfile static rules/graphs; no deployment evaluation |
| Drift and impact | WORKING_AND_VERIFIED | Actual two-snapshot browser fixture, graph-linked changes, explicit runtime limitations |
| Engineering Changes | WORKING_AND_VERIFIED | Controlled base/head backend comparisons and browser component behavior; not a live enterprise PR acceptance |
| Quality gates, human review, exceptions | WORKING_AND_VERIFIED | Scoped policies/review/audit tests and real source workflows; representative accuracy remains unmeasured |
| Trust & Coverage | WORKING_AND_VERIFIED | Captured/non-source/unsupported/skipped distinctions, parser limits and runtime UNOBSERVED |
| Audit history and retained checkpoint checks | WORKING_AND_VERIFIED | Original rows preserved; linked chains verify; privileged rewrite tests use independently retained checkpoint |
| Cloud assets/identities/exposure/risk paths | IMPLEMENTED_BUT_UNVERIFIED | Native adapters and credential gates tested; no actual cloud account inventory acceptance |
| Encrypted object-store adapter | IMPLEMENTED_BUT_UNVERIFIED | Mocked S3 encryption/KMS/policy tests; no live object storage restore |
| Local queue, leases and bounded retry | WORKING_AND_VERIFIED | Actual local processing and Linux child failure recovery, duplicate-claim PG tests |
| Native incremental analysis | WORKING_AND_VERIFIED | Version/path/content/tenant keyed cache; one-file-change benchmarks below |
| Entire pipeline durable multi-task resume | MISSING | Native cache checkpoints exist; global publication has no durable staging generation |
| Public production deployment / paid integrations | OUT_OF_SCOPE | No authorization to publish/buy resources; private local staging only |

## D. Repository validation

| Actual input | Files | State | End-to-end seconds | Stored analysis seconds | Snapshot |
| --- | --- | --- | --- | --- | --- |
| small-real-zip | 6 | COMPLETED | 7.512083 | 4.10508 | 6a6bad35-2112-4aae-bb03-ecf6488e43f8 |
| authorized-smart-waste-zip | 47 | PARTIAL | 18.247095 | 16.11912 | 72288393-7bfd-47b8-9b96-152fcc327b99 |
| actual-public-github | 50 | PARTIAL | 9.939057 | 5.37715 | 32f87a9c-d762-42e4-bdb9-876a05b755ca |

The smart-waste archive SHA-256 is `293fca0b7f1cf9b42b6726073b3468ae05ba432fe310daa81b93e0f7fd969919`.
Its snapshot reported 74 claims, 29 native findings and 297 dependency observations, with scope/diagnostics explicitly PARTIAL. The public provider ran against actual `pallets/itsdangerous`; its pinned provenance is in `staging-acceptance.json`. These API staging checks used fresh audit accounts/DB, not the user's account.

The current large input is exactly `OpenMetadata-main.zip`, SHA-256 `027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`, 157,126,481 compressed / 330,420,155 expanded bytes / 21,636 inventory entries. Original job `f88efa38-5485-4a1e-acde-d93a51ad6cc5`, repository `4f7304f9-c355-467f-8799-785e74b83cdf`, organization `second` (`c1d9f579-bdd2-4d2b-b22f-a2020aa4a2dc`), retained complete inventory `9093402c-ab51-4b5b-9685-c72f2a30add4`. The separate CAPTURING inventory `237aa0af-6999-449b-9919-372ec8539610` was retained and never treated as analyzable.

The actual new large publication contains **18,859 evidence records, 1,500 claims, 7,904 findings, 2,090 dependencies, 231,229 graph nodes and 289,745 edges**. Its native pre-publication summary reports 7,900 findings; four derived PT-CONSISTENCY-001 findings are included in the final 7,904. Both historical and fresh large snapshots have 7,904 unique persisted finding fingerprints, identical rule-count distributions and identical rule/path/line/category/severity coordinate sets. They belong to different tenants, so this is comparable static-output evidence, not a repeated same-tenant performance run. Current JSON scope mismatches: 0. No duplicate fingerprint was introduced.

The initial latest failure lasted 1,027.33577 s in ANALYZING, not correlation. ZIP capture took 831.57757 s separately. Windows Kernel-Power events show approximately 584.484 s of modern standby within that original job. Awake current retry 1 still exceeded its budget, proving standby was not the only large-repository limitation. A controlled cProfile replay of its two previously slowest Python files took 4.34415 s including profiler overhead; parser timings were 0.485219 s (`test_airflowapi.py`) / 1.422026 s (`test_dbtcloud.py`), with nine findings and no warnings. It does not establish a whole-repository cold runtime or a parser bug.

Adversarial actual staging: malformed ZIP → 422 `ARCHIVE_INVALID`; traversal ZIP → 422 `ARCHIVE_UNSAFE_PATH`; another tenant's snapshot → 404. The final backend suite also exercises path/symlink/compression/directory metadata limits, syntax budgets, DNS/redirect/TLS/SSRF restrictions, callback/replay/role policies and source-inertness fixtures.

Concurrent actual PG: four simultaneous deliveries claim one owner; dispatch-version race, tenant/repository admission, stale fencing and independent branch publication pass. This is bounded correctness evidence, not sustained multi-tenant throughput qualification.

## E. Performance and checkpoint behavior

Hardware: Windows 11 Home Single Language 10.0.26300, Intel Core 5 120U / 12 logical CPUs, 16,806,244,352 bytes RAM. Installed Python 3.14.3, SQLAlchemy 2.1.3, SQLite 3.50.4, schema 0014, WAL, one local analysis writer, 32 MiB SQLite connection-cache target; this target is not a process memory ceiling. Native helper concurrency remains capped at two; Windows descendants include launchers and nested processes, not equivalent analyzer slots.

Private Linux staging: PostgreSQL 17.11 (1 GiB/2 CPUs), Redis 7 alpine (128 MiB/0.5 CPU), backend Python 3.14.8, Celery 5.6.3 prefork concurrency one (2 GiB/2 CPUs), API 512 MiB/1 CPU; worker/API read-only roots, dropped capabilities, no-new-privileges, noexec/nosuid tmpfs, separate fresh volumes/network. Gateway nginx 1.30.5; exact image digests are retained in private receipts. APP_ENV is demo/private local, not a TLS production certification.

| Attempt | State | Last stage | Stored analysis s | Monitor wall s | API CPU s | Sampled descendant CPU s | Peak process-tree GiB | Cache hits | Cache misses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Retry 1, partially warm | FAILED | ANALYZING | 915.3404 | 933.105566 | 221.265625 | 418.875 | 1.194 | 3425 | 8004 |
| Retry 2, retained cache | PARTIAL | PARTIAL | 865.59361 | 904.105301 | 464.34375 | 156.4375 | 4.119 | 11311 | 7548 |

Monitor wall includes initial input/hash/retry admission and polling; it is not identical to the worker's analysis clock. Stored duration is recorded before final commit and underreports full successful call wall. The recorded worker start plus first externally visible terminal observation bounds the second attempt's publication-inclusive worker time to approximately **888.706–890.706 seconds**. This derived interval accounts for the monitor label's one-second precision and polling delay; it is not an exact worker-return stopwatch. It supports one completion under 900 seconds, with less than 12 seconds of headroom, and exceeds the 720-second target. `full-runtime-bounds.json` retains the calculation. Measurements sample owned processes once per second; short-lived helpers may be missed. Cold/partially warm replay initially overlapped bounded staging/browser checks; the full backend suite and isolated benchmark series were serialized after the full replays. Background desktop activity and OS caches were not controlled.

| Pipeline stage seconds | Current retry 1 | Current retry 2 |
| --- | --- | --- |
| VALIDATING | 2.026449 | 1.428163 |
| PARSING | 1.026818 | 0.603107 |
| ANALYZING | 912.260375 | 449.65145 |
| EXTRACTING_CLAIMS | NOT_REACHED | 6.5077 |
| VERIFYING | NOT_REACHED | 26.312572 |
| BUILDING_EVIDENCE | NOT_REACHED | 110.303729 |
| CORRELATING | NOT_REACHED | 270.773473 |
| FINALIZING | NOT_REACHED | 0.000941 |

| Inclusive component seconds | Current retry 1 | Current retry 2 |
| --- | --- | --- |
| PARTITION_PARSE | 840.942201 | 361.346069 |
| SYNTAX_HELPER | 457.67907 | 175.706272 |
| PYTHON_NATIVE | 27.027071 | 0.579399 |
| TREE_SITTER | 349.808552 | 114.250725 |
| CACHE_LOOKUP | 16.750389 | 48.279535 |
| CACHE_WRITE | 18.2039 | 5.69848 |
| CLAIM_EXTRACTION | NOT_REACHED | 6.503598 |
| CLAIM_VERIFICATION | NOT_REACHED | 0.44921 |
| EVIDENCE_SOURCE_READ | NOT_REACHED | 57.49577 |
| EVIDENCE_REDACTION | NOT_REACHED | 26.755908 |
| FUNCTION_GRAPH | NOT_REACHED | 135.032155 |
| FINDING_HISTORY | NOT_REACHED | 2.932445 |
| POLICY_PROJECTION | NOT_REACHED | 7.57229 |

Stage timers include nested components; syntax-helper wait overlaps measured parser execution. Never sum component timers as wall time. NOT_REACHED identifies stages for which this attempt provides no completed measurement. Slow measured operations retained by the job:

| Attempt | File | Operation | Seconds | State |
| --- | --- | --- | --- | --- |
| Retry 1 | OpenMetadata-main/openmetadata-ui/src/main/resources/ui/playwright/e2e/Pages/CustomProperties.spec.ts | TREE_SITTER | 3.613062 | COMPLETED |
| Retry 1 | OpenMetadata-main/ingestion/tests/unit/topology/pipeline/test_openlineage.py | PYTHON_NATIVE | 3.565088 | MEASURED |
| Retry 1 | OpenMetadata-main/openmetadata-ui/src/main/resources/ui/playwright/e2e/Pages/Domains.spec.ts | TREE_SITTER | 3.480102 | COMPLETED |
| Retry 1 | OpenMetadata-main/openmetadata-ui/src/main/resources/ui/playwright/e2e/Pages/DataContractsSemanticRules.spec.ts | TREE_SITTER | 3.476083 | COMPLETED |
| Retry 1 | OpenMetadata-main/openmetadata-ui/src/main/resources/ui/playwright/e2e/Pages/Glossary.spec.ts | TREE_SITTER | 2.816561 | COMPLETED |
| Retry 2 | OpenMetadata-main/openmetadata-integration-tests/src/test/java/org/openmetadata/it/tests/TestCaseResourceIT.java | TREE_SITTER | 2.093337 | PARTIAL |
| Retry 2 | OpenMetadata-main/docker/docker-compose-quickstart/Dockerfile | FILE_POSTPROCESS | 1.863694 | MEASURED |
| Retry 2 | OpenMetadata-main/ingestion/Dockerfile | FILE_POSTPROCESS | 1.736585 | MEASURED |
| Retry 2 | OpenMetadata-main/ingestion/operators/docker/Dockerfile | FILE_POSTPROCESS | 1.64099 | MEASURED |
| Retry 2 | OpenMetadata-main/openmetadata-integration-tests/src/test/java/org/openmetadata/it/tests/BaseEntityIT.java | TREE_SITTER | 1.595307 | PARTIAL |

Current published coverage summary: `{"files_discovered": 21636, "files_with_native_scan": 18859, "source_analysis_percent": 92.967005, "source_files": 15669, "source_files_parsed": 14567, "states": {"BINARY": 189, "EXCLUDED_GENERATED": 1058, "EXCLUDED_VENDOR": 95, "IGNORED_BY_POLICY": 1475, "PARSE_FAILED": 33, "PARTIAL": 17671, "SKIPPED_SIZE_LIMIT": 32, "UNSUPPORTED": 1083}}`. A failed attempt has retained inventory/cache/diagnostics, not a passing full coverage or gate result. Original diagnostics are preserved separately and in the immutable audit backup.

| Language inventory | Files | Source parser completed | Maturity |
| --- | --- | --- | --- |
| CloudFormation | 17 | 17 | PARTIAL |
| Compose | 29 | 26 | PARTIAL |
| Dockerfile | 26 | 16 | PARTIAL |
| Java | 4609 | 4598 | PARTIAL |
| JavaScript | 112 | 112 | PARTIAL |
| Kubernetes | 41 | 39 | PARTIAL |
| Make | 3 | 0 | UNSUPPORTED |
| Other text / binary | 4799 | 0 | UNSUPPORTED |
| Python | 3054 | 3037 | PARTIAL |
| SQL | 342 | 0 | UNSUPPORTED |
| Shell | 60 | 0 | UNSUPPORTED |
| TypeScript | 7866 | 6820 | PARTIAL |
| UNKNOWN | 678 | 0 | UNSUPPORTED |

The earlier correlation investigation remains valid for its measured warm tenant/inventory: it proved fragmented function-graph ORM flushes (5,120 → 1,594 full-record batches, bounded at 250 rows; consult the exact historical table rather than substituting current cold timings). Final isolated full call was 330.507886 s and installed fenced full call 481.234476 s, published PARTIAL with 14,567/15,669 declared source parser completion (92.967005%), 105 warnings and runtime UNOBSERVED. Both genuinely built the full graph. See [correlation validation](CORRELATION_PERFORMANCE_FINAL_VALIDATION.md); these prior passes are not fresh cold qualification for `data`/`second`.

Fresh current-code fixture benchmarks (cold = empty application cache; OS cache uncontrolled):

| Files | Mode | State | Full call s | Parent CPU s | Helper CPU s | Peak MiB | Cache hits | Cache misses | Findings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | cold | COMPLETED | 1.603595 | 0.921875 | 0.0 | 97.22 | 0 | 20 | 200 |
| 20 | warm | COMPLETED | 0.554482 | 0.53125 | 0.0 | 108.61 | 20 | 0 | 200 |
| 20 | one_file_change | COMPLETED | 0.900059 | 0.859375 | 0.0 | 119.43 | 19 | 1 | 200 |
| 100 | cold | COMPLETED | 2.731201 | 2.546875 | 0.0 | 130.08 | 0 | 100 | 1000 |
| 100 | warm | COMPLETED | 2.288721 | 2.046875 | 0.0 | 162.02 | 100 | 0 | 1000 |
| 100 | one_file_change | COMPLETED | 4.288324 | 3.953125 | 0.0 | 192.5 | 99 | 1 | 1000 |
| 500 | cold | COMPLETED | 18.234719 | 17.15625 | 0.0 | 392.27 | 0 | 500 | 5000 |
| 500 | warm | COMPLETED | 9.144521 | 8.015625 | 0.0 | 451.06 | 500 | 0 | 5000 |
| 500 | one_file_change | COMPLETED | 17.171311 | 15.96875 | 0.0 | 586.64 | 499 | 1 | 5000 |

All three modes publish their declared scope; a one-file change reparses one file, while global verification/history/graph work still recomputes. Warm/change runs can be slower as publication/comparison/database size increases. Detailed stage/SQL/flush/coverage/resource counters live in each `benchmark-final-*/receipt.json`. This is not a 100,000-file scale claim.

SQLite contention reproducer: idle recovery before = DATABASE_BUSY after 5.570833 s; after = NO_WORK in 0.069791 s. Busy ZIP before = 503 LOCAL_DATABASE_BUSY after 5.542257 s; after = 503 LOCAL_CAPTURE_BUSY in 0.106328 s with Retry-After 2. Security and serialized race rechecks remain.

## F. Security

Native and imported sources remained inert throughout actual imports, parser probes, benchmarks and crash drills. Private source is encrypted and tenant-namespaced; no source was sent to Sonar/Wiz/AI. Actual HTTP cross-tenant checks returned 404; PG source-inventory composite FK negatives and ORM scope tests passed. Scoped checks, cancellation fences, quotas, syntax limits, and TLS/DNS pinning were retained.

`pip-audit -r requirements.lock` reported no known vulnerabilities; npm audit reported zero known vulnerabilities. These are dependency advisory results, not container/OS image, supply-chain attestation or comprehensive security certification. Fresh keys/passwords were generated only for isolated audit staging; customer keys, passwords and configured provider references were preserved. Secrets and raw exception/source output are excluded from the report.

Remaining security qualification: no broad PG RLS/full compound-FK defense across every generic Record relationship; no fully isolated per-job main-process/network sandbox; large aggregate memory has no independent hard in-process ceiling; no real TLS/IdP/GHES/cloud/S3/rotation acceptance or production accuracy qualification. Audit chain VERIFICATION covers linked history; the initial database also contained legacy unlinked events. An operator able to rewrite a whole chain needs an independently retained authenticated checkpoint to expose that rewrite; no WORM archive is claimed.

Actual GitHub App metadata probe: authorized `maninani12/OpenMetadata`, `refs/heads/projecttrace-snapshot-test`, HTTP 200, resolved `b1fab2bc21c63335dead4daaaa28194c9878e9bf`, 2.2696195 s. Existing exhausted SCM job remains failed and was not reset or replaced. The original `SCM_GITHUB_WEBHOOK` reference is absent; the operator must restore the matching original secret for live signed deliveries. A new secret was not generated.

## G. Data integrity and recovery

Before changes: consistent SQLite backup **4,958,789,632 bytes**, `integrity_check=ok`, zero FK violations, schema 0014. Backup plus complete integrity/FK verification took **897.071468 s**, not just copy time. Baseline: 79 organizations/users, 74 repositories/grants, 176 snapshots, 621,942 generic records, 5,092 audit events, 3,088 audit links, 64,082 source blobs, 109,712 inventory entries, 60,225 parser artifacts. The huge pre-existing uncommitted working tree was hashed and preserved; no commits/pushes occurred.

Read-only final preservation compared old rows against the actual consistent backup: **True**, old snapshot/domain/claim/evidence/graph/review/exception/typed/cache/inventory/audit rows unchanged. The intentionally retried incident job is excluded from immutable comparison, with **2** prior attempts retained; queue cursor/audit heads/session lifecycle are mutable. Old blob files checked: **64082**, missing **0**, actual decrypt/hash sample **100**. Full raw source ciphertext equality against a pre-audit file manifest was not available; do not present the sample as full-file cryptographic verification. Audit chain states: `{"VERIFIED": 20}`. Detailed counts/exclusions: `preservation-final.json`.

Actual Linux worker child SIGKILL at durable BUILDING_EVIDENCE: zero snapshots visible, all 500 parser artifacts retained, parent worker survives. The private fault injector expired only that test job's lease; the unchanged application recovery task requeued it once. Final state COMPLETED, one published snapshot, 500 cache hits, old unpublished summary/stage/performance retained, audit verified, overall 52.913166 s. It tests expired-lease handling without waiting 930 idle seconds; it does not qualify autonomous Beat scheduling or durable global graph resumption. PG stale worker and failure rollback tests separately prove newer leases cannot be released/published by stale owners.

Private restart drill retained the session, original snapshot JSON and verified audit chain in 12.382087 s. Actual PG 0005→0014→0005→0014 migration preservation ran in disposable UUID schemas. Customer migrations were not rolled back.

Actual fresh PG backup/restore: `pg_dump -Fc` to new private file, separate database `projecttrace_audit_restored`, `pg_restore --exit-on-error`; all public-table row fingerprints/counts identical. Backup/ciphertext copy 5.285462 s, PG restore 9.862343 s; 13616808 bytes. All **214 copied encrypted blobs** decrypted to their content digests using the separately retained key; seven staging audit chains verified. Original DB was not replaced. These small local timings do not establish managed production RPO/RTO.

## H. Developer experience and actual runtime

Installed managed API/UI were gracefully stopped/restarted, original settings/db/accounts/key references retained, and API `/ready` plus UI `/api/auth/options` proxy verified. Installed worker was refreshed only after verifying its command, working directory and no running work. Existing user Redis/Beat were preserved. The local default requires no Redis for ZIP/public jobs.

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace'
& .\scripts\start.ps1
# Open http://127.0.0.1:5181/repositories and use your existing account.
& .\scripts\stop.ps1
```

Stop drains active local work and preserves queued inputs/source/accounts; it does not kill unrelated listeners or independent workers. Configuration-only check: `.\.venv\Scripts\python.exe scripts/dev_workers.py --check-only`; private SCM strict check adds `--require-scm`. Raw keys/shell directives are rejected from operator JSON configuration. No seed/reset command is needed on the existing installation.

Audit-only services are bound to loopback, use fresh private volumes and are not public deployments. QA API/UI 8012/5182, private PG/Celery API 8013, gateway 8014 and static preview 5183 are separate from the user's 8011/5181 session. Private artifacts contain confidential databases/keys and must not enter source packaging.

After validation, the five verified owned Docker audit containers and QA/preview listeners were stopped. All private data, volumes, keys, logs and receipts remain; the user's API/UI returned 200 afterwards and its existing Redis/worker/Beat were retained. The preview used a relative command path, so cleanup additionally verified its process CWD before stopping it. Exact shutdown verification is in `audit-shutdown.json`, `stop_audit_services.py` and `finish_shutdown.py`.

## I. Frontend acceptance

Initial browser run: five passed, seven failed, one skipped; the failures reproduced asynchronous API assumptions. Final local async browser run: **12 passed / 1 skipped / 0 failed**, 252.458008 s reported by Playwright. The skipped production-static test was then actually exercised: Vite production preview one passed, and real Nginx one passed (35.385210 s). The initial Nginx run failed on its internal-port redirect and was repaired/retested; failure artifacts are retained.

Verified: fresh real workspace creation/import, terminal job status, real source evidence/review/history/graph/Ask, two actual fixture snapshots/drift/impact/gates/audit, isolation and reload/legacy route navigation. Dedicated checks cover quality tabs/profiles/coverage/mobile/axe, enterprise audit/policies/IaC, components/history/graph paging, native profiles/cloud credential gates, captured coverage, public onboarding, responsive 360/390/768/1024/1280/1440 widths, theme/reduced motion/Guide and failure/404 routes. Production public HTML works across 41 prerendered pages without JavaScript and hydrates without eagerly loading graph/workspace bundles.

Human visual spot-checks of `real-repository.png`, `real-drift-impact.png`, `quality-1440.png` show actual loaded results; generic navigation screenshots alone are not evidence that every collector/function executed. Northstar pages remain labeled deterministic demo data. Actual imported result proofs are stored separately in `browser-proof`.

## J. Tests, commands and execution evidence

| Executed check | Passed | Failed | Skipped | Wall s | Local completion | Scope |
| --- | --- | --- | --- | --- | --- | --- |
| Initial backend regression | 455 | 0 | 0 | 1290.021 | 2026-10-09 10:15:05 | Initial state; before final recovery change |
| Final complete backend, including real PostgreSQL | 467 | 0 | 0 | 406.189 | 2026-10-09 11:17:38 | Current final source; no skips |
| Worker/import/scope regressions | 103 | 0 | 0 | 464.477 | 2026-10-09 10:30:53 | Before final additive history retention patch |
| Final scheduler/worker/timeout regressions | 13 | 0 | 0 | 55.571 | 2026-10-09 10:37:49 | Current recovery change |
| Final real PostgreSQL regressions | 8 | 0 | 0 | 106.342 | 2026-10-09 10:38:38 | Actual PostgreSQL 17.11; isolated UUID schemas |

Frontend unit: 32 tests / eight files passed; production TypeScript/Vite build and 41 public pages passed. Ruff final passed. Python and npm advisory audits passed. The Starlette/httpx deprecation warning remains non-fatal and is documented rather than suppressed. Intermediate failing iterations are retained: PG harness field/scope mistakes, stale old snapshot-provenance test expectation, original async browser assumptions, and the actual gateway redirect. These are not omitted or counted as successful checks.

Exact current core commands from receipts (backend cwd is the actual Root; frontend commands run in `frontend`; disposable PG URL is loaded from the private secret file, never printed):

```powershell
& "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe" -m pytest -q "--basetemp=C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit\pytest-backend-final" "--junitxml=C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit\backend-final.xml"
```

```powershell
& "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe" -m pytest -q tests/test_postgresql_integration.py "--basetemp=C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit\pytest-postgres-recovery-final" "--junitxml=C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit\postgres-recovery-final.xml"
```

```powershell
& "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe" -m pytest -q tests/test_fair_scheduling.py tests/test_worker_failure.py tests/test_timeout_recovery.py "--basetemp=C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit\pytest-recovery-final" "--junitxml=C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit\recovery-final.xml"
```

```powershell
& cmd.exe /c npm test
```

```powershell
& cmd.exe /c npm run build
```

```powershell
& "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe" -m ruff check backend analyzers integrations workers tests scripts
```

```powershell
& "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe" -m pip_audit -r requirements.lock --format=json "--output=C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\product-audit\python-vulnerabilities.json"
```

```powershell
& cmd.exe /c npm audit --json
```

Additional actual commands: `python work/product-audit/staging_acceptance.py`; `python work/product-audit/worker_interrupt.py`; `python work/product-audit/postgres_restore.py`; `python work/product-audit/preservation.py`; `python work/product-audit/retry_data_incident.py` and the already permitted `--attempt 2`. Private script cwd is the Chat workspace and Python is Root's venv. These scripts preserve private configuration in memory and write sanitized receipts.

Benchmark command for each N=20,100,500:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_repository_analysis.py --output <new-empty-private-directory> --files N --functions 10
```

Browser: `node frontend/node_modules/@playwright/test/cli.js test --config=<private-playwright-final.config.cjs>` against localhost:5182. Production static run uses `PROJECTTRACE_STATIC_BASE_URL=http://127.0.0.1:8014`, private gateway-final config and `--grep="production public HTML"`. The actual Nginx probe validates config with `nginx -t` before reload. Backend CI adds a disposable PostgreSQL 17 service and runs async local browser startup; remote CI itself was not invoked or claimed passed.

## K. Files changed

Files changed/added since the actual audit source-hash baseline (earlier uncommitted modifications are excluded):

- `.github/workflows/ci.yml`
- `PROJECTTRACE_PRODUCT_AUDIT_AND_READINESS.md`
- `README.md`
- `backend/domain.py`
- `backend/main.py`
- `backend/scheduling.py`
- `docs/LOCAL_LOGIN_AND_IMPORT.md`
- `docs/RELEASE.md`
- `docs/backup-recovery.md`
- `docs/operations.md`
- `frontend/e2e/analysis.ts`
- `frontend/e2e/code-quality.spec.ts`
- `frontend/e2e/enterprise-trust.spec.ts`
- `frontend/e2e/hardening.spec.ts`
- `frontend/e2e/native-platform.spec.ts`
- `frontend/e2e/phase2-coverage.spec.ts`
- `frontend/e2e/public-site.spec.ts`
- `frontend/e2e/real-import.spec.ts`
- `infrastructure/kubernetes/nginx.conf`
- `infrastructure/nginx.conf`
- `tests/test_fair_scheduling.py`
- `tests/test_import_reliability.py`
- `tests/test_postgresql_integration.py`
- `tests/test_repository_store.py`
- `workers/tasks.py`

Application fixes are limited to scheduling/admission/claim ownership/provenance; existing analyzers, graph semantics and profiles were preserved. New PG and regression tests exercise the repaired invariants. Browser changes correct async lifecycle assumptions. Gateway configuration changes fix actual body and redirect behavior. CI provides real PG correctness coverage. Private audit tools, receipts, DBs, source backups and screenshots remain outside the source root; no secret/customer-data bundle was published.

## L. Release blockers and required architectural correction

| Priority | Blocker | Required action |
| --- | --- | --- |
| P0 | Complete analysis is not durably resumable across bounded stage tasks | Introduce scoped generation/work-unit state with fenced ownership, immutable input/profile versions, idempotent bounded stage output, invisible staging and atomic publication pointer |
| P0 | Current large cold/partially warm repository cannot be advertised as predictably complete under the budget | Profile/benchmark native packet cost and global publication on intended hardware after the staged architecture; qualify full cold and repeat runs, not cached throughput alone |
| P1 | Main aggregate graph/snapshot memory exceeds existing small worker envelope | Bound aggregation/index/serialization work and cgroup-aware backpressure; measure actual large PG/Celery target without weakening limits |
| P1 | Long ZIP capture is synchronous and not a durable ingestion task | Persist validated encrypted upload receipt, process bounded capture work asynchronously, publish only CAPTURED inventory; ensure idempotent receipt/auth/cleanup/failure visibility |
| P1 | Database and parser sandbox defense insufficient for production security claims | Complete tenant relationship constraints/RLS where appropriate and isolate main analysis/filesystem/network/resource privileges; real negative qualification |
| P1 | External provider / production operational acceptance incomplete | Restore original webhook reference; supply real GHES/IdP/cloud/object-store/TLS staging and validate scoped lifecycle/restore/rotation |
| P1 | Accuracy/sustained workload/managed DR not qualified | Independently labeled representative corpora and real sustained concurrent load/backup recovery tests before scale/SLA/blocking-policy promises |

The exact publication invariant prevents a quick 'commit every batch' fix: current generic claim/evidence/finding/graph rows and typed projections are visible through many repository and direct-ID reads. Committing current partial graph batches would expose unfinished output and break snapshot/history/gate assumptions. A safe correction needs an explicit unpublished generation and every relevant read constrained to PUBLISHED generations; work-unit retries must not modify prior snapshots or audit history.

Implement bounded ingestion/native/claim/verification/evidence/graph/history/finalization units with a durable input manifest and generation signature. Store checkpoint/output keys per scope and unit, fence each attempt and recheck grants; apply backpressure/CPU/memory limits. Reconcile global graph/history idempotently in private staging, then validate counts/relationships/coverage and atomically switch publication state/pointer with the completion audit. Cancellation/failure leaves only inventory/diagnostics visible. Qualify crash-at-each-boundary, stale ownership, concurrent tenants and repeated unchanged runs. This is a planned architecture, not implemented functionality.

No public launch, credential rotation, destructive customer migration or paid deployment was undertaken. The minimum external operator action currently identified is restoring the matching original GitHub webhook secret reference; doing so alone does not resolve these architecture/resource blockers.

## M. Actual repeatable buyer demonstration

Use the installed local app and an existing real workspace, or create a fresh local account through the normal signup UI. Do not represent Northstar fixture data as customer analysis.

1. Open `http://127.0.0.1:5181/repositories`, choose **Import repository → Upload ZIP → New repository**. Select the authorized `smart-waste-management-system-main.zip` (actual SHA above), give it a new explicit name, submit and wait for its actual job. If a full writer is active, honor LOCAL_CAPTURE_BUSY/Retry-After rather than creating duplicates.
2. Open the published result and **Trust & Coverage**. Present the PARTIAL state, actual languages/parsers/skips and runtime UNOBSERVED before findings. Open Claim Ledger, a supported finding and its redacted source/evidence links; record a review with an explicit reason and inspect Audit Trail.
3. For a repeatable change demonstration, use the owned `frontend/e2e/fixtures/native-fixture.zip`, then **Upload new snapshot** with `native-fixture-updated.zip`. These are labeled controlled fixtures genuinely parsed by the native pipeline, not preloaded scan results. Inspect drift, changed claims, impact graph, dependencies and advisory gates, then reload and verify history. This exact browser workflow passed.
4. For provider proof, **Public GitHub URL** with `https://github.com/pallets/itsdangerous`; show its resolved provider commit and actual coverage. Actual Linux staged acceptance passed; network/provider refusal must remain visible if it happens later.
5. Present the OpenMetadata reports and failed/partial attempt diagnostics as a scale limitation. Do not promise cold full analysis, zero vulnerabilities, runtime exploitability, production cloud coverage, global stage resumability or a production-ready deployment.

Final release decision remains **BLOCKED**; verified source-backed demonstrations are available within the documented scope.
