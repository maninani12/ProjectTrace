# SCALE-001: b1fb6fe qualification and bounded OpenAPI continuation

Status: **BLOCKED / unqualified**. Work remains on
`codex/scale-001-local-continuation`; PR #4's shared cloud branch and main are
outside this iteration. No resource, parser, security or production time limits
are raised.

## Completed GitHub evidence

Authenticated GitHub CLI inspection confirms regression
[40227376407](https://github.com/maninani12/ProjectTrace/actions/runs/40227376407)
**succeeded**, all four jobs, at
`b1fb6fe4283d1a3b0cc533258ff624308f6c89a4`: 770 backend passed / 2 preserved
Windows skips, 77 required Linux cases, 4 real broker cases, 49 frontend units,
18 full browser cases / 10 preserved skips plus 4 focused. Lint, builds,
migrations, audits and Docker checks passed. This does not qualify the workload.

Constrained run
[40227376411](https://github.com/maninani12/ProjectTrace/actions/runs/40227376411)
**failed**, both jobs. The authenticated downloads are retained as sanitized
receipts in [the run evidence](evidence/SCALE001_CGROUP_40227376411.json) and
**38,800** application-only inner/host samples in
`evidence/SCALE001_CGROUP_40227376411_MEMORY.jsonl.gz`. Original ZIP hashes and
full receipts are preserved. Deliberate envelope-probe OOM receipts are kept
separately; they are not application OOM evidence.

| Cold attempt | Baseline 243513ee | Candidate b1fb6fe |
|---|---:|---:|
| Sampled coordinator RSS peak, bytes | 695,992,320 | 517,267,456 |
| Sampled instantaneous namespace RSS peak, bytes | 769,740,800 | 669,540,352 |
| Kernel memory.peak, bytes | 768,000,000 | 768,000,000 |
| Last sampled memory.events max | 2,328 | 10,172 |
| Docker exit / OOMKilled | 137 / true | 137 / false |
| Termination | Kernel OOM | Host 2,400-second watchdog |
| Last durable job stage | ANALYZING | EXTRACTING_CLAIMS |
| Retained parser artifacts | 3,747 | 18,756 |
| SQLite / FK errors | ok / 0 | ok / 0 |
| Published pointers / generations | 0 / 0 | 0 / 0 |

The baseline's last sampled OOM counters were zero **before** its Docker-confirmed
OOM kill. The candidate has zero sampled application OOM/kill counters and an
explicit host timeout. Its `qualification.json` still says cold RUNNING because
SIGKILL prevented a terminal receipt; it is not an active job or an application
TimeoutError receipt. All subsequent scenarios remain NOT_RUN. RSS can double
count shared pages and is not the kernel cgroup charge.

The full manifest is unchanged: **21,636** entries, SHA-256
`081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89`;
21,269 retained text entries / 330,420,155 declared bytes. The pinned source is
`b1fab2bc21c63335dead4daaaa28194c9878e9bf`, archive SHA-256
`95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257`.
No imported code was executed. The baseline remains the historical integration
revision, not a complete golden-output result.

## Time and memory attribution

These are first-to-last sample spans, not exact stage boundary receipts:

| Candidate stage | Elapsed first–last, seconds | Sampled span | Cgroup CPU delta |
|---|---:|---:|---:|
| Encrypted archive replay | 0.271–27.970 | 27.699 | 28.703 |
| Capture | 28.222–178.771 | 150.549 | 150.899 |
| ANALYZING | 179.036–1811.276 | 1632.240 | 1645.415 |
| EXTRACTING_CLAIMS | 1811.529–2403.461 | 591.932 | 593.822 |

ANALYZING includes native parsing and dependency work. Claims did **not** consume
the whole experiment. Approximately 168 seconds remained of the unchanged
1,800-second application analysis budget at the transition. The old JSON loop
did not check that deadline until its following stage, allowing the host
watchdog to terminate first.

During candidate ANALYZING, independent inner-sample memory.stat peaks were
623,009,792 anonymous / 438,517,760 file / 59,105,280 kernel bytes. During claims,
they were 472,506,368 / 243,707,904 / 56,180,736. Do not add independent peaks.
The final host sample had 368,492,544 anonymous / 243,523,584 file / 55,894,016
kernel bytes, including 54,336,456 reclaimable slab; counters are not atomic.
Anonymous memory includes coordinator and helpers. File includes cached source,
SQLite, ciphertext/temp-file pages and runtime files; it is not all heap or all
spill. No shmem or swap was measured.

Candidate whole-experiment cgroup totals were 2,421.441 CPU seconds (2,264.118
user / 157.324 system), 0.095 CPU-throttled seconds, 0.379497 memory-pressure
some-stall seconds and 14.107524 IO-pressure some-stall seconds. IO counters
recorded 279,756,800 bytes read and 3,415,732,224 bytes written. Memory-limit events
show reclaim under charge pressure; these totals do not establish memory or IO
stall as the dominant cause of the 592-second claims span.
The stage samples show memory.events.max rising from 0 to 10,145 during
ANALYZING, then from 10,145 to 10,172 during claims. Most observed limit events
therefore preceded claim extraction; only 27 were added in its sampled span.

The killed artifacts contain no operation profile splitting Markdown from JSON,
nor final metric/symbol/spill counts, checkpoint/serialization costs or hashes.
Those values cannot be reconstructed from memory.stat. Source retrieval reads
bounded tenant-scoped ciphertext, authenticates/decrypts and verifies its digest;
the repository mapping already holds authorized metadata. No receipt proves a
missing database index or decryption dominates claims. Native metrics/symbols,
global graph/correlation and serialization remain open scalability concerns.

## Measured bottleneck and correction

The old claims loop launches an isolated JSON helper for **each** `.json` source,
including unrelated metadata. The pinned manifest has 2,276 JSON and 535 Markdown
entries at/below the existing 512,000-byte file ceiling; these are manifest counts,
not a claim of exact attempted helper counts before interruption.

An owned 16-file JSON dispatch prototype measured **10.096507 seconds / 16
fresh processes** versus **0.616745 seconds / one process**, with identical
complete contract-selection hash
`d3902fb15c667cc54e0b92d7418e9f00044fa01a5828f3733b7a5043f4205257`.
[Raw profile and limitations](evidence/SCALE001_OPENAPI_BATCH_PROFILE.json):
Windows / CPython 3.14.3, owned inert JSON, development dispatch; excludes real
Linux enforcement and coordinator IPC validation. This measures redundant
bootstrap cost; it does not apportion historical Linux claim time or prove a
complete workload speedup. Native analysis still accounts for most elapsed time.

The continuation adds sequential OpenAPI batches of at most **100 files and
512,000 source bytes total**, using the same installed worker and unchanged
Landlock/seccomp/environment/CPU/memory/output controls. Every selected JSON
source is parsed, including escaped `openapi` keys. Unrelated parsed objects stay
in the helper; real contracts retain complete ordered data. The parent verifies
scope, source hashes and envelope types, consumes and releases the current batch,
and keeps only bounded iterator lookahead. Existing warning predicates, caps,
route/method order, verdicts and publication behavior remain unchanged.

If the extra batch wrapper exceeds the existing protocol nesting guard, a narrow
protocol-decoder fallback uses the original per-source helper and original guard.
The public parser API normalizes decoder failures to HELPER_PROTOCOL; no failed
batch payload is consumed. Other failures
propagate; an over-deep original source still fails closed. No parser guard is
raised or bypassed. The batch and fallback check the existing cancellation,
deadline and lease between bounded work units; finally blocks release pending
contracts on failure/candidate cap. No persistent format or encryption changes.

New aggregates split DOCUMENTATION_CLAIMS, OPENAPI_SOURCE_READ,
OPENAPI_CONTRACT_BATCH and OPENAPI_CLAIMS and count submitted/consumed/contracts/
invalids/fallbacks. Source-read timing includes bounded partition lookahead;
component times overlap and must not be summed as wall time. Read-only post-exit
inspection now exports only committed aggregate job performance, never source or
per-file slowest-operation data. It may precede death and is not a terminal or
recovery receipt.

## Validation and remaining gates

Local owned-fixture broad regression selection: **211 passed / 2 skips** before
the final nesting fallback and diagnostic additions. Final targeted batch and
diagnostic selection: **18 passed**. Complete engine output equality covers
ordinary/escaped/malformed/partial contracts, route verdicts and existing final
1,500-claim cap; only the existing generated quality duration is normalized.
Tests verify byte/count bounds, single source reads, identity/substitution
rejection, deadline failure retaining parser cache with zero publication, and
original nesting-guard behavior. Existing generation/recovery/security tests
are in the broad selection. Local Windows development mode is not a Linux
enforcement pass. Three real required-Linux acceptance tests are added for CI.
The final batch/diagnostic/parser-security/checkpoint/timeout selection passed
**52 tests / 2 preserved Windows skips** in 14.27 seconds; selections overlap and
must not be summed. Repository Ruff, compilation and diff checks passed.

The next justified push must run regression and the unchanged **768,000,000-byte,
zero-swap**, full pinned workload qualification. Compare actual anonymous/file/
kernel peaks, stage/operation timing, completed files/artifacts, aggregate spill
costs, full output hashes and publication state. No new complete-workload benefit
has yet been measured. A timeout may still occur within the legitimate analysis
budget; the correction does not extend it.

If cold succeeds, inspect warm automatically attempted by the driver and continue
incremental, cancellation/exhaustion/fresh-worker recovery and concurrent-tenant
qualification. The current driver explicitly leaves unsupported scenarios
NOT_RUN; that is a remaining implementation/evidence gate. PostgreSQL and real
Redis/Celery recovery remain separate Linux acceptance gates. Full output
equivalence requires a complete valid comparator, not the OOM-interrupted
baseline. No cold-only or regression-only result closes SCALE-001.

## First Linux follow-up at 5758a63

[Regression 40241617717](https://github.com/maninani12/ProjectTrace/actions/runs/40241617717)
caught the fallback error-code mismatch: the first required isolation selection
had 17 passed / 1 failed (the new nesting-boundary test). The local mock had
bypassed the public call() decoder normalization. The ordinary batch/identity
and multi-batch helper-count tests passed under real Linux enforcement. This is
not a passing regression workflow.

The correction accepts the public HELPER_PROTOCOL decoder error for a bounded
retry of the original sources through the original single-source API. Invalid
originals still fail the unchanged guard. The portable test now substitutes only
the transport and exercises actual call()/decode_packet(), including the failed
single-source case. The test's substantive nesting expectations are retained.
The final focused selection again passed 52 tests / 2 skips (17.18 seconds),
with Ruff passing. Publication of this follow-up was held until constrained run
40241617715 completed, avoiding cancellation/duplicate qualification.

## Completed constrained follow-up: claims finish; coordinator OOM later

[Constrained 40241617715](https://github.com/maninani12/ProjectTrace/actions/runs/40241617715)
failed on both revisions at 5758a63. Both application containers (not the separate
probe) have Docker OOMKilled=true / exit 137 under the same 768,000,000-byte / zero
swap envelope. Candidate SQLite integrity is ok, FK violations zero; parser
artifacts 18,756, published generations/pointers zero. Baseline again retained
3,747 artifacts and died in ANALYZING. The candidate reached **VERIFYING**.
Post-kill cold RUNNING receipts are stale; later scenarios were NOT_RUN.

The [new raw receipts](evidence/SCALE001_CGROUP_40241617715.json) and **30,715**
application samples in `evidence/SCALE001_CGROUP_40241617715_MEMORY.jsonl.gz`
include the committed aggregate profile recovered by the new post-exit exporter.
The downloaded candidate ZIP SHA-256 was independently matched to GitHub's
published digest `8209e90d90622088a214ee08cf93863d7cde8015a8718fa77e8e1329b3064601`.
The full pinned manifest remains identical.

Durable candidate profile at VERIFYING entry:

| Measured operation | Seconds | Count |
|---|---:|---:|
| ANALYZING stage | 1295.110941 | — |
| PARTITION_PARSE (includes nested helper work) | 1218.486008 | 199 |
| OBSERVATION_SPILL | 55.830303 | 199 |
| CACHE_WRITE | 5.783388 | 199 |
| DEPENDENCIES | 0.663936 | 1 |
| EXTRACTING_CLAIMS stage | **24.986637** | — |
| DOCUMENTATION_CLAIMS | 3.125327 | 1 |
| OPENAPI_SOURCE_READ | 0.444773 | 49 |
| OPENAPI_CONTRACT_BATCH | 21.268294 | 49 |
| OPENAPI_CLAIMS (includes batch/read work) | 21.859466 | 1 |

All **2,275** submitted JSON sources / **19,275,081** bytes were consumed in 49
helpers: four invalid JSON files, one actual OpenAPI contract. This is the actual
retained-input count, distinct from the 2,276-file manifest count. No source or
contract was skipped by a keyword heuristic. No fallback counter was recorded on
this workload. The older run was still extracting after at least 591.932 sampled
seconds; the corrected path now completes in about 25 seconds. Different runners
and incomplete older outputs prevent a complete-workload speedup claim or
attributing the ANALYZING timing difference to this claims-only change.

Native aggregates: **18,859** processed cache misses / zero hits, **103** files
with persisted diagnostics, **195,982** metric rows, **12,435,603** retained
duplication tokens, **53,467** symbol rows and **457,636,900** aggregate spill
ciphertext bytes. These are not resident heap sizes or total disk footprint.
Timings overlap; do not sum nested helper/component durations.

After claims, VERIFYING lasted **128.708 sampled seconds** until the last inner
sample at 1596.231 seconds total. Coordinator RSS peaked at **768,835,584 bytes**
with no helper RSS in that peak sample. Independent stage anonymous/file/kernel
peaks were 742,498,304 / 269,611,008 / 55,250,944 bytes. The last host sample had
741,474,304 anonymous, only **278,528 file**, and 25,632,768 kernel bytes. Its OOM
counters still precede the Docker-confirmed kill. This is now coordinator
anonymous-memory exhaustion after file-cache reclamation, not the earlier host
time budget failure or evidence that file cache alone caused the OOM.

The persisted profile is the VERIFYING entry checkpoint; its near-zero VERIFYING
duration is stale. It cannot identify the operation executing at death. This
label covers the claim-verdict/evidence cache and claim list, storage claims,
exact-body duplicate index, infrastructure linking, quality aggregation and final
identity. No trace proves which retained structure dominated. The next exact
engineering action is to persist bounded operation-boundary/claim-batch profiles
within this stage, then reproduce the growing collection with owned equivalent
fixtures before choosing its spill/ownership correction. Dropping evidence,
reducing coverage or increasing the ceiling is not a remedy.

Regression 40241617717 finished with **three successful jobs and one failed**:
validate (786 backend / 2 Windows-specific skips, 49 frontend, builds/migrations/
audits/Docker), browser (18 / 10 skips plus 4 focused), and real broker (4) passed.
The required Linux job stopped at the identified 17-pass/1-failure nesting case;
its remaining selections did not run. The corrected public-API fallback requires
fresh Linux CI. Full-workload output hashes, successful publication and all later
qualification scenarios remain unavailable. **SCALE-001 is still unqualified.**
