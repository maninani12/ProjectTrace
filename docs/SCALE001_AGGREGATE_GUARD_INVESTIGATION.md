# SCALE-001 aggregate guard investigation

Date: 2026-10-29 (Windows local investigation)

**Decision: STOP — SCALE-001 remains NOT QUALIFIED.** The reproduced complete
50k logical snapshot contains 1,115,947 nodes under the sanitizer's actual
counting rules. The unchanged aggregate cap is 1,000,000. Lossless storage,
streaming, or compression cannot make this logical value admissible without
changing the cap's semantics. Resetting the counter per page would be a policy
change, so no storage candidate qualifies under the current instruction.

Commercial V1 remains **DEVELOPMENT IN PROGRESS**. This is Windows-only
evidence; it does not qualify Linux, PostgreSQL, distributed workers, or the
full Commercial V1 release.

## Repository preservation

The investigation used `C:\Users\sai krishna\Projects\ProjectTrace-local`.
At entry the branch was `codex/scale-001-local-continuation` and HEAD was
`9e21509591bfa5457cc829ebd5637f95be68d573`, matching the requested values.
The pre-existing worktree had 10 modified tracked files (287 insertions and
86 deletions) and a large set of untracked development, evidence, and database
artifacts. Those changes were left in place. The four preserved benchmark
databases were SHA-256 checked against their existing baseline receipt before
and after this investigation; all four still match.

The new files are this report, its machine-readable receipt, and
`tests/test_sanitization_aggregate_guard.py`. The only other edits are this
addendum to ADR 0007 and a dated note appended to `PROJECTTRACE_PROGRESS.md`.
No production module, database, migration, published snapshot, sanitizer
limit, or admission behavior was changed. No commit, push, PR, workflow,
production migration, or destructive Git command was used.

## Actual sanitizer policy

`analyzers/sanitization.py:metadata` starts a fresh local counter at zero for
each call. Its recursive `visit` increments once for the current value before
checking the depth and node budgets. The default maximum is 1,000,000; a call
raises `ValueError("Sanitization structure budget exceeded")` when the
counter becomes 1,000,001. Root containers count. Lists and tuples count once
and each visited element counts. Dictionaries count once and recursively
visited values count; dictionary keys are type-checked, stringified and
sanitized, but do not themselves increment the node counter. Strings and
scalar values count when visited. Ordinary nested dictionaries, references,
nulls, and non-sensitive values follow these same rules. Non-null values under
sensitive keys are replaced by `"[REDACTED]"` without recursively visiting
their contents, so those contents do not contribute. The depth limit is 60.
The optional `maximum_nodes` argument can override the default, but the
production final-snapshot call uses the default.

The guard is per sanitizer invocation, not intrinsically shared across
separate calls. `add()` sanitizes each record independently, and several
update paths sanitize individual records. Those calls do not constitute the
one complete final snapshot. The complete final snapshot path in
`backend/domain.py:persist_analysis` builds `snapshot.data` from the previous
snapshot fields, captured snapshot fields, and final claims, findings,
dependencies, cloud assets, risk paths, changed lines, quality summary/gates,
drifts, impact and status, then calls `sanitize_metadata` on the complete
mapping at line 1816. The direct 50k reproduction hits that same sanitizer
operation before snapshot publication. The evidence receipt explicitly does
not claim a fresh full 50k analysis or publication attempt.

No alternate production snapshot admission limit was found in these call
sites. The `Generation.validate` path is not an alternate sanitizer: it reads
the inline captured collections, builds six full ID-indexed dictionaries,
then validates output rows in bounded batches. Other relevant whole-value
paths remain: `comparison_snapshot` selects complete requested JSON arrays;
`quality_fields` reads complete JSON members; quality comparison builds a
previous-metric dictionary; snapshot/quality persistence serializes whole JSON
values; and generation validation decodes and canonicalizes the full snapshot
for its digest. Bounded fetch batches do not eliminate these complete
materializations.

## Boundary reproduction and exact 50k count

A focused test creates a top-level list with `N-1` scalar children, so its
sanitizer node count is exactly `N`. Three fresh Python 3.14.3 processes
executed the actual sanitizer:

| Logical nodes | Result | Duration | Process peak RSS |
|---:|---|---:|---:|
| 999,999 | accepted | 0.159 s | 40,550,400 bytes |
| 1,000,000 | accepted | 0.172 s | 40,755,200 bytes |
| 1,000,001 | rejected with the existing budget error | 0.171 s | 40,771,584 bytes |

Durations and peak working sets are single-process observations, not a
throughput claim. `tests/test_sanitization_aggregate_guard.py` encodes the same
three cases. Since pytest is not installed in the available Python 3.14 or
3.11 environments, the pytest test file could not be invoked; the standalone
runner directly executed the same acceptance and error assertions.

The 50k fixture was built from the preserved 30k database by cycling its
complete metric rows to 50,000 and retaining all other snapshot fields. A
second independent structural walk, matching the sanitizer's node traversal
and sensitive-value skip behavior, counted **1,115,947** logical nodes:

- preserved 30k database SHA-256: `c7313fd66baa9e23ec5f5a7e9bdb8003554d086796c101be14f8d02d6ee5e9a4`;
- source snapshot JSON: 26,197,173 bytes;
- complete logical count: 1,115,947;
- excess over unchanged cap: 115,947 nodes;
- actual sanitizer outcome: `ValueError: Sanitization structure budget exceeded`;
- existing direct-reproduction duration: 2.463 s; process peak RSS: 126,091,264 bytes.

The prior full final-snapshot profile records 681,257 nodes for the complete
30k case. It reports 10k at 261,257 nodes. Its 30k run variants produced
5.21–12.96 s final-path time and 522.6–523.5 MB sampled peak RSS, but those
variants used different instrumentation and are not a controlled timing
comparison. The 50k guard reproduction is not an end-to-end performance run.

## Allocation and candidate assessment

Existing owned profiling identifies multiple complete-value costs on the
successful 30k path: final snapshot assembly and recursive sanitization make a
new sanitized structure; quality persistence serializes a 24,971,033-character
JSON value; final snapshot persistence serializes a 26,197,173-character JSON
value; SQLite snapshot update reached a sampled process peak of 502,472,704
bytes, with SQLite's measured peak malloc at 350,664,352 bytes; and
`Generation.validate` loads the captured arrays into full dictionaries before
processing output rows in bounded batches. Its canonical fingerprint also
serializes the complete snapshot. The exact measured components and provenance
are in the pre-existing final snapshot profile evidence linked from the new
receipt.

No candidate was eligible for end-to-end comparison because the first
non-negotiable condition—unchanged aggregate admission—fails for 50k:

| Candidate | Aggregate treatment | Disposition |
|---|---|---|
| Streaming persistence / validation / BASE-HEAD iteration | Could lower materialization costs, but the complete logical value still has 1,115,947 nodes when admitted. | Does not fix the admission conflict. Whole-array paths also remain in existing persistence, comparison, and validation code. |
| Compact lossless encoding or compression | Decoding restores the same logical values and node count. Counting only a smaller descriptor or encoded byte stream would not satisfy the existing rule. | Still rejected at 1,115,947 nodes. |
| Independent page sanitization | Resets the per-call counter and would admit pages whose aggregate logical count exceeds one million. | Rejected because it changes the policy. |
| Generation map iteration optimization | Existing isolated 50k map evidence reports 47.44 s median before and 5.70 s after iteration changes, with peak RSS 129,028,096 and 128,094,208 bytes respectively. | A scoped map-only improvement; it does not change final snapshot admission or remove validation's six captured maps. It is not a qualifying 50k snapshot result. |

No new snapshot storage format was prototyped. Doing so could not establish
admission under the current policy; a segmented prototype would fail the
explicit aggregate requirement or silently change it. No broad suite was run
against such an invalid candidate.

## Equivalence, test status, and limits

The boundary assertions passed in the isolated direct runner: 999,999 and
1,000,000 nodes accepted; 1,000,001 rejected with the unchanged error. The
independent 50k counting walk agrees with the direct sanitizer rejection. The
existing owned cold/warm/incremental, replay, SQLite integrity, FK, graph
ownership, audit, and tenant evidence remain historical results; they were
not rerun for this investigation and do not validate a new candidate. The
new pytest test is not run because pytest is unavailable. No other test suite
was run. No result in this report upgrades SCALE-001 qualification.

The machine-readable evidence at
`docs/evidence/SCALE001_AGGREGATE_GUARD_INVESTIGATION.json` records the exact
commands, Windows/Python/SQLite environment, initial Git state and existing
database hashes, boundary measurements, 50k count, relevant existing
measurement sources, test availability, and output hashes.

## Required policy decision

This investigation selects neither option. A product/security owner must
choose between:

1. Keep the 1,000,000-node aggregate limit and explicitly treat logical
   snapshots above it as unsupported; or
2. Request an explicit product/security policy decision to change the limit
   or redefine its semantics, followed by resource-budget analysis, threat
   review, a versioned aggregate admission contract, and new acceptance tests.

Until the decision is made and the required gates pass, ADR 0007 remains
**NEEDS POLICY DECISION**, SCALE-001 remains **NOT QUALIFIED**, and Commercial
V1 remains **DEVELOPMENT IN PROGRESS**.

## SP-B investigation authorization and bounded-policy proposal (2026-10-29)

The current task authorizes **SP-B investigation only**. It does not authorize a new cap or admission semantics. The current sanitizer still counts one complete logical value against 1,000,000 nodes. The recorded “50k” case is 50,000 metric rows in a complete snapshot fixture, not 50,000 files: its independent structural count is 1,115,947 nodes, 115,947 above the current cap. The direct sanitizer reproduction rejects before snapshot SQL persistence, `Generation.validate`, BASE/HEAD comparison, or publication; none of those later costs has been measured for this fixture.

The smallest defensible future policy work is to define a workload envelope rather than select a larger node number from this one observation. Keep node count, serialized bytes, maximum depth, maximum scalar size, collection width, snapshot assembly, checkpoint bytes, SQL/native allocations, generation validation, BASE/HEAD work, concurrent-tenant isolation, time, cancellation, and recovery as separate measured dimensions. A complete accepted target must pass all of them under the existing process-tree resource envelope. A policy proposal must state which dimensions are security bounds and which are operational bounds, and how rejection leaves no COMPLETE snapshot or pointer. A page-local counter reset, compression-based node count, or partial sanitization is not compatible with the current rule.

No numeric future threshold is selected here. Establishing one requires an independently reproducible owned fixture, complete end-to-end measurements through persistence/validation/comparison/publication, adversarial boundary tests, threat review, operational headroom, and explicit product/security approval. Until then, logical values over 1,000,000 nodes remain unsupported by this sanitizer path. The investigation evidence and measured limits are recorded in `docs/evidence/SCALE001_CP_B_SP_B_INVESTIGATION_20261029.json`.
