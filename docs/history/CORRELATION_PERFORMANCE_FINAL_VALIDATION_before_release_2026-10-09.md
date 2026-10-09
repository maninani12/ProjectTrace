# Correlation performance final validation

Final decision: **PASS for the measured unchanged OpenMetadata retained-inventory retry on awake local hardware.**
The correlation batching/storage bottleneck is corrected. This is a measured result for this repository,
cache and machine, not a general cold-cache or maximum-scale SLA. The published result remains **PARTIAL**
with its original coverage limitations and warnings; completion of the pipeline does not mean complete
semantic/security coverage. Interrupted standby runs below remain FAILED and are not counted as successful scans.

## Incident, environment and provenance

This continues `REPOSITORY_TIMEOUT_ROOT_CAUSE_AND_RECOVERY.md`; its historical failed results are retained.
Original job: `3e9e5140-5218-4277-ac6e-6616f7fbd9c3`; repository `metadata`,
`9fe836be-1317-4316-b733-1ec63d905f45`; tenant `0f1e9356-279a-4805-b44e-aacc3cd9005f`.
The relevant prior recovery failed CORRELATING at **900.56607 s**, not 900 seconds solely in correlation.
It entered correlation after about **594.5 s**, spent **306.023966 s** there, and published no snapshot.

The exact archive is `C:\Users\sai krishna\Downloads\OpenMetadata-main.zip`, SHA-256
`027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`.
Retained inventory `cbbe4102-c2f5-4e96-a3fc-eb8321c32472` has 21,636 entries, 21,269 text files,
330,420,155 expanded bytes; archive size 157,126,481 bytes. Ordered path/digest/metadata manifest:
`2f8f3478eacc93d4cfa2a1182dd21ab3e68c3ebce0d49c5d55bbb305d7ffaf40`.
All replays use this manifest, original analysis options and 900-second budget, without provider refetch,
source extraction or customer-code execution. Parser/rule signature remains
`6bb6bc805e8cc99f849bf0ffa9e26c39867a6e863c020497eb61fff40a6bb9cb`.

Measured installation: Windows 11 Home Single Language 10.0.26300; Intel Core 5 120U,
12 logical processors; 16,806,244,352 bytes RAM; Python 3.14.3.
Actual app: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`.
SQLite 3.50.4 / SQLAlchemy 2.1.3, WAL, immediate foreign keys, synchronous=2;
schema 0014; initial backup 2,762,104,832 bytes. Test runner: pytest 9.1.1.
Local API/UI 8011/5181, one local runner; independent Celery solo worker/Beat retained.
SQLite admission permits one active analysis writer across adapters. Helpers remain capped at two;
all complete full runs observed one active helper and 23 launches, not effective two-core saturation.
Desktop activity/OS caches were uncontrolled. Final fixture and full validation runs did not overlap
the backend test suite, frontend build or another full analyzer benchmark.

## Pipeline and resource measurements

| Stage / measured seconds | Failed original retry | Old scheduling control | Final isolated repeat | Installed fenced worker |
| --- | --- | --- | --- | --- |
| VALIDATING | 0.423503 | 0.030670 | 0.017191 | 0.248439 |
| PARSING | 0.276845 | 0.162639 | 0.069313 | 0.139193 |
| ANALYZING | 149.114441 | 77.016911 | 35.264649 | 64.693630 |
| EXTRACTING_CLAIMS | 59.980697 | 55.573308 | 2.309271 | 26.033497 |
| VERIFYING | 39.309809 | 37.972531 | 13.586512 | 14.675642 |
| BUILDING_EVIDENCE | 345.430262 | 274.656495 | 108.247835 | 114.133290 |
| CORRELATING | 306.023966 | 278.460510 | 154.403173 | 205.236252 |
| FINALIZING | Not reached | 0.002414 | 0.001925 | 0.002885 |

Stage wall timers include their nested components. Do not sum inclusive component/SQL/flush timers.
Final serialization and snapshot cleanup are included in CORRELATING. The legacy FINALIZING timer and
stored duration are recorded before the final transaction commit; they are not the full completion wall time.
The isolated final commit measured **16.601574 s** separately. Full call wall below includes commit/cleanup;
copying/migrating the disposable benchmark database and initial ZIP capture are outside that clock.
Historical source capture took 928.03566 s separately; no end-to-end import-under-720 claim is made.

| Run | Full call wall s | Stored duration s | Parent / helper CPU s | Sampled peak GiB | Published state |
| --- | --- | --- | --- | --- | --- |
| Original failed retry | 903.638362 | 900.56607 | 645.625 / 9.594 | 2.120 | FAILED |
| Old scheduling control | 741.813725 | 723.88490 | 478.578 / 8.000 | 4.580 | PARTIAL |
| Corrected run 1, before final boundary drain | 221.293625 | 200.00715 | 170.281 / 8.719 | 4.622 | PARTIAL |
| Corrected run 2, before final boundary drain | 516.076998 | 463.58724 | 314.688 / 8.219 | 4.620 | PARTIAL |
| Final isolated repeat | 330.507886 | 313.90364 | 205.172 / 7.797 | 4.354 | PARTIAL |
| Installed fenced worker | 481.234476 | 425.16637 | 277.984 / 8.984 | 4.618 | PARTIAL |

Corrected runs 1 and 2 predate the final quality-projection boundary drain. The final isolated repeat
and installed worker both use the final code and actually construct/publish the whole graph; neither
returns an existing snapshot. They meet both the existing 900-second budget and the 720-second headroom
target. The installed validation job is `5d4f69be-3deb-4b2b-9374-25981ff99ea2`; snapshot `96f07afc-c0c8-48a4-8741-abc1cc64774d`.

Nested static-analysis and publication timings (inclusive; not additional stage wall time):

| Inclusive component / seconds | Failed original retry | Final isolated repeat | Installed worker |
| --- | --- | --- | --- |
| CLAIM_EXTRACTION | 59.972353 | 2.306323 | 26.027167 |
| CLAIM_VERIFICATION | 0.367820 | 0.287154 | 0.472520 |
| QUALITY_AGGREGATION | 8.499703 | 3.615978 | 3.787120 |
| FINAL_IDENTITY | 25.473108 | 7.868077 | 7.926743 |
| EVIDENCE_SOURCE_READ | 263.502484 | 83.957066 | 68.677266 |
| EVIDENCE_REDACTION | 42.973939 | 14.073233 | 22.411706 |
| EVIDENCE_BLOB_STORE | 6.722599 | 1.923827 | 4.134427 |
| PUBLISH_CLAIMS | 8.135153 | 2.600368 | 4.068508 |
| PUBLISH_FINDINGS | 6.767500 | 1.401956 | 3.019395 |
| PUBLISH_DEPENDENCIES | 1.797654 | 0.325535 | 0.916551 |

## Proven cause and profiling controls

The verified avoidable correlation cost was fragmented ORM graph persistence. `graph_add` already
counted output rows to 250, but deadline/lease checkpoints also flushed on computation steps and elapsed
time. Function iteration, candidate finding iteration, add(), nodes and edges all advanced that counter;
it flushed partial batches before the explicit graph writer reached 250 rows. Thus a row bound existed,
but effective batches were much smaller. The full function graph creates **398,272 records**:
195,982 FUNCTION nodes and 202,290 edges. Their count and complete relationship semantics are unchanged.

With the repaired measurement collector but old flush scheduling and original 2 MiB page-cache target,
function graph work took **167.864509 s**, with **5,120 flushes**, about 78 rows/flush and maximum 167.
SQL cursor time was **107.367503 s**; inclusive flush wall was **133.073517 s**. This was the dominant
measured correlation sub-operation, rather than finding history or an inferred parser hang.
The scheduling control preserves new boundary drains and original checks; it isolates the two
production scheduling/page-cache changes rather than reverting unrelated historical repairs.

| Correlation sub-operation / seconds | Old scheduling control | Final isolated repeat | Installed fenced worker |
| --- | --- | --- | --- |
| FINDING_CORRELATION | 30.772287 | 43.671273 | 27.068306 |
| FINDING_HISTORY | 3.810125 | 1.501722 | 1.697051 |
| ARTIFACT_GRAPH | 28.762919 | 10.632598 | 11.739127 |
| CONFIGURATION_GRAPH | 2.639895 | 1.441295 | 5.460077 |
| FUNCTION_GRAPH | 167.864509 | 72.802688 | 103.517009 |
| OWNERSHIP_GRAPH | 24.324535 | 11.390459 | 14.593321 |
| POLICY_PROJECTION | 7.570259 | 4.943815 | 14.639500 |
| IMPACT_GRAPH | 2.774526 | 1.465655 | 5.824559 |

| Function-graph measurement | Old scheduling control | Final isolated repeat |
| --- | --- | --- |
| SQL statements | 8702 | 5176 |
| SQL cursor seconds | 107.367503 | 40.410105 |
| Nonempty flushes | 5120 | 1594 |
| Flush wall seconds | 133.073517 | 53.293743 |
| Largest flush rows | 167 | 250 |

With explicit batch scheduling the same 398,272 records require 1,594 function flushes, maximum 250.
Fence SELECT counts stay at 3,582 in the before/after isolated measurements: permissions/lease checks
were not removed to obtain throughput. Statement/flush reductions and full graph equality support the
batching cause independently of source-I/O variability. No speculative claims-index, N+1 bypass,
graph truncation, analyzer disablement or larger timeout was introduced.

SQLite's default approximately 2 MiB cache also churned while inserting immutable graph/index pages
into the 2.7 GB database. An identical 20,000-record ORM experiment in a disposable full database,
80 statements/250-row batches, measured 2 MiB cursor **1.876901 / 1.615842 s** versus 32 MiB
**0.724222 / 0.702296 s**; wall **3.349362 / 3.078006** versus **2.277699 / 2.195375 s**.
These alternating trials retain tenant/FK guards and roll back the same writes. A baseline replay may
have been active, so their absolute times are qualified; the same-work storage comparison supports
the adapter target. WAL, durability and safety settings are unchanged.

The first cProfile function run was intrusive: 279.55154 s function stage, 204.084133 s inclusive
flush time, and 70,200 observer `process_stats` calls with 159.576932 s cumulative profile time.
The observer repeatedly rebuilt Windows ctypes layouts and sampled exited helper handles. Its
timings overlap application work and cannot be subtracted or summed as disjoint costs. We corrected
that collector and performed the unprofiled old-scheduling control before drawing the conclusion.
The profile's 799.910905 s full call is diagnostic, not the performance baseline for a speedup ratio.

Evidence source reads were also expensive: 263.502484 s in the original failed retry, 199.823912 s
in the control, and 14.985856 / 138.175288 s in the first two corrected runs. A 500-file read-only
experiment found OS open/read latency dominated its first pass; later one-/two-reader passes changed
with warming. It does not prove a whole-repository parallel-reader speedup. Disk cache, desktop
memory pressure and antivirus/OneDrive contributions were not separately proven, so none is asserted
as the root cause. No unmeasured source-read parallelism was added. Isolated reads additionally check
a read-only overlay path before using original encrypted blobs; installed worker uses normal storage.

## Smallest safe code correction

1. `backend/analysis_budget.py`: allow `flush=False` while retaining every deadline/cancellation/fenced
   lease callback. The explicit graph writer schedules its own 250-row flushes in the same transaction.
2. `backend/domain.py`: use that option only for deferred graph additions and artifact/function work;
   drain pending projections at graph boundaries and before/after typed quality projections. Snapshot
   SQL parents/FKs retain their ordering. A fixture caught a pending QualityAnalysis beside 250 graph
   rows; the final drain and regression close that 251-row boundary case. Other publishers keep normal
   checkpoint flush behavior. No partial global graph commit or tenant-guard bypass is introduced.
3. `backend/db.py`: `PRAGMA cache_size=-32768` on SQLite connections only. This is a 32 MiB cache
   target per connection, not a hard process RSS limit; PostgreSQL is unchanged. Multiple pooled
   connections can consume multiple targets (5 pooled + 15 overflow could target about 480 MiB).
4. `scripts/benchmark_repository_analysis.py`: cache Windows measurement layouts/API handles;
   enumerate descendants only with active helpers; retain final CPU then close exited process handles.
   Sampling remains 100 ms. Short-lived undiscovered helpers/between-sample RSS peaks can be missed;
   parent CPU includes the collector, and parent lifetime peak is retained separately.
5. `tests/test_correlation_performance.py`: five regression cases for cache/durability, deferred
   deadline/rollback, complete bounded function graphs, collector cleanup, and typed-projection bounds.

Earlier cache lookup migration, finding-history batching, file-owner lookup/cache, immutable parser
artifacts and completed-partition retention are preserved. They are not counted as new fixes here.
The main result still holds a large graph/analysis in memory; adding global concurrency would increase
write/memory pressure. This fix preserves existing bounded helpers and one SQLite writer.

## Staged cold, warm and incremental validation

Inert Python fixtures contain source-text eval calls; imported functions are never invoked.
Each file has ten functions. Source capture is outside the analysis timer. Every row below completed
all pipeline stages, had 100% declared source parser completion and identical expected finding counts
(200/1,000/5,000); semantic maturity remains PARTIAL. A one-file source comment changes the parser key
and recomputes global/history output with an actual baseline. Warm runs use a different captured commit
to force publication, not an existing-snapshot shortcut. Cold means empty application cache; OS coldness
is not controlled. Incremental parser reuse does not eliminate global work and can cost more than cold.

| Files | Run | Wall s | Parent CPU s | Peak MiB | Parser hits / misses | Max flush rows |
| --- | --- | --- | --- | --- | --- | --- |
| 20 | cold | 0.659123 | 0.625 | 95.5 | 0 / 20 | 250 |
| 20 | warm | 0.286591 | 0.25 | 108.9 | 20 / 0 | 250 |
| 20 | one_file_change | 0.422369 | 0.390625 | 119.7 | 19 / 1 | 250 |
| 100 | cold | 1.599591 | 1.515625 | 131.1 | 0 / 100 | 250 |
| 100 | warm | 1.800917 | 1.671875 | 161.8 | 100 / 0 | 250 |
| 100 | one_file_change | 5.158874 | 4.9375 | 217.8 | 99 / 1 | 250 |
| 500 | cold | 17.524289 | 16.859375 | 390.2 | 0 / 500 | 250 |
| 500 | warm | 15.072298 | 14.390625 | 451.7 | 500 / 0 | 250 |
| 500 | one_file_change | 29.142724 | 28.265625 | 590.5 | 499 / 1 | 250 |

All full unchanged-input runs use the existing eligible application cache: 18,756 hits / 103 misses,
199 partitions. Warning/partial paths intentionally generate new scoped diagnostics. A cold empty-cache
full repository and a changed-file full repository were not benchmarked in this continuation; staged
incremental results must not be presented as whole-repository incremental throughput.

## Tests, correctness, preservation and security

- Full backend suite after initial batching/cache correction: **454 passed in 404.12 s**.
- Final boundary correction and fifth new test: **92 affected regressions passed in 79.09 s**,
  covering performance, timeout recovery, quality, graph/impact/pages/advisory graph, local jobs,
  queue fencing and fair scheduling. This is not represented as a second full-suite run or added
  into a fabricated distinct-test count. Existing scope/auth, Claim Ledger, reviews/exceptions,
  audit, OIDC/GHES, native security/IaC and failure tests passed in the full suite. One existing
  Starlette TestClient deprecation warning remains.
- Frontend **8 files / 32 tests passed in 59.04 s**; TypeScript, client/SSR build and 41 prerendered
  routes passed. No frontend functionality was replaced; browser session E2E was not performed.
- Ruff and whitespace diff checks pass for the changed scope (Windows LF/CRLF advisories are not errors).
- Deferred-checkpoint regression still raises its deadline/fence failure and rolls all unpublished
  graph rows back. Existing timeout/lease/cancel recovery tests preserve native cache/diagnostics and
  UNPUBLISHED summaries; no new crash-resumable global graph protocol is claimed.
- Full publication comparison **passed**: all complete scoped record multiset hashes, multiplicities,
  graph classes/relationships, coverage, finding/quality occurrence counts match the before control.
  It normalizes generated record/snapshot UUIDs and new observation times, plus 386 intentionally fresh
  AMBIGUOUS concept IDs and their dependent policy identities. It preserves observation/confidence/
  status/topology data. This is full semantic comparison, not counts alone. No duplicate finding keys.

| Published scoped records | Count |
| --- | --- |
| claim | 1500 |
| dependency | 2090 |
| edge | 289745 |
| evidence | 18859 |
| finding | 7904 |
| graph_node | 231229 |

Each complete run also has 7,904 finding occurrences and 6,843 quality occurrences. Native summary
has 7,900 findings; four claim-verification findings are preserved in publication. 1,500 claims and
2,090 dependencies are processed under the existing declared caps/options. Normal local advisory cache
is supplied in the control, final isolated run and installed worker. Its one lodash 4.17.20 entry does
not match this inventory's three lodash 4.18.1 dependencies, so earlier isolated runs lacking that
argument are equivalent for these findings; no analyzer is disabled.

Disposable replays preserve hashes and presence of all 70,321 pre-existing records in the backup,
foreign keys and verified audit chain. Live recovery preserves **70424 old records**,
**3587 old audit events**, every account/grant, original failed parent including
retry_count=2/history, and the full inventory manifest. Existing snapshots, findings, Ledger data,
graph relationships, reviews and exceptions were not deleted, reassigned or overwritten.
Audit integrity remains VERIFIED; foreign-key violations remain zero. Original diagnostic records
remain, with new attempt-local diagnostics appended under scope. Raw old-record/audit hashes are
checked independently of the semantic normalization. Tenant authorization tests retain scope rejection.
Old typed quality/finding projections, occurrence history, snapshot inventory links, audit links,
profiles, policies, OIDC mappings, cloud assets and complete account/tenant/repository rows also
retain their stored-row hashes and presence; per-table checks are in the installed receipt.

The one installed recovery is a new, bounded audited maintenance validation, not a reset of the
exhausted parent's retry count. It verifies the original enabled submitting account/repository grant,
reuses unchanged unexpired encrypted input, passes ordinary admission and executes the real fenced
worker. Operator actor is LOCAL_FILESYSTEM_OPERATOR with original submitter attribution. API and idle
Celery were reloaded with tested code; credentials, tenant assignments and production retry policy were
not changed. Only this requested local repository was admitted. No imported builds, installations,
infrastructure commands or customer source execution occurred.

## Coverage and honest incomplete states

Published coverage is unchanged: **18859 native-scanned files**;
**14567 / 15669 declared source files parsed
(92.967005%)**, 105 existing warnings. Runtime evidence is UNOBSERVED.
Parser completion is not a claim of complete security assurance. Unsupported languages, oversize files,
generated/vendor exclusions and parser failures remain visible rather than becoming successful coverage.
Largest skipped entry remains the 50,915,683-byte fr-cities.json, never fed to a parser.

| Inventory disposition | Files |
| --- | --- |
| BINARY | 189 |
| EXCLUDED_GENERATED | 1058 |
| EXCLUDED_VENDOR | 95 |
| IGNORED_BY_POLICY | 1475 |
| PARSE_FAILED | 33 |
| PARTIAL | 17671 |
| SKIPPED_SIZE_LIMIT | 32 |
| UNSUPPORTED | 1083 |

| Declared language / classification | Inventoried files | Parser-completed files | Maturity |
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

## Interrupted final-code trials and operational limits

| Final-code interrupted run | Actual wall s | Parent CPU s | Last stage | Outcome |
| --- | --- | --- | --- | --- |
| final-run3 | 6461.365378 | 66.09375 | ANALYZING | FAILED |
| final-run4 | 13116.003731 | 33.25 | EXTRACTING_CLAIMS | FAILED |

Windows System power events record entry/exit from Modern Standby (including lid reasons) during these
trials. The first had 66.09375 s parent CPU and a single CACHE_REUSE timer inflated to 6,383.214882 s;
the second completed native analysis in 39.512412 s and had 33.25 s parent CPU before its elapsed
deadline failure. These failures and their complete elapsed times are retained, not relabeled successful
or subtracted from wall time. They support a host-suspension explanation for these trials, not a new
parser defect or an explanation for the historical 900.57 correlation timeout.
Final validation uses a temporary process-thread Windows SYSTEM_REQUIRED idle-sleep request, released
on exit; global power policy and explicit lid behavior are unchanged. Deadlines still expire across
standby and fence out the old worker on resume. Awake hardware is a condition of the measured target.

Remaining limits: full successful publication uses approximately 4.6 GiB in earlier samples (see current
measurements above), versus 2.1 GiB in the incomplete failed baseline; those are not equal completion
points. There is no newly enforced main-process RSS cap. 16 GB/one writer is measured, not multiworker
capacity, 100,000-file support, PostgreSQL throughput or an empty-cache full-repository SLA. Global
analysis/graph output recomputes atomically after failure; only native artifacts/file diagnostics resume.
Database commit and individual cooperative operations are not forcibly preempted at 900 seconds;
the reported full wall must be checked, not only legacy duration. Further safe architectural options
are scoped durable graph staging plus atomic publication pointer, compact graph/result storage and
streamed serialization, after separate provenance/rollback/resource benchmarks. They are unnecessary
for this measured warm-cache correction and are not silently introduced here.

## Reproduction receipts and decision

Private local receipts under `C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\ingestion`:
`actual-timeout-recovery-retry.json`, `correlation-baseline-profile/receipt.json` and function .pstats,
`correlation-original-scheduling-control/receipt.json`, corrected runs 1/2, final runs 3/4/5,
`correlation-storage-profile/receipt.json`, `correlation-source-read-profile.json`,
`correlation-live-recovery.json`, `correlation-publication-comparison-final.json`.
Staged final receipts are in sibling `work/correlation-fixtures-final/{20,100,500}/receipt.json`.
The archive/provenance hashes above identify exact input; receipts contain diagnostics/counts/timings,
not credentials. Disposable benchmark DBs and the original backup remain recoverable.

Reproduce isolated whole-inventory validation with trusted private `correlation_replay.py --name <fresh-name>`
under the verified installed runtime and a fresh backup copy; benchmark never resets the live incident.
For staged inert fixtures use `.venv\Scripts\python.exe scripts/benchmark_repository_analysis.py
--output <new-empty-directory> --files 20` (then 100/500). Do not rerun the single live maintenance helper
as an unlimited retry mechanism; it deliberately rejects a reused natural key/receipt.

**Final decision: PASS.** The measured final unchanged repository repeat and installed fenced-worker
publication are below 720 seconds, preserve complete declared analysis scope, and match full published
semantics under the existing 900-second budget. The specific warm-cache correlation timeout blocker is
fixed on the stated awake hardware. Standby safety failures and unmeasured cold/full-scale/resource
guarantees remain explicitly outside that result; the snapshot continues to expose honest PARTIAL coverage.
