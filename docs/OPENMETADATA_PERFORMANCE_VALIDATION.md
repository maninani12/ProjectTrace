# OpenMetadata performance investigation — 2026-10-08

The unchanged ZIP was retried through the same retained local job and inventory twice. The repository analysis limit remains **900 seconds**. The live job exhausted its normal retries, so subsequent correlation repairs are validated in an isolated database with the same repository, retained inventory and parser cache. No live retry count was reset or exceeded. This report continues the ZIP performance observation in [Import reliability validation](IMPORT_RELIABILITY_VALIDATION.md); it does not assert that the private GitHub path has completed.

## Evidence behind the original timeout

Original ZIP job: `e3986c27-737f-447b-a2d4-197beedffaa5`; repository `8ab5f0b7-7c0d-43c6-98cc-cbd64df2ef3e`; complete retained inventory `821307d0-f546-4ef6-bca8-e2789855742a`. The previous attempt failed at **901.44 seconds** during ANALYZING, before evidence publication. It reached approximately 160 native partition checkpoints. The slowest recorded partition interval was **14.32445 seconds**; the next were 12.38849 and 11.60934 seconds. Those old checkpoints did not retain file-level timers, so their exact slowest file cannot be reconstructed honestly.

The repository contains **21,636 inventory files**, with **18,859 native candidates** in 199 planned bounded partitions. Original intake counts: 21,269 TEXT, 189 BINARY, 108 RAW_BYTES, 38 UNSUPPORTED links and 32 SKIPPED_SIZE_LIMIT entries. Capture was complete; archive limits did not cause the analysis timeout.

Controlled profiles selected the three largest eligible Python, Java, TSX and YAML files from the unchanged archive. Only owned ProjectTrace parsers ran, with 512 MiB / 25 CPU-second resource ceilings and a 30-second supervisor timeout. Source stayed inert in memory. These twelve profiles are a selected sample, not a global cold-repository ranking. cProfile adds overhead; times are observations on this PC.

| Selected file | Before / after seconds | Measured bottleneck or outcome |
| --- | --- | --- |
| `ingestion/tests/unit/lineage/queries/test_complex_query_patterns.py` | **3.901 / 1.790** | Structural identity annotation **2.9141 → 0.5594 s**; 39 findings and zero warnings both times |
| `ingestion/tests/unit/test_dbt.py` | 2.346 / 2.243 | Python analysis/metrics/structure and identity; 7 findings, zero warnings |
| `.github/scripts/tests/test_playwright_ci_planning.py` | 1.602 / 1.524 | Python analysis/identity/flow; 8 findings, zero warnings |
| `openmetadata-integration-tests/.../WorkflowDefinitionResourceIT.java` | 0.188 / 0.189 | Exceeds 40,000-node syntax budget; explicit partial diagnostic, no fabricated parsed coverage |
| `openmetadata-integration-tests/.../TableResourceIT.java` | 0.124 / 0.160 | Same node-budget outcome |
| `openmetadata-integration-tests/.../DataContractResourceIT.java` | 0.144 / 0.161 | Same node-budget outcome |
| `openmetadata-ui/.../components/common/Table/TableV2.tsx` | 0.365 / 0.351 | Tree-sitter traversal/tokenization; 5 findings, zero warnings |
| `openmetadata-ui/.../ColumnGrid.component.tsx` | 0.458 / 0.489 | Tree-sitter traversal; 5 findings, zero warnings |
| `openmetadata-ui/.../utils/CSV/CSVUtilsClassBase.tsx` | 0.429 / 0.563 | Tree-sitter traversal; 5 findings, zero warnings |
| `conf/openmetadata.yaml` | 0.156 / 0.194 | Bounded YAML scan/construction |
| `conf/openmetadata-h2-test.yaml` | 0.140 / 0.167 | Bounded YAML scan/construction |
| `docker/development/distributed-test/local/server3.yaml` | 0.103 / 0.125 | Bounded YAML scan/construction |

All sample finding/warning counts matched before/after. Short sample timings vary; only the Python identity improvement is a clear measured reduction. Node-budget failures are coverage gaps, not slow successfully parsed files.

## Implemented changes

- File structural hashes are computed once per Python file, and owner-context hashes once per owner. The previous per-finding whole-file AST dumping was unnecessary repeated work. Metric identity lookup now uses an indexed key while preserving first-match behavior. Tree-sitter token traversals memoize identical node spans within a file.
- Quality observation lookup now sorts the metrics for each file once, preserving the narrowest enclosing symbol and stable tie order. Previously each observation sorted the entire repository's metric list. A controlled 200-file / 10,000-metric / 1,000-observation benchmark changed **0.850753 → 0.073780 seconds** with exact complete output equality excluding timing fields. This is a synthetic lookup benchmark, not the whole-repository runtime.
- A verified plaintext source cache is scoped to one partition, capped at **2,000,000 UTF-8 bytes**. Scope/path checks precede cache access. A new partition decrypts and verifies again; the cache does not replace stored immutable digests or integrity validation.
- At most **two** independent owned syntax/IaC helpers run concurrently. Database/source orchestration remains on the caller thread. Existing helper time, memory, CPU, file, byte and result caps remain. Deterministic helper-output equality is regression-tested.
- Parser cache writes are batched within the existing bounded transaction. Existing artifacts remain immutable and tenant/content/path/parser/rule/profile scoped. Completed artifacts from the failed attempt are reused; changed files and failed/partial parsers are re-evaluated. Global verification, quality and correlations are recomputed.
- Repository-wide duplication tokens use a lossless compact in-memory sequence instead of millions of token dictionaries. Durable cache JSON and existing snapshots stay unchanged; full duplication output equality is tested.
- Helpers emit bounded completed-file packets. A later timeout/CPU/output failure retains completed packets and diagnoses every unfinished file. Unknown paths, duplicates, malformed packets and excessive output are rejected. A resource failure cannot become a fake successful parse.
- Safe timings are retained on the job at partition/stage checkpoints and on failure: stage wall times, parser/helper/cache totals and 40 slowest measured file operations. Component/helper timers may overlap; they are not added together as elapsed runtime. Current-attempt cache reuse time is distinguished from historical parse time, which old artifacts did not retain.
- File parser diagnostics are durable scoped `parser_diagnostic` records linked to the job/inventory. They are explicitly FILE_LOCAL_DIAGNOSTIC_ONLY and do not publish incomplete findings/evidence as a completed snapshot. Existing skipped/binary/unsupported inventory rows remain unchanged.
- Publication batches explicit-UUID evidence/graph rows within the same atomic transaction, capped at **250 records** per flush. Snapshots still flush before dependent SQL foreign keys. Ownership decisions are reused per file. The deadline and fenced lease are checked every 250 publication/computation steps or at the next iteration after one wall second. Non-insert correlation, history, quality projection and documentation loops now participate. Checks suppress implicit ORM autoflush; pending updates flush as bounded batches after checking. These are cooperative checks between bounded operations, not a claim that a slow operating-system or SQL call is preempted exactly at 900 seconds. No checkpoint commits an unfinished graph; failure clears callbacks before audit and rolls back pending output.
- Correlation reuses whole-file redacted lines for one consecutive file only, preserving redaction and line/signature behavior. Function-to-quality edges now inspect only that function's file, preserving finding order and enclosing-range checks instead of scanning every repository finding per function. CODEOWNERS rules (at most 5,000 lines) compile once per immutable inventory/attempt; last matching supported glob and fallback behavior are unchanged. Additional timings separate finding history, artifact/configuration/function/ownership graphs, policy projection and impact.
- Correlation groups signature work by file while updating the original ordered findings list in place. Strong references to this attempt's created finding rows avoid repeated SELECT/autoflush work after weak ORM references are released; the tenant/FK guards still run. Claim and comparison lookups use ID indexes. Reconciliation indexes fingerprint candidates without changing ambiguous-match, used-ID, rename or branch-ancestry rules.
- Completed global analysis now stores a durable, scoped **UNPUBLISHED** coverage/count summary before evidence publication. It survives a subsequent rollback and retains its original inventory ID. Only a successfully committed snapshot marks it PUBLISHED. Retry history preserves the previous summary and performance. The full original inventory/skipped rows and file-local diagnostic records remain the detailed diagnostic source. Evidence timings additionally distinguish verified source reads, redaction and blob storage, with bounded slow-file metadata.

## Retry and preservation

The local filesystem operator command `scripts/retry_retained_analysis.py --job-id <existing job>` requeues only a retained LOCAL/INVENTORY job, checks its original enabled submitting account, tenant and repository grant, enforces the two-retry limit, retains attempt history and uses the same encrypted complete inventory. It does not impersonate a login, create a provider commit, fetch source again or reset retry counts. The ordinary worker still checks scope and its fenced lease. The audit actor is `LOCAL_FILESYSTEM_OPERATOR`; production/private/provider jobs are outside the command's scope.

Before retry, **175 existing snapshot payloads** were fingerprinted for preservation. After the first instrumented retry, all **175 matched their original raw-JSON SHA-256**, the retained inventory metadata matched, and the original encryption key matched. The old failure/stages/duration remain in this job's attempt history. Both retries use inventory `821307d0-f546-4ef6-bca8-e2789855742a`, so they benefit from prior completed cache entries; these are **incremental warm retries**, not a claim about a fresh cold import in another tenant.

Archive: `C:\Users\sai krishna\Downloads\OpenMetadata-main.zip`; compressed bytes **157,126,481**; SHA-256 **027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914**. No source repacking, editing, execution, installation, build or untrusted hook occurred.

## Verification

The final affected regression group passed **129 tests in 1,011.91 seconds**, including **19 performance/resource/protocol/preservation tests**, source-store, real pipeline, identity, quality, graph impact, advisory graph, API authorization, fair scheduling, local jobs and queue tests. Earlier focused groups passed 117 tests in 115.66 seconds and 94 in 175.68 seconds before the final deadline/summary changes. Suite runtime includes repeated API/demo fixture initialization; it is separate from the repository-analysis runtime. No product limit or authorization check was weakened. Targeted Ruff checks passed. Existing frontend code was unchanged in this performance repair.

Tests verify bounded source caching with fresh integrity checks, one whole-file identity dump, two-helper concurrency, unchanged helper/duplication results, changed-file cache invalidation, completed partition retention after timeout, persistent diagnostics, enabled-member/grant checks, finite operator retry, completed-packet retention, packet corruption/scope rejection, bounded timing output, per-file quality sort/identity equivalence, publication deadline rollback, and bounded writes preserving all 600 fixture rows. Added regressions cover a correlation computation loop with no record inserts, coverage surviving publication rollback, and at least 320 fixture findings correlated without individual finding SELECTs or update batches exceeding 250. Full production load and a complete cold OpenMetadata import with this repair were not measured.

## First instrumented retry

Retry 1 finished **FAILED** at **1,148.12513 seconds**. Native parsing/dependency inventory completed in **285.484533 seconds**, claim extraction in **70.466713 seconds**, and VERIFYING in **212.616390 seconds**. Inside VERIFYING, claim verification itself took **1.493646 seconds**, quality aggregation **154.284637 seconds**, and final finding identity **43.862712 seconds**. Remaining VERIFYING time includes assembly/coverage. The job reused **16,028** file artifacts, reparsed **2,831**, and retained **103** file diagnostics. All 18,859 native candidates reached the aggregate phase.

BUILDING_EVIDENCE consumed approximately **578.75 seconds** before the next stage tried to check the deadline. The old stage-only check therefore reported the 900-second violation late; the configured limit was not increased. No incomplete snapshot was committed. This measurement motivated the per-file quality index, bounded publication batches, and intra-publication checks before retry 2. Completed new cache entries and the 103 diagnostic records from retry 1 remain available.

## Second live retry and remaining bottleneck

Retry 2 finished **FAILED** at **900.22029 seconds** with `ANALYSIS_TIME_BUDGET`. The new intra-publication check caught the deadline during CORRELATING. Its stage measurements were ANALYZING **283.196746 s**, EXTRACTING_CLAIMS **11.595074 s**, VERIFYING **59.868088 s**, BUILDING_EVIDENCE **185.884134 s** and CORRELATING **357.869380 s**. Claim verification itself was **1.545633 s**, quality aggregation **8.399756 s**, and final identity **38.759193 s**. Other timing differences include source/file cache and machine variation; these are incremental warm runs, not equal cold-load experiments.

Publication components: evidence files **169.001401 s**, claims **13.053262 s**, findings **3.032786 s**, dependencies **0.629655 s**. Cache lookup/loading was **169.738165 s**; reuse **62.810859 s**. Native parsing partitions read **112** source blobs, with **103** partition source-cache hits. These source counters exclude global phases/publication. Parser artifacts reused **18,756** paths; **103** partial/warned paths were reparsed. All **18,859** candidates completed their native pass. Current Java tree-sitter timing max was **0.445097 s** on `BaseEntityIT.java`, an explicit node-budget PARTIAL, not a slow successful parse. The slowest successful current-attempt parser was measured on retry 1 (`TableUtils.test.tsx`, **1.114541 s**); cached paths have no fresh parser execution time in retry 2.

The original job still has retry_count **2**. It retains both prior attempts, all completed cache entries and **206 file-local diagnostic records for 103 distinct paths**. First diagnostic codes across the two attempts: ValueError 166, SYNTAX_NODE_BUDGET 20, SOURCE_SYNTAX_FAILED 16, JSONDecodeError 2, ScannerError 2. All **175** earlier snapshot payloads still match their original raw-JSON hashes. Original 75 users, 75 organizations, 67 repositories, 67 grants and 3 provider rows match; prior job IDs, inventory metadata, archive SHA-256 and encryption key are preserved. No snapshot for this live ZIP job was committed.

The first isolated replay used a consistent database backup and a separate copy of the same tenant's encrypted source objects. Setup took **144.171958 seconds**, outside the replay analysis timer. It failed in BUILDING_EVIDENCE after **901.97737 seconds**. Its ANALYZING stage took 331.031528 s, extraction 85.971861 s, verification/aggregation 73.475878 s and evidence publication 410.667632 s before the deadline. No snapshot was committed.

An isolated retry read the original verified encrypted objects **read-only**, directing any new/redacted blob writes into a separate overlay. It failed at **1,113.06724 seconds** in CORRELATING. ANALYZING was 248.695809 s, extraction 63.574770 s, VERIFYING 12.892995 s, evidence publication 557.959795 s and correlation 229.828862 s. Components exposed evidence file work at **515.723618 s** and finding correlation at **220.231334 s**; quality aggregation was 2.762074 s and final identity 6.988367 s. The correlation loop did no record additions for 220 seconds, revealing the remaining deadline gap. This is why the final repair checks computation as well as record insertion. Source I/O/cache/machine variation is evident across runs; these timings do not establish a specific filesystem or antivirus cause.

The final validation uses the same isolated job's remaining normal retry (retry_count 2), the same read-only source plus isolated overlay, and the unchanged repository/inventory/profile/parser cache. Original enabled membership/grant checks and the 900-second budget remain. It does not re-fetch source, reset retries or requeue the exhausted live job. Output is a validation artifact, not a live application snapshot. The managed API/UI and verified idle Celery worker are reloaded with the tested code, retaining credentials, Redis, Beat, accounts and provider state.

## Final retry runtime and coverage

**The final unchanged-inventory validation still FAILED at 900.21170 seconds**, with `ANALYSIS_TIME_BUDGET` during CORRELATING. Total call wall time, including setup/cleanup around the analysis timer, was **903.52841 seconds**. The 900-second limit was enforced by a computation checkpoint. The original live job remains FAILED at **900.22029 seconds**, retry_count **2**, with its raw job data unchanged by this isolated replay. No snapshot was committed in either case. The scale acceptance gate remains blocked; this repair is not a successful full-repository publication claim.

| Final replay stage | Wall seconds |
| --- | ---: |
| ANALYZING | **291.332688** |
| EXTRACTING_CLAIMS | 69.489933 |
| VERIFYING / aggregation | 51.394377 |
| BUILDING_EVIDENCE | **220.259971** |
| CORRELATING, incomplete | **267.493256** |

The slowest completed component measurements were cache lookup/loading **178.580215 s**, evidence files **213.243367 s**, finding correlation **76.329655 s**, artifact graph **74.763889 s**, and finding history **45.467153 s**. Evidence work separates **97.369211 s** of verified source reads, **81.188986 s** of redaction and **13.377157 s** of blob storage/reference handling. No individual evidence file exceeded **0.330007 s**; repeated work across 18,859 files drives the total. Configuration graph completed in **7.758463 s**; the subsequent function graph section did not complete before the deadline. Ownership, policy projection, impact and final snapshot serialization have no completed timings in this run. Component timers can overlap and must not be added as a whole-run total.

Finding correlation was observed at **76.33 s**, versus **220.23 s** in the preceding isolated retry, after grouping file reads, retaining created ORM rows, and indexing lookups. Finding history remains material; cache loading, redaction/source reads and graph publication still exceed the available total budget. These runs include cache and machine variation and do not establish a cold-run speed guarantee.

Current-attempt slow file operations, distinct from selected cold-parser profiles above:

| File, relative to `OpenMetadata-main/` | Operation | Seconds | Outcome |
| --- | --- | ---: | --- |
| `.github/actions/cache-ui-dist/action.yml` | Native postprocessing | **0.716417** | Measured; not a parser timer |
| `.github/workflows/git-create-release-branch.yml` | Native postprocessing | 0.671516 | Measured |
| `ingestion/Dockerfile` | Native postprocessing | 0.670993 | Measured |
| `openmetadata-ui/.../InboxPage/taskResolve.utils.test.ts` | Cache reuse | 0.580488 | Reused; historical parser time unavailable |
| `openmetadata-integration-tests/.../BaseEntityIT.java` | Java tree-sitter | **0.508024** | Node-budget PARTIAL |
| `openmetadata-integration-tests/.../TestCaseResourceIT.java` | Java tree-sitter | 0.473667 | Node-budget PARTIAL |
| `openmetadata-integration-tests/.../WorkflowDefinitionResourceIT.java` | Evidence read/redact/store/row | **0.330007** | Measured publication work |

All 199 native partitions reached aggregation: **18,756** artifact hits and **103** misses/diagnostic paths. Fresh Java/TypeScript tree-sitter work totalled **3.059940 s** for 18 failed/partial parser executions; its 14 syntax-helper calls, including supervision/startup/wait, totalled **12.627849 s**. Nine IaC-helper calls totalled **4.970401 s**. Successful cached files were not freshly parsed, so those timers cannot rank every parser across the whole original cold repository. The selected Python profile remains the measured evidence for the original AST identity bottleneck.

The completed static analysis summary was durably captured at **412.455323 seconds**, before publication. It remains explicitly **UNPUBLISHED**, with **7,900 native findings**, **2,090 dependencies**, **1,500 capped claims**, and **105 warnings**. Those are analysis counts, not live published finding records or a passing gate. Completed immutable file artifacts, parser diagnostics and original inventory rows remain available.

| Retained coverage measure | Actual |
| --- | ---: |
| Inventory files discovered | **21,636** |
| Retained text files | 21,269 |
| Files with native static scan | **18,859** |
| Source files in the coverage denominator | **15,669** |
| Source files whose parser completed | **14,567** |
| Source parser completion | **92.967005%** |
| PARSE_FAILED, including configuration parsers | **33** |
| SKIPPED_SIZE_LIMIT | **32** |
| EXCLUDED_GENERATED | 1,058 |
| EXCLUDED_VENDOR | 95 |
| UNSUPPORTED | 1,083 |
| IGNORED_BY_POLICY | 1,475 |
| BINARY | 189 |
| PARTIAL | 17,671 |

The state counts sum to the 21,636-entry inventory. Parser-completed source counts by language: Python **3,037 / 3,054 inventoried**, Java **4,598 / 4,609**, JavaScript **112 / 112**, TypeScript **6,820 / 7,866**. Language inventory totals include exclusions; they are not the same denominator as eligible parser work. All supported language semantic maturity remains PARTIAL. **92.97% is parser completion for the declared source denominator, not full semantic/security coverage or snapshot publication.** Claims remain capped at 1,500. Runtime evidence remains UNOBSERVED; customer code was not executed.

Final private receipts are retained in the local chat workspace: `isolated-final-receipt.json` (validation runtime, components, coverage and unchanged live job), `performance-final-receipt.json` (live failure and preservation), selected before/after parser profiles and the quality lookup benchmark. The database/source overlay stays separate from live data. The latest managed API/UI and idle worker were reloaded with the tested code; service readiness and preservation are checked separately from this failed large-repository run.
