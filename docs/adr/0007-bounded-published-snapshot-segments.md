# ADR 0007 — bounded published snapshot segments

Status: **PROPOSED — requires an explicit architecture/admission decision**.
No production schema, snapshot payload format, public reader or migration has
been changed for this proposal. SCALE-001 remains NOT QUALIFIED.

## Reproduced problem and rejected shortcuts

The existing owned 50k final-snapshot job fails the unchanged 1,000,000-node
sanitizer guard before publication. The new direct reproduction uses complete
metric rows from the preserved 30k snapshot, cycles them to 50k and calls the
actual sanitizer without modifying its arguments. This is direct guard evidence,
not a new full-job/cgroup result. Commands and receipts are recorded in the
Commercial V1 progress/evidence work root.

`backend/domain.py:persist_analysis` captures `quality_metrics`, constructs the
final full snapshot and sanitizes it. `backend/quality_domain.py:persist` also
stores complete quality data. `Generation.validate` hydrates complete Record
JSON, checks relationships and hashes its canonical document. SQLAlchemy must
bind a complete JSON string; the four original graph indexes evaluate against
that full string even when their graph keys are absent.

Preserving only a small descriptor without adapting readers would lose logical
output. Increasing the sanitizer guard, dropping metrics, bypassing validation,
publishing partial state as COMPLETE, or adopting a rejected index projection is
not an acceptable correction.

## Smallest plausible direction

Use a **new, explicit immutable snapshot format for new captures only**, with
bounded authenticated content segments for large observation arrays. Keep the
original Record table, graph-key JSON fields, four indexes and read ordering.
Existing inline snapshots remain unchanged and readable.

Reuse persistent encrypted content-object primitives only after proving their
ownership, retention and backup contracts for this purpose. A permanent segment
must bind organization, repository, snapshot/generation, field, ordinal, count,
codec version and content digest in its authenticated identity. A complete
manifest admits exactly its segment inventory, order and logical hashes.
Staged objects remain private; publication atomically admits the parent and its
complete authenticated references. Retry is idempotent; cancellation/exhaustion
cannot publish dangling references. GC must distinguish abandoned private
objects from permanently referenced published objects.

**Do not reuse expiring GenerationContextPart/GenerationChunk rows as permanent
snapshot storage.** Their normal 72-hour expiry intentionally removes private
recovery data even for published generations. Temporary EncryptedRows owners
also have attempt-local lifetimes. Either would create dangling snapshots.

## Decision requiring approval

The current sanitizer's million-node rule applies to one complete materialized
document. Segmenting changes that admission/persistence contract even if every
segment and manifest retains the existing node/depth/byte guards. It therefore
requires a versioned, reviewed policy defining aggregate encrypted quota,
per-row bounds, descriptor inventory, complete verification and permanent
retention. It must not be introduced as an invisible per-page reset of a global
guard. No existing memory, time, spill or checkpoint quota may be raised.

Approval must also settle the logical read contract. Existing consumers include:

- Record/source inspector and ordinary JSON/SQLAlchemy serialization;
- `snapshot_context.comparison_snapshot` / `quality_fields` SQL JSON projections;
- Claim Ledger, graph/correlation/history and BASE/HEAD comparisons;
- typed v1/v2 generation replay and final validation/canonical fingerprints;
- quality metrics APIs, pagination, exports, trust/coverage and source inventory;
- backup/restore, key rotation, retention, forward/reverse migration and all
  tenant/private-generation visibility rules.

Readers cannot assume a descriptor is an array. A compatibility resolver or
versioned API must preserve complete values, order, typed references and all
documented output semantics. Streaming HTTP JSON must not accidentally perform
full `jsonable_encoder`/Pydantic materialization before sending. No caller may
load all segments merely to satisfy an old `.data` access under the memory gate.

## Required proof before a production proposal

1. A failing intended-success 50k regression with complete owned observations.
2. Complete old-inline versus segmented logical output, ordering and canonical
   digest equality; v1/v2 receipt and legacy snapshot compatibility.
3. Missing/swapped/corrupt/cross-tenant pages, quota overflow, key rotation,
   partial writes, cancellation and actual process-exit recovery fail closed.
4. No orphan publication; immutable previous generations/pointers/audit history
   remain intact. Segment expiry cannot remove published data.
5. Supported API/frontend readers, exports, SQL projections and BASE/HEAD
   comparisons work through the real versioned path.
6. Fresh-process small/10k/50k resource measurements, then the separately
   authorized full pinned Linux 768,000,000-byte, zero-swap acceptance matrix.

The design is not SAFE TO MIGRATE or implemented. Continue independent expiry,
commercial workflow and security validation while this decision is pending.

## Engineering review — 2026-10-29

Disposition: **NEEDS POLICY DECISION — not approved for implementation**.

The central concern is the interaction with the existing 1,000,000-node
sanitizer limit. The reproduced 50k logical snapshot is rejected because the
complete value crosses that limit. Sanitizing each segment independently and
admitting a manifest whose aggregate logical value exceeds 1,000,000 nodes
would change the effective aggregate admission limit, even if every page keeps
the existing per-call node and byte checks. This would be a policy change, not
only a storage implementation. Under the current instruction to keep the
global guard unchanged, segmenting cannot make this 50k logical snapshot
admissible. The proposal must explicitly resolve that conflict before code is
written.

The memory path also has materialization points beyond SQL binding:

- `backend/domain.py:persist_analysis` assembles the complete final snapshot
  mapping and passes it to `sanitize_metadata`, which recursively constructs a
  full sanitized copy before persistence.
- `backend/quality_domain.py:persist` stores the complete quality projection,
  while the snapshot also captures `quality_metrics`; metrics therefore have
  two logical persisted locations whose readers and canonical equality must be
  addressed together.
- `backend/generations.py:Generation.validate` builds full ID-indexed maps for
  six captured collections before it validates staged records. Replacing only
  the SQL bind with segment writes would leave this simultaneous materialization
  in the publication path.
- `backend/snapshot_context.py:comparison_snapshot` selects complete captured
  arrays for the fields it requests. `quality_fields` similarly selects whole
  JSON members. `backend/quality_domain.py:apply_comparison` builds a complete
  previous-metric dictionary, and history walks retain complete finding arrays
  for up to 200 ancestors. A descriptor-aware format must provide bounded
  consumers at each of these paths; an implicit `.data` resolver would not
  change these SQL JSON projections or bound their allocations.

The proposal correctly identifies permanent retention, tenant-bound
authentication, atomic admission, legacy inline reads, and the expiring
checkpoint tables as design concerns. It is not yet an implementable contract:
it does not select the durable storage primitive/schema, define the exact
versioned logical-to-physical representation, specify behavior for SQL JSON
expressions and ordinary serialization, or give an aggregate logical-node
admission rule. Atomic publication also needs to state whether all segment
bytes and the manifest share a database transaction or how a separate object
store is recovered after process exit.

**Recommendation:** do not implement ADR 0007 under the current unchanged
global sanitizer rule. First settle whether the 1,000,000-node bound applies to
the complete logical snapshot or to each authenticated stored object. If it
remains aggregate, the 50k requirement needs a lossless representation that
still satisfies that aggregate bound; otherwise the requirement and the
no-limit-change rule conflict. After that decision, revise the ADR with the
durable ownership/transaction model and a caller-by-caller streaming or
pagination contract, then review it again before implementation. No code,
schema, migration, snapshot format, or admission behavior was changed for this
review.

## Aggregate guard investigation addendum — 2026-10-29

Disposition: **STOP — NEEDS POLICY DECISION. SCALE-001 remains NOT QUALIFIED.**

The actual `analyzers.sanitization.metadata` traversal counts the root and each visited container/value, but not dictionary keys. Non-null values under sensitive keys are redacted without recursively visiting their contents. The default aggregate maximum is 1,000,000 visited nodes per call. A boundary reproduction accepted 999,999 and 1,000,000 nodes and rejected 1,000,001.

An exact count using those same traversal rules over the complete preserved 50k snapshot fixture is **1,115,947**, or **115,947 above the unchanged cap**. The fixture retains all original snapshot fields and cycles complete metric rows from the preserved 30k database to 50,000 rows. The actual sanitizer raises `ValueError("Sanitization structure budget exceeded")` while `persist_analysis` sanitizes the complete assembled final snapshot, before publication. The direct reproduction took 2.463 seconds and reached 126,091,264 bytes process peak RSS; it is not a full analysis/publication run.

Streaming, lossless compact storage, or compression can reduce some materialization costs but cannot admit this logical value while preserving the current node rule. Sanitizing pages independently would reset the per-call counter and admit an aggregate above the policy limit, so it is rejected. No production representation or admission behavior was changed. The report and machine-readable receipt are `docs/SCALE001_AGGREGATE_GUARD_INVESTIGATION.md` and `docs/evidence/SCALE001_AGGREGATE_GUARD_INVESTIGATION.json`.

The product/security decision remains open:

1. Keep the 1,000,000-node aggregate limit and explicitly leave larger logical snapshots unsupported; or
2. Explicitly change or redefine the policy, then complete resource-budget analysis, threat review, and new acceptance tests before implementation.

Neither option is selected by this addendum. Commercial V1 remains **DEVELOPMENT IN PROGRESS**.
