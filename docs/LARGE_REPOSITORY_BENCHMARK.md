# Large repository measurements

These measurements use owned inert generated source through tenant-encrypted capture and the actual persisted native pipeline. They do not execute fixture source, install customer dependencies or invoke project hooks. Reports record implementation hashes, parser signature, platform and resource ceilings. A RUNNING/FAILED report is never a successful measurement.

| Fixture | Report state | Phase | Files / physical LOC | Inventory active seconds | Pipeline active seconds | Total active seconds | Actual wall seconds | Suspend seconds | Process peak MiB | Cache hits / misses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Final-code 500-file smoke | MEASURED_SYNTHETIC_LOCAL | INITIAL | 500 / 5,000 | 2.274 | 15.628 | 17.902 | 17.903 | 0.0 | 102.6 | 0 / 500 |
| Final-code 500-file smoke | MEASURED_SYNTHETIC_LOCAL | EIGHT_FILE_HEAD | 500 / 5,000 | 1.431 | 2.978 | 4.409 | 4.409 | 0.0 | 108.0 | 492 / 8 |
| 10k Python / 100k LOC | MEASURED_SYNTHETIC_LOCAL | INITIAL | 10,000 / 100,000 | 88.287 | 333.887 | 422.174 | 994.619 | 572.444 | 233.1 | 0 / 10,000 |
| 10k Python / 100k LOC | MEASURED_SYNTHETIC_LOCAL | EIGHT_FILE_HEAD | 10,000 / 100,000 | 8.309 | 28.463 | 36.772 | 36.772 | 0.0 | 359.6 | 9,992 / 8 |
| 50k Python / 500k LOC | MEASURED_SYNTHETIC_LOCAL | INITIAL_RECOVERY_CACHE_WARM | 50,000 / 500,000 | 0.0 | 1661.249 | 1661.249 | 1661.249 | 0.0 | 1525.1 | 50,000 / 0 |
| 50k Python / 500k LOC | MEASURED_SYNTHETIC_LOCAL | EIGHT_FILE_HEAD_RECOVERY_CAPTURED | 50,000 / 500,000 | 0.0 | 848.584 | 848.584 | 848.585 | 0.0 | 1321.0 | 49,992 / 8 |
| 10k Python / 3M LOC | MEASURED_SYNTHETIC_LOCAL | INITIAL | 10,000 / 3,000,000 | 95.025 | 1159.386 | 1254.411 | 1254.411 | 0.0 | 647.9 | 0 / 10,000 |
| 10k Python / 3M LOC | MEASURED_SYNTHETIC_LOCAL | EIGHT_FILE_HEAD | 10,000 / 3,000,000 | 58.065 | 177.382 | 235.447 | 235.447 | 0.0 | 703.1 | 9,992 / 8 |
| 10k mixed-language files | MEASURED_SYNTHETIC_LOCAL | INITIAL | 10,000 / 99,991 | 217.414 | 810.859 | 1028.273 | 1858.894 | 830.62 | 397.0 | 0 / 10,000 |
| 10k mixed-language files | MEASURED_SYNTHETIC_LOCAL | EIGHT_FILE_HEAD | 10,000 / 99,991 | 96.52 | 134.851 | 231.372 | 231.372 | 0.0 | 452.2 | 9,992 / 8 |

Raw reports: [final-code-500-file-smoke.json](../benchmarks/final-code-500-file-smoke.json), [large-repository-10000-current.json](../benchmarks/large-repository-10000-current.json), [large-repository-50000-current.json](../benchmarks/large-repository-50000-current.json), [large-repository-3mloc-current.json](../benchmarks/large-repository-3mloc-current.json), [large-repository-mixed-10000.json](../benchmarks/large-repository-mixed-10000.json).

A successful initial phase persists a complete snapshot. INITIAL_RECOVERY_CACHE_WARM reuses an interrupted owned inventory; its near-zero intake value measures reference reuse, not archive capture throughput. HEAD changes exactly eight source files against the explicit initial BASE. Cache reuse avoids unchanged source decryption during parsing; source intake/hash validation, global correlation, duplicate/documentation checks, graph and snapshot persistence still cost time. All Python/JS/TS/Java semantics remain PARTIAL. A PASS gate applies to its configured scope and is not proof of complete semantics or a clean repository.

Resource environment: Windows 11 / Python 3.14.3 / local SQLite / one synchronous worker per run on a shared 16 GB desktop. Several owned runs and browser checks overlapped; timings are not isolated machine capacity. The helper guard bounds the owned benchmark process to 1.5 GiB committed memory and 7,200 user CPU seconds. Peak working set is measured for the parent process lifetime, not summed child RSS or total machine allocation. Helper CPU and queue delay are explicitly UNMEASURED here.

Timing: fresh benchmark scripts use active system time that excludes Windows suspend for the internal 3,600-second execution budget. Production execution still uses wall time. Reports preserve actual wall time, active time, suspend estimate and parent CPU separately; no suspend duration is advertised as analyzer throughput. Earlier 50k/3M wall-budget failures are retained as `large-repository-50000-suspended-failure.json` and `large-repository-3mloc-suspended-failure.json`. These failed attempts are not passes. The historical first 10k recovery report remains available; use the fresh `-current` report for current memory results.

Budget consequence: the three-million-line initial pipeline measured more than the default 900-second large-job budget on this host. Larger deployments must explicitly size `REPOSITORY_ANALYSIS_SECONDS` (120–3,600), worker resources and queue limits and validate real workloads; quota admission alone does not establish completion under default settings. Automatic partition checkpoint recovery after a worker crash is not equivalent to skipping all global recomputation: persisted parser artifacts can be reused, while uncommitted output is rolled back and the retained job retries.

Declared boundaries: the mixed fixture includes an inert `.projecttrace/components.json` declaring Python, JS, TS, TSX and Java component roots. Its actual physical LOC is measured from captured files, including the one-line configuration; requested arithmetic is not substituted for measured LOC. Partitions stop at component boundaries and retain the 100-file / 2 MB ceiling.

## Code-version boundaries

Each report preserves its implementation hashes. The 10k/3M/mixed measurements predate graph batching. The cold 50k attempt stopped before snapshot commit; its interrupted report is retained. Two warm attempts failed during final update/late job-link commit; both failure reports are retained. A later run committed its initial snapshot, then HEAD failed at the initial metadata INSERT; large-repository-50000-initial-success-head-memory-failure.json retains the full outcome. The current report imports that successful initial phase unchanged with its historical hashes. Its recovered HEAD uses current code hashes and the failed attempt’s fully path/hash-validated encrypted capture. Only the eight owned changed-file artifacts are evicted, explicitly reported, to measure 49,992 unchanged hits/eight misses. Near-zero recovery intake measures reference reuse; the historical failed-attempt HEAD capture time is recorded separately. Previous jobs and snapshots remain stored. Cold 50k completion throughput is UNMEASURED. Final code defers full snapshot serialization until working-set release and reads only required BASE/ancestor/quality fields; historical stored payloads remain unchanged. Capture uses explicit 100-row flushes while blob lookups avoid per-file implicit flushes, preserving tenant/FK/integrity checks. The parser signature remains unchanged because valid observations are unchanged. A separate current 500-file initial/HEAD smoke is not extrapolated to 50k. Final API samples use unchanged current read APIs against retained owned fixture databases.

Stage timing fields in the older 10k report include wall-clock suspension; its separate pipeline_active_seconds field is the active measurement. Later active-clock runs label stage clock explicitly. Source-store Windows file-open cost and shared-host contention affect these numbers.

Owned reproduction: `python -m scripts.benchmark_repository_scale --files 50000 --lines 10 --work-dir <fresh-private-directory> --output <report.json>`. Use `--fixture mixed` for the five-language fixture, or `--files 10000 --lines 300` for three million physical lines. Recovery modes accept only script-owned fixture identities and content hashes: `--resume-captured` requires one inventory, one to ten terminal failed/interrupted owned jobs and no non-job output; `--resume-initial` requires a completed initial snapshot. Preserve the earlier report separately. Recovered observations and missing original measurements remain explicitly labeled. Captured HEAD recovery uses `--resume-head-captured --initial-report <preserved-owned-report.json>` and requires exactly one committed BASE, two fully hash-validated owned inventories and retained terminal jobs with no extra output. Its eight changed-artifact evictions and historical code boundaries are reported. Never point these helpers at a customer database.

## API measurements

Ten scoped TestClient samples per endpoint include authorization and JSON serialization, but exclude network/TLS transport. Scoped expression indexes are installed. Quantiles use the lower observed order statistic at floor((n - 1) * p), as implemented by the helper; with ten samples the reported p95 selects the ninth sorted observation. Endpoint response sizes are measured; the roughly 4.7 MB legacy workspace metadata payload is a remaining optimization target, even though source caches are omitted. Small samples on a contended desktop are not production p95 guarantees.

| Dataset / endpoint | p50 ms | p95 ms | Maximum response bytes |
| --- | --- | --- | --- |
| large-repository-10000-api-final.json / graph_nodes_page_50 | 622.414 | 830.662 | 37,501 |
| large-repository-10000-api-final.json / graph_neighborhood_page_50 | 1425.078 | 1691.541 | 98,456 |
| large-repository-10000-api-final.json / workspace | 1821.335 | 2233.804 | 4,697,696 |
| large-repository-10000-api-final.json / authorized_evidence | 8.927 | 11.366 | 1,051 |
| large-repository-3mloc-api-final.json / graph_nodes_page_50 | 693.872 | 964.729 | 37,501 |
| large-repository-3mloc-api-final.json / graph_neighborhood_page_50 | 861.652 | 1006.701 | 98,456 |
| large-repository-3mloc-api-final.json / workspace | 1588.96 | 1786.835 | 4,697,699 |
| large-repository-3mloc-api-final.json / authorized_evidence | 11.91 | 15.9 | 7,533 |
| large-repository-50000-api.json / graph_nodes_page_50 | 6277.411 | 7760.139 | 37,542 |
| large-repository-50000-api.json / graph_neighborhood_page_50 | 15797.217 | 25729.323 | 98,534 |
| large-repository-50000-api.json / workspace | 13514.135 | 14641.284 | 4,697,702 |
| large-repository-50000-api.json / authorized_evidence | 13.68 | 15.648 | 1,051 |

Unindexed 10k timings are retained separately in `large-repository-10000-api.json`; they are historical evidence for the indexed query improvement. Large-scale live PostgreSQL query plans, Redis/Celery scheduling, sustained arrivals during a huge analysis, representative customer monorepos, network-storage costs and production failure/restore behavior remain UNMEASURED. Controlled queue/crash evidence is reported separately in [PR_LOAD_BENCHMARK.md](PR_LOAD_BENCHMARK.md).
