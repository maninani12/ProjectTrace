# SCALE-001: metric ownership increment

Verdict: **PARTIALLY ADDRESSED — NOT QUALIFIED**. Base PR #3 commit f655415f0971b86c2eddfb77ac98ae21f411d79c and CI 40178440270 were verified green. This separate branch targets codex/linux-parser-isolation; earlier PRs and main are unchanged. SEC-002 controls and all existing CI jobs remain required.

## Historical qualification target and recovery

SDLC_ACCEPTANCE_2026_10_15.md records 21,636 captured files / 7,744 artifacts and MemoryError during VERIFYING under a Windows 768 MB process-tree committed-memory ceiling. The line-56 traceback identifies allocation at metric projection, not the sole cause. Original raw profiling logs, encrypted inventory/DB and archive manifest are absent from this workspace. GitHub access to the documented b1fab2bc21c63335dead4daaaa28194c9878e9bf commit was verified (tree 98be740cd54db8653ce735946b6fd6bd5986e5e3). That commit identity alone does not recover the exact later pinned archive/hash or retained-inventory experiment. No historical failure was relabeled reproduced or passed.

## Retention inventory

- partitioned_analysis bounds source parsing but retains all findings, signals, warnings, assets and metric dictionaries globally. CompactTokens reduces token storage; it does not bound total observations.
- engine retains those observations while deriving dependencies, claims, exact-body duplicate indexes and quality output. Its exact-body duplicate index also holds metric references until return.
- code_quality.core created a second dictionary for every selected metric, plus per-path indexes, production metric references and symbol dictionaries. Duplication has existing work budgets; they remain unchanged.
- publication has bounded ORM batches and encrypted receipts, but complete result/graph/snapshot serialization and several correlation indexes remain global. Queue/recovery and publication contracts are unchanged.
- native helper resource limits are per process, not a coordinator-wide memory budget. The local cgroup filesystem is not writable; Windows Job Objects are unavailable on Linux. RLIMIT_AS must not be represented as a general process-tree committed-memory ceiling.

## Implemented correction and ownership contract

The inventory coordinator already creates disposable metric dictionaries separate from durable ParserArtifact JSON. It now explicitly transfers their ownership to global quality aggregation. Selected metric rows reuse those dictionaries; duplicate token arrays are released only after token-window duplication has completed. Unselected owned token arrays are released too. Symbol/index/source/observation collections are not truncated. Default callers retain the non-mutating copy behavior; implicit engine cache ownership transfer is rejected.

Failure after consuming scratch metrics does not mutate durable parser artifacts; a retry reconstructs observations from tenant-scoped cache rows. No schema, tenant, source identity, admission, sandbox, timeout, cancellation or publication controls change. Existing interruption/cache/publication tests remain required. This reduces one peak; it does not make global aggregation bounded.

## Executed profiling

Raw per-stage Python allocation peaks, peak RSS, durations, output sizes/counts and SHA-256 values are committed in evidence/SCALE001_METRIC_STAGE.json. Command: `python -m scripts.profile_scale_metrics --count N` for 1000, 10000 and 50000. Each launches copy-control and two ownership runs, asserting identical output digests. Inputs are owned synthetic metric dictionaries, one inert file, zero parser artifacts and no publication. They are not real parser observations or a large-repository accuracy test. Copy-control measures the retained legacy projection behavior in the same code, not a replay of the full historical commit.

Python 3.12 local measurements (bytes):

| Metric rows | Copy Python peak | Owned Python peak | Copy peak RSS | Owned peak RSS |
|---|---:|---:|---:|---:|
| 1,000 | 3,266,419 | 2,381,611 | 19,816,448 | 18,640,896 |
| 10,000 | 32,614,699 | 23,737,891 | 80,777,216 | 71,860,224 |
| 50,000 | 163,250,283 | 118,859,779 | 342,495,232 | 284,823,552 |

Each worker enforces 768 MiB RLIMIT_AS and has no helper subprocesses. RSS includes tracemalloc overhead and imports; sampling records cumulative process peak, not instantaneous stage RSS. This is not the historical Windows process-tree commit limit, a cgroup-enforced concurrent parser tree, or production throughput. Outputs match at each size across all three runs. Publication integrity is NOT EXERCISED by this microbenchmark.

Tests verify full quality/duplication output equality, ownership identity, unchanged borrowed/cache token data, positive duplicate findings before token release and rejection of implicit cache transfer. CI retains the medium profile and preserves backend/PostgreSQL, real Linux sandbox, broker and browser jobs. Commit-specific final counts/status live in the draft PR; no previous head's green counts qualify this change.

## Remaining acceptance gates

Recover an authorized exact source archive plus byte/hash manifest (no application credentials needed), or agree an explicitly different pinned qualification input. Replay cold, warm and incremental analyses under an actual 768 MB process-tree limit with per-stage tree measurements. Require complete file/artifact accounting, deterministic ordered digests, unchanged claims/findings/edges/source identity, successful atomic publication, forced exhaustion/cancellation with no public pointer, and recovery in a fresh worker/session. Global observations, symbols, duplication indexes, graph and serialization need further bounded storage/iteration design before this gate can close. Synthetic 50,000 metrics do not satisfy it.

The exact-body duplicate index in engine is also released immediately after its findings are emitted, before quality aggregation; its last-use lifetime is independently identifiable in the call graph. The microbenchmark does not measure that engine-wide saving. Final local focused selection: 78 passed; Ruff, compilation and diff checks passed. Current-head infrastructure/CI outcomes will be recorded in the draft PR.
