# SCALE-001 full-workload gate at 57e71b9

**NOT QUALIFIED.** This record concerns published
`57e71b90262a48b83c924baa9c0c6b67d8d83c19` on
`codex/scale-001-local-continuation`. All four regression jobs passed. Both
constrained jobs failed. The candidate never entered VERIFYING, so this attempt
does not measure the new encrypted quality-output stores on the full workload.

## Completed authenticated GitHub evidence

[Regression 40274461867](https://github.com/maninani12/ProjectTrace/actions/runs/40274461867)
is **SUCCESS**: 798 backend passed / 2 preserved Windows skips, 49 frontend
tests, 80 real Linux parser/security cases, 4 real broker/prefork recovery cases,
4 focused browser cases and 18 full browser cases / 10 preserved skips. Lint,
compilation, builds, migrations, audits and both Docker builds passed. Expected
FK rejections in negative tenant tests are not regression failures.

[Constrained 40274461935](https://github.com/maninani12/ProjectTrace/actions/runs/40274461935)
is **FAILURE**, after both jobs completed. Artifacts were downloaded through
authenticated GitHub CLI and matched GitHub's SHA-256 digests:

| Application measurement | Integration baseline | Candidate 57e71b9 |
|---|---:|---:|
| Artifact ID | 12629614633 | 12630847928 |
| Exit status | 137 | 1 |
| Docker OOMKilled | true | false |
| Final durable stage | ANALYZING | ANALYZING |
| Failure classification | application OOM kill | ANALYSIS_TIME_BUDGET / TimeoutError |
| Coordinator peak RSS bytes | 696,623,104 | 497,123,328 |
| Child peak RSS bytes | 126,119,936 | 140,697,600 |
| Namespace peak RSS bytes | 749,268,992 | 623,890,432 |
| Cgroup peak bytes | 768,000,000 | 768,000,000 |
| Retained valid parser artifacts | 3,747 | 15,329 |
| Published generations / pointers | 0 / 0 | 0 / 0 |
| SQLite integrity / FK violations | ok / 0 | ok / 0 |
| VERIFYING journal events | 0 | 0 |

The final baseline sample preceded the OOM; Docker records the kernel's OOM
state. The deliberate envelope-probe OOMs are separately identified in the raw
evidence and are not application failures. Independent component peaks are not
simultaneous and must not be added; summed RSS can double-count shared pages.

Both runs enforce memory.max **768,000,000**, swap.max **0**, and unchanged
production isolation/parser limits. The manifest remains exactly 21,636 entries,
330,420,155 bytes; 21,269 retained text files. Manifest SHA-256:
`081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89`.
Archive SHA-256:
`95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257`.
No imported repository code was executed.

Complete sanitized receipts and **37,972 application memory samples** are in
[SCALE001_CGROUP_40274461935.json](evidence/SCALE001_CGROUP_40274461935.json) and
its companion compressed JSONL. ZIP hashes and separate envelope-probe receipts
are retained. No source payload, database or key is exported.

## Candidate time, memory and I/O attribution

The candidate's entire sampled attempt lasted 2058.757 seconds. Archive replay
spans about 37.02 seconds and capture 200.207 seconds in inner samples. Committed
ANALYZING time is **1809.807071 seconds**, crossing the existing 1800-second
deadline at the completed-partition progress check. The final failure stack
names `parse_partition -> stage -> check_current`. This is not a qualification
2400-second outer timeout and not a claims or VERIFYING failure.

| Committed component | Seconds | Count |
|---|---:|---:|
| PARTITION_PARSE | 1700.337008 | 159 |
| NATIVE_HELPER_TRANSPORT | 313.777265 | 159 |
| NATIVE_PACKET_VALIDATION | 297.044774 | 159 |
| SYNTAX_HELPER_TRANSPORT | 250.353412 | 104 |
| SYNTAX_PACKET_VALIDATION | 172.102476 | 104 |
| OBSERVATION_SPILL | 94.791298 | 159 |
| CACHE_WRITE | 7.344084 | 159 |

Component/helper times overlap and must not be summed as independent wall time.
PARTITION_PARSE accounts for about 94% of committed ANALYZING. Parent syntax and
native packet validation total about 469.15 seconds inside it. The largest
proven blocking operation is partition parsing; detailed owned profiling below
isolates a reducible validation cost rather than attributing all 1700 seconds
to one function.

Committed work: 15,429 parser-cache misses / zero hits, 100 diagnostic files,
159,934 native metric rows, 10,798,897 tokens, 43,073 native symbols and
381,629,420 aggregate observation-spill ciphertext bytes. None are counts of a
completed quality-output vector. Claims/quality/publication were not reached.

The final candidate sample has 438,136,832 anonymous, 280,399,872 file and
48,975,872 kernel bytes; reclaimable slab is 47,594,480 bytes. Independent inner
peaks: anonymous 577,150,976, file 437,809,152, kernel 59,146,240 bytes.
memory.events reports max=12,638 and oom=oom_kill=0. Reaching memory.max with file
cache does not itself establish an OOM. Final CPU usage is 2092.569079 seconds,
with 0.269919 throttled seconds. Lifetime memory pressure is about 0.491 seconds
and I/O pressure about 9.293 seconds. The recorded device totals are
1,408,507,904 bytes read and 2,924,367,872 written. These are whole-experiment
counters, not per-file spill/encryption accounting. They support investigating
CPU work rather than attributing the deadline solely to reclaim or disk stalls.

The encrypted replay reports no plaintext source on disk. Source encryption,
private typed-row encryption, scope binding and disclosure regressions pass;
there is no separate full-run filesystem-forensic receipt. Post-exit database
integrity does not establish worker recovery. With no complete publication on
either revision, full-workload output equivalence cannot be asserted. Smaller
peaks at fewer completed files do not prove complete-workload memory savings.

## Reproduced privacy-validation cost and minimal correction

An owned replay uses eight native-shaped compact file packets, 400 metrics and
25,600 mixed identifier/operator/literal-hash tokens. Wire size is 1,698,416
bytes; expansion retains both independent observation and cache projections.
It exercises the unchanged pure-Python IPC decoder, expansion and complete
metadata guard. The profiled baseline spends 2.119 of 2.431 seconds in metadata,
including 1.674 seconds in the fixed-format redactor (about 69% of validation).
The pure-Python decoder accounts for 0.311 seconds. Profiling perturbs timings;
the relevant unprofiled comparison is **0.678 -> 0.320 seconds** in fresh Windows
processes. Complete logical output remains 3,390,872 bytes with SHA-256
`716bad37484f44c67a5c379edf94e9502c7132d29d3226947b4b6ac06cd809cf`.

`analyzers/sanitization.py` now tests the finite introducers required by every
supported rewrite. Ordinary identifiers, operators and literal hashes without
an introducer return unchanged after this fixed search. Every possible match
uses the original detailed scanner. No regex or repository-defined grammar is
introduced. Text/type budgets run first; string subclasses retain the old
scanner path. There is no cross-packet/tenant cache or cache-cap increase.
The IPC decoder, depth/node budgets, complete metadata traversal, sensitive-key
masking, collision rejection, schema, scope and source-hash checks are unchanged.
No file, token, claim, metric, symbol or graph edge is removed.

See [packet profiles](evidence/SCALE001_PACKET_PRIVACY_PROFILE.json).
This correction addresses a measured cost within the current blocking stage;
only a new full constrained run can establish its workload-level impact.

## Output equivalence and regression

Focused regression: **93 passed / 2 preserved Windows skips**. This includes
privacy differential coverage against the original scanner, Unicode and mixed
case, sensitive containers, text budgets, sanitized-key collisions, logical
node/depth budgets, complete compact/legacy packet equivalence, truncated-helper
recovery, scope/hash guards, quality storage/recovery and output comparison.
Ruff, compilation and diff checks pass.

The unchanged complete-output comparator matches pre/post owned cold, warm and
incremental snapshots, including every scoped claim/finding, quality metric and
symbol, graph edge, parser artifact, source hash and publication projection.
Fixture administrative IDs/capture timestamp are controlled without changing
execution clocks, budgets, comparison predicates or excluding new fields.
Post-exit SQLite/FK checks pass. These 19-file Windows fixtures are not Linux
large-repository qualification. See
[equivalence receipts](evidence/SCALE001_PACKET_PRIVACY_EQUIVALENCE.json).

An additional owned token-bearing quality benchmark confirms the output-store
tradeoff: 50,000 metrics / 3.2 million tokens / 63,600 output symbols retain
identical 42,962,760-byte output, peak RSS 240,467,968 -> 81,457,152 bytes, build
38.406 -> 117.836 seconds. It does not change the conclusion that the full
candidate never reached this code. The slower quality path remains an open
runtime concern after native throughput is improved.
Raw measurements are retained in the
[token-bearing quality profiles](evidence/SCALE001_TOKEN_BEARING_QUALITY_PROFILE.json).

## Next safe gate

Push only the validated minimal correction to the existing local continuation
branch after verifying the remote head; do not update PR #4, main or older
branches. Run the unchanged regression and full constrained workflows once.
Inspect their actual completed receipts before another implementation change.

SCALE-001 remains **NOT QUALIFIED**. Required evidence still includes complete
cold publication under the unchanged ceiling, then warm/repeat, BASE/HEAD
incremental, complete deterministic output comparisons, cancellation,
memory/disk exhaustion, worker termination/recovery, duplicate delivery,
atomic publication/pointer integrity and tenant isolation. The present driver
cannot award full qualification while dependent scenarios remain NOT_RUN.
