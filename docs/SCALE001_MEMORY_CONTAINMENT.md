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

## Continuation: encrypted observation spill and full-workload resource gate

Integration starting head: `243513ee9acb6e4ed66cd3582ba79dc5a787b084`. Earlier history and the contrary 500-file RSS result above remain valid. This continuation does not claim closure.

### Workload reconciliation

The authorized commit ZIP downloaded from `https://codeload.github.com/maninani12/OpenMetadata/zip/b1fab2bc21c63335dead4daaaa28194c9878e9bf` is **158,981,993 bytes**, SHA-256 **95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257**. This independently matches the reported alternative, rather than the 157,126,481-byte historical archive with SHA-256 `027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`. The historical archive is absent locally. This is explicitly a new qualification workload, not a reproduction of the historical byte input.

No repacking, customer script execution, package installation, checkout hooks or source imports occur. The archive retains GitHub's top directory prefix. The required-isolation manifest pass hashes **all non-directory members**, including oversized content and symlink payload bytes, without extraction or following links. SHA-256/byte counts for every member are retained in canonical ordered JSONL; its whole-file digest, count and expanded bytes are checked against 21,636 / 330,420,155. Analysis uses the existing 512,000-byte parser limit and full inventory accounting, including explicit unsupported/size exclusions. This is not silent truncation or removal of those entries. Codeload may change archive bytes; SHA mismatch fails the gate and requires an explicitly documented new pin.

### Retention findings and correction

`analyze_inventory` held all partition signals (including nested symbol/flow data) and all raw metric dictionaries/token windows until global verification/publication. Metric ownership alone did not remove this residence. Exact-body duplication also retained references to complete metric dictionaries although its later consumers need only path and line.

The coordinator now appends immutable typed signal and raw metric snapshots to separate **attempt-private encrypted SQLite spill stores**. Storage names are random, scoped envelopes authenticate tenant/repository/inventory, store identity and ordinal, and no key, path or database connection reaches a parser. Each collection uses a 1 MiB SQLite page cache with mmap disabled, an 8,000,000-byte row budget and a 256,000,000-byte ciphertext budget. Full rows are decrypted individually. Duplication retains integer selected-row offsets and its pre-existing work budgets; it can retrieve prior token rows without retaining every token array. Exact-body duplicate groups retain path/line only. Ordered JSON checkpoint/graph consumers iterate lazily. Completed parser artifacts remain the independent durable retry authority. Ephemeral spill files are not recovery receipts and are closed on interruption; exhaustion produces an actionable failed-job diagnostic without publication. Disk filesystem metadata/unused pages add to ciphertext size, so this is not a literal total-disk cap.

The final token-free quality metrics, selected/path/symbol indexes, findings, assets, global correlation, snapshot JSON, finding working-map and reconstructed generation receipts remain size-dependent. These are **still unresolved architecture**, not qualification assumptions. Encrypted spill is a coherent reduction of repository-wide raw payload retention, not a complete bounded global pipeline. Installed coordinator code remains trusted. Row mutation is explicitly unsupported; artifact data and parser cache are unchanged. Existing v1 checkpoints and generation receipts remain readable. No migration/schema change is introduced.

### Enforced Linux experiment

`.github/workflows/scale-qualification.yml` compares the exact integration baseline with the candidate, with the same owned profiling scripts copied into the baseline image (production modules untouched). Both use the same pinned ZIP. Each cold/warm attempt executes in a separate non-root Docker cgroup v2 with **memory.max=768000000**, **memory.swap.max=0**, network disabled, all capabilities dropped and no-new-privileges. The harness verifies Docker configuration, kernel counters and the inner limit; a missing prerequisite fails rather than skipping. Coordinator, archive helper and native parser descendants share this cgroup. SQLite is inside it; PostgreSQL/Redis validations remain separate service-backed regression jobs and are not falsely included in the envelope. Kernel cgroup charge includes page cache; sampled RSS and Python allocation peaks are different counters. Linux charge is not Windows committed-memory accounting.

Outer kernel sampling retains `memory.current`, `memory.peak`, `memory.events`, swap and cgroup process membership. Inner sampling retains coordinator/child RSS and stage names. The manifest pass also crosses the production SEC-002 archive boundary; no untrusted ZIP parser runs in the coordinator. No filesystem/network sandbox or resource budget is relaxed.

The current qualification driver runs full cold and warm capture/analysis/publication, failing on actual application/resource errors. Incremental, forced OOM recovery, stage cancellation, fresh-worker restart and concurrent-tenant scenarios are explicitly **NOT_RUN** until implemented on a completing workload; the driver cannot award full qualification while these are missing and exits unsuccessfully. Complete graph/claim/evidence equivalence remains a mandatory gate, not an assumed consequence of matching metric output. CI preserves sanitized JSON/JSONL only, never source bytes, encrypted tenant databases, encryption keys or full environment dumps. Seven-day artifact retention is not permanent evidence retention.

At implementation time: local cgroup mount read-only; Docker/PostgreSQL/Redis unavailable; required Landlock unavailable. Local owned-fixture development-mode tests are not security enforcement evidence. Initial existing focused regression selection: **80 passed**. Additional tests and actual CI/resource results must be recorded after execution. No large-workload pass is claimed by this guide.
