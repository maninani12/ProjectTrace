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

The coordinator now appends immutable typed signal and raw metric snapshots to separate **attempt-private encrypted SQLite spill stores**. SQLite uses unnamed temporary databases (already-unlinked files on tested Linux); scoped envelopes authenticate tenant/repository/inventory, store identity and ordinal, and no key, path or database connection reaches a parser. Each collection uses a 1 MiB SQLite page cache with mmap disabled, a 32,000,000-byte row budget (without tightening the existing maximum IPC envelope) and a 256,000,000-byte ciphertext budget. Full rows are decrypted individually. Duplication retains integer selected-row offsets and its pre-existing work budgets; it can retrieve prior token rows without retaining every token array. Exact-body duplicate groups retain path/line only. Ordered JSON checkpoint/graph consumers iterate lazily. Completed parser artifacts remain the independent durable retry authority. Ephemeral spill files are not recovery receipts and are closed on interruption; exhaustion produces an actionable failed-job diagnostic without publication. Disk filesystem metadata/unused pages add to ciphertext size, so this is not a literal total-disk cap.

The final token-free quality metrics, selected/path/symbol indexes, findings, assets, global correlation, snapshot JSON and reconstructed generation receipts remain size-dependent. These are **still unresolved architecture**, not qualification assumptions. Encrypted spill is a coherent reduction of repository-wide raw payload retention, not a complete bounded global pipeline. Installed coordinator code remains trusted. Row mutation is explicitly unsupported; artifact data and parser cache are unchanged. Existing v1 checkpoints and generation receipts remain readable. No migration/schema change is introduced.

### Enforced Linux experiment

`.github/workflows/scale-qualification.yml` compares the exact integration baseline with the candidate, with the same owned profiling scripts copied into the baseline image (production modules untouched). Both use the same pinned ZIP. Each cold/warm attempt executes in a separate non-root Docker cgroup v2 with **memory.max=768000000**, **memory.swap.max=0**, network disabled, all capabilities dropped and no-new-privileges. The harness verifies Docker configuration, kernel counters and the inner limit; a missing prerequisite fails rather than skipping. Coordinator, archive helper and native parser descendants share this cgroup. SQLite is inside it; PostgreSQL/Redis validations remain separate service-backed regression jobs and are not falsely included in the envelope. Kernel cgroup charge includes page cache; sampled RSS and Python allocation peaks are different counters. Linux charge is not Windows committed-memory accounting.

Outer kernel sampling retains `memory.current`, `memory.peak`, `memory.events`, swap and cgroup process membership. Inner sampling retains coordinator/child RSS and stage names. The manifest pass also crosses the production SEC-002 archive boundary; no untrusted ZIP parser runs in the coordinator. No filesystem/network sandbox or resource budget is relaxed.

The current qualification driver runs full cold and warm capture/analysis/publication, failing on actual application/resource errors. Incremental, forced OOM recovery, stage cancellation, fresh-worker restart and concurrent-tenant scenarios are explicitly **NOT_RUN** until implemented on a completing workload; the driver cannot award full qualification while these are missing and exits unsuccessfully. Complete graph/claim/evidence equivalence remains a mandatory gate, not an assumed consequence of matching metric output. CI preserves sanitized JSON/JSONL only, never source bytes, encrypted tenant databases, encryption keys or full environment dumps. Seven-day artifact retention is not permanent evidence retention.

At implementation time: local cgroup mount read-only; Docker/PostgreSQL/Redis unavailable; required Landlock unavailable. Local owned-fixture development-mode tests are not security enforcement evidence. Initial existing focused regression selection: **80 passed**. Additional tests and actual CI/resource results must be recorded after execution. No large-workload pass is claimed by this guide.

### Full constrained experiment: actual failure, not memory qualification

Head `9309c026449dba712fa14037e0b0322148f4d658` has successful regression workflow [40189259310](https://github.com/maninani12/ProjectTrace/actions/runs/40189259310): **692 backend passed / 2 Windows skips**, **77 Linux acceptance/regressions**, **4 real broker cases**, **18 browser passed / 10 preserved fixture skips**, **49 frontend units**, **33 benchmarks**. Ruff/compilation, types/build, migrations/seed, Python/npm audits and both Docker builds passed. These results apply to that head only. Expected FK rejection logs belong to passing tenant-constraint tests.

The separate [constrained workflow 40189259317](https://github.com/maninani12/ProjectTrace/actions/runs/40189259317) **failed on both revisions during CAPTURING**, before global analysis. Both manifest passes succeeded in real Linux isolation under memory.max **768,000,000** and swap.max **0**. Full canonical per-file JSONL SHA-256: **081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89**, independently identical across both runners: **21,636 entries, 330,420,155 expanded bytes, 38 symlinks, 32 oversized regular files**. The complete hash-only manifest is retained as deterministic gzip in `docs/evidence/SCALE001_OPENMETADATA_MANIFEST.jsonl.gz`; raw experiment receipts are in `SCALE001_CGROUP_INTAKE_FAILURE.json`. No source payload or key is committed.

| Initial capture | Baseline 243513ee | Candidate 9309c026 |
|---|---:|---:|
| Kernel memory.peak bytes | 409,628,672 | 396,099,584 |
| Sampled coordinator RSS peak | 116,838,400 | 116,375,552 |
| Sampled helper RSS peak | 111,861,760 | 126,173,184 |
| Duration seconds / exit | 150.762 / 1 | 150.890 / 1 |
| Error / stage | ARCHIVE_HELPER_TIMEOUT / CAPTURING | ARCHIVE_HELPER_TIMEOUT / CAPTURING |
| OOM / pointers / artifacts | 0 / 0 / 0 | 0 / 0 / 0 |
| SQLite integrity / FK violations | ok / 0 | ok / 0 |

The manifest worker finished in **13.143 / 13.454 seconds**. Code inspection confirms the fixed archive deadline also counts time suspended at `yield` while downstream lexical classification, encryption and persistence run. The continuation's qualification adapter first drains validated entries into bounded encrypted replay rows (512 MB ciphertext / 2 MB row budgets), then calls unchanged production `capture` from bounded replay. Both revisions use the same adapter; baseline production modules are untouched. The helper's time, CPU, memory, filesystem and network budgets are unchanged. This is an analysis qualification adapter, **not a claim that the application's direct ZIP-to-capture backpressure defect is repaired**.

### Continued bounded working storage and recovery contract

The finding working map now uses encrypted row storage rather than a repository-wide second dictionary of full finding JSON. Its existing 250-object ORM cache, fenced pending updates, deterministic order and serialized v1 receipt representation remain compatible. Encoders iterate snapshots without constructing another complete finding list. Raw signals/metrics and finding working rows are attempt-private; parser artifacts and encrypted generation receipts remain the durable recovery authority. Linux unnamed SQLite files were observed already unlinked while live and tested through owned-process SIGKILL; kernel descriptor cleanup reclaims them. No Windows cleanup equivalence is claimed.

A mandatory owned two-child allocation test verifies that the shared cgroup actually denies aggregate memory, separately from the application analysis. It is **envelope enforcement evidence, not application exhaustion/recovery evidence**. The harness also performs read-only post-container-exit DB checks. Keys remain in a private 0600 fixture key file for later replay and are excluded from uploads. No source, DB or key artifact is uploaded. The cold/warm/incremental/cancellation/fresh-worker/concurrent-tenant matrix remains required; this driver cannot award full qualification while scenarios are missing.

The workspace reset during continuation. Published head 9309c026 and its CI artifacts were recovered into a separate worktree, preserving the older local PR #3 checkout. Unpublished code was reconstructed and retested; original uncaptured local profiling files were unavailable. Previous observed small-workload results must not be represented as newly recovered raw files. New benchmark receipts are generated afresh where feasible.

**Remaining architecture:** token-free metric/symbol/output vectors, global correlation/graph structures, snapshot JSON, checkpoint buffering/encryption, and joined receipt restoration remain size-dependent. A passing small workload or regression suite does not close SCALE-001. New current-head CI/cgroup evidence must be evaluated before the final verdict.

### Recovered-workspace validation of the reconstructed revision

Local generation/auth/repository/storage selection: **70 passed** (before the additional read-protocol case); latest dedicated storage/comparison/manifest cases pass, including membership/reverse iteration and preservation of JavaScript parser-symbol identity. Ruff/compilation/diff checks pass. The local required Linux probe actually failed closed with LANDLOCK_ABI_3_REQUIRED; cgroup is read-only and Docker/PostgreSQL/Redis executables are absent. Only CI can qualify active enforcement here.

Fresh 100-file / 10-function benchmark: all cold/warm/one-file-change snapshots completed with 1,000 findings, 1,000 metrics, 2,108/2,108/2,107 graph nodes, 3,303 edges per snapshot, and 101 final parser artifacts. Canonical hashes of all scoped rows, complete snapshot/quality projections, source inventories and parser artifacts match. The comparator retains every edge/row and rejects ambiguous snapshot identities. Unknown fields named performance are retained; only known generated timing/spill diagnostics are excluded. Tests deliberately alter edges, claims, metrics, source hashes and artifacts and detect mismatches.

| Owned small fixture | Baseline cumulative parent RSS | Final candidate RSS | Baseline / candidate duration |
|---|---:|---:|---:|
| cold | 221,904,896 | 227,766,272 | 77.939 / 71.295 s |
| warm | 234,213,376 | 246,579,200 | 71.574 / 68.493 s |
| one_file_change | 266,199,040 | 274,554,880 | 74.456 / 73.906 s |

**No whole-pipeline memory improvement is demonstrated by this small fixture.** Python 3.12.14, cProfile enabled, development mode, zero helpers, no memory enforcement. Baseline ran concurrently with the provisional candidate; final candidate ran subsequently, so durations are not throughput comparisons. Raw receipts, profiling hotspots, counts and complete semantic fingerprints are committed in docs/evidence/SCALE001_PIPELINE_100.json. This is compatibility/diagnostic evidence, not large-repository qualification. The Linux capped workflow remains authoritative.

### Actual analysis under the shared limit (12a8e14e)

Regression workflow **40210108872 succeeded**: **705 backend passed / 2 Windows skips**, **77 Linux acceptance/regressions**, **4 broker**, **18 full browser passed / 10 preserved skips** plus **4 focused**, **49 frontend**, **33 benchmarks**; migrations, builds, lint/compile/types and both dependency audits passed. These are verified results for 12a8e14e.

Constrained workflow **40210109062 failed**. The encrypted intake replay completed: **21,636 inventory entries, 21,269 retained text entries, 330,420,155 declared bytes**, 324,054,740 replay ciphertext bytes. Both actual kernels enforced memory.max **768,000,000**, swap.max **0**. The owned two-child test genuinely triggered kernel OOM kills in the shared envelope; it is not an application recovery test.

| Full-workload attempt | Baseline 243513ee | Candidate 12a8e14e |
|---|---|---|
| Stage reached | ANALYZING | ANALYZING |
| Kernel memory.peak | 768,000,000 | 768,000,000 |
| Exit / OOM kill | 137 / yes | 1 / no |
| Retained valid parser artifacts | 3,747 | 5,327 |
| Application job | Interrupted ANALYZING | FAILED / ANALYSIS_OBSERVATION_BUDGET |
| Published pointers / generations | 0 / 0 | 0 / 0 |
| SQLite integrity / FK errors | ok / 0 | ok / 0 |

The candidate rejected its spill budget safely after **1,153.644 seconds total sampled experiment duration**, rather than completing. Its sampled coordinator RSS peak was **482,889,728**, helper RSS peak **143,265,792**, instantaneous sampled tree RSS peak **620,978,176** bytes. Those RSS peaks occur at different times; do not add individual peaks or equate them to cgroup charge. Raw stage/kernel/RSS samples and post-exit checks are committed in `SCALE001_CGROUP_40210109062.json` and `SCALE001_CGROUP_40210109062_MEMORY.jsonl.gz`. Warm/incremental/cancellation/fresh-worker/concurrent-tenant/full-output-equivalence are **NOT_RUN** for the large workload. The interrupted baseline is not a valid complete golden result. **Verdict at this head: BLOCKED.**

The next bounded correction also spills pre-quality finding payloads (previously resident throughout parsing). A verified 256 MB collection-budget rejection motivates testing an explicitly configured **512,000,000-byte per-collection disk budget**; the process-tree memory limit remains 768,000,000 with zero swap. Default spill budget remains 256 MB, configurable up to the existing 2 GB upper bound. This changes disk allowance, not worker RAM or parser budgets. Metadata/index/free-page overhead is additional disk use. Failure diagnostics now include fixed collection/budget/count fields and owned stack module/function/line only, never source text, locals or credentials.

A separate observed cost regression required correction: with 1,001 owned typed signals and 20 claims, repeated full scans decrypted **40,040 rows** (0.482 s, plain-list control 0.0013 s). Scoped HMAC-tagged type/exact/import-root indexes reduce that case to **20 decryptions** (0.0020 s), with identical complete verdicts/fingerprints/evidence. Verifiers still apply their original predicates, preserve every match/duplicate and include every affirmative authentication mode. Unknown evidence remains unknown. The index values are not plaintext. This is a typed-result index, not an uncontained source parser. Raw cost receipts are in `SCALE001_SIGNAL_LOOKUP.json`; this does not establish large-repository throughput.

Local index/auth/storage selection: **57 passed**; broader current streaming/repository/quality/auth selection: **118 passed**; generation/cache/index selection: **95 passed** (overlapping selections, do not sum). New current-head CI and full constrained results remain mandatory. Global quality/output/correlation/serialization architecture is still not fully bounded; increasing disk allowance must not be presented as closing SCALE-001.

The post-correction owned 20-file cold/warm/one-file-change run also completes with identical complete semantic fingerprints against 243513ee (source inventories, parser artifacts, snapshot/quality projections and every scoped evidence/claim/finding/dependency/node/edge). Raw receipts are retained in `SCALE001_STREAM_EQUIVALENCE_20.json`. It has no memory enforcement and uses development mode on owned inert input; it is not the large qualification. No rows are filtered to obtain equality.
