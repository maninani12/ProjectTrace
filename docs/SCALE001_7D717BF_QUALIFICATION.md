# SCALE-001: completed local-continuation qualification

Assessed candidate: `7d717bf2dad6e78e7f2ac07904ab00e7e53f76c9`.
Baseline: `243513ee9acb6e4ed66cd3582ba79dc5a787b084`.
Verdict: **BLOCKED — neither revision completed the cold workload**.

## Verified CI and evidence

[Regression 40223143091](https://github.com/maninani12/ProjectTrace/actions/runs/40223143091)
completed successfully: **756 backend passed / 2 Windows skips**, **77 required
Linux checks**, **4 real Redis/PostgreSQL/Celery recovery cases**, **49 frontend
tests / 12 files**, **18 browser cases / 10 preserved fixture skips**, plus
**4 focused browser cases**. Lint, compilation, analyzer benchmarks, migrations,
audits, types/builds and both Docker builds passed. Expected FK-denial messages
in passing tenant tests are not CI failures. The 10,000-metric copied/owned/repeat
profile has identical complete digests; it does not qualify the large workload.

[Constrained run 40223143093](https://github.com/maninani12/ProjectTrace/actions/runs/40223143093)
completed with both jobs failed. All failed-job logs, both ZIP artifacts,
qualification receipts, inner/outer memory streams and post-exit integrity
results were inspected using authenticated GitHub CLI. No duplicate run was
launched while these workflows were active, and source changes waited for their
terminal results.

| Full cold attempt | Baseline | Candidate 7d717bf |
|---|---:|---:|
| Kernel memory.peak | 768,000,000 | 768,000,000 |
| Sampled coordinator RSS peak | 694,812,672 | 496,246,784 |
| Sampled helper RSS peak | 126,033,920 | 143,360,000 |
| Instantaneous namespace RSS peak | 748,449,792 | 632,369,152 |
| Retained parser artifacts | 3,747 | 14,287 |
| Exit / Docker OOMKilled | 137 / true | 1 / false |
| Candidate terminal error | — | TimeoutError / ANALYSIS_TIME_BUDGET |
| Last sampled analysis stage | ANALYZING | ANALYZING |
| SQLite integrity / FK violations | ok / 0 | ok / 0 |
| Published pointers / generations | 0 / 0 | 0 / 0 |

The baseline's last inner sample was **757.821 seconds**; no completion receipt
exists. Its stale cold=RUNNING field is not success or recovery evidence. The
last kernel sample precedes its OOM and still records zero oom_kill events;
Docker's OOMKilled=true and exit 137 independently establish the application
OOM. Preserve this sampling limitation rather than treating zero as proof of
no kill. Deliberate envelope-probe child OOMs belong to separate cgroups and are
never included in application outcomes.

The candidate's full experiment lasted **2,053.134 seconds**, including capture
and failure inspection. Recorded ANALYZING duration was **1,809.837 seconds**.
It failed at the deadline check after committing a completed partition/cache
batch. Cold failed; warm, incremental, exhaustion/cancellation, fresh-worker
recovery and concurrent-tenant scenarios were NOT_RUN.

Compared with the preceding 7e2f217e run, the candidate retained 14,287 rather
than 11,097 artifacts at timeout. This is further **partial progress**, not a
completed-workload throughput improvement, output-equivalence proof or memory
qualification. Different failure progress also prevents a completed before/
after comparison with the baseline.

Raw receipts and **37,424 application inner/outer samples** are preserved in
`evidence/SCALE001_CGROUP_40223143093.json` and its deterministic
`_MEMORY.jsonl.gz`. ZIP IDs/hashes are recorded there. Both full hash-only
manifests match `081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89`
with 21,636 entries. Source payloads, databases and encryption keys are absent.

## Measured bottleneck

Candidate aggregate performance records:

| Component | Seconds | Scope |
|---|---:|---|
| PARTITION_PARSE | 1,712.129 | Entire bounded native observation path |
| CONTAINED_NATIVE | 672.509 | Nested native helper, decoding and validation |
| TREE_SITTER | 164.119 | Nested per-file parser timings |
| PYTHON_NATIVE | 63.235 | Nested per-file parser timings |
| OBSERVATION_SPILL | 83.542 | Encrypted observation writes |
| CACHE_WRITE | 7.190 | Durable parser-cache batch work |

Durations overlap and must not be summed. **153 partitions / 14,829 source reads**
produced **140,461 metric rows, 9,446,463 duplication tokens and 40,170 symbol
rows**, with **336,067,496 ciphertext bytes** across the observation collections.
The symbol counter covers structural symbols in parser signals, not the final
quality symbol vector, which was never built in this attempt.
There were zero cache hits in this cold attempt and 542 files with persisted
parser diagnostics. Global quality aggregation, graph/correlation and checkpoint
serialization were not reached; their known retention risks cannot explain
this particular timeout.

The new cgroup counters identify real charged file pages alongside anonymous
memory: the final candidate host sample contains **429,486,080 anonymous bytes,
265,310,208 file bytes and 48,816,128 kernel bytes**. memory.events.max reached
**10,990**, with zero oom/oom_kill events for the candidate. Total experiment
counters show about **2,089 CPU seconds**, **0.437 memory-pressure seconds**,
**7.263 I/O-pressure seconds** and **0.226 CPU-throttled seconds**. These include
capture and failure inspection and are not per-component costs. They support
CPU/packet-processing work as the primary deadline target; they do not establish
that every anonymous byte is a retained Python object or that file reclaim has
no cost.

Source inspection and an owned packet profile isolate a removable transport
cost: native replies serialized findings, signals and metrics both directly
and inside the exact cache artifact. The parent independently decoded and
sanitized both copies.

## Smallest next correction

Native packets now transmit one complete artifact plus failures, reuse count
and performance metadata in the private `projecttrace-native-artifact-v1`
envelope. The parent reconstructs the original nine-field observation/cache
shape **before** the existing metadata guard and independent native scope,
hash, version, rule and line checks. The guard still visits both logical
projections and creates independent mutable observation/cache copies. Unknown
or incomplete envelopes fail; legacy list packets remain readable; completed
prefixes still survive a truncated later packet.

The outer packet schema and every byte/node/depth, helper CPU/memory/time,
source/partition, row/disk and application/cgroup limit are unchanged. There is
no C JSON-parser substitution, durable artifact/receipt/schema migration,
tenant-boundary change or loss of observations. Efficient wire representation
can permit more completed files within the same physical output cap; it does
not enlarge that cap or discard diagnostics.

Added timings separate syntax/native helper transport from parent packet
validation. These locate remaining costs on the next actual Linux workload;
they are not themselves proof of a pass.

The owned 12-file / 2,000-token-per-file microbenchmark retained exact complete
row equality, reducing wire bytes from **1,925,900 to 966,820**. Local repeated
packet processing measured **0.447 / 0.275 seconds** and **0.422 / 0.269 seconds**;
tracemalloc peaks were **13,118,224 / 11,051,137 bytes**, excluding preallocated
wire buffers. These scoped measurements are retained in
`evidence/SCALE001_NATIVE_ARTIFACT_TRANSPORT.json`. They do not measure Linux
bootstrap, full parsing, publication or whole-workload throughput.

Local follow-up validation: **172 passed / 3 platform-specific skips**, covering
the real owned helper dispatch/emitter, reconstructed-result privacy and scope
checks, cache independence, legacy packets, malformed framing, logical structure
and wire caps, completed-prefix recovery, storage, generation/publication,
checkpoint, timeout, authentication/drift and complete-output comparison tests.
Ruff, compilation and diff checks passed. A scratch-only pytest ID hook shortened
giant adversarial parameter labels for Windows paths; all parameter values and
assertions remained unchanged. An initial synthetic artifact fixture omitted
the existing sorted-key infrastructure signature and was correctly rejected;
the fixture was corrected to exercise the intended hash/scope guards. None of
these portable tests claims Linux enforcement for the new transport revision.

## Next qualification requirements

Run the new revision through standard regression CI and the same pinned
768,000,000-byte / zero-swap cgroup experiment. Require complete cold/warm
publication before interpreting later-stage retention or completed throughput.
The full incremental, cancellation/exhaustion, fresh-worker recovery,
concurrent-tenant and deterministic complete-output matrix remains mandatory.
Global metric/symbol/output vectors and checkpoint/receipt restoration remain
open architecture; this transport correction does not close them.

PR #4, its shared cloud branch and main remain unchanged. New work uses only
`codex/scale-001-local-continuation`, with ordinary commits and pushes.
