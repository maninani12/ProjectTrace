# SCALE-001 VERIFYING memory recovery

SCALE-001 remains **unqualified**. This record distinguishes the completed
2927693 measurement from the operation-attribution revision and subsequent
memory corrections. Development stays on `codex/scale-001-local-continuation`;
PR #4's shared branch and main are unchanged.

## Confirmed 2927693 results

Authenticated GitHub CLI inspection confirms
[regression 40244419518](https://github.com/maninani12/ProjectTrace/actions/runs/40244419518)
**SUCCESS**, all four jobs: 786 backend / 2 Windows-specific skips, 80 required
Linux cases plus non-root Docker enforcement, 4 real broker cases, 49 frontend
units, 18 full browser / 10 preserved skips plus 4 focused. Builds, migrations,
lint, compilation and audits passed.

[Constrained 40244419571](https://github.com/maninani12/ProjectTrace/actions/runs/40244419571)
**FAILED** on both revisions. Both application containers have Docker
OOMKilled=true / exit 137 at the verified 768,000,000-byte ceiling and zero swap.
These are separate from the deliberate envelope-probe OOMs.

Candidate claims completed in **31.546425 seconds** at this head, including
3.920938 seconds Markdown and 27.623277 seconds OpenAPI. It consumed 2,275 JSON
sources / 19,275,081 bytes in 49 batches. ANALYZING took 1665.516764 committed
seconds. These values do not inherit the earlier head's 24.987-second timing.

The candidate then OOM-killed under VERIFYING. Last inner sample was 2053.979
seconds total; its VERIFYING span was at least 171.584 seconds. Coordinator RSS
peaked at **767,320,064 bytes**. The last host record caught **oom=1 / oom_kill=1**
after the kill; its reduced charge is not the pre-kill peak. Native aggregates:
195,982 metric rows, 12,435,603 tokens, 53,467 symbols and 457,995,144 aggregate
spill ciphertext bytes. Parser artifacts retained: **18,756**; SQLite integrity
ok / zero FK violations; published generations and pointers **zero**. Baseline
again OOM-killed in ANALYZING with 3,747 artifacts and intact DB/FKs.

Raw receipts and **38,199 application samples** are preserved in
[SCALE001_CGROUP_40244419571.json](evidence/SCALE001_CGROUP_40244419571.json) and
`evidence/SCALE001_CGROUP_40244419571_MEMORY.jsonl.gz`. Original artifact IDs,
ZIP hashes and full manifests are retained. The pinned 21,636-entry manifest is
unchanged. Cold RUNNING after SIGKILL is stale; all later scenarios are NOT_RUN.
The durable profile is the VERIFYING entry checkpoint and cannot identify the
operation executing at death. Database integrity is not fresh-worker recovery.

## Read-only owned profiling before implementation changes

Installed quality aggregation was profiled with fresh, encrypted, inert metric
rows on Windows / CPython 3.14.3. No imported repository code ran. Public output
was serialized completely, preserving ordered metrics and symbols; only the
existing generated quality duration was removed from the deterministic hash.

| Owned rows | Python live before build | At duplication entry | After build |
|---|---:|---:|---:|
| 10,000 | 690,731 | 29,397,329 | 31,607,963 |
| 50,000 | 891,487 | 144,371,899 | 155,550,065 |

At 50,000 rows, decoded JSON keys/strings/objects retain 98,816,378 bytes and
the metric-dictionary projection retains 42,042,848 bytes before duplication
begins. The per-path list/index is comparatively small. A separate **untraced**
process measured 35,508,224 input RSS -> 195,674,112 at duplication entry ->
207,810,560 after build. Tracemalloc snapshots greatly perturb RSS, so their
process peaks are not production-memory evidence. Both 50,000-row runs emit
50,000 metrics and 50,000 symbols, 39,835,983 bytes, SHA-256
`5d6572bfc5a48a1620989253e768e4219ab6274d0fac26da6afc4044735560e5`.

[Owned baseline receipts](evidence/SCALE001_VERIFYING_OWNED_BASELINE.json) show
linear retention in token-free metric and symbol materialization. This is a
measured candidate bottleneck, not yet precise allocation attribution for the
full cgroup workload. No large-repository pass or complete-workload speedup is
claimed from this fixture.

## Persistent operation-attribution revision

The qualification-only recorder flushes START/END/ERROR records with elapsed
time, coordinator/namespace RSS and cgroup charge/stat/events at fixed owned
boundaries. It records no arguments, return data, source, exception messages,
database files or keys. The journal is streamed; memory does not grow with the
event count. A START without END localizes a killed operation. Kernel/RSS HWM
counters are lifetime peaks, not per-operation peaks; independent component
peaks must not be summed.

Boundaries cover claim verification, storage declarations, infrastructure links,
quality inventory, **metric projection**, owner index, production selection,
duplication, **symbols**, rule evaluation, final identity, implementation claims,
checkpoint serialization, publication preparation and generation validation/
promotion. The small optional quality observer has no default behavior change.
The baseline retains its old production modules; unsupported internal observer
callbacks are not injected into its historical API. No production limit changes.

The full owned cold/warm/incremental fixture retains all scoped claims, metrics,
symbols, findings, nodes, edges, hashes, parser artifacts and quality projections.
Its initial independent runs differed in administrative history timestamps and
generation-derived review IDs; those private runs are preserved and are not
reported as equivalence passes. Fresh repeats control fixture administrative ID
streams and the capture timestamp, without changing the execution clock, budgets,
comparison predicates or omitting fields. They compare equal across three
complete snapshots, with independent post-exit SQLite/FK checks. See
[complete fingerprints](evidence/SCALE001_VERIFYING_BASELINE_EQUIVALENCE.json).

Recorder/ownership/diagnostic selection: 12 passed. Quality/comparison/recorder
selection: **49 passed** (overlapping selections, do not sum). Repository Ruff,
compilation and diff checks pass. These Windows development tests are not Linux
enforcement evidence. The next qualification must identify the actual growing
operation before a correction is presented as the large-run OOM remedy.

## Remaining acceptance

No full cold publication has passed. Warm, incremental, cancellation, exhaustion,
fresh-worker recovery and concurrent-tenant qualification remain open under the
same agreed process-tree cgroup ceiling. Graph/correlation, checkpoint buffering,
encryption, serialization and generation restoration remain potential later
size-dependent costs. No evidence may be dropped and no limit raised to turn
this result into a pass. PostgreSQL and real Redis/Celery acceptance remain
separate Linux gates. Cold-only success would not close SCALE-001.
