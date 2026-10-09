# Repository timeout root cause and recovery

Follow-up: [final correlation performance validation](CORRELATION_PERFORMANCE_FINAL_VALIDATION.md)
records the subsequent batching/storage correction and unchanged-input full
publication in 330.51 / 481.23 seconds under the same 900-second budget. The
failed attempts and unresolved decision below describe this historical
investigation; the follow-up preserves them and documents the current measured
PASS, honest PARTIAL coverage, standby failures and remaining scale limits.

Investigation: 2026-10-08–09 IST (UTC receipts dated 2026-10-08), local Windows ProjectTrace installation. This report describes measured local results, not a production capacity guarantee.

## Incident and evidence

The exact reported `actual 900.31; maximum 900` was located in the first attempt of job **3e9e5140-5218-4277-ac6e-6616f7fbd9c3**, repository **metadata**, repository ID **9fe836be-1317-4316-b733-1ec63d905f45**. The durable duration is **900.31028 s**. This is separate from the earlier ZIP validation job and private `maninani12/OpenMetadata` job; their failures were not substituted for this incident.

The first attempt failed during ANALYZING. VALIDATING and PARSING completed; global claim extraction, verification, evidence publication and correlation had not completed. Instrumentation counted 96 processed partitions, 9,267 cache misses/native file results, zero cache hits and 93 diagnostic paths/records. These are processed counts, not proof that every final partition write committed: the next retry reused 9,074 successful artifacts. Its last durable ANALYZING entry is a checkpoint, not proof of completed whole-repository analysis.

The already-running normal retry was inspected without interruption. It subsequently failed at **900.02363 s**, during CORRELATING. All 199 native partitions completed; 9,074 artifacts were reused and 9,785 files were processed again. A static analysis summary was captured at **694.815295 s**, explicitly **UNPUBLISHED**. No snapshot was committed. There were 196 durable parser diagnostic records for 103 distinct paths across these two attempts.

The complete retained inventory is **cbbe4102-c2f5-4e96-a3fc-eb8321c32472**. It records ZIP_STREAM, 21,636 entries, 330,420,155 uncompressed bytes and 928,035.66 ms ingestion wall time. This ingestion time is outside the later analysis attempt's clock: ingestion was expensive, but the specific 900.31-second exception occurred during native analysis. Existing receipts do not break the historical ingestion time into provider, encryption, I/O and database CPU costs.

Unchanged archive: `OpenMetadata-main.zip`, 157,126,481 bytes; SHA-256 `027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`. Ordered retained path/digest/metadata manifest SHA-256: `2f8f3478eacc93d4cfa2a1182dd21ab3e68c3ebce0d49c5d55bbb305d7ffaf40`. The retry uses this inventory without extraction, provider refetch or customer execution.

## Environment and safety limits

- Actual codebase: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`, with earlier working changes preserved.
- Windows 11 Home Single Language, build 26300; Python 3.14.3. CPU: Intel Core 5 120U, 10 cores / 12 logical processors. Visible RAM: 16,806,244,352 bytes (15.65 GiB). Free RAM during initial inspection: about 1.3–1.9 GiB. Other desktop applications remained open; cache and memory pressure varied. The idle API held about 1.56 GB working set after its failed analysis and was gracefully reloaded before recovery.
- Local SQLite database in WAL mode, 2,762,104,832 bytes before recovery, schema 0013 before the additive migration. Current schema is 0014. Deployed PostgreSQL throughput was not benchmarked here.
- API: APP_ENV=demo, JOB_MODE=local, one local runner. Actual incident execution is LOCAL / INVENTORY. A separate verified Celery solo worker and Beat remain configured; parser helper concurrency is capped at two independent syntax/IaC helpers. Queue defaults: global 4, tenant 2, repository 1; the local runner processes one job at a time.
- Repository deadline **900 seconds**, unchanged (runtime environment did not override this default). Repository inventory limits: 100,000 files, 2,000,000,000 uncompressed bytes, 512,000,000 archive bytes; individual file 512,000 bytes. These are admission ceilings, not measured supported scales.
- Partitions: at most 100 files / 2,000,000 bytes, respecting declared component boundaries. Decrypted source cache: at most 2 MB per partition, with fresh integrity checks for a new partition.
- Syntax helper: 30 s wall timeout, 512 MiB memory commit ceiling, 25 s CPU ceiling; syntax walk/token and output caps retained. IaC helper: 15 s wall, 384 MiB, 10 s CPU; YAML depth/token/alias and output caps retained. Windows Job Objects enforce helper memory/CPU ceilings. They do not provide network/filesystem isolation. Imported code, package installation, builds and infrastructure commands were never run.
- Publication retains the existing deadline/fenced lease checks, bounded work and atomic snapshot transaction. Cache entries and scoped file diagnostics commit at completed partitions. An unpublished graph rolls back; partial inventory remains visible.

## Measured bottlenecks and root cause

| Component | First 900.31-second attempt, partial | Existing retry, 900.02 seconds |
| --- | ---: | ---: |
| ANALYZING wall | 898.662858 s | 658.639064 s |
| Partition parsing, inclusive | 743.958910 s / 96 partitions | 405.012478 s / 199 |
| Python native | 288.209075 s / 3,035 calls | 1.207433 s / 19 calls |
| Tree-sitter file work | 153.048250 s / 4,616 calls | 195.715115 s / 7,980 |
| Syntax helper supervision, inclusive | 211.023986 s / 53 calls | 265.793129 s / 92 |
| IaC helper supervision | 15.408957 s | 10.279645 s |
| Native file postprocessing | 123.474576 s | 84.230112 s |
| Partition finding identity | 58.282355 s | 0.903916 s |
| Cache lookup / load | 89.067354 s | 194.705300 s |
| Cache writes | 26.801631 s | 17.041417 s |
| EXTRACTING_CLAIMS wall | Not reached | 5.938791 s |
| VERIFYING wall | Not reached | 28.867967 s |
| BUILDING_EVIDENCE wall | Not reached | 91.110603 s |
| CORRELATING wall | Not reached | 114.096239 s, incomplete |

Component/helper timers overlap; do not sum them into a whole-run time. Existing retry publication components: verified source reads 24.976418 s, redaction 35.780340 s, evidence-file loop 73.906971 s; finding correlation 52.363333 s, finding history 16.283878 s, artifact graph 42.144032 s. Configuration/function/ownership/policy/finalization had no completed timing in that failed attempt.

**Demonstrated database defect:** cache lookup asks for `organization_id = tenant AND id IN (up to 100 keys)`, but SQLite selected `ix_parser_artifact_scope (organization_id, content_hash, parser_version)` using only the tenant prefix. That repeatedly scans the tenant's artifact keys rather than locating the requested keys. The incident tenant had 37,512 immutable artifacts under the same current parser signature. This is inefficient lookup, not demonstrated cache invalidation: a read-only preflight found **18,756 eligible hits out of 18,859 candidates**; the 103 remaining warning/partial paths intentionally require new diagnostics.

For the same 100 keys and 5,106,168 bytes of returned payload, the original plan took **0.493439 / 0.372092 / 0.332617 s**. A read-only diagnostic using the existing primary-key index, while retaining the tenant predicate, took **0.009719 / 0.010900 / 0.008538 s**. After the new tenant-plus-ID index, the normal unhinted query plan uses both columns and took **0.066549 / 0.009082 / 0.006410 s**. These raw SQLite measurements exclude ORM JSON decoding; they do not promise that all cache-loading cost disappears.

**Demonstrated history defect:** an inert 100-file / 1,000-finding profile showed per-identity SELECTs and per-identity flushes in `finding_history.project`, plus repeated ORM reference lookups. The original cold fixture used 6,191 statements and 2,086 flushes. Batching history and memoizing references within each flush reduced this to 2,231 statements and 103 flushes, with batches no larger than 250. History time under the same profiler changed from **3.567926 s to 0.688564 s**. Finding semantics, fingerprints, states and coverage matched across cold, warm and changed-file runs.

**Conclusion about the original cause:** the first cold attempt accumulated parsing, postprocessing, identity and database work across thousands of files until the 900-second deadline. It did not demonstrate a single runaway parser. Inefficient cache lookup and history persistence are proven defects; large aggregate source/evidence/graph work remains relevant. Historical CPU/RSS were not recorded, so the precise effects of disk cache, memory pressure or antivirus cannot be reconstructed or asserted as causes.

**Checkpoint durability edge case:** a completed native partition wrote its immutable artifacts/diagnostics before calling progress, but the progress callback checked the deadline before committing. A deadline at this boundary rolled those completed rows back with the failed job transaction. The incident's processed-versus-reused counts differ by 100 successful rows after accounting for diagnostics, consistent with that boundary. The repair commits independently valid bounded native results before the following check; it does not commit incomplete graph/snapshot output or suppress failure. A dedicated regression reproduces this exact boundary with inert input.

### Slowest observed files

| Path relative to OpenMetadata-main | Operation | Seconds | Attempt |
| --- | --- | ---: | --- |
| ingestion/tests/unit/test_dbt.py | Python native | 2.888396 | Original |
| ingestion/tests/unit/lineage/queries/test_complex_query_patterns.py | Python native | 2.243787 | Original |
| ingestion/src/metadata/ingestion/source/database/sample_data.py | Python native | 2.228842 | Original |
| ingestion/tests/unit/topology/pipeline/test_openlineage.py | Python native | 1.987610 | Original |
| .github/scripts/tests/test_playwright_ci_planning.py | Python native | 1.735966 | Original |
| openmetadata-integration-tests/src/test/java/org/openmetadata/it/tests/LineageResourceIT.java | Tree-sitter, completed | 1.479688 | Original |
| openmetadata-ui/src/main/resources/ui/playwright/e2e/Pages/DataContractsSemanticRules.spec.ts | Tree-sitter, completed | 2.833609 | Existing retry |
| openmetadata-ui/src/main/resources/ui/playwright/e2e/Pages/Domains.spec.ts | Tree-sitter, completed | 2.735755 | Existing retry |
| openmetadata-ui/src/main/resources/ui/playwright/e2e/Pages/ExplorePageRightPanel.spec.ts | Tree-sitter, completed | 2.068019 | Existing retry |

Largest skipped entry is `ingestion/src/metadata/data_quality/data/fr-cities.json` (50,915,683 bytes). The 35,607,473-byte database test archive, 15,800,975-byte video and other oversize entries remain explicitly skipped. They were not fed to source parsers. A cached file has no fresh parse duration in a warm run.

## Changes and rationale

Changes made during this investigation:

1. `backend/db.py`: add `ix_parser_artifact_lookup (organization_id, id)`; snapshot the dirty set once per flush and memoize reference objects only within that flush. Every row still receives its original repository/tenant/FK check, including immutable tenant reassignment checks.
2. `backend/migrations/versions/0014_parser_artifact_lookup.py`: additive, reversible index migration. It neither replaces cache payloads nor changes their keys, tenant scope, findings or profiles.
3. `backend/finding_history.py`: prefetch at most 250 concept IDs, validate existing concept scope, flush identity parents, then write bounded occurrence batches under ordinary ORM and SQL FK enforcement. INTRODUCED/SEEN/MOVED/CONTEXT_CHANGED/RESOLVED/NOT_OBSERVED/REOPENED logic remains intact. Deadline checks run before batch publication. No partial snapshot commit was introduced.
4. `scripts/benchmark_repository_analysis.py`: reproducible empty-directory benchmark with inert fixtures or an explicitly selected ZIP component, cold/warm/one-file-change runs, SQL/flush counters, component timings, optional cProfile and Windows process-tree CPU/RSS measurements. ZIP content stays data; no extraction or execution. Application cache coldness is distinct from uncontrolled OS cache state.
5. `tests/test_timeout_recovery.py`, `tests/test_migrations.py`: scope, history preservation, bounded batch/query-plan and migration regression checks.
6. `backend/partitioned_analysis.py`: commit each completed bounded native cache/diagnostic partition before its progress check, preserving results if that check fails. This final boundary repair was made after the measured recovery worker had loaded the module; its dedicated validation and runtime reload are recorded separately from that replay's performance.
7. This report and operations documentation: measured behavior and limits.

Existing bounded helper concurrency, immutable file cache, packet-prefix retention, compact token representation, parser diagnostics, publication checkpoints and UNPUBLISHED summaries were retained and retested. They were already present at the start of this incident investigation; they are not falsely presented as new changes here. Global verification, quality thresholds and graph correlations still recompute. Full graph/snapshot construction is not durably resumable; a failed publication resumes native artifacts and rebuilds its atomic global output.

## Staged benchmarks

Generated Python source contains `eval` calls as inert text; the analyzer never executes them. Each file has ten functions. Runs include analysis, publication and commit; source fixture capture is outside this timer. Warm runs use identical content with a new captured commit to exercise publication, rather than returning an existing snapshot. Changed-file runs retain a real baseline and change one file.

| Unprofiled input / run | Wall s | Parent CPU s | Sampled peak RSS MiB | SQL cursor s | Statements | State |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 20 files cold | 0.829833 | 0.765625 | 98.2 | 0.061538 | 475 | COMPLETED |
| 20 files warm | 0.317414 | 0.281250 | 100.9 | 0.055480 | 472 | COMPLETED |
| 20 files one changed | 0.649593 | 0.625000 | 110.9 | 0.220609 | 504 | COMPLETED |
| 100 files cold | 2.069454 | 1.953125 | 111.9 | 0.322268 | 2,231 | COMPLETED |
| 100 files warm | 4.064003 | 3.875000 | 127.2 | 1.062189 | 2,221 | COMPLETED |
| 100 files one changed | 8.052421 | 7.718750 | 161.5 | 4.242848 | 2,266 | COMPLETED |
| 500 files cold | 25.589546 | 24.500000 | 358.5 | 7.350125 | 11,010 | COMPLETED |
| 500 files warm | 24.289812 | 22.250000 | 421.3 | 9.532866 | 10,964 | COMPLETED |
| 500 files one changed | 47.609289 | 46.046875 | 564.5 | 27.691743 | 11,073 | COMPLETED |

Generated fixtures have 100% declared source parser completion, with semantic maturity PARTIAL. They produced 200 / 1,000 / 5,000 findings respectively. Cold cache hit counts were zero; warm counts were all files; changed runs reparsed one file. Max measured publication flush size was 250. Warm/incremental can cost more than cold because publication/history/comparison and database growth remain; this benchmark does not claim that changed-file caching removes those global costs. These runs precede the final additive lookup index, whose large-cache benefit was separately measured against the incident tenant.

Authorized ZIP components: first 20 sorted entries under `common`, then first 50 under `openmetadata-service/src/main/java/org/openmetadata/service`. Common: 1.624568 / 0.225078 / 0.352265 s cold/warm/change; 14/15 declared source files parsed, one unsupported, overall PARTIAL. Java service component: **6.527055 / 3.940520 / 4.556359 s**, 50/50 parser completion, 60 findings, all stages completed. Its cold parent/helper CPU was **4.250000 / 1.265625 s**, sampled process-tree peak **145.4 MiB**. Warm/change briefly overlapped frontend test startup, so their wall times are not clean comparative throughput claims. Early common helper CPU measured only the Windows launcher and is omitted; the collector was corrected to include owned venv descendants before service/full-repository measurements.

Resource collection samples at 100 ms, includes owned helper descendants discovered during samples and obtains final process CPU from retained handles. Very short-lived undiscovered descendants and between-sample RSS peaks can be missed; parent lifetime peak RSS is also retained. SQL cursor time excludes fetching, JSON decoding and ORM processing. cProfile figures have profiler overhead and are separated from unprofiled runs.

## Validation and preservation

- Full backend suite after history/reference repair: **448 passed, 542.06 s**. This covers real pipelines, native quality/security/IaC, Claim Ledger/graph/impact/drift, review and finding history, quality gates, organization/repository scope, audit integrity, OIDC/GHES, queue fencing, cancellation, expiry/recovery, archives and import safety.
- After the final additive cache index: **51 passed, 84.14 s** across migrations, timeout recovery, analysis performance, repository storage and import reliability. This includes upgrade/base/upgrade and preservation rollback, the actual tenant-plus-ID query plan, cache invalidation on one changed file, partial partition/diagnostic retention and atomic output rollback.
- Frontend: **8 files / 32 tests passed, 75.40 s**; TypeScript/client/SSR build passed; 41 public routes prerendered. These checks include import/retry rejection and authenticated CSRF retry behavior. No browser-session end-to-end verification was performed.
- Ruff and `git diff --check` passed for the changed scope; existing Windows LF/CRLF advisory warnings are not failures.
- A 510-finding regression verifies exactly three identity batch SELECTs, every occurrence retained and flushes no larger than 250. Mixed-scope/reassigned tenants and prefetched foreign concepts are rejected. Existing finding-history regression verifies review carry-forward, contextual reopening and ancestor/branch behavior.
- Before/after 100-file profiled snapshots have identical selected finding semantics/fingerprints/coverage across all three modes and no duplicate fingerprints. This is stronger than count-only equivalence; it excludes generated IDs/timestamps.
- A consistent 2,762,104,832-byte database backup was preserved before recovery. Its initial copy restarted while the idle local poller wrote its queue cursor; draining the verified idle API allowed it to finish. This is an operational backup observation, not asserted as the analysis timeout cause.

After the final completed-partition boundary repair: **56 passed, 49.05 s** across timeout recovery, analysis performance, repository storage, fair scheduling, local jobs and queue tests. The new boundary regression retains all 20 completed file artifacts when the immediately following progress checkpoint raises; failure/cancellation/lease and atomic-output regressions still pass. These overlapping runs are not added into a fabricated distinct-test total. The final boundary change was reloaded into the idle runtime after this large replay; its small-fixture durability validation is separate from the replay's timings.

### Actual unchanged-repository retry

The matched **same live job** used its remaining ordinary retry, **retry_count 1 → 2**, through the fenced worker. Existing enabled submitter/repository grant checks, encrypted input, finite retry ceiling, original inventory and 900-second limit remained. The filesystem operator action is audited as `OPERATOR_RETRIED_RETAINED_ANALYSIS`; no account/session was impersonated. Other exhausted ZIP/private-SCM jobs were not requeued, reset or used as substitutes. The API/UI and idle Celery worker were reloaded with tested index/history changes before dispatch.

**Outcome: FAILED / CORRELATING / ANALYSIS_TIME_BUDGET, 900.56607 seconds.** Total measured operator/worker call wall time, including retry/cleanup, was **903.638362 seconds**. `snapshot_id=null`; publication state remains **UNPUBLISHED**. The timing includes the normal worker's input and permission checks, not only a direct analyzer call.

| Recovery stage | Actual wall seconds |
| --- | ---: |
| VALIDATING | 0.423503 |
| PARSING | 0.276845 |
| ANALYZING | **149.114441** |
| EXTRACTING_CLAIMS | 59.980697 |
| VERIFYING / aggregation | 39.309809 |
| BUILDING_EVIDENCE | **345.430262** |
| CORRELATING, incomplete | **306.023966** |

Native cache lookup/load was **76.243727 s**, reuse **36.390329 s**, partition parsing **51.956871 s**. This is 18,756 hits / 103 misses over all 199 partitions. It cannot be compared to the preceding 658.64-second native pass as a pure index speedup: the preceding attempt reparsed 9,785 files; this one reparsed 103. The independent identical-key query-plan experiment is the evidence for the index improvement.

The remaining dominant work was **263.502484 s of verified evidence-source reads** over 18,859 files; evidence redaction was **42.973939 s**, blob catalog/store handling **6.722599 s**, and the inclusive evidence-file loop **328.676456 s**. Previous retry source reads were 24.976418 s. This large I/O/decoding/verification variation is measured, but its exact filesystem, cache, memory or antivirus contribution is unproven. No security or integrity verification was skipped to conceal this cost.

Correlation components: finding correlation **99.520685 s**, history **12.026603 s**, artifact graph **62.203982 s**, configuration graph **12.272258 s**. FUNCTION_GRAPH had no completed timer; the subsequent function section occupied approximately 120 seconds before the checkpoint failure, inferred from remaining correlation time and code order. Ownership/policy/impact/final serialization/commit were not reached with completed timings. It would be false to claim finalization or a successful full graph was benchmarked.

Current slowest measured evidence operations: `openmetadata-airflow-apis/tests/integration/operations/run_automation.py` **1.971290 s**, UI `CredentialFileField.utils.ts` **1.647413 s**, `OntologyStructuralDiffServiceTest.java` **1.552559 s**. These are read/redact/store/row operations, not fresh parser timings. The slowest current fresh tree-sitter operation was `BaseEntityIT.java` **0.575673 s**, explicitly node-budget PARTIAL.

Resource measurements on the hardware above: parent CPU **645.625 s**, discovered helper CPU **9.593750 s**, sampled process-tree peak RSS **2,275,799,040 bytes (2.120 GiB)**; parent lifetime peak **2,275,528,704 bytes**. Parent plus discovered helper CPU represents about 0.725 CPU-core equivalents over measured wall time, not 72.5% of all 12 logical processors. There were **23 helper launches**; observed helper concurrency was **1**, configured maximum **2**. The uncached warning paths were separated across partitions, so this does not establish a scheduling defect. SQL cursor time **132.463776 s**, 51,508 statements, 10,674 flushes, largest flush **250 rows**. Statement counts include lifecycle, lease and repeated reference/catalog work, not just inserts; cursor time excludes decoding/ORM cost. One cooperative operation can exceed the precise deadline boundary; this run detected it 0.56607 s after 900.

The last committed stage appeared as BUILDING_EVIDENCE while global output was running because stage updates share the atomic output transaction. After failure, the durable performance/stage history correctly records CORRELATING. A last committed stage entry must not be mistaken for the current stack location or a completed stage.

Preservation checks after retry: **175/175 pre-existing snapshot raw-JSON hashes unchanged**, ordered inventory manifest unchanged, **299 parser diagnostic records retained** (103 new plus 196 previous), **zero SQLite foreign-key violations**, audit integrity **VERIFIED before and after**. No snapshot was committed for the failed job. The two earlier attempts remain in its history; retry_count is 2 and was not reset. The incomplete graph transaction rolled back. Accounts, grants, source inventory and provider settings were not edited by the repair; consistent backup is retained. These checks do not claim that every unrelated account/provider row was newly rehashed in this turn.

### Actual retained coverage

The summary was retained at **249.109 seconds**, before publication, with **7,900 native findings, 2,090 dependencies, 1,500 capped claims and 105 warnings**. These are completed static-analysis summary counts, not live published findings or a passing gate.

| Measure | Actual |
| --- | ---: |
| Inventory entries discovered | 21,636 |
| Text files retained | 21,269 |
| Files with native scan | 18,859 |
| Source denominator | 15,669 |
| Source parser-completed | 14,567 |
| Source parser completion | **92.967005%** |
| PARTIAL | 17,671 |
| PARSE_FAILED, including configurations | 33 |
| SKIPPED_SIZE_LIMIT | 32 |
| EXCLUDED_GENERATED | 1,058 |
| EXCLUDED_VENDOR | 95 |
| UNSUPPORTED | 1,083 |
| IGNORED_BY_POLICY | 1,475 |
| BINARY | 189 |

States sum to 21,636. Language inventory/parsed counts: Python **3,054 / 3,037**, Java **4,609 / 4,598**, JavaScript **112 / 112**, TypeScript **7,866 / 6,820**; CloudFormation **17 / 17**, Compose **29 / 26**, Dockerfile **26 / 16**, Kubernetes **41 / 39**. Unsupported inventory: SQL 342, shell 60, Make 3, unknown 678; other text/binary 4,799. Language totals include excluded files, unlike the source denominator. All supported semantic maturity remains PARTIAL. **92.97% describes parser completion, not full security coverage, runtime observation, successful publication or a passing quality gate.** Inventory/skipped-file records and scoped parser diagnostics remain available to the authorized owner.

Private sanitized receipts are retained under the local chat workspace: `actual-timeout-incident.json`, `cache-query-profile.json`, `cache-query-profile-after.json`, `current-cache-expectation.json`, `actual-timeout-recovery-retry.json`, and the `timeout-benchmarks` receipts/profile/semantic comparison. They contain IDs, paths, timings and generated coverage rather than customer source or credential values. They are not committed as customer data in this repository.

Final runtime: managed API/UI readiness confirmed on ports 8011/5181; the verified idle Celery solo worker was reloaded and confirmed ready after the boundary repair. Existing Redis/Beat, credentials and application data were retained. The failed job was not requeued again.

## Final recovery decision

**UNRESOLVED for full-repository completion under 900 seconds.** The cache query and history defects are fixed and validated; the completed-partition durability edge case is repaired and validated. They mitigate cost and preserve recoverable results, but the actual same-repository retry still failed. The scale acceptance gate therefore remains blocked. No final successful snapshot, full graph, 100,000-file scale or empty-cache full-repository performance target is claimed.

Next measured work should separate encrypted-object open/read/decrypt/hash costs on the intended storage, evaluate bounded I/O prefetch only against those measurements, and profile function/ownership/policy/serialization work on bounded representative slices before another isolated scale benchmark. Global staging/resume must retain publication and permission invariants; merely creating unlimited new retries or raising the timeout is not a recovery strategy. The exhausted live retry counter remains intact.

## Remaining limitations

Full cold 21,636-entry publication with an empty application cache has not passed a benchmark under 900 seconds. No 100,000-file capacity or production PostgreSQL/cloud SLA is claimed. Global comparison, graph work, large snapshot serialization and final database commit remain work proportional to the resulting repository; checks are cooperative and cannot preempt an individual OS/SQL call. Helpers have hard resource caps; the main aggregate process does not currently have a separate hard memory ceiling. Failed graph publication does not resume midway through that graph. History/performance metadata must not turn UNPUBLISHED summaries or parser completeness into full semantic/security assurance. Runtime evidence is UNOBSERVED and claims remain capped at 1,500.
