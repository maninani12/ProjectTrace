# SCALE-001: bounded global checkpoints (local, uncommitted)

Status: **NOT QUALIFIED**. Base and current HEAD are
`9e21509591bfa5457cc829ebd5637f95be68d573`, branch
`codex/scale-001-local-continuation`. This implementation is local only. No
commit, push, PR change, merge, deployment or workflow dispatch was authorized
or performed. Migration tests use fresh owned databases; no deployment database
was migrated.

## Verified failure and exact cause

[Regression 40280428892](https://github.com/maninani12/ProjectTrace/actions/runs/40280428892)
completed successfully: all four jobs, 801 backend cases / 2 platform skips,
49 frontend units, 80 Linux parser/security cases, 4 real broker-recovery cases,
4 focused plus 18 full browser cases / 10 preserved skips. These results apply
to the published base, not the uncommitted checkpoint changes.

[Constrained 40280429009](https://github.com/maninani12/ProjectTrace/actions/runs/40280429009)
completed with both workload jobs failed. Candidate artifact **12633028505** has
SHA-256 `3b61c5dd4cfe863f82241c99fc648db06f50b30b1e6f5e0c810090c8ab4ae411`;
baseline artifact **12631224908** has SHA-256
`b66221363c7cca3608eed5c81420e4ff7929758f4f40a64c12bb67b2e8ce5df5`.
Authenticated GitHub CLI downloads matched both digests. Both failed jobs' logs,
qualification, envelope, integrity, memory and operation records were inspected.

| Candidate measurement | Verified result |
|---|---:|
| Exit / Docker OOMKilled | 1 / false |
| Error / stage | GLOBAL_CHECKPOINT_BUDGET / VERIFYING |
| Configured checkpoint maximum | 64,000,000 bytes |
| Committed ANALYZING | 1173.218985 seconds |
| Claim extraction stage | 25.077880 seconds |
| Quality aggregation | 183.295558 seconds |
| Final identity | 301.930217 seconds |
| Committed VERIFYING | 513.642960 seconds |
| Entire sampled attempt | 1875.465 seconds |
| Coordinator / child peak RSS | 582,090,752 / 165,163,008 bytes |
| Namespace peak RSS | 661,950,464 bytes |
| Enforced cgroup peak / swap maximum | 768,000,000 / 0 bytes |
| Valid parser artifacts / diagnostic files | 18,756 / 103 |
| Native metrics / tokens / symbols | 195,982 / 12,435,603 / 53,467 |
| Aggregate native spill ciphertext | 457,995,276 bytes |
| Published generations / pointers | 0 / 0 |
| SQLite integrity / FK violations | ok / 0 |

The final inner sample has 492,417,024 anonymous, 225,976,320 file and 49,434,624
kernel bytes. Its max-event count is 75,479, with oom=oom_kill=0. File cache and
independent RSS peaks are not equivalent to cgroup charge; component peaks must
not be added. Baseline again OOM-killed in ANALYZING, exit 137. Deliberate
resource-envelope probe kills are kept separate from application outcomes.

The candidate's 46 operation events include GLOBAL_CHECKPOINT returning after
about 2.069 seconds. `analysis_checkpoints.save` returned False while building
its one uncompressed JSON bytearray; `jobs.save_checkpoint` then raised the
existing guarded IntakeError. It did not fail from an OOM or an outer timeout.
`domain.persist_analysis` invokes this save before publication preparation,
generation admission and evidence/graph publication. Consequently no incomplete
generation or pointer was published.

The serializer iterates lazy collections but accumulates their entire JSON in
one buffer. It repeats shared projections (`result.quality_metrics` and
`result.code_quality.metrics` refer to the same collection). The old reader
decrypts and `json.loads` the whole receipt. Merely splitting ciphertext and
joining it on recovery would preserve that materialization defect. The failed
receipt supplies a lower bound exceeding 64 MB, not an exact full serialized
length; the encoder stopped at the guard.

Raw receipts, operation boundaries and **35,884 application memory samples**
are preserved in [SCALE001_CGROUP_40280429009.json](evidence/SCALE001_CGROUP_40280429009.json)
and its companion compressed JSONL. No source payload, DB or encryption key is
included.

## New v2 representation and resource contract

`backend/checkpoint_pages.py` stores collection rows as canonical JSON frames,
compressed into pages and authenticated with the existing Fernet/MultiFernet
keyring. An encrypted manifest describes the complete object, counts, ordering,
page ranges and SHA-256 collection digests. Repeated collection owners are
stored once and restored as shared views. Reference syntax is out-of-band from
user JSON values, so literal `schema`, `$ref` and similar keys remain data.

The 64,000,000-byte setting is **not increased or applied once per page**. The
representation changes from uncompressed monolithic JSON to compressed encoded
pages. All retained encrypted page payloads plus the active manifest, including
staging attempts, must fit that aggregate budget. Logical expanded output can
exceed 64 MB because of compression and shared references; this is not a claim
that the old uncompressed JSON fits the original buffer. Database indexes/WAL
are not counted as payload bytes, just as the legacy guard did not account for
database overhead. No resource-limit environment value or production ceiling
was raised.

Additional explicit bounds:

- Decoded page: 256,000 bytes. A writer buffer holds fewer than two pages.
- Atomic row/manifest: at most `min(32,000,000, checkpoint budget) - 4096`
  encoded bytes, reserving space for the private replay scope envelope.
- Metadata descriptor traversal: depth 60 and at most 256,000 nodes.
- Private replay: one encrypted SQLite owner and its existing 1 MB cache for
  all collections, under the unchanged `ANALYSIS_OBSERVATION_SPILL_BYTES` cap.
- Computation checks: bounded cadence during serialization; every durable page
  write and admission uses the existing fenced checkpoint/deadline callback.
  Replay checks between pages and bounded groups of rows.

The new byte guard still rejects incompressible excess, oversized rows and
manifests. `jobs.py` retains GLOBAL_CHECKPOINT_BUDGET on a False save; it cannot
continue publication without a complete receipt. Exceptions other than the
existing explicit budget-return contract propagate. Privacy/schema, parser,
tenant, source-hash and time limits are unchanged. The format does not use
pickle, external file references or executable deserialization.

## Admission, concurrency and recovery

Pages belong to a random attempt and are scoped to job, organization,
repository, signature, collection and page ordinal inside authenticated data.
The new table also has a composite tenant/job FK. Every page commits in a short
fenced transaction. Long serialization and replay use read-only lease checks,
allowing an external cancellation writer to proceed.

An active receipt remains valid while a replacement stages. Before atomic
manifest replacement, the writer refreshes the root, rechecks aggregate quota
and validates its complete staged page inventory under the writer lock. A
reproduced tokenless interleaving initially allowed an older writer to admit
pages already reaped by a newer writer; the final guard rejects that attempt
and preserves the newer complete receipt. No public generation pointer is
touched by checkpoint staging.

On an interrupted save, only that attempt's unreachable pages are reclaimed.
An actual subprocess exit before admission leaves the prior complete root
readable; the next fenced attempt reaps orphan staging. If a commit succeeds
but its acknowledgement is lost, admitted pages are preserved and the original
error is propagated. Retry can recover them; the error is not suppressed.

Recovery authenticates the root and every ordered page, checks exact counts,
digests, page/row bounds and scope, then copies bounded row snapshots into one
attempt-private encrypted store. No complete collection is joined or loaded
into a Python list. The result is returned only after validation of the entire
page inventory and a final check that its root did not change. Missing,
swapped, extra, expired, corrupted and over-expanding pages fail closed.

The local path/ordinal index holds HMAC tags and integers. Encrypted replay rows
bind collection and position, rejecting index substitution. Shared metric views
preserve persisted new-code annotations. Inventory ownership updates explicitly
replace lazy snapshots, so mutations survive subsequent reads. These are the
existing encrypted-row snapshot semantics, not arbitrary in-place list-row
mutation semantics.

The replay owner is registered for attempt cleanup. Failed/cancelled attempts
close it; successful consumers keep it alive through final serialization. Replay
remains readable after durable checkpoint cleanup. Admission data is removed
atomically with successful publication; unrelated or historical public output
is untouched. Expired orphan-page reclamation is batched, and normal job/quota
history is retained.

## Compatibility and migration

Migration **0026** adds the parts table and a format marker defaulting existing
rows to v1; their ciphertext/digest bytes are preserved. The reader retains the
original v1 envelope checks and logical JSON result. Legacy decoding retains
its historical bounded monolithic format; the new large-result path writes v2.
Existing publication/generation receipt formats are unchanged.

Downgrade refuses while v2 manifests or staged pages remain. Operators must
complete/expire recovery state before removing its schema. Tests cover legacy
byte preservation and safe rollback. No deployed database was altered here.

## Actual local validation

- Broad selection: **136 passed / 2 preserved platform skips**, 583.88 seconds.
  Checkpoints, quality storage, migrations, generation interruption/promotion,
  deadlines, lease races, queue fairness, parser packets and output comparison.
- Final checkpoint suite: **29 passed**, 19.99 seconds, including the admission
  race guard, key rotation and real independent-session cancellation. Selections
  overlap and must not be added. The admission guard was added after the broad
  run; its affected checkpoint paths were rerun in the final suite.
- Ruff, compilation and diff checks pass. No tests were removed or weakened.
  The migration-head assertion advances to 0026 and gains schema/rollback checks.
  An inconsistent run started before the final schema marker was added was
  stopped and excluded; the consistent rerun supplies the broad result above.
- Complete pre/post owned cold/warm/incremental fingerprints match, including
  claims, findings, metrics/symbols, every scoped graph edge, parser artifacts,
  source inventories/hashes and quality projections. The unchanged comparator
  has no added normalizations or omissions. Prior fixture administrative ID/
  capture-time controls remain; each post-exit DB passes SQLite/FK checks.

The owned >64 MB experiment uses fresh writer and recovery processes:

| Measurement | Legacy writer | V2 writer | Fresh v2 replay |
|---|---:|---:|---:|
| Complete logical JSON bytes | 161,787,896 | 161,787,896 | 161,787,896 |
| Save/replay result | rejected | complete | identical full hash |
| Peak RSS bytes | 208,044,032 | 99,979,264 | 98,533,376 |
| Operation seconds | 1.429 (rejected) | 9.694 | 1.642 |
| Encrypted pages + manifest | none | 1,568,540 bytes / 322 pages | fully authenticated |

All 12,000 owned metric rows, both logical metric projections, symbols, claims,
findings and graph values are retained. Complete JSON SHA-256:
`f735a9a9b08c668cda4be224877fff4915c41a5d68ba0f7331572228ee0f07ee`.
These repeated-text Windows inputs prove bounded complete checkpoint/replay,
not OpenMetadata's compression ratio or full Linux workload success. Timings
overlap regression activity and are not a controlled throughput comparison.

See [owned measurements](evidence/SCALE001_CHECKPOINT_PAGES_OWNED.json) and
[complete equivalence](evidence/SCALE001_CHECKPOINT_PAGES_EQUIVALENCE.json).

## Remaining gates and next safe action

SCALE-001 remains **NOT QUALIFIED**. No Linux cgroup, PostgreSQL, real broker or
full pinned-workload run has been performed for these uncommitted changes.
After review and explicit authorization, validation must keep the same
768,000,000-byte / zero-swap envelope, pinned 21,636-file input and all original
parser/security/time limits, measuring actual checkpoint bytes/pages, replay
scratch, operation durations, complete outputs and final publication.

The inspected downstream generation implementation still has its existing
64 MB per-stage context guard and joined v1 context restoration. Large captured
snapshot/quality contexts, final sanitization/materialization and publication
are remaining scale risks; this change does not relax those guards or claim to
solve them. The earlier final-identity/inventory costs also remain measured
runtime concerns. A completing global checkpoint alone is not full publication.

Required acceptance still includes cold publication, warm/repeat and BASE/HEAD
incremental equivalence, cancellation, actual memory/disk exhaustion, worker
termination/recovery, duplicate delivery, tenant isolation and atomic pointer
integrity. Local quota and process-exit tests are not those full-scale gates.
The next safe action is to review the uncommitted diff and, only with explicit
authorization, commit/push and run the Linux qualification. No such action was
performed during this task.
