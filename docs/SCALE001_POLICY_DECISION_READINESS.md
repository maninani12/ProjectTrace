# SCALE-001 policy decision readiness

Date: 2026-10-29. Scope: local Windows investigation and test recovery.

**Recommendation: retain the 1,000,000-node aggregate guard for now (Option A),
with an explicit product-owner decision that larger logical snapshots are
unsupported. Do not claim 50k support or qualification.** The evidence proves
that the owned 50k snapshot is rejected by policy. It does not prove that a
higher budget would be safe: the successful-path persistence, validation,
BASE/HEAD comparison, concurrency, and bounded-memory behavior at 50k have not
been measured. Any future Option B proposal is a separate product/security
policy change and requires explicit approval before an over-limit path is
exercised.

**Status remains SCALE-001 NOT QUALIFIED and Commercial V1 DEVELOPMENT IN
PROGRESS.** The worktree branch and HEAD were unchanged from the requested
values. The four original databases still match their existing SHA-256
receipts. No production code, schema, migration, sanitizer limit, admission
behavior, or snapshot format was changed.

## Executive finding

An independent structural walk of the reproduced fixture counted 1,115,947
logical nodes, 115,947 above the current limit. The new regression test
accepted 999,999 and 1,000,000 nodes and rejected 1,000,001. A fresh
full-analysis 50k test reached the same final sanitizer call and failed after
451.57 seconds, at 303,468,544 bytes sampled process peak RSS. It produced no
published pointer. The generation remained STAGING and the job ended FAILED.

The 50k job failed before snapshot SQL persistence and `Generation.validate`.
Consequently, those downstream 50k resource costs are unknown. The 50k
fixture's serialized JSON size, depth, and strings are below several unrelated
limits, so those guards do not explain this rejection. Raising the aggregate
limit by 11.6% would have no evidence-based safety margin and is not
recommended.

## Preservation and test environment

The starting state was branch `codex/scale-001-local-continuation`, HEAD
`9e21509591bfa5457cc829ebd5637f95be68d573`. At entry the worktree had the
existing 10 tracked-file changes (287 insertions, 86 deletions) plus the
pre-existing untracked development, database, and evidence artifacts. The
entry status is recorded in the JSON receipt. No pre-existing changes were
discarded or rearranged.

The four original benchmark databases were compared to the SHA-256 values in
the existing `commercial-v1-20261027-01/baseline.json`; all four still match.
The previous aggregate investigation report, its machine evidence, and ADR
0007 addendum also retain the hashes recorded in their evidence receipt. New
tests used a separate scratch directory under the task workspace; they did not
use the four original databases.

The repository's documented `.venv` was absent in the checkout. The documented
existing venv at
`C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv` was available and
matches the locked test tools: Python 3.14.3, pytest 9.1.1, and Ruff 0.16.10.
`pip check` reported no broken requirements. No package was installed and no
manifest or lockfile changed. Test databases, keys, blob directories, pytest
temporary roots, and XML receipts were isolated under
`C:\Users\sai krishna\Documents\Codex\2026-10-29\files-pasted-by-the-user-projecttrace\work\scale001-test-run`.

## Verified admission path and counting semantics

`analyzers/sanitization.py:metadata(value, maximum_nodes=1_000_000)` owns the
guard. Each invocation starts a new counter. The recursive visitor increments
for the current value before checking the limit, and raises
`ValueError("Sanitization structure budget exceeded")` once the count is
1,000,001. Therefore a call admits exactly one million visited nodes.

- The root, nested containers, visited list/tuple elements, strings, nulls,
  booleans, integers, and finite floats each count as one node.
- Dictionary keys are type-checked, stringified, and sanitized, but are not
  passed through the visitor and do not count. Their ordinary values do.
- A non-null value under a sensitive key is replaced with `"[REDACTED]"`
  without recursively visiting that value; the hidden subtree is not counted.
- The depth limit is 60. Individual text values have a 1,000,000-character
  limit. Those are distinct from the aggregate node limit.
- `maximum_nodes` is an explicit function argument, but the production final
  snapshot path passes no override and uses 1,000,000.

In `backend/domain.py:persist_analysis`, the final snapshot mapping combines
the current snapshot fields, captured fields, complete metrics, claims,
findings, dependencies, cloud assets, risk paths, changed lines, quality
summary/gates, drifts, impact, and status. At line 1816,
`sanitize_metadata` recursively builds the sanitized result. The failure occurs
there, before the final snapshot update/persistence and before publication.
`backend/jobs.py` catches the `ValueError`, rolls back the attempt, records a
FAILED job with a generic supported-limits error, and re-raises. The profile
test observed zero published pointers, no snapshot ID on the failed job, a
STAGING generation, and valid SQLite/FK integrity. `Generation.validate` and
promotion were not reached.

The count is aggregate over the one complete logical snapshot passed to this
call. Calls that sanitize individual records elsewhere have their own counters
and are not substitutes for this final-snapshot check. No page-local
alternative is used in this investigation.

After admission, `Generation.validate` still hydrates the complete captured
claims, findings, dependencies, drifts, risk paths, and cloud assets into six
ID-indexed dictionaries, then reads output rows in batches of 250. The batch
read is bounded; those captured dictionaries are not. BASE/HEAD comparison
uses `comparison_snapshot` to select complete requested JSON arrays, and
quality comparison reads metric members and builds previous-metric state.
These later materializations matter to Option B, but the 50k failing test
never reaches them.

## Reproduced facts and measurements

### New results

| Measurement | Result | Scope and limitation |
|---|---:|---|
| Boundary regression | 3 passed | Actual sanitizer, separate fresh process per boundary. |
| Complete 50k logical node count | 1,115,947 | Independent read-only traversal matching sanitizer counting and redaction skips. |
| Serialized 50k logical snapshot | 42,856,474 bytes | `JSONEncoder.iterencode` counted and hashed chunks; no complete JSON string retained; separate process. |
| 50k maximum depth / longest string | 6 / 229 characters | This fixture only; compared with limits 60 and 1,000,000. |
| Full-analysis attempt until guard failure | 451.567 s | Fresh disposable SQLite fixture; it failed at final sanitization, not a successful 50k analysis. Pytest test elapsed 455.68 s. |
| Process peak RSS in 50k attempt | 303,468,544 bytes | Windows process peak sampled by the owned profiler; not a Linux cgroup or hard memory limit. |
| Final sanitizer span | 17.250 s | 50,000 metric rows and 336 findings present at call; sanitizer failed. |
| Metric spill before failure | 51,820,828 ciphertext bytes | 50,000 metric rows, SQLite cache setting `-1024`; this is not final snapshot storage. |
| Publication state | 0 pointers; 1 STAGING generation | Job FAILED with `ValueError`; no snapshot ID; SQLite integrity `ok`, no FK violations. |

The independent streamed-JSON measurement took 1.399 seconds and peaked at
94,097,408 bytes in its own process. It measures encoding of the fixture; it
does not include the production sanitizer copy, SQLite binding/index work,
generation validation, or BASE/HEAD comparison.

### Previously recorded evidence

- 10k: 261,257 nodes; 30k: 681,257 nodes. These are complete final snapshot
  profile counts from the prior owned profile.
- Successful 30k path variants recorded 5.21–12.96 seconds and 522.6–523.5 MB
  sampled process peak RSS. The variants differ in instrumentation, so this
  is not a controlled scaling curve. One 30k profile measured SQLite peak
  malloc at 350,664,352 bytes during snapshot update.
- A 30k comparison profile measured `QUALITY_COMPARISON` at 8.214 seconds.
  No comparable 50k comparison result exists.
- Existing 50k map iteration data measures map iteration only. It has no
  bearing on final snapshot admission; it is excluded from the policy case.

The old 50k direct-sanitizer receipt (2.463 s, 126,091,264-byte process peak)
was a sanitizer-only reproduction. The new 455.68-second test is stronger
evidence for the full path up to rejection; neither is a successful 50k
publication run.

### Independent guard and resource limits

The sanitizer's 1,000,000-node, depth-60, and 1,000,000-character-per-text
checks apply independently. The exercised stored-inventory path also has
source-input quotas (default 100,000 files, 2,000,000,000 total source bytes,
512,000,000 archive bytes, and 512,000 bytes per individual source file) and
partitions source capture into at most 100 files / 2,000,000 bytes per batch.
The older direct `validate_files` path has separate 1,000-file and
10,000,000-total-byte limits with the same 512,000-byte per-file bound. These
input quotas are not the snapshot-node limit. There is a default 900-second
inventory-analysis budget (bounded configuration range 120–3,600 seconds;
non-inventory jobs default to 120 seconds), plus separate encrypted
spill/checkpoint and generation-context limits. The owned 50k profile reports
256,000,000 bytes for observation spill and 64,000,000 bytes for encoded stage
context. Those budgets do not override the final snapshot node count. The
reproduced 50k inventory analysis failed after about half of the default
900-second budget; its completion time if admitted is unknown.

There is no Windows hard process-memory ceiling established by these results.
SQLite's 30k peak allocation is not the same as process RSS and cannot be
extrapolated to the unexecuted 50k SQL update. Concurrent analysis and
per-tenant resource contention were not measured.

## Test-environment recovery and exact outcomes

All test commands used the existing venv above, `APP_ENV=demo`,
`JOB_MODE=sync`, a scratch `DATABASE_URL`, scratch source/blob directories,
and scratch pytest bases. The full exact commands and XML receipt paths are
in the JSON evidence. Results:

1. Sanitizer boundary and new regression test: **3 passed**.
2. Full owned 50k rejection/publication test (`test_snapshot_materialization_profile.py -k 50000`): **1 passed, 3 deselected**, 455.68 s. It independently confirmed no publication.
3. Focused persistence/BASE-HEAD snapshot tests in `test_repository_store.py`: **4 passed, 15 deselected**.
4. Generation/context/maps regression files: **104 passed**. This included the map-only tests as regression checks, not as admission evidence.
5. Commercial rules, open API batches, quality profiles/spill, and real-pipeline files: **105 passed**.
6. Graph/security files: **22 passed, 70 skipped**. Skips were explicitly gated by “Explicit disposable ownership required” or “Explicit disposable prototype ownership required.”
7. JSON export and sanitizer suites: **116 passed, 2 failed** on the default randomized hash seed. Both failures were the typed-context set-order equality cases: equivalent set members serialized in opposite array order (`["b","a"]` versus `["a","b"]`). Rerunning those two tests with `PYTHONHASHSEED=0` yielded **2 passed**. This is a pre-existing test/serialization determinism issue in the dirty tree, not a sanitizer failure; it is reported, not changed here.
8. Checkpoint and retention files: **65 passed, 1 skipped**. The skip requires an explicitly disposable PostgreSQL test database, which was not configured.
9. Ruff: initial run found one import-spacing violation in the new boundary test; corrected the extra blank line. Final `ruff check backend analyzers integrations workers tests scripts`: **passed**.
10. `python -m compileall -q backend analyzers integrations workers scripts tests integration_tests`: **passed**. `git diff --check`: **passed**.

No full repository test suite, PostgreSQL service, broker recovery, Linux
cgroup, or distributed-worker qualification was run. One Starlette/httpx
deprecation warning and pytest `record_property`/JUnit-family warnings were
non-failing. Test receipt files and skipped/failed details are preserved in
the task scratch directory, not in the original databases.

## Option A and Option B

| Area | Option A: retain the cap | Option B: propose a bounded amendment |
|---|---|---|
| Admission | Keeps the existing definition: one complete logical snapshot may contain at most 1,000,000 counted nodes. | Must define a new externally visible aggregate budget. Per-page resets are not acceptable. |
| Large repositories | Input size alone does not guarantee support. Any completed snapshot over the node cap remains unsupported, including this 50k fixture. | Could enable this fixture only if the chosen aggregate policy and all other resource bounds are justified and tested. Current evidence does not establish that. |
| Product claims | Can state a precise structural boundary, but must avoid “50k supported” or a raw file-count promise. The boundary depends on snapshot shape and the counting/redaction semantics documented above. | Could eventually support larger snapshots, but no safe cap or supported scale can yet be stated. |
| Compatibility/security | Preserves current sanitization, fail-closed behavior, and stored formats; no migration. A failed job remains unpublished. Current user-facing error is generic and could be made clearer in a separately authorized UX task. | Changes security admission semantics. Requires threat review for deep/wide/adversarial structures, versioning/compatibility analysis, and explicit product/security approval. |
| User experience | Over-limit analysis ends FAILED with a generic “check supported input limits” message; it does not publish a partial snapshot. The owned test verifies this. | If safely implemented later, needs predictable bounded admission and actionable errors for each exceeded budget. Failure/cancellation must leave no visible partial snapshot. |
| Qualification | This is an admission-policy decision, not a performance qualification. SCALE-001 stays NOT QUALIFIED for the 50k requirement. | Remains NOT QUALIFIED until successful end-to-end resource evidence and all acceptance gates pass. |
| Resource evidence | Existing behavior is measurable; no new budget is justified. | Missing 50k successful persistence/update/SQLite allocation, `Generation.validate`, BASE/HEAD comparison, cancellation after staging, concurrent/tenant isolation, and supported-platform resource-cap evidence. |

The 50k count is 11.6% above the current numeric cap, but the serialized
fixture is 42.86 MB and the analysis has already consumed 451.57 seconds before
rejection. The downstream SQLite update alone reached a 350.66 MB SQLite
allocation peak at 30k. These facts do not support choosing 1.12 million, or
any other replacement cap by arithmetic margin.

## Recommendation and approval gate

Recommend **Option A as the current operating policy** until product and
security owners decide otherwise: preserve the limit, state clearly that
logical snapshots above it are unsupported, and do not advertise the 50k
fixture as supported. The product owner must explicitly approve that support
boundary. If the commercial requirement makes 50k support mandatory, owners
must instead authorize a formal Option B policy investigation; that
authorization is not implementation approval.

Before any Option B cap can be proposed, the smallest defensible experiment
sequence is:

1. Obtain written product/security authorization for an isolated test-only
   over-limit evaluation, with a temporary owned database and no change to
   production/default admission behavior.
2. Capture the complete successful 50k path at the candidate budget, including
   final sanitize, full snapshot/quality SQL writes and SQLite peak allocations,
   validation, BASE/HEAD comparison, peak process RSS, wall time, serialized
   bytes, and memory at each stage. Repeat in at least three fresh processes.
3. Repeat under concurrency and tenant isolation at the declared deployment
   memory/time ceilings; exercise cancellation, process exit, malformed/deep
   input, all budget failures, and verify no partial publication.
4. Run the accepted boundary and regression matrix on the supported Linux
   cgroup/zero-swap environment and the actual database/worker services. Keep
   Windows measurements labeled local-only.
5. Complete threat review, compatibility/versioning review, explicit owner
   approval of the resulting aggregate definition and resource envelope, then
   implementation and acceptance tests as a separately authorized task.

No over-limit continuation was attempted in this task. The first and largest
missing fact is the successful post-admission 50k resource path, which current
policy intentionally blocks. Until the written policy decision and that
evidence exist, the recommendation is to keep the current guard and retain the
qualification blocker.

## Remaining qualification gates

- Product/security owner decision on the supported aggregate-node boundary.
- If Option B is chosen, explicit new policy approval plus successful repeated
  50k end-to-end resource, concurrency, cancellation, adversarial-input, and
  atomicity evidence.
- Required Linux memory/cgroup and zero-swap acceptance; current fresh 50k
  evidence is Windows-only.
- PostgreSQL, broker/worker recovery, multi-tenant concurrent load, and full
  release-gate acceptance on supported services.
- Resolve or separately disposition the JSON export test's hash-order
  determinism issue before treating that suite as fully green.

Machine-readable evidence, including test XML paths, exact commands, test
outcomes, measured profiles, original-artifact hashes, and unresolved
assumptions, is in
`docs/evidence/SCALE001_POLICY_DECISION_READINESS.json`.
