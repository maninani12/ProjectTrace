# SCALE-001 local continuation — 26 October 2026

Verdict: **BLOCKED / NOT QUALIFIED**. Development continues from published
`7e2f217e2c4cd003d9f606f62f81c739abbc83ea` on the separate local branch
`codex/scale-001-local-continuation`. Cloud workspace state is unknown. PR #4,
its shared branch, earlier PR branches and main must remain unchanged.

## Checkout and evidence provenance

Both Windows checkouts were inspected before fetching. The OneDrive Desktop
`ProjectTrace` checkout is clean on main at
`46efd42b77ab1c9bfd48b64647b5d2b394d64c70`; it remains untouched. The VS Code
checkout, `C:\Users\sai krishna\Projects\ProjectTrace-local`, was clean on
`codex/scale-001-memory-containment` at the verified head. Fetch confirmed that
remote head, and the local continuation branch was created from that exact
commit. Neither checkout contained uncommitted changes or unpushed commits.
This establishes local state only; it does not recover or exclude cloud-local
changes.

The user independently inspected artifacts from run **40216200591** and supplied:

| Application attempt | Baseline | Candidate 7e2f217e |
|---|---|---|
| Failure | Exit 137; kernel OOM kill | TimeoutError / ANALYSIS_TIME_BUDGET |
| Stage | Interrupted analysis | ANALYZING |
| Retained parser artifacts | 3,747 | 11,097 |
| Candidate kernel peak | — | 768,000,000 bytes |
| Application OOM kills | Recorded | 0 |
| Candidate DB / FKs | — | integrity ok / 0 violations |
| Published generations / pointers | 0 / 0 | 0 / 0 |
| Cold / subsequent scenarios | Failed / not completed | Failed / NOT_RUN |

These latest outcomes are **human-confirmed evidence, not newly read raw
artifacts**. The ZIPs, qualification receipts and time series have not yet been
provided to the local agent. Earlier committed evidence belongs to earlier
runs and must not substitute for these samples. The resource-envelope probe's
intentional OOM is separate from application OOM and recovery evidence.

Current-head regression run **40216200638 succeeded**. Qualification run
**40216200591 failed**; the PR description's earlier “running” status is stale.
No PR edit is included in this local continuation.

## Findings and minimal corrections

The reported failure occurs before complete native observation collection.
Global quality, correlation, graph and checkpoint materialization cannot yet
be blamed for that particular timeout. Their later memory risks remain open.

1. **Repeated privacy-guard work.** On 20 owned typed rows with 5,000 duplicate
   tokens each, cProfile observed 300,060 redaction calls. A packet-local LRU now
   holds at most 128 strings of at most 256 characters. Every structural node,
   scalar check, sensitive-key decision and sanitized-key collision still
   crosses the original guard. Long strings bypass caching. Cache data is not
   shared across calls, workers or tenants. Full repeated-row outputs match.
   Unprofiled alternating baseline/candidate measurements were 1.534 / 0.193
   seconds and 1.274 / 0.177 seconds. This is a sanitizer microbenchmark only.
   A separate allocation probe did not demonstrate a memory reduction.

2. **Publication-visibility expression construction.** In the owned complete
   20-file profile, 5,371 ORM reads spent 21.409 cumulative profiled seconds in
   `hide_unpublished`, constructing all visibility expressions for each read,
   including unrelated source/cache queries. One immutable expression set is
   now retained per Session and active generation ID; changing worker scope
   replaces it. Database publication state, tenant predicates, aliases and
   per-query audit-integrity mode remain live checks. An alternating 500-read
   in-memory probe measured 0.482 / 0.125 seconds and 0.461 / 0.123 seconds.
   This caches SQL expressions, never authorization or query results.

3. **Missing attribution diagnostics.** Partition performance now includes
   observation-spill time, ciphertext bytes, metric/token/symbol counts and
   completed partitions. Failure qualification receipts retain aggregate
   stage/component/counter performance without the per-file slowest list.
   Inner and outer cgroup samples add memory.stat, CPU counters, pressure and
   I/O counters. Missing counters say UNAVAILABLE. These can distinguish
   anonymous memory, charged file pages, dirty/writeback pages, reclaim stalls
   and CPU throttling on the next Linux run. Reaching memory.max alone does
   not establish which of these dominated or prove an application OOM.

No production memory, execution-time, parser, IPC, row or disk limit changed.
No observation, source, symbol, finding or graph edge is discarded. Encryption,
parser execution boundaries, cache identity, fencing and atomic promotion are
unchanged. No schema or durable receipt-format migration is introduced.

The mutable-spill exhaustion test also used 1,000 repeated `x` characters that
could compress into the same Fernet size block as the original row. It now uses
deterministic varied content so that it actually exceeds the ciphertext quota;
the quota and implementation are unchanged.

## Local profiles and remaining retention

Sanitized measurements, implementation hashes and complete small-output
fingerprints are retained in
`evidence/SCALE001_LOCAL_CONTINUATION_2026_10_26.json`.

The owned fixture has 20 Python files, one function and 80 physical lines per
file. Both cold and eight-file-change snapshots completed. Canonical complete
snapshot/quality/record/graph/source-inventory/parser-artifact fingerprints
match across baseline and candidate. Both databases pass integrity and FK checks,
including read-only inspection after exit. Development mode does not exercise
Linux isolation. Baseline and candidate profiling overlapped different local
work, and startup/OS caches were uncontrolled, so their whole-pipeline wall times
must not be presented as a controlled throughput comparison.

The same cProfile captures quality aggregation, partition parsing, global
checkpoint save/load, generation save/load/batching/validation and graph and
correlation callers. Cumulative durations overlap and must not be summed.
Checkpoint save still buffers up to its existing 64 MB plaintext budget before
encryption; receipt restoration still joins its chunks. Those paths were only
exercised on the small fixture.

An owned encrypted-metric probe measured retained Python bytes after quality
build of **3,299,712 at 1,000 metrics** and **15,818,957 at 5,000 metrics**.
Corresponding symbol counts are 1,000 and 5,000. Streaming serialization does not
release these resident output vectors. These are tracemalloc measurements, not
RSS or cgroup charge, and cannot be extrapolated to qualify the pinned input.
Token-free metrics, per-path indexes, symbols, correlation/graph state, snapshot
JSON and joined receipts remain size-dependent. The raw spill encoder is also
a measured microbenchmark CPU cost; its bounded streaming implementation is
retained pending workload attribution rather than replacing it with an
unbounded full-row encoding allocation.

## Validation and next gate

Final focused validation passed **182 tests with one Linux-only skip** across
three disjoint selections: **103 storage/lexical/metric/diagnostic/checkpoint/
security**, **34 generation/private-publication**, and **45 auth/drift/output-
comparison/benchmark-integrity/Engineering Changes/queue/timeout/recovery**.
These exercise worker exits, scope changes, aliases, audit integrity and
publication. Ruff and compilation passed across backend, analyzers,
integrations, workers, tests, scripts and integration_tests; diff checks passed.
Local tests are explicit development-mode checks, not Linux enforcement evidence.

The first test invocation encountered an inaccessible default Windows pytest
temporary root. Fresh task-owned temporary roots were used without deleting or
changing that directory. An initial new visibility test attempted an ORM state
change while its private snapshot was hidden; the existing tenant-reference
guard correctly rejected it. The corrected test changes a controlled database
fixture to test visibility state, independently of application promotion.

The qualification workflow now also accepts pushes to the separate continuation
branch. Standard CI continues to cover Linux isolation, PostgreSQL, real
Redis/Celery recovery, browser regressions and Docker builds. The full pinned
workload retains memory.max **768,000,000**, swap **0**, the original baseline
and existing analysis budgets. Its missing incremental/exhaustion/cancellation/
fresh-worker/concurrent-tenant matrix still prevents full qualification.

Next: inspect both latest artifact ZIPs, keeping application and envelope-probe
directories separate; correlate stage/RSS/cgroup events with the candidate
timeout; run the continuation branch through Actions. If old samples lack
memory.stat/pressure counters, leave attribution unresolved until new samples
exist. Current local GitHub authentication was rejected; no current-head Linux
qualification is claimed. Keep PR #4 unchanged until cloud handoff is safe.
