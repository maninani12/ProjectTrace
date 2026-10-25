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


### Continued constrained run at 204e4481: measured native metric storage exhaustion

[Run 40213479233](https://github.com/maninani12/ProjectTrace/actions/runs/40213479233) failed on both revisions under the same verified **768,000,000-byte cgroup / zero swap**. Complete capture and the unchanged per-file manifest succeeded. The candidate reached **11,797 durable parser artifacts** before **98,329 metric rows** would exceed its **512,000,000-byte ciphertext budget** (attempted 512,001,320 bytes, collection NATIVE_METRICS). The owned stack identifies `partitioned_analysis.parse_partition -> metrics.extend -> EncryptedRows.append`. It had not reached global verification/quality/publication. This is a storage-budget rejection, not a kernel OOM or an attribution of all memory to metrics.

| Full cold attempt | Baseline 243513ee | Candidate 204e4481 |
|---|---:|---:|
| Kernel memory.peak bytes | 768,000,000 | 768,000,000 |
| Sampled coordinator RSS peak bytes | 693,317,632 | 526,123,008 |
| Sampled helpers RSS peak bytes | 149,553,152 | 148,852,736 |
| Sampled instantaneous namespace RSS peak bytes | 757,764,096 | 661,630,976 |
| Retained parser artifacts | 3,747 | 11,797 |
| Exit / kernel OOM kills | 137 / 1 | 1 / 0 |
| Published pointers / generations | 0 / 0 | 0 / 0 |
| SQLite integrity / FK errors | ok / 0 | ok / 0 |

The baseline's last inner sample was **466.563 seconds**, without a completed receipt because it was killed. The candidate's complete sampled experiment lasted **1,265.813 seconds**, including intake/capture. Different progress and incomplete outputs prohibit presenting these peaks/durations as a completed whole-pipeline before/after improvement. The baseline job remains interrupted ANALYZING; the candidate is FAILED / ANALYSIS_OBSERVATION_BUDGET. Neither is fresh-worker recovery evidence. The subsequent large-workload scenarios remain NOT_RUN.

Raw JSON receipts plus **23,228 stage/RSS/kernel samples** are committed as `SCALE001_CGROUP_40213479233.json` and `SCALE001_CGROUP_40213479233_MEMORY.jsonl.gz`. Original [baseline artifact 12607135659](https://github.com/maninani12/ProjectTrace/actions/runs/40213479233/artifacts/12607135659) and [candidate artifact 12606589753](https://github.com/maninani12/ProjectTrace/actions/runs/40213479233/artifacts/12606589753) have seven-day retention; committed evidence preserves sanitized counts/counters, not source, databases or keys. **Verdict for 204e4481: BLOCKED.**

The next correction losslessly compresses the coordinator's own bounded JSON spill envelopes before Fernet authentication. Native duplication tokens are retained completely, with original values, lines and order; durable parser-cache records and public schemas remain unchanged. This addresses the measured verbose metric-storage failure without increasing RAM, row, disk or parser budgets. Each row is decompressed only after authentication, with a hard original row-byte ceiling; truncated streams, trailing bytes, unknown framing and oversized decoded content are rejected. No compressed repository input is passed to this trusted decoder: its inputs are exclusively authenticated envelopes emitted by the owned row store. This decoder/JSON codec is part of the coordinator's trusted computing base, not an extension of the SEC-002 untrusted-parser claim. Temporary stores never survive as durable receipt formats, so no persisted format migration is needed.

Local compression/storage/index/quality-ownership/comparison tests: **65 passed** on owned input in explicit development mode; Ruff/compilation/diff checks passed. An initial required-mode invocation produced **64 passed / 1 failed**, because the local kernel rejected LANDLOCK_ABI_3_REQUIRED before the fixture could be captured; that invocation is not an enforcement pass. The required-mode CI/security gates remain unchanged. Compression benefit on an owned token row and complete round-trip are tested; only another full constrained run can establish its real-workload effect. Complete bounded quality/output/correlation/graph/receipt architecture, application recovery, full output equivalence and production qualification remain open.

Standard [CI 40213479256](https://github.com/maninani12/ProjectTrace/actions/runs/40213479256) subsequently succeeded for **204e4481**: **743 backend passed / 2 Windows skips**, **77 required Linux cases**, **4 real broker cases**, **18 full browser passed / 10 preserved skips** plus **4 focused**, **49 frontend units / 12 files**, **33 analyzer cases**. Ruff/compilation, TypeScript/build, fresh migration cycle/seed and preservation tests, both audits (no known Python / zero npm vulnerabilities) and both Docker images passed. These results precede the compressed-envelope follow-up and do not qualify it. The completed regression workflow does not override the failed constrained workflow.

Compression follow-up publication/cache/generation/authentication/Engineering Changes selection: **113 passed / 1 Windows extended-path skip** in 208.97 s (development mode on owned fixtures). Two integrity-gate tests also passed. A separate 20-file invocation of the older owned benchmark script reported completion but produced malformed local SQLite files on **both unchanged 243513ee and the compressed candidate** (Python 3.12.14 / SQLite 3.53.1 / overlay filesystem). Those new timing/equivalence measurements are rejected; private fixture files are preserved for diagnosis, not uploaded. No compression causality or production database defect has been established. The benchmark now requires post-run SQLite integrity and foreign-key validation before writing MEASURED_SYNTHETIC_LOCAL. Raw sanitized statuses are retained in SCALE001_COMPRESSED_FOLLOWUP_LOCAL.json. Earlier valid equivalence measurements remain explicitly scoped to their earlier commits.

Fresh sequential guarded 8-file and 20-file benchmark runs complete with post-run SQLite integrity ok and zero FK violations, independently rechecked after process exit. They use one-function owned files, cold/eight-file HEAD, development mode and a per-process guard, not the declared cgroup workload or the earlier ten-function equivalence fixture. The initial malformed local files were not repaired/deleted or used as baselines, and their cause remains unresolved; successful fresh fixtures do not prove that intermittent integrity issue corrected.

### Local Windows continuation, 26 October 2026

Work continues from 7e2f217e on the separate `codex/scale-001-local-continuation`
branch while cloud state remains unknown. PR #4 and its shared branch remain
unchanged. The user-confirmed latest run 40216200591 candidate timed out during
ANALYZING with 11,097 retained artifacts, no application OOM kill, intact DB/FKs
and zero publication. Raw latest artifacts are pending local inspection.
Measured local corrections reduce repeated packet sanitization and publication
visibility SQL-expression construction; aggregate spill and cgroup breakdown
diagnostics support the next qualification. Global output retention and the
full acceptance matrix remain open. See
[the local handoff record](SCALE001_LOCAL_HANDOFF_2026_10_26.md) and its sanitized
evidence for scope, provenance, measurements, tests and remaining gates.

### Completed local CI at 7d717bf; native transport continuation

Regression run 40223143091 passed (756 backend / 2 skips, 77 required Linux,
4 real broker, 49 frontend, 18 browser / 10 preserved skips plus 4 focused).
Constrained run 40223143093 failed: baseline OOM / 3,747 artifacts; candidate
ANALYSIS_TIME_BUDGET / 14,287 artifacts, zero application OOM kills and zero
publication. Both DB/FK checks passed. The candidate spent 1,712.129 of
1,809.837 analysis seconds in the partition parse path; global quality and
publication were not reached. Raw receipts and 37,424 samples are preserved.
The next correction removes duplicate native wire payloads while reconstructing
the complete original logical result before the existing guards. See
[the completed qualification and correction record](SCALE001_7D717BF_QUALIFICATION.md).
All full-workload acceptance gates remain open.

### Completed b1fb6fe qualification; bounded OpenAPI continuation

Regression 40227376407 succeeded (770 backend / 2 skips; all four jobs).
Constrained 40227376411 failed: baseline kernel OOM / 3,747 parser artifacts;
candidate host 2,400-second timeout / 18,756 artifacts / EXTRACTING_CLAIMS,
zero application OOM kills and zero publication. Both SQLite/FK checks passed.
The candidate spent about 1,632 sampled seconds in ANALYZING and at least 592
in claims; the full timeout is not claim-extraction duration. Anonymous, file
cache and kernel charges are preserved separately with 38,800 raw samples.
An owned dispatch profile isolates repeated JSON-helper startup cost. The next
correction batches all selected JSON inside unchanged Linux isolation, returns
complete OpenAPI contracts only, preserves the original nesting guard, and adds
bounded deadline checks and durable aggregate diagnostics. No limits are raised.
See [the evidence and correction record](SCALE001_B1FB6FE_CLAIM_EXTRACTION.md).
Complete-workload correctness, publication and recovery remain unqualified.

The 5758a63 follow-up (40241617715) confirms full-workload claim extraction now
completes in 24.987 seconds: 2,275 JSON sources / 49 helpers. It then OOM-kills the
coordinator in the broad VERIFYING stage, with 18,756 parser artifacts, intact
SQLite/FKs and no publication. The last host charge is predominantly anonymous
(741,474,304 bytes; file cache 278,528). Committed aggregates expose 195,982 metric
rows, 12,435,603 tokens and 53,467 symbols; the precise post-claims allocation
hotspot still needs operation-level persistence/profiling. Regression has three
passing jobs and one new nesting-fallback failure; its correction preserves the
original public protocol guard and needs a fresh Linux run. Both completed
workflows were allowed to finish before another push. Raw receipts and 30,715
samples are preserved in SCALE001_CGROUP_40241617715 evidence. No complete-output
or recovery qualification is claimed.
