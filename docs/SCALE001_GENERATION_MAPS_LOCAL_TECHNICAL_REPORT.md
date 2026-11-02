**SCALE-001: indexed generation-context dictionaries — local technical report**

2026-10-26. Status: **NOT QUALIFIED**.
Branch: `codex/scale-001-local-continuation`.
HEAD: `9e21509591bfa5457cc829ebd5637f95be68d573`.

All earlier uncommitted checkpoint, generation, migration and evidence changes
were retained. This task did not edit the migration, publication promotion,
domain snapshot construction or production resource configuration. No commit,
push, merge, PR change, deployment, workflow dispatch or full Linux qualification
was performed. This report supplements the earlier checkpoint report; its
historical statements about unchanged generation formats do not describe the
later uncommitted generation architecture.

**Confirmed defect and correction**

The first added test was
`test_ten_thousand_entry_dictionary_round_trip`. Its dictionary has 10,000 entries
and 28 scalar fields per value. The compact JSON including the `claims_by_id`
wrapper is exactly **3,808,908 bytes**. Before implementation, the test failed in
`Writer.node` with `Generation context descriptor budget exceeded.` The encoder
expanded dictionary values into more than 256,000 manifest descriptor nodes.

The corrected writer stores this dictionary as one ordered entry collection and
one map descriptor. The regression asserts **3 descriptor nodes, 1 collection,
1 map**, checks every original key/value, exact iteration order, equality in both
directions, standard JSON output and validation-only replay. It passes on the
final implementation. No node guard was raised or disabled.

**Files changed in this iteration**

- `backend/context_maps.py`: new ordered encrypted map view, disk-backed HMAC
  lookup/index validation, dictionary operations and JSON compatibility.
- `backend/generation_context.py`: map descriptors and entry framing, bounded
  nested collection routing, writer/reader agreement, uniqueness validation,
  private mutations and typed-reference preservation.
- `backend/context_json.py`: retain indexed map/encrypted sequence owners during
  nested write-through wrapping instead of copying their complete payloads.
- `tests/test_generation_maps.py`: 19 focused map cases, including the original
  regression, actual subprocess replay, v1-to-v2 compatibility and failure paths.
- This report and `docs/evidence/SCALE001_GENERATION_MAPS_OWNED.json`: measurements,
  final source hashes, test receipt summaries and complete owned output hashes.

These paths include files that were already uncommitted; their existing
checkpoint/generation behavior was extended rather than reset or replaced.

**Representation, ownership and bounds**

A map descriptor points to existing authenticated generation collection pages.
Entries are ordered `[key, value]` frames. JSON-only entries use the existing `J`
frame; references/nested paged collections use typed `E` descriptors. Dictionary
order is the stored entry ordinal, never hash order. Native dictionary values
remain complete, and dictionary identity aliases reuse their map descriptor.

Maps with more than eight entries are paged when encountered by the descriptor
writer. Atomic JSON rows may contain small native containers; nested maps or
sequences over 128 elements, encrypted sequences and existing indexed views are
routed back through the typed collection codec. This avoids assembling a large
nested dictionary/list inside an atomic row merely to evade the descriptor
guard. Neither threshold changes an admission/resource ceiling.

Replay authenticates all pages and complete collection digests/counts before
returning the context. It copies bounded frames into the existing encrypted
attempt-private row owner. Its SQLite index contains only collection IDs,
positions and HMAC key tags. Keys and values remain inside encrypted frames.
Lookup and iteration verify the decoded key against its index tag; encrypted
row envelopes also bind collection and position. Duplicate keys, substituted
positions and incomplete indexes fail closed.

| Bound | Final implementation |
|---|---:|
| Descriptor nodes | 256,000, unchanged |
| Descriptor depth | 60, unchanged |
| Collection headers | At most 256,000; writer/reader agree at the boundary |
| Aggregate retained stage ciphertext | 64,000,000 bytes, unchanged |
| Decoded page | 256,000 bytes, unchanged |
| Atomic generation row/manifest | 32,000,000 minus 8,192 bytes |
| Live replay SQLite configured cache | Existing 1,048,576 bytes, shared with its row owner |
| Replay encrypted payload quota | Existing `ANALYSIS_OBSERVATION_SPILL_BYTES`, unchanged |

The stage quota continues the existing uncommitted v2 representation contract:
it counts aggregate encoded ciphertext, including staging attempts, rather than
the legacy expanded JSON buffer. It is not a separate 64 MB allowance per page.
Map indexes and database overhead are not falsely reported as ciphertext bytes.

Writer transient payloads are bounded by an atomic row and page buffers. Its
memo holds collection headers/owner references, not an entry-to-value copy of
the dictionary. The caller's original native dictionary can still be resident;
this change does not fix its construction in domain correlation code.

Replay holds a bounded manifest, one bounded row/page working set, fixed
configured SQLite caches and collection headers bounded by the descriptor
guard. It does not build a Python key/value index for every map entry. Mutable
row identity uses weak references: callers retaining values retain their own
payloads, while the map does not strongly cache every value traversed. A large
number of distinct collections or a maximum-sized atomic value can still be
expensive. These bounds are not proof that the complete pipeline fits 768 MB.

Validation-only replay uses a temporary disk-backed HMAC uniqueness index with
a 1 MB configured cache. It closes that owner on success or failure and does
not recreate all ORM records or complete dictionaries for validation.

Deletion/reinsertion preserves dictionary order; replacement keeps the existing
position. Nested mutations write through to bounded encrypted rows. Deleted
private row payloads remain charged to the existing spill quota until owner
cleanup; the implementation does not hide storage growth by dropping accounting.
Oversize rows, quota failures and cancellation propagate.

**Security, admission and compatibility**

The existing Fernet/MultiFernet page encryption, generation/tenant/repository/
signature/stage/attempt identity, composite foreign keys, dependency digests,
fences, page-inventory checks and atomic receipt admission remain in force.
Maps add no durable table or migration. A new attempt never treats a partial
map as a completed public generation. Missing/corrupt/expired pages and budget
failures continue to block progress. Parser isolation and source handling were
not changed; no imported repository code was executed.

Typed Record lookup checks tenant/repository and generation visibility, including
cached ORM objects. Record append/replacement inside a mutable paged sequence
uses the typed codec, and foreign-scope references are rejected. Finding working
state remains typed and registers its encrypted owner for attempt failure
cleanup, including lazy retrieval after the initial replay.

Standard `json.dumps`, sorted JSON, streaming `JSONEncoder.iterencode`, dictionary
conversion, and the existing SQLAlchemy JSON serializer retain complete output.
The dict subclass keeps one private base slot because CPython's accelerated
encoder otherwise treats a physically empty subclass as `{}`. Public mapping
operations/`items()` expose only real entries, and explicit tests check that
serialization emits every value. No global JSON monkeypatch or engine serializer
change was introduced. String keys remain the existing context-writer contract;
Unicode and surrogate keys are tested. Unhashable lookups retain dictionary
error behavior.

**Whole-document JSON exports are not bounded-memory streaming APIs.** Standard
JSON/SQLAlchemy exports can allocate the complete output string and temporary
item lists. Explicit `dict()`, copying and set reconstruction also have their
ordinary allocation costs. The bounded storage/replay path uses row streaming;
this report does not disguise complete-document export memory as a small index.
Alternative JSON encoders and Linux runtime builds still need qualification.

The original v1 decoder and receipt format remain supported. A new test writes
and restores a complete 10,000-entry v1 map, feeds it into a v2 receipt, verifies
every value/order and asserts that the v1 digest, marker and ciphertext chunks
remain unchanged. Existing receipt history is not rewritten.

**Actual local tests**

| Run / receipt | Result | Scope |
|---|---|---|
| `map-regression-before.xml` | 1 failed, 0 skips; expected red test | Original 10,000-entry failure before implementation |
| `map-initial.xml` | 19 passed, 0 skips, 47.23 s | Initial map regression plus generation contexts |
| `map-targeted-initial.xml` | 9 passed, 0 skips, 71.34 s | Initial expanded map tests |
| `map-regression-full.xml` | 102 passed, 0 skips, 862.33 s | Maps, contexts, checkpoints, analysis checkpoints, all generation tests |
| `map-targeted-final.xml` | 15 passed, 0 skips, 118.93 s | Added large v1 compatibility |
| `map-references-final.xml` | 77 passed, 0 skips, 373.80 s | Typed sequence/lookup corrections, checkpoints and selected worker/stage recovery |
| `map-final.xml` | **37 passed, 0 skips, 40.23 s** | Final 19 map cases plus 18 generation-context cases |

Selections overlap and must not be added. The 102-case run preceded the typed
sequence/lookup corner corrections; the 77-case rerun covers those changes.
The final 37-case rerun follows the last empty-map index and header-boundary
corrections. That run closed the dictionary-storage iteration; subsequent
iteration optimization and its final checks are recorded below.

Additional red tests found typed Record append failure/unhashable lookup
behavior (2 failures), missing empty-map index on fresh replay (1 failure), and
the reader header-cap off-by-one (1 failure). Each is corrected and covered in
the final 37 cases. `map-cap-before.xml` was a superseded test setup error
(`receipt=None`); `map-cap-before-valid.xml` reproduces the actual cap mismatch.
It is not counted as a product failure or passing test. Assertions were not
relaxed to accept incorrect output.

Coverage includes full value/order equality, nested maps/sequences/references,
mutation then serialization and another receipt, two subprocess hash seeds,
partial-stage deterministic identities, legacy v1, the actual 256,000-node
failure, quota exhaustion, duplicate-key decoding, scope/key-index attacks,
cancellation and cleanup, empty maps and exact collection-cap agreement. The
broader suite includes real subprocess exits at BATCH/HISTORY/VALIDATED, all
14 stage restart points, lost acknowledgements, publication guards and default
private-reader visibility.

Ruff over `backend analyzers tests scripts`, compilation over those directories,
and `git diff --check` pass. The only reported test warning is the installed
Starlette/httpx deprecation; no case was skipped or suppressed.

**Exact test invocations**

The working directory was `C:\Users\sai krishna\Projects\ProjectTrace-local`.
The aliases below resolve to the executable and absolute output paths used by
the recorded commands. These are historical evidence paths, not fresh rerun
directories.

```powershell
$scalePython = 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe'
$scaleWork = 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work'
$env:PYTHONPATH = $scaleWork

# Before implementation: the module contained only the original regression.
& $scalePython -m pytest -q tests/test_generation_maps.py -p short_test_ids --basetemp="$scaleWork\p50" --junitxml="$scaleWork\map-regression-before.xml"

# Broad run before the later corner cases were added (14 map cases then).
& $scalePython -m pytest -q tests/test_generation_maps.py tests/test_generation_context.py tests/test_checkpoint_pages.py tests/test_analysis_checkpoints.py tests/test_generations.py -p short_test_ids --basetemp="$scaleWork\p53" --junitxml="$scaleWork\map-regression-full.xml"

# Rerun after typed reference mutations and lookup corrections.
& $scalePython -m pytest -q tests/test_generation_maps.py tests/test_generation_context.py tests/test_checkpoint_pages.py tests/test_analysis_checkpoints.py 'tests/test_generations.py::test_actual_worker_exit_resumes_partial_stage_with_new_lease' 'tests/test_generations.py::test_each_stage_survives_restart_without_private_reader_leaks[SNAPSHOT]' 'tests/test_generations.py::test_each_stage_survives_restart_without_private_reader_leaks[CORRELATION]' 'tests/test_generations.py::test_each_stage_survives_restart_without_private_reader_leaks[FINAL_OUTPUT]' -p short_test_ids --basetemp="$scaleWork\p56" --junitxml="$scaleWork\map-references-final.xml"

# Final implementation: 19 map and 18 context cases.
& $scalePython -m pytest -q tests/test_generation_maps.py tests/test_generation_context.py -p short_test_ids --basetemp="$scaleWork\p60" --junitxml="$scaleWork\map-final.xml"

& $scalePython -m ruff check backend analyzers tests scripts
& $scalePython -m compileall -q backend analyzers tests scripts
git diff --check
```

The intermediate p51/p52/p54 runs use the same pytest flags with, respectively,
`tests/test_generation_maps.py tests/test_generation_context.py`,
`tests/test_generation_maps.py`, and `tests/test_generation_maps.py`; their
matching XML names are in the table. The failure receipts name the exact failed
selectors; machine-readable summaries are retained in the evidence JSON.

**Complete owned outputs and memory measurements**

The unchanged owned pipeline fixture ran cold, warm and incremental analyses
after the typed mutation correction. Complete fingerprints equal the prior
fixture, including all scoped outputs, quality projections, parser artifacts
and source inventories. SQLite integrity is `ok`, foreign-key violations zero;
the fixture publishes three generations with two branch pointers. Its `PARTIAL`
status is existing static coverage semantics, not incomplete fixture execution.
It contains 19 inert owned files, not the pinned OpenMetadata workload.

Final separate writer/replay processes also checked 1,000, 10,000 and 50,000 map
entries. Complete streaming hashes and SQLite/FK checks pass at every size.

| Entries | Map-only JSON bytes | Descriptor nodes / collections | Ciphertext bytes | Fresh replay peak RSS | Peak including complete streaming hash |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 379,891 | 3 / 1 | 11,572 | 89,100,288 | 89,989,120 |
| 10,000 | 3,808,891 | 3 / 1 | 93,176 | 97,853,440 | 100,851,712 |
| 50,000 | 19,088,891 | 3 / 1 | 458,104 | 99,414,016 | 128,741,376 |

All three retain one Python base-dict slot and one collection header, rather
than an in-memory index of every key/value. The regression's outer wrapper adds
17 bytes to the map-only JSON count. At 50,000 entries the writer starts at
241,586,176 RSS bytes with its caller-owned native dictionary and peaks at
262,017,024 bytes; the input itself is not claimed to disappear.

Final 50,000-entry write/replay times are 4.429/6.601 seconds. An earlier
concurrent profile took 30.915 seconds to replay the same map. Profiling
overlapped other local activity, so these are not controlled throughput claims.
The extra CPU/encryption/index I/O still needs operation-level attribution.
Stored ciphertext size alone is not memory evidence; neither these Windows
RSS samples nor fixture publication is cgroup qualification.

These owned commands ran from the task directory with the same executable:

```powershell
& $scalePython work/profile_generation_maps.py work/generation-map-profile-final batch
$env:PYTHONHASHSEED = '0'
& $scalePython work/verify_pipeline_fixture.py work/vp-generation-maps-final
```

The private encryption key was inherited only by owned child processes. No key,
source payload, database or imported repository was exported in the evidence.

**Acceptance state and remaining separate issues**

- **VERIFIED locally:** original dictionary regression, final targeted tests,
  representative complete output/order equivalence, typed mutations and foreign
  scope rejection, v1 compatibility, authenticated/indexed replay, quota and
  cancellation failures, owned recovery/publication, Ruff and compilation.
- **FAILED before correction:** the original dictionary guard regression and
  the documented corner-case red tests above; final focused cases pass.
- **Unresolved separately:** final snapshot sanitization still applies the
  one-million-node guard to a materialized complete snapshot. The earlier owned
  4,115,624-node case failed and was not redesigned here. QualityAnalysis JSON,
  Record hydration, native correlation dictionaries/sets and whole-document
  exports remain whole-pipeline memory risks.
- **Unresolved separately:** migration downgrade still rejects retained v2
  generation receipts after normal context expiry. No safeguard was weakened,
  marker reset or history rewrite performed to make downgrade appear possible.
- **NOT_RUN:** full pinned 21,636-file OpenMetadata analysis at 768,000,000 bytes
  and zero swap; full warm/incremental equality, resource-exhaustion,
  cancellation/recovery/duplicate-delivery/tenant/atomic-publication acceptance;
  Linux parser isolation, PostgreSQL, Redis/Celery and Docker validation of this
  diff. No GitHub CI result certifies these uncommitted changes. The normal
  expiry/downgrade integration gate was also not run in this focused task.

At the end of that iteration, the next task was an owned operation-attribution/read-count
test for `ContextMap.items()`: key iteration, key lookup and value retrieval
decrypted the same frame repeatedly. The following section records that
measurement and correction with the same authentication and resource limits.
Final-snapshot storage and migration expiry/downgrade require separate changes
and acceptance evidence. Full qualification remains **NOT QUALIFIED**.

**Subsequent iteration: eliminate repeated frame decryption (2026-10-26)**

Status remains **NOT QUALIFIED**, on the same branch and HEAD. Earlier work is
preserved. Hash checks confirm `generation_context.py`, `context_json.py` and
the earlier `test_generation_maps.py` are unchanged from the preceding evidence.
The baseline `context_maps.py` was also preserved in the task's work directory;
its SHA-256 is
`74d275529d7cc8d36b3f0bbdc5f6366d579ea0df1be334fda6a5abe9dd49a716`.

Only these repository paths were changed/added for this optimization:

- `backend/context_maps.py`: fused ordered item/value iteration, verified-frame
  reuse for direct lookup, and iterator/resource lifetime handling.
- `tests/generation_map_iteration_probe.py`: reproducible owned dataset and
  fresh-process real-Fernet operation/time/RSS probe.
- `tests/test_generation_map_iteration.py`: counts, integrity, ordering,
  mutations, invalidation and iterator/owner lifetime regressions.
- This report and `docs/evidence/SCALE001_GENERATION_MAP_ITERATION.json`.

No receipt format, durable schema, migration, generation admission, source
parser, global cache, production resource limit or publication policy changed.
No commit, push, PR change or remote workflow was performed.

**Measured baseline and exact call paths**

Each benchmark dataset has 28 integer fields per value and insertion-ordered
string keys. For each size, three independent measured processes restore the
complete map, then hash its complete streaming JSON with a fixed hash seed.
The fixture-authoring process is outside measured RSS. It drops its input
dictionary before launching measurements. Private keys are inherited through
the child environment only and are not exported.

The probe wraps the actual attempt-private Fernet cipher, delegates encryption/
decryption unchanged, counts operations, and captures only the first three call
paths. It starts counting after replay. Thus these are **map-entry iteration
decryptions**, not durable page decryption or whole-application totals.

Previously `ItemsView.__iter__` performed three decryptions per entry:

1. `ContextMap._keys -> _frame -> ReplayRows.__getitem__ -> EncryptedRows.__getitem__`:
   read the ordered entry and verify its index HMAC.
2. `ContextMap.__getitem__ -> _position -> _frame -> ReplayRows.__getitem__ -> EncryptedRows.__getitem__`:
   look up the same key and verify its entry again.
3. `ContextMap.__getitem__ -> ContextRows.__getitem__ -> ReplayRows.__getitem__ -> EncryptedRows.__getitem__`:
   retrieve/decode its value again.

All three reach the actual `Fernet.decrypt` implementation. Key-only iteration
already needed one read; direct lookup needed two. Baseline tests confirmed
30,000/150,000 decryptions for 10,000/50,000 entries, respectively, in **every**
sample, with complete expected output hashes.

**Small bounded correction**

`MapItems` and `MapValues` retain the standard mapping-view interfaces and use
one ordered `_iterate` generator. Each step reads one frame, retaining the
existing Fernet authentication, encrypted scope/collection/position validation,
decoded-key validation and index-HMAC comparison. `_value` decodes that same
verified frame instead of issuing another lookup/decryption. Direct lookup
likewise passes its verified frame from `_located` into `_value`.

The decoded frame is explicitly released **before yield**. There is no added
map-wide cache, plaintext key index or frame retained for a later entry. A
suspended iterator retains its cursor and current public result; any caller
retaining results retains its own payloads as before. Collection, page, row,
spill and descriptor bounds remain unchanged, including the 256,000-node guard
and configured 1 MB SQLite cache.

Index HMAC verification still occurs once for each yielded entry. The removed
second HMAC computation was the redundant point-lookup tag computation, not
the ordered-entry verification. Typed `J`/`E` decoding and the existing weak
mutable-value identity cache are retained. Even a retained live mutable value
requires a fresh authenticated frame on an independent lookup.

Replacements do not invalidate structural iteration and upcoming entries are
read afresh. Nested changes write through; replaced old proxies cannot
overwrite their replacements. Insert/delete/reinsert/clear still invalidate
active iterators through the existing version counter. Multiple iterators have
independent positions. Explicit close, exhaustion and errors release cursors;
owner close invalidates suspended reads without attempting to close an already
invalidated native cursor.

A new lifetime test caught a check removed with the redundant value read:
owner closure during frame authentication could otherwise precede a returned
value. `_value` now retains the original value-read open check, before both
weak-cache access and decoding. Both lookup and item iteration reject that
case without performing a second decryption. The final measurements below were
repeated after restoring this check.

**Final before/after measurements**

| Entries | Decryptions per full iteration, before -> after | HMAC tag computations, before -> after | Median iteration seconds, before -> after | Maximum process peak RSS bytes, before -> after |
|---:|---:|---:|---:|---:|
| 10,000 | 30,000 -> 10,000 | 20,000 -> 10,000 | 3.975712 -> 1.219993 | 118,894,592 -> 118,890,496 |
| 50,000 | 150,000 -> 50,000 | 100,000 -> 50,000 | 47.443799 -> 5.700312 | 129,028,096 -> 128,094,208 |

There were zero encryptions during each measured iteration. Every before/after
sample retains one collection header, one Python base slot and `cache_size=-1024`.
All full hashes match:

- 10,000 entries, 3,808,891 map-only JSON bytes:
  `dfd65078bdf464191ed4034af1c8d31221f60933a6bfc5df377401f662dc0c7b`.
- 50,000 entries, 19,088,891 map-only JSON bytes:
  `b3c66416c2976176f65c22ccd0a7637c6317ed50fe2c171e6834fcc7b107abdc`.

The deterministic improvement is **two fewer decryptions per entry (66.7%)**,
with the integrity checks retained. The timing medians are local observations,
not isolated causal or production speedup claims. For example, untimed replay/
load durations at 50,000 entries varied from 17.66–27.95 s before to 6.79–7.75 s
after despite no optimization to that replay-builder operation. Host/I/O
variance therefore affects elapsed comparisons. Each reported RSS peak includes
replay plus iteration in its measured child; it is not process-tree/cgroup
qualification. No peak-RSS growth was observed across these samples.

**Actual iteration validation and commands**

| Receipt | Result | Interpretation |
|---|---|---|
| `map-iteration-before.xml` | 5 failed, 1 passed, 0 skipped, 285.87 s | Expected red count tests on baseline: items/values and lookup repeat decryptions |
| `map-iteration-small.xml` | 29 passed, 2 deselected, 0 skipped, 40.10 s | Initial focused correctness/count/lifetime cases |
| `map-iteration-after.xml` | 2 passed, 0 skipped, 206.06 s | Initial three-sample measurements, before the last owner-open correction |
| `map-iteration-owner-before.xml` | 2 failed, 0 skipped, 3.66 s | Lifetime regression exposed the missing mid-read owner-open check |
| `map-iteration-regression.xml` | 136 passed, 2 deselected, 0 skipped, 720.04 s | Wider checks including all 14 stage restarts, before the last owner-open correction |
| `map-iteration-after-final.xml` | **2 passed, 0 skipped, 93.07 s** | Final three-sample 10,000/50,000-entry measurements |
| `map-iteration-final.xml` | **68 passed, 2 deselected, 0 skipped, 45.68 s** | Final 31 small iteration, 19 map and 18 context cases after the owner-open correction |

Selections overlap. Deselected cases are the two large profiles, run separately
for timing isolation; they are not skipped acceptance checks. Baseline xunit2
emitted `record_property` format warnings; the measurement metadata was still
captured. Later receipts use the supported xunit1 property format. The installed
Starlette/httpx deprecation warning remains; no error or test was suppressed.

Tests verify actual Fernet counts, zero read-side encryption, all-key/value
hashes, unchanged caches, mutable replacement/invalidation, typed reference
updates and receipt replay, independent iterators, cursor cleanup, lazy-owner
retention/collection, decoded-frame release before yield, closed owners,
future ciphertext corruption, live-cache authentication, HMAC tampering and
index completeness. Wider tests cover existing maps, checkpoints, analysis
checkpoints and every generation/publication/recovery test. Ruff, compilation
and diff checks pass on the final code.

Using the executable/path aliases defined earlier, from the repository directory:

```powershell
# Baseline: six cases existed at collection time.
& $scalePython -m pytest -q tests/test_generation_map_iteration.py -p short_test_ids --basetemp="$scaleWork\p61" --junitxml="$scaleWork\map-iteration-before.xml"

# Wider iteration/map/checkpoint/generation regression run.
& $scalePython -m pytest -q tests/test_generation_map_iteration.py tests/test_generation_maps.py tests/test_generation_context.py tests/test_checkpoint_pages.py tests/test_analysis_checkpoints.py tests/test_generations.py -k 'not large_map_iteration' -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p64" --junitxml="$scaleWork\map-iteration-regression.xml"

# Final measurements: three fresh processes per parameter, complete output hash.
& $scalePython -m pytest -q tests/test_generation_map_iteration.py::test_large_map_iteration_decrypts_each_entry_once -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p66" --junitxml="$scaleWork\map-iteration-after-final.xml"

# Final affected-path regression run including the owner-open check.
& $scalePython -m pytest -q tests/test_generation_map_iteration.py tests/test_generation_maps.py tests/test_generation_context.py -k 'not large_map_iteration' -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p67" --junitxml="$scaleWork\map-iteration-final.xml"

& $scalePython -m ruff check backend analyzers tests scripts
& $scalePython -m compileall -q backend analyzers tests scripts
git diff --check
```

The owned cold/warm/incremental fixture was also rerun on final code into
`work/vp-map-iteration-final` using the earlier fixture command with
`PYTHONHASHSEED=0`. Its complete fingerprints equal the pre-optimization
`work/vp-generation-maps-final` fixture, including every scoped output and
projection. SQLite integrity and FK checks pass; all three fixture generations
publish with two pointers. This is still only the 19-file owned fixture.

**Remaining separate blockers and next action**

Whole-document JSON export, final snapshot sanitization/materialization,
QualityAnalysis/Record hydration, native correlation structures and the normal
expiry/downgrade defect remain unchanged and unresolved. The full pinned Linux
workload, 768,000,000-byte/zero-swap process-tree envelope, PostgreSQL, real broker
and complete acceptance matrix were not run. No remote CI result certifies this
uncommitted change. **SCALE-001 remains NOT QUALIFIED.**

The next smallest engineering task is to attribute **replay-builder** cost:
separately measure page decode, private-row encryption/insertion and HMAC-index
writes. Iteration now performs its minimum one frame decryption per entry;
replay/load itself was not optimized here. Do not infer its dominant operation
from noisy aggregate timings or increase the cache to conceal the cost.

**Subsequent iteration: whole-document JSON export (2026-10-26)**

Status: **NOT QUALIFIED**. Same branch and unchanged HEAD
`9e21509591bfa5457cc829ebd5637f95be68d573`. All preceding uncommitted work is
preserved. This section supersedes the earlier statement that SQLAlchemy export
is unchanged; final snapshot construction and downgrade/expiry are still untouched.
No commit, push, PR edit, merge, remote workflow or full Linux workload was run.

**Measured root causes and scope**

`json.dumps(ContextMap)` uses CPython's accelerated dictionary-subclass path,
which collects `items()` before encoding. Each value then has a strong reference
from that complete items collection. `"".join(JSONEncoder.iterencode(...))` has a
different problem: joining a generator collects all its string fragments before
joining them. These operations additionally allocate the complete result string;
an HTTP `Response` or UTF-8 conversion then allocates complete output bytes.

Ordinary ContextMap/ContextRows mutable reads can also create write-through
wrappers with reference cycles (`root -> wrapper -> changed -> root`). Collection
of discarded wrappers depends on cyclic GC, even when a streaming encoder does
not explicitly retain them. The export-specific read path avoids creating those
wrappers. Existing caller-held live values are honored after fresh authentication.
Ordinary mutation and iterator APIs were preserved.

No extra decryption was found in these baseline exports: they already decrypt
each entry once after the previous iteration's correction. The problem here is
retention/duplication, not a new repeated-decryption optimization.

**Changed files in this iteration**

- `backend/json_export.py`: insertion-order incremental text/UTF-8 encoding,
  short-write handling, circular-reference detection, explicit failure/cancel/
  abandonment cleanup, and a SQLAlchemy-compatible string adapter. At most 64
  small native nodes are inspected for its accelerated stdlib fast path; this
  threshold adds no cache or resource entitlement. Supported options are explicit
  and identical for small and large inputs. Sorting/indent options are not part
  of this new adapter; existing standard JSON APIs remain unchanged.
- `backend/context_maps.py`: private non-tracking JSON iterator using the same
  authenticated frame, HMAC, ordering, completeness, mutation and owner-open
  checks; iterator-local frame reuse remains in place.
- `backend/generation_context.py`: non-tracking sequence export, fresh frame
  authentication even for caller-held mutable rows, and a mid-read open check.
- `backend/db.py`: use the incremental string adapter for JSON binding, retaining
  the database driver's complete-string contract and ordinary JSON spelling.
- `backend/quality_api.py`: stream detached JSON after existing authorization and
  scoped retrieval. Response body, media type and attachment filename stay the
  same. The response no longer advertises a precomputed Content-Length. The
  `current_findings` producer still returns a complete list; its query/order/
  transaction semantics were not redesigned here.
- `tests/generation_json_export_probe.py`, `tests/test_json_export.py`: owned,
  fresh-process measurements and focused semantic/failure/security regressions.
- This report and `docs/evidence/SCALE001_GENERATION_JSON_EXPORT.json`: commands,
  raw samples, test receipts, source hashes and complete owned output comparison.

**Bounds and guarantees**

The encoder never calls `dict(map)`, `list(map.items())`, sorts a lazy map, or
joins a document-wide fragment list. It walks one entry at a time, retaining only
active ancestor iterators. No new plaintext spool or global payload/index cache
is introduced. UTF-8 is batched in a character accumulator; each emitted byte
chunk is at most **65,536 bytes**. Partial writes are retried until accepted;
zero/None/invalid counts and sink exceptions propagate. Cancellation checks run
at entry, every 256 text fragments, at writes and completion. Source owners remain
caller-owned; owned iterators close on success, corruption, cancellation,
consumer close and retained exception tracebacks.

An arbitrary sink can retain a prefix on failure (even a complete-looking prefix).
There is no successful return/receipt on failure, no implicit rollback of caller
files or network writes, and no publication operation in this exporter. Streaming
consumers must close abandoned iterators. Callers must not concurrently mutate
the document; this is not a new transactional snapshot mechanism.

The precise incremental state bound is **O(D + sum(R_i) + Q + B)**: traversal
depth, decoded atomic payloads at each active ancestor, the current escaped scalar
token, and bounded transport/conversion buffers. Fernet/JSON decoding uses further
transient copies of the current atomic row. Existing source objects, replay
headers/cache, typed-record hydration and arbitrary `default` callback allocations
are additional costs. For example, the unchanged `generations.encoded(set)`
callback constructs a list; custom callback allocation is not bounded by the
encoder. A string-returning SQL bind additionally retains **O(output bytes)**.

The unchanged v2 descriptor depth, 256,000-node guard, 31,991,808-byte atomic-row
limit, 64,000,000-byte encoded stage budget and 1 MiB replay SQLite cache still
apply. The worst-case product of active ancestor row sizes can exceed 768 MB;
this correction removes document-wide accumulation, **not** all whole-pipeline
memory risks. It does not alter manifests, receipt formats, encryption keys,
HMAC verification, admission/publication or v1/v2 recovery contracts.

**Reproducible measurements**

`generation_json_export_probe.profile` creates inert owned inputs in the parent,
closes its session and drops the source map, then measures fresh child processes.
Two samples per size/mode use the same logical input and `PYTHONHASHSEED=0`.
Replay/load is timed separately. Peaks below include replay/imports plus export in
the child, not fixture authoring, the process tree, or a cgroup. The stream hashes
into a non-retaining sink. String modes retain their returned text and perform
the same complete UTF-8 conversion to that sink. CPU/load times are in raw JSON.

| Entries | Complete JSON bytes | Baseline dumps peak / median s | Baseline joined-fragments peak / median s | Final stream peak / median s | Final string peak / median s |
|---:|---:|---:|---:|---:|---:|
| 16 | 6,072 | 84,291,584 / 0.003686 | 84,160,512 / 0.002284 | 84,021,248 / 0.001627 | 84,168,704 / 0.001152 |
| 10,000 | **3,808,908** | 126,824,448 / 0.583841 | 163,942,400 / 0.772245 | 97,689,600 / 1.258751 | 104,927,232 / 0.641609 |
| 50,000 | 19,088,908 | 296,620,032 / 10.204563 | 342,122,496 / 11.886652 | 99,270,656 / 9.918324 | 137,289,728 / 6.995818 |

All bytes are raw bytes, not MiB. Timings are local observations with host/I/O/GC
variance, not full-workload performance guarantees. The 10,000-entry stream uses
more CPU/time than accelerated dumps in these samples; no time budget was raised.
An initial per-fragment UTF-8 prototype measured 14.509905 s at 50,000 entries;
batching conversion measured 9.918324 s in the final samples. Raw initial profiles
are retained rather than substituted with the final profiles.

Before each frame read, baseline accelerated export observed up to 49,999 live
mutable values at 50,000 entries; final exports created **zero** live wrappers.
Every export mode still decrypts exactly N frames, with zero encryption, retaining
the prior **66.7% reduction from the older 3N path**. Focused tests also check one
HMAC tag computation per exported map entry. The replay cache stays `-1024`.

Every before/after sample has the identical complete logical hash:

- 16: `85a6fc1cd67c42e644169e9de34f006715c8330f3890a3b6c544b6cfb3a7fa28`.
- 10,000 (historical wrapper included):
  `f18654506761241ebb4dcadc08363aac78a0b0e1fe65f429f57eb44f54c3589b`.
- 50,000: `1722811c3a7f0ead580775786ddc77b6a17761e6ada39ec761d2611ec5d012f6`.

**Validation receipts and exact commands**

The aliases `$scalePython`, `$scaleWork` and PYTHONPATH are the absolute paths
defined earlier in this report. All commands ran from the same local repository.

| Local receipt | Actual outcome | Notes |
|---|---|---|
| `json-export-small.xml` (p68) | 55 passed, 2 failed, 3 deselected; 13.57 s | Test expected only `branch`; existing fixture also adds trust metadata. Corrected to compare the full pre-export snapshot. |
| `json-export-after.xml` (p69) | 62 passed; 160.75 s | Initial UTF-8 prototype, including two fresh processes per mode/size. |
| `json-export-final.xml` (p70) | **64 passed; 138.37 s** | Final batched implementation and all three fresh-process profiles. |
| `json-export-regressions.xml` (p71) | **248 passed, 1 failed, 5 deselected; 553.88 s** | One new sequence-corruption test used the map-only damage helper and failed before invoking export. All other wider cases passed. |
| `json-export-ownership.xml` (p72) | 3 passed, 1 failed, 64 deselected; 2.67 s | Isolated the same test-helper mistake; nested cursor cleanup, mid-read close and options checks passed. |
| `json-export-ownership-final.xml` (p73) | **133 passed, 5 deselected; 83.64 s** | After fixing the helper to corrupt the actual sequence row, reran all export, map-iteration, map and context cases except the five separately measured large profiles. |

There are **zero skips** in these receipts. Selections overlap; do not sum their
pass counts. The five deselections are three new export profiles (passed in p70)
and two prior large iteration profiles (not rerun in this task). Current export
profiles still verify one decryption per frame at 10,000 and 50,000 entries.
Only the test-helper correction and a docstring clarification followed p71;
runtime implementation did not change. The wider suite was not rerun wholesale
after that fixture-only correction. The final p73 receipt covers the correction
and every other affected export/map/context test on the current source.

The wider run includes every generation stage restart, actual worker exits at
three boundaries, lost acknowledgements, cancellation, publication rejection,
private-reader visibility, receipt corruption, checkpoint quotas, v1 support,
quality API and security-hardening regressions. New tests cover exact stdlib
JSON spelling/order, Unicode/surrogates, floats/nonfinite values, invalid keys/
types, cycles, typed records/sets/tuples/FindingRecords, mutations and later stage
replay, partial writes, cancellation/sink failure, two simultaneously active map
cursors, caller-held sequence authentication, owner closure during frame reads,
frame release, large scalar chunks and SQL JSON binding.

The installed Starlette/httpx deprecation warning remains. Initial Ruff checks
found import order/E731 issues in new code; these were corrected. Final Ruff over
`backend analyzers tests scripts`, compilation and `git diff --check` all pass.
No assertion, error, security guard or warning was suppressed to obtain a pass.

```powershell
# Baseline: same owned corpus, two fresh children per mode and size.
@'
import json
from pathlib import Path
from tests.generation_json_export_probe import profile
root = Path(r'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work')
results = [profile(root / ('json-export-before-' + str(n)), n, ['dumps', 'join']) for n in (16, 10000, 50000)]
(root / 'json-export-before.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results))
'@ | & $scalePython -

& $scalePython -m pytest -q tests/test_json_export.py -k 'not fresh_process_export_profiles' -p short_test_ids --basetemp="$scaleWork\p68" --junitxml="$scaleWork\json-export-small.xml"

& $scalePython -m pytest -q tests/test_json_export.py -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p69" --junitxml="$scaleWork\json-export-after.xml"
& $scalePython -m pytest -q tests/test_json_export.py -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p70" --junitxml="$scaleWork\json-export-final.xml"

& $scalePython -m pytest -q tests/test_json_export.py tests/test_generation_map_iteration.py tests/test_generation_maps.py tests/test_generation_context.py tests/test_checkpoint_pages.py tests/test_analysis_checkpoints.py tests/test_generations.py tests/test_code_quality.py tests/test_security_hardening.py -k 'not large_map_iteration and not fresh_process_export_profiles' -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p71" --junitxml="$scaleWork\json-export-regressions.xml"

& $scalePython -m pytest -q tests/test_json_export.py -k 'sequence_export_never or inner_corruption or adapter_options' -p short_test_ids --basetemp="$scaleWork\p72" --junitxml="$scaleWork\json-export-ownership.xml"

& $scalePython -m pytest -q tests/test_json_export.py tests/test_generation_map_iteration.py tests/test_generation_maps.py tests/test_generation_context.py -k 'not large_map_iteration and not fresh_process_export_profiles' -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p73" --junitxml="$scaleWork\json-export-ownership-final.xml"

$env:PYTHONHASHSEED = '0'
& $scalePython "$scaleWork\verify_pipeline_fixture.py" "$scaleWork\vp-json-export-final" | Tee-Object -FilePath "$scaleWork\json-export-pipeline.log"

& $scalePython -m ruff check backend analyzers tests scripts
& $scalePython -m compileall -q backend analyzers tests scripts
git diff --check
```

Measurements use fresh child processes before wider tests started; later wider
tests and the owned pipeline ran concurrently for correctness, without claiming
their timing as a performance benchmark. Complete fingerprints from
`work/vp-json-export-final/receipt.json` equal
`work/vp-map-iteration-final/receipt.json`, using the unchanged comparator and no
additional normalization. Every cold/warm/incremental phase completes. SQLite
integrity is `ok`, FK violations zero, three generations are `PUBLISHED`, and two
pointers exist. These are 19 inert owned files with existing `PARTIAL` static
coverage status, not an OpenMetadata qualification.

Raw before/prototype/final samples, all six test-receipt summaries, individual
failure messages, final source hashes and complete fixture evidence are bundled
in `docs/evidence/SCALE001_GENERATION_JSON_EXPORT.json`. Original local XML and
receipts remain at the exact work paths above. The recording script is
`work/record_json_export_evidence.py`; run it with `$scalePython` from the repo.

**Acceptance state and exact next action**

| State | Gate and scope |
|---|---|
| VERIFIED | Local small/10k/50k complete export/import hashes, bounded stream chunks and measured process peaks, one authenticated decryption per entry, unchanged cache, exact JSON text and typed replay, failure/cancel/owner/cursor cleanup. |
| VERIFIED | Local owned cold/warm/incremental complete output equality, database/FK integrity and fixture publication; focused/wider recovery, tenant/private-reader and admission regressions as qualified above. |
| VERIFIED | Final Ruff, compilation and diff checks; unchanged HEAD and prior work preserved. |
| FAILED | Latest previously established full qualification on the published base, run 40280429009: GLOBAL_CHECKPOINT_BUDGET in VERIFYING. Local changes do not supersede that failed system qualification. |
| NOT_RUN | Current uncommitted architecture on pinned 21,636-file OpenMetadata, 768,000,000-byte Linux process-tree cgroup, zero swap, unchanged production time/parser/security limits. |
| NOT_RUN | Complete large cold/warm/incremental equality/publication, Linux cancellation and memory/disk exhaustion, real broker/worker recovery and duplicate delivery, PostgreSQL, maximum active ancestor-row/typed-hydration envelope and the full acceptance matrix. |

Remaining separate engineering blockers are final snapshot
`domain.persist_analysis` / `sanitize_metadata` whole-document materialization and
the existing 1,000,000-node guard; full QualityAnalysis/Record hydration and SQL
string results; native correlation working sets; replay-builder cost; the
materialized `current_findings` export producer; and the retained-v2-receipt
normal-expiry/downgrade defect. No migration safeguard or historical receipt was
rewritten here. Custom default callback allocations and deep active ancestor-row
products remain explicit memory risks. The streaming change alone does not solve
these issues.

The next smallest separate engineering task is to measure the final snapshot
sanitizer's projected node count and retained payload on an owned representative
fixture, then design bounded complete projection without changing verdicts or
raising its guard. Do not combine that work with downgrade/expiry repair. Full
Linux qualification subsequently needs explicit authorization to publish the
reviewed continuation work and dispatch the unchanged constrained workflow; no
such action was taken. **SCALE-001 remains NOT QUALIFIED.**

**Subsequent iteration: final snapshot materialization profiling (2026-10-27)**

Status: **NOT QUALIFIED**. Branch and HEAD remain
`codex/scale-001-local-continuation` /
`9e21509591bfa5457cc829ebd5637f95be68d573`. This iteration changed **no production
source, migration, limit, index, receipt or persistence contract**. All 225
pre-existing backend/analyzer/test Python file hashes still match the frozen
manifest. Prior map iteration and JSON export implementations/tests remain intact.
The prior fixture database is byte-identical, still has three PUBLISHED
generations and two pointers, and its references/history were not rewritten.

New local-only files are `tests/snapshot_materialization_probe.py`,
`tests/snapshot_component_probe.py`, `tests/sqlite_memory_probe.py`,
`tests/test_snapshot_materialization_profile.py`, this report update, and the
summary/raw evidence files `docs/evidence/SCALE001_FINAL_SNAPSHOT_PROFILE.json`
and `docs/evidence/SCALE001_FINAL_SNAPSHOT_PROFILE_RAW.json.gz`.

**Method and limits of inference**

Every measured run uses a fresh process and an isolated database. The control
uses the unchanged 19 inert owned files and executes real `execute_analysis` /
`persist_analysis`, all required receipts, validation, promotion and commit.
Cold/warm/incremental complete fingerprints equal the previously published owned
fixture under the unchanged comparator, without additional normalization.

Synthetic variants retain all original 147 metrics and add encrypted MetricRows
with the real first metric's shape until totals reach 10,000, 30,000 or 50,000.
Both quality and captured snapshot fields refer to the same collection. The
original graph, claims, findings and sources are retained. A structured warning
explicitly marks synthetic observation-volume profiling; these observations do
not establish parser coverage or truth on a repository with that many functions.
Successful fixture status is existing `PARTIAL`, not an incomplete execution
being labeled COMPLETE. No imported source code executes.

The normal runs use the existing defaults: **900 seconds/job**, **256,000,000
spill bytes**, **64,000,000 encoded stage bytes**, **256,000 descriptor nodes**,
**1,000,000 sanitizer nodes**, and the unchanged main/replay SQLite caches.
Windows development parser mode is explicit. These are coordinator/process RSS
measurements, **not** process-tree/cgroup, zero-swap or Linux isolation results.

Memory evidence includes entry/exit RSS, sampled stage RSS every 5 ms and Windows
lifetime peak RSS. A lifetime peak cannot be assigned to a later stage merely
because its value remains high. Short allocations can evade sampling or occur
while the encoder holds the GIL; the SQLite write independently sets a new
lifetime high-water mark. Tables do not add overlapping/nested peaks together.
Timings vary with host scheduling/I/O/GC and instrumentation. No throughput
guarantee follows from one local sample.

An additional 2,000-metric process uses tracemalloc with eight frames after the
final boundary. Its overhead is substantial (74.76 s for sanitization), so its
timing/RSS are **not** used as normal performance measurements. It identifies
retained Python allocation sites. Two normal fresh processes per component
experiment compare canonical hashing and read-only SQLite expressions; further
traced/native-counter runs attribute their allocation mechanisms.

**Actual entry points and publication ownership**

1. `jobs.execute_analysis:205` calls `domain.persist_analysis`. The captured
   snapshot (`domain.py:554-610`) retains quality_metrics and capture metadata;
   the initial private snapshot row contains a smaller identity payload.
2. `quality_domain.persist:104-138` builds the quality-finding reference list and
   stores QualityAnalysis JSON. SQLAlchemy binds its complete string via
   `json_export.dumps`; the encrypted metric collection is encoded once here.
3. After IMPACT and the FINAL_OUTPUT lookup, `domain.persist_analysis:1816`
   assembles the final mapping and calls `sanitization.metadata`. Its list
   comprehension (`sanitization.py:189`) and dictionary assignments (`192,201`)
   construct the native sanitized output. The old analysis references are deleted
   and GC runs **after** this copy, not before it.
4. The captured cold call stack proves the first large UPDATE is triggered by
   `domain.audit:103` (`db.get(Audit, ...)`) from `persist_analysis:1874` through
   `Session._autoflush` / `Session.flush`. This occurs before the later explicit
   `project_snapshot` flush. Optimistic version checking remains in the SQL:
   `UPDATE records SET data=?, version=? WHERE records.id = ? AND records.version = ?`.
5. Workspace projection and the FINAL_OUTPUT receipt finish private preparation.
   `Generation.validate:303-418` validates receipts, materializes bounded *row
   counts*, collects captured identity dictionaries, fetches persisted JSON and
   computes canonical hashes (`:361`). Row-count bounds do not bound one large
   snapshot's JSON bytes. Receipt reference validation uses `Record.id` when
   `materialize=False`; it does not repeatedly hydrate the full snapshot.
6. `jobs.execute_analysis` calls `Generation.promote`, then commits pointer,
   visibility, terminal job and cleanup atomically. The short promotion/commit
   is distinct from the earlier private flushes and is not the measured peak.
   Actual typed FINAL_OUTPUT restart semantics are covered by the focused
   regression; large-restart RSS is not inferred from cold measurements.

**Confirmed outcome by fixture**

| Metric rows | Sanitized snapshot nodes | Final-path outcome | Process lifetime peak RSS | Publication |
|---:|---:|---|---:|---|
| 147 | 54,340 cold; 54,240 warm; 55,207 incremental | All three complete | 167,309,312 cold; later phases have retained process state | 3 generations / 2 pointers |
| 10,000 | 261,257 | Cold complete | 294,780,928 | 1 / 1 |
| 30,000 | 681,257 | Cold complete, reproduced | **521,617,408** final native-counter run | 1 / 1 |
| 50,000 | Exceeds 1,000,000; sanitizer does not return | **ValueError: Sanitization structure budget exceeded** | 302,055,424, set before final copy fails | **0 pointers**, private STAGING generation |

The 50,000-row application job is FAILED, last job stage CORRELATING, actual
operation FINAL_SANITIZE. No FINAL_OUTPUT promotion occurs. SQLite/FK checks
pass. Its encrypted metric spill is 51,820,828 bytes with cache_size=-1024, so
neither the spill quota nor an OOM explains this failure. The 21-node owned row
shape alone requires 1,050,000 metric nodes at 50,000 rows, before other fields.
The analogous arithmetic for 195,982 owned rows is 4,115,622 metric nodes; that
is a projection, **not** a measured pinned-repository final payload.

**Stage breakdown: final 30,000-metric run**

All memory columns are raw bytes. Entry/exit RSS are retained process state,
not exact live Python bytes. The SQLite-write peak is separately confirmed by
the lifetime high-water mark and native allocator counters.

| Operation | Seconds | RSS entry -> exit | Sampled stage RSS peak |
|---|---:|---:|---:|
| Quality comparison | 8.2140 | 145,604,608 -> 147,701,760 | 147,701,760 |
| Quality JSON string binding (24,971,033 chars) | 1.5149 | 156,467,200 -> 182,034,432 | 182,034,432 |
| Final sanitization | 1.5298 | 204,017,664 -> 210,317,312 | 210,317,312 |
| Final GC | 0.1589 | 210,317,312 -> 210,317,312 | 210,317,312 |
| Snapshot JSON string binding (26,197,173 chars) | 0.5977 | 210,329,600 -> 236,429,312 | 236,429,312 |
| **SQLite snapshot UPDATE** | **0.2111** | **236,429,312 -> 262,627,328** | 502,472,704; **lifetime peak 521,617,408** |
| FINAL_OUTPUT receipt | 0.6013 | 236,429,312 -> 236,437,504 | 236,437,504 |
| Snapshot JSON decode during validation | 0.1474 | 244,035,584 -> 289,435,648 | 289,435,648 |
| Canonical snapshot string (24,903,656 chars) | 0.1719 | 263,237,632 -> 288,976,896 | 288,976,896 |
| Canonical UTF-8/hash update | 0.0239 | 288,976,896 -> 288,976,896 | 288,976,896 |
| Complete generation validation (includes above decode/hash) | 5.4841 | 236,437,504 -> 222,965,760 | 289,435,648 |
| Promotion | 0.0302 | 222,965,760 -> 223,010,816 | 223,010,816 |
| Atomic publication commit | 0.0050 | 223,010,816 -> 223,010,816 | 223,010,816 |
| **Complete final boundary -> atomic commit** | **8.6733** | **204,017,664 -> 223,010,816** | **Lifetime peak 521,617,408** |
| Later full QualityAnalysis hydration | 0.3053 | 223,010,816 -> 263,139,328 | 288,112,640 |
| Later current_findings producer (330 quality findings) | 0.0198 | 263,139,328 -> 263,151,616 | 263,151,616 |

The final process/database contains 30,000 complete metrics, 336 findings and all
original graph output. Its private metric ciphertext is 31,100,828 bytes. The
main database is 64,987,136 bytes after disposal/checkpoint, WAL zero. SQL counters
and commit events are retained in raw evidence; raw validation batches are at
most 250 rows, but one batch includes the 26.2 MB snapshot. ID-only receipt
fetches are aggregated (2,613 calls / 2,413 rows), not stored as thousands of
instrumentation event objects. An earlier detailed-fetch run is retained and
reproduces the same operation peak (523,485,184 bytes); a later aggregate run
measured 522,592,256. These are independent observations, not improvements.

**Allocation mechanisms, necessity and risk**

- **Final native copy, confirmed:** the traced 2,000-row run retains 2,824,933
  new Python bytes across sanitization. Dominant sites are dictionary child
  insertion (1,705,688), row decryption/JSON strings (437,493), dictionary creation
  (402,624), and list creation (225,112). Shared caches and allocator reuse mean
  RSS can stay nearly flat while this new graph exists. It survives in
  `snapshot.data`; input references survive until after sanitization. Privacy,
  collision/depth/type/node checks are required. Returning input or resetting
  the node counter per row would change those guarantees.
- **SQL strings, confirmed:** the traced string adapter retains one complete
  3,113,207-byte result in the 2,000-row fixture (`json_export.py:201`). Complete
  strings are required by the current SQLAlchemy/driver API. QualityAnalysis and
  snapshot both serialize metrics under existing persistence contracts; removing
  either field is a compatibility change, not a proven redundant write.
- **Dominant native SQLite work, confirmed:** during the actual UPDATE,
  SQLite-managed outstanding allocations are **62,482,680 before**, **350,664,352
  at peak**, **88,676,208 after**. The 288,181,672-byte native increase closely
  matches the process RSS spike. These counters exclude underlying allocator
  overhead and cover the process's SQLite connections, not Python objects.
  Only the profiling high-water statistic is reset; no SQLite memory/cache
  setting changes. See the [SQLite allocator API](https://www.sqlite.org/c3ref/memory_highwater.html).
- **Graph index expression evaluation, confirmed contributor:** db.py:112-133
  and migrations 0013/0016 define four generic JSON expression indexes on records,
  including snapshot rows. A read-only CTE evaluates their exact expressions on
  the same snapshot with **one bound input**, without dropping indexes, changing
  schema, or writing data. SQLite malloc peaks are 54,673,472 for `length`,
  107,067,944 for one JSON extraction, and **264,261,088 for the four index
  expressions**. The latter is 209,587,616 above the binding/length control.
  EXPLAIN UPDATE also shows the JSON functions. This establishes a large native
  expression-evaluation cost; it does not individually partition JSON parse
  caches, SQLite value copies, pager/index-update and allocator fragmentation.
- **Decode/hydration, confirmed:** validation's database snapshot read and later
  quality read each construct another native Python object graph. In the traced
  2,000-row run, json.decoder contributes 6,194,954 and 3,533,732 bytes respectively.
  One decode event has a negative *net* delta because unrelated SQLAlchemy objects
  are collected; this does not mean decoding has no allocations. Full typed-record
  hydration is not exercised by the cold final lookup; it remains a large-restart
  measurement gate, not a claimed cold-run root cause.
- **Canonical hash duplication, confirmed but secondary:** `generations.py:361`
  allocates the entire sorted JSON string and UTF-8 bytes before hash update.
  The isolated whole/stream experiment has identical byte counts and SHA-256.
  Traced peak new Python allocations are **49,815,360 -> 192,895 bytes**. Untraced
  median times are **0.2353 -> 0.7372 s**. Whole-process peaks remain approximately
  130.9/130.8 MB because earlier input decoding already peaked there. Thus this
  is measured component allocation relief, **not a measured pipeline peak fix**.
- **Ancestors and callbacks, confirmed separate costs:** authenticated depth
  1/4/8 map exports with a 1,000,000-character pending scalar per ancestor retain
  complete hashes, 64 KiB chunks, cache -1024 and exactly 400/1,000/1,800
  decryptions. Stream sampled peaks are 124,841,984 / 132,886,528 / 138,362,880;
  earlier replay may set a higher lifetime peak. Existing `encoded(set)` for
  50,000 members allocates a 400,056-byte list of references. These are additional
  costs, not the dominant SQLite UPDATE spike in the final-snapshot fixture.
- **Finding lists and identity maps, inspected/measured at current scope:**
  `quality_domain.persist:105`, `current_findings:141`, and
  `Generation.validate:341` retain reference lists/dictionaries. This fixture's
  producer has 330-331 quality findings, not tens of thousands. No large-finding
  RSS claim is made from that small producer. Validation does not drop duplicate
  checks. The short atomic commit has six identity-map objects, two dirty and
  one new row in the large run; it is not a repository-sized publication buffer.

**Recommended next task; measured benefit versus expectation**

The first full-workload blocker is the **inline snapshot representation versus
the unchanged 1,000,000-node privacy guard**. At the same inline contract, merely
streaming JSON, compressing ciphertext or batching validation cannot make the
50,000-row owned payload pass. A future complete snapshot representation decision
must preserve privacy/resource accounting and old readers; resetting counters,
omitting metrics, changing verdicts or raising the guard is not an acceptable fix.
That broader representation work was not started here.

The smallest focused candidate addressing the **measured successful-path peak**
is **avoiding generic graph JSON expression-index evaluation for snapshot rows**.
Next implementation task: prototype snapshot-excluding/guarded graph indexes in
a new disposable owned database, keep every row/tenant predicate intact, and
prove complete query-result equality plus EXPLAIN QUERY PLAN coverage for graph,
endpoint, snapshot, legacy and mixed-kind reads. Partial-index eligibility must be
proved; SQLite cannot be assumed to infer every implied kind predicate. Only
after that proof should model definitions and an additive index migration be
proposed. Do not touch downgrade/expiry or alter historical receipts for this.

Expected benefit is removal of a large SQLite-native allocation component; the
209.6 MB expression-control difference is a target, **not a promised reduction
of the 521.6 MB pipeline peak**. No snapshot-excluding index was installed, so no
pipeline before/after optimization benefit is claimed. Streaming the canonical
validation digest is a smaller code-only alternative with proven component byte
equality, but it is slower in this experiment and would leave the dominant write
peak and the sanitizer refusal intact. Prioritize the measured write/index path
over claiming qualification from that secondary allocation saving.

**Validation, reproducibility and acceptance state**

| Receipt / check | Actual result |
|---|---|
| `snapshot-profile.xml` (p74) | **4 passed**, 0 skipped, 483.68 s: control three phases, 10k, 30k and expected 50k fail-closed |
| `snapshot-profile-large-final.xml` (p75) | **1 passed**, 70.99 s after aggregating tiny metadata-fetch events |
| `snapshot-regressions.xml` (p76) | **139 passed**, 5 deselected, 0 skipped, 322.04 s |
| `snapshot-profile-native-final.xml` (p77) | **1 passed**, 90.29 s with SQLite allocator counters |
| Component experiments | 14 fresh child runs + 3 traced component runs + 3 final native-counter runs: exit 0; complete hash/byte equality assertions pass |
| Traced 2k pipeline / cold call-path pipeline | Exit 0; successful PARTIAL publication and SQLite/FK integrity |
| Full owned comparisons | Control all three phases equals prior fixture; independent 30k repeats equal under unchanged complete comparator |
| Preservation | All 225 frozen source hashes and prior database byte hash unchanged; old 3 generations / 2 pointers retained |
| Static checks | Full Ruff, compileall and git diff --check pass |

Additional read-only checks verify the old and new control audit chains (28
linked events each, identical event-ID fingerprint) and 3,694 edges each, with
zero unresolved/cross-tenant/cross-generation endpoints or duplicate complete
edge payloads. The final large fixture has nine verified audit events and 1,230
checked edges. These checks do not rewrite history or count a valid PARTIAL
snapshot as full-repository qualification.

Selections overlap. The five deselections are the prior two large iteration and
three large JSON-export profiles; current nested export experiments and focused
regressions preserve their read/lifetime invariants. The installed Starlette/httpx
deprecation remains. Initial profiling-only Ruff/import issues were corrected.
An initial 10k pilot appended a string instead of the existing structured warning
shape and failed with AttributeError before final profiling; it was a **fixture
error**, preserved as such, not a memory finding. Corrected scaled fixtures retain
all original metrics and use the proper structured warning. No application error
or guard was suppressed; the intentional 50k refusal remains FAILED in its job.

Use the previously defined executable/work aliases. These are **historical
evidence paths**; use fresh basetemp/output names on rerun, since pytest clears
its basetemp. The scripts and raw evidence retain complete subprocess commands,
exit codes, timings, hashes and paths.
The evidence packager is `work/record_snapshot_materialization_evidence.py`.
It verifies source/database preservation and the read-only audit/graph checks,
then writes the summary JSON and deterministic compressed raw bundle. No private
keys, database files or source payloads are included in that evidence bundle.

```powershell
& $scalePython -m tests.snapshot_materialization_probe "$scaleWork\snapshot-control-pilot" --all-phases
& $scalePython -m tests.snapshot_materialization_probe "$scaleWork\snapshot-medium-pilot" --metrics 10000
& $scalePython -m tests.snapshot_materialization_probe "$scaleWork\snapshot-medium-validated" --metrics 10000

& $scalePython -m pytest -q tests/test_snapshot_materialization_profile.py -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p74" --junitxml="$scaleWork\snapshot-profile.xml"
& $scalePython -m pytest -q 'tests/test_snapshot_materialization_profile.py::test_owned_final_snapshot_profile[30000]' -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p75" --junitxml="$scaleWork\snapshot-profile-large-final.xml"

& $scalePython "$scaleWork\run_snapshot_components.py"
# Three traced hash/index components use --allocation; full commands are in
# work/snapshot-components/traced-runs.json and the compressed raw evidence.
& $scalePython -m tests.snapshot_materialization_probe "$scaleWork\snapshot-allocation-2000" --metrics 2000 --allocation

& $scalePython -m pytest -q tests/test_json_export.py tests/test_generation_map_iteration.py tests/test_generation_maps.py tests/test_generation_context.py 'tests/test_generations.py::test_each_stage_survives_restart_without_private_reader_leaks[FINAL_OUTPUT]' tests/test_generations.py::test_final_promotion_rejects_cancellation_replacement_and_access_revocation tests/test_generations.py::test_final_commit_failure_or_lost_acknowledgement_is_consistent -k 'not large_map_iteration and not fresh_process_export_profiles' -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p76" --junitxml="$scaleWork\snapshot-regressions.xml"

& $scalePython -m pytest -q 'tests/test_snapshot_materialization_profile.py::test_owned_final_snapshot_profile[30000]' -o junit_family=xunit1 -p short_test_ids --basetemp="$scaleWork\p77" --junitxml="$scaleWork\snapshot-profile-native-final.xml"
& $scalePython "$scaleWork\run_snapshot_native_components.py"

& $scalePython -m ruff check backend analyzers tests scripts
& $scalePython -m compileall -q backend analyzers tests scripts
git diff --check
```

Normal RSS runs were isolated from the concurrent traced/allocation and regression
work; instrumented runs are identified rather than mixed into the normal stage table.
Allocator counters use only the already loaded, version-matched Windows SQLite
DLL (3.50.4). No cache/heap limit, database state, crypto verification or parser
control is changed. Sampling, native allocator, Python tracing and database size
are distinct measurements and are not interchangeable with cgroup memory.stat.

**VERIFIED:** owned complete outputs and three-phase control equivalence;
repeated 30k output equivalence; actual node-guard refusal; native SQLite UPDATE
peak/contributor; authenticated nested export/callback experiments; focused
recovery/atomicity/security regressions; SQLite/FK integrity; preservation/static
checks. No production optimization was implemented or benchmarked before/after.

**FAILED:** the owned 50k inline final snapshot cannot pass its unchanged node
guard. The last established published-base full Linux qualification failure is
also not superseded by these diagnostics.

**NOT_RUN:** new architecture on the full pinned 21,636-file workload, Linux
768,000,000-byte process-tree cgroup/zero swap, production Linux parser isolation,
full large cold/warm/incremental/restart memory, PostgreSQL/broker/worker and
exhaustion acceptance matrix, and candidate index query-plan/migration proof.
Large finding-producer scaling, maximum ancestor/typed hydration, replay-builder
cost and the separate normal-expiry/downgrade defect remain open. Full constrained
Linux qualification remains separately pending authorization. No commit, push,
PR/main change, remote workflow or release action occurred.
**SCALE-001 remains NOT QUALIFIED.**

## Disposable graph-index prototype and compatibility decision — 2026-10-27

**Decision: REJECTED for the tested candidates. SCALE-001 — NOT QUALIFIED.**
The experiment independently demonstrates a substantial native-memory reduction,
but all three candidate designs change the returned sequence of an existing
mixed-kind snapshot query. The plain partial and CASE variants also change
malformed-snapshot write behavior. These are recorded failures, not waived
because a memory benchmark improved. No production migration is proposed here.

Branch remains `codex/scale-001-local-continuation`, HEAD remains
`9e21509591bfa5457cc829ebd5637f95be68d573`. All 229 frozen preexisting Python
source/test hashes and all four source database byte hashes are unchanged.
The old fixture still contains three PUBLISHED generations and two pointers.
Only new opt-in probe modules, this appended report, new evidence and disposable
work-directory artifacts were added in this task. No application source,
migration, production index, published generation or pointer was changed.

**Scope and reproducibility.** Python 3.14.3 / SQLite 3.50.4 / Windows. These
are coordinator RSS and SQLite allocator measurements, **not Linux cgroup or
process-tree qualification**. Same owned 19-file fixture and successful
147/10,000/30,000-metric volumes from the preceding diagnostic. Scaled fixtures
retain all original metrics. Ordinary PARTIAL snapshot publication is legitimate
for this fixture; it does not demonstrate a COMPLETE full pinned analysis.
The 50,000-metric sanitizer refusal remains a separate failed gate.

All writes require an exact resolved database ownership marker inside:
`C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\graph-index-prototype-20261027`.
Original databases are read-only SQLite backup sources. Existing destinations
are refused. The original-read-only and outside-root refusal tests pass.
No production database is opened for writes. No key, database or session cookie
is included in the evidence bundle.

### Original schema and measured cause

`backend/db.py:112–133`, migrations 0013/0016, and the actual sqlite_master
definitions establish these four expressions (CASTs and JSON_QUOTE retained):

```sql
CREATE INDEX ix_records_graph_class ON records (organization_id, repository_id, kind, CAST(JSON_EXTRACT(JSON_QUOTE(JSON_EXTRACT(data, '$."scope"')), '$."snapshot_id"') AS VARCHAR), CAST(JSON_EXTRACT(data, '$."class"') AS VARCHAR), id);
CREATE INDEX ix_records_graph_snapshot ON records (organization_id, repository_id, kind, CAST(JSON_EXTRACT(JSON_QUOTE(JSON_EXTRACT(data, '$."scope"')), '$."snapshot_id"') AS VARCHAR));
CREATE INDEX ix_records_graph_source ON records (organization_id, repository_id, kind, CAST(JSON_EXTRACT(data, '$."snapshot_id"') AS VARCHAR), CAST(JSON_EXTRACT(data, '$."source"') AS VARCHAR));
CREATE INDEX ix_records_graph_target ON records (organization_id, repository_id, kind, CAST(JSON_EXTRACT(data, '$."snapshot_id"') AS VARCHAR), CAST(JSON_EXTRACT(data, '$."target"') AS VARCHAR));
```

The final write is `UPDATE records SET data=?, version=? WHERE records.id = ?
AND records.version = ?`. All four full indexes participate in snapshot-row
maintenance. Their JSON expression evaluation retains substantial SQLite-native
allocation while the complete snapshot SQL string and other pipeline state are
alive. This prototype measures the effect of excluding that row from these
expressions; it does not assume four independent parses or sum overlapping
allocator/RSS peaks. All other indexes, including snapshot identity and summary
indexes, are unchanged. Complete-string SQL binding, canonical hashing,
sanitization and hydration still execute through the existing code.

### Candidates, unchanged semantics, and actual incompatibilities

`tests/graph_index_prototype.py::install` implements disposable alternatives:

1. `rebuilt`: recreate the identical full definitions; separates rebuild/free-page
   effects from snapshot exclusion. This is a measurement control.
2. `partial`: append `WHERE kind != 'snapshot'` to each original definition.
3. `validated_partial`: same partial indexes plus two snapshot validation
   triggers and a conservative test-only query adapter.
4. `guarded`: retain full index membership, wrap each original JSON expression
   in `CASE WHEN kind != 'snapshot' THEN <original expression> END`.

DDL installation is enclosed in a savepoint; exceptions roll back all candidate
DDL. Incomplete legacy index sets are refused before mutation. No application
migration code or downgrade was added. Existing migrations were exercised only
on a newly created disposable legacy database.

The validated variant's BEFORE INSERT / BEFORE UPDATE OF data,kind trigger runs
one multi-path JSON1 expression on snapshots:

```sql
SELECT json_extract(NEW.data,
  '$.scope', '$.snapshot_id', '$.source', '$.target', '$.class');
```

Its WHEN clause requires `NEW.kind = 'snapshot'` and every actual NOT NULL
column to be non-NULL. Native NOT NULL constraints still reject invalid rows;
this condition preserves the tested error precedence rather than allowing a
JSON trigger to mask the original constraint error. The initial trigger lacked
this condition and failed the NULL-natural-key plus malformed-JSON case; that
prototype failure is retained in `compatibility.json`. The final variant matches
all 229 tested insert/update/error/rollback results, including exception type,
message, SQLite error code/name, transaction state and stored byte/type values.
This corpus is evidence, not proof of all SQLite constraint combinations.

No strict `json_valid` guard was substituted: that could reject legacy JSON5 or
JSON-as-BLOB values the original JSON1 expressions accept. The corpus includes
JSON5, JSONB and malformed/one-byte-mutated blobs, empty/truncated/invalid text,
duplicate fields, NULL/missing fields, scalar/array/object type variation,
Unicode, embedded NUL, numeric/string affinity, duplicate keys/IDs, FK errors,
kind transitions and savepoint rollback. Original CASTs, BINARY comparison and
query collations remain intact. SQLite documents the relevant compatibility in
[JSON1](https://www.sqlite.org/json1.html).

`guarded_statement` adds the exact redundant exclusion only for a proven root
AND-conjunct on the real Record table: static non-snapshot `kind ==` or a
nonempty all-non-snapshot `kind IN`. It refuses aliases, OR inference, collation
changes, NULL/empty sets and runtime parameter overrides. It preserves tenant,
repository and publication-visibility predicates. This is test-only plumbing,
not a safe general-purpose production rewrite. SQLite's partial-index predicate
inference is limited; see [partial indexes](https://www.sqlite.org/partialindex.html).

**Latest exact compatibility matrix: `compatibility-4.json`.** Each mode executes
62 SQL query shapes with complete raw row content/order and 229 write cases.
All explicit-order results match; the typed field projection also matches.

| Candidate | Changed complete result sequences / 62 | Changed write results / 229 | Decision |
|---|---:|---:|---|
| Partial | 1 | 18 | REJECTED |
| Validated partial | 1 | 0 | REJECTED |
| CASE guarded | 1 | 18 | REJECTED |

The concrete sequence failure is
`backend/domain.py::snapshot_record_query` (`:204`) as used by
`scoped_snapshot_records` (`:219`), with scope.snapshot_id OR top-level
snapshot_id and no kind restriction / ORDER BY. The complete row set is equal,
but the mixed-kind returned sequence differs. Baseline uses
`ix_records_graph_target (organization_id=? AND repository_id=?)`; partial uses
`ix_records_scoped_current` for the same prefix. CASE keeps a graph-index scan
but changes legacy snapshot expression keys and the sequence. The fixture
includes historical snapshot rows with non-NULL top-level graph fields to expose
that case. Although SQL without ORDER BY does not promise ordering, the requested
compatibility contract expressly includes observable sequence equality. Neither
sorting the evidence nor weakening that assertion is an acceptable fix here.

### Query plans and read-performance risk

All 62 original/candidate SQL statements, binds, full rows, hashes, seven latency
samples and EXPLAIN QUERY PLAN outputs are retained in the raw receipt. Examples:

| Query | Original full indexes | Validated partial prototype |
|---|---|---|
| Node page | graph_snapshot: tenant/repository/kind/snapshot expression seek | Same expression seek after explicit exclusion |
| Known-kind class filter | graph_class expression seek where selected | Original expression usable with proven exclusion |
| Workspace direct count | covering graph_snapshot expression seek | Same covering seek after exclusion |
| Neighborhood UNION branches | graph_source / graph_target: snapshot and endpoint expression seeks | scoped_current: tenant/repository/kind prefix only |
| Mixed snapshot query | graph_target tenant/repository prefix | scoped_current prefix; sequence changes |

The root-only adapter does not descend into UNION branches or nested subqueries.
This is a **confirmed query-plan regression**, with measurable read slowdown:
on `neighborhood_compat-node-0000_0`, seven-sample medians were baseline 0.058 ms,
plain partial 4.364 ms, validated partial 7.751 ms and CASE 7.203 ms. Node-page
medians were 0.043 / 0.141 / 0.191 / 0.368 ms respectively. These small warm
microtimings are host/order sensitive and do not predict production latency;
loss of the selective seek is established independently by the plans. No claim
of general query acceleration is made. Multi-repository nested workspace shapes
also need explicit coverage before proposing any adapter.

### Fresh-process write and publication measurements

45 fresh child processes: three sizes × five modes × three repetitions, randomly
interleaved with fixed seed 74. Authentic snapshot bytes/version are written back
unchanged and then a second update is rolled back. Every run verifies exact
contents/version, integrity, FKs and unchanged generations/pointers. SQLite main
cache remains 32 MiB, WAL and FK enforcement remain enabled. SQLite counters
reset only statistics. Process RSS includes copy/DDL/setup; native peak is reset
around the measured UPDATE. Values below are max bytes and median seconds.

| Metrics | Mode | Process peak RSS (bytes) | SQLite UPDATE peak (bytes) | UPDATE median s |
|---|---|---:|---:|---:|
| 147 | Baseline | 50,425,856 | 24,607,120 | 0.01354 |
| 147 | Identical rebuilt | 64,458,752 | 36,845,800 | 0.01436 |
| 147 | Validated partial | 55,255,040 | 24,132,128 | 0.01536 |
| 10,000 | Baseline | 161,615,872 | 127,122,696 | 0.06193 |
| 10,000 | Identical rebuilt | 165,937,152 | 131,338,176 | 0.07272 |
| 10,000 | Validated partial | 88,748,032 | 53,769,200 | 0.02011 |
| 30,000 | Baseline | 393,166,848 | 342,798,648 | 0.16231 |
| 30,000 | Identical rebuilt | 397,656,064 | 347,028,336 | 0.17263 |
| 30,000 | Validated partial | 188,215,296 | 137,459,424 | 0.06148 |

The raw and summary receipts include every plain partial / CASE sample and DDL
installation timing as well. Small-process RSS does not improve: setup effects
dominate at 147 rows. The identical-rebuild control does not explain the large
candidate reduction. The validating trigger has a real parse/allocation cost
relative to unvalidated exclusion, which cannot safely replace it.

Ten additional fresh full owned-pipeline runs retain sanitization, encrypted
stores, hashes, original persistence and atomic publication: one baseline and
candidate process each for 147 (cold/warm/incremental) and 10k (cold); three
baseline and three candidate processes for 30k (cold). No sanitizer or publication
operation is skipped. Full repository files are never executed.

| Cold metrics | Mode | Repetitions | Peak RSS at final path (bytes) | SQLite UPDATE peak (bytes) | UPDATE median s | Final path median s |
|---|---|---:|---:|---:|---:|---:|
| 147 | Baseline | 1 | 167,034,880 | 31,941,328 | 0.01383 | 4.732 |
| 147 | Validated partial | 1 | 158,621,696 | 19,300,792 | 0.01536 | 5.564 |
| 10,000 | Baseline | 1 | 295,825,408 | 149,171,584 | 0.25813 | 15.822 |
| 10,000 | Validated partial | 1 | 219,480,064 | 71,667,568 | 0.03321 | 6.830 |
| 30,000 | Baseline | 3 | 523,722,752 | 350,662,000 | 0.21887 | 11.529 |
| 30,000 | Validated partial | 3 | 342,511,616 | 167,289,392 | 0.09525 | 12.604 |

The measured 30k publication RSS reduction is **181,211,136 bytes (34.6%)**;
SQLite UPDATE peak reduction is **183,372,608 bytes (52.3%)**. These are actual
prototype results, distinct from the earlier 209.6 MB expression-control estimate.
Whole-process peaks for the three-phase small runs were baseline 204,980,224 and
candidate 195,145,728 bytes (later phases/readback included), so the cold boundary
must not be confused with the complete small process. The large whole-process
peaks equal the final-path maxima in the table.

30k complete cold-analysis medians were 114.441 s baseline and 117.441 s candidate.
The shorter UPDATE does **not** yield an established end-to-end speedup. The final
path median is slower here; reads/query-plan loss, other work and host variation
remain relevant. Early small comparisons overlapped non-RSS regression work and
are not isolated causal timing experiments. All individual timings are retained.

**Database size:** main file allocated pages remain identical in every mode:
147: 30,457,856 bytes; 10k: 29,220,864; 30k: 64,987,136. Baseline→candidate free
pages are 79→140, 147→164, 285→304; identical rebuild produces the same counts.
No VACUUM or shrink was performed, and free pages are not a file-size saving.
Exact per-index bytes are **BLOCKED** on this linked SQLite build because `dbstat`
is unavailable (`no such table: dbstat`). No unmeasured index-size saving is
claimed. Full definitions and allocation/page receipts are preserved.

### Correctness, security, recovery tests and commands

Five unchanged `scripts/compare_scale_outputs.py` comparisons pass: complete
control cold/warm/incremental, 10k and each of the three 30k baseline/candidate
pairs. Every snapshot, quality projection, finding, claim, evidence item,
dependency, graph node/edge, drift/risk path, parser artifact and inventory hash
is included by the existing comparator. Only its preexisting administrative
identity/timing and declared unordered-set normalization is used. No additional
normalization was added. This does **not** erase the separately failed raw SQL
sequence comparison.

Read-only checks verify all ten publication databases plus all four originals:
SQLite/FK integrity, every audit-chain link, complete edge endpoints and ownership,
no unresolved/cross-tenant/cross-generation or duplicate complete edge data.
The two three-phase controls retain three PUBLISHED generations/two pointers;
each scaled cold database has one PUBLISHED generation/one pointer. No failed
or incomplete snapshot was relabeled COMPLETE.

| Check / receipt | Actual outcome |
|---|---|
| Strict prototype contract, `candidate-contract-current.xml`, p82 | **17 passed, 5 FAILED**, 0 skipped, 15.34 s; exit 1 retained |
| Same strict checks before formatting, p80 | 17 passed, 5 FAILED, 18.73 s |
| Existing regressions with validated candidate, `candidate-regressions.xml`, p79 | **27 passed**, 0 skipped, 178.97 s |
| Same regressions with original baseline, `baseline-regressions.xml`, p81 | **27 passed**, 0 skipped, 90.64 s |
| HTTP comparison, `api-2/result.json` | **20 requests/mode, zero differences**, complete response byte SHA/content-type/status and payload equality |
| Legacy 0013 refusal → 0016 data → existing head upgrade | Pass in strict suite; original ordered queries and all writes equal; indexes/triggers survive existing upgrades; integrity/FKs pass |
| Fresh isolated UPDATE children | 45/45 exit 0; integrity/FKs/content/version/pointers pass |
| Full owned pipeline children | 10/10 exit 0; legitimate PARTIAL outputs published |
| Complete fingerprint comparisons | 5/5 exit 0, equal |
| Ruff / changed-file formatting / compileall / diff check | Pass; exact outputs in `final-checks.json` |

The five strict failures are three candidate sequence failures and plain-partial
/CASE write-equivalence failures. They are real failed assertions, not xfail,
skipped, suppressed or included as passing regressions. The opt-in proof file
lives outside default production test discovery because these are explicitly
unapproved disposable candidates. The 27-test sets overlap; they are not 54
distinct regressions. They cover graph pagination/filtering/relationships,
workspace indexes/pages, publication visibility, cancellation/access revocation,
final commit failure and lost acknowledgement. The HTTP comparisons additionally
check anonymous 401, cross-tenant/revoked grant/private-generation 404 and complete
authorized graph pages/neighborhoods. Credentials are never written to receipts.

Initial harness errors (missing required natural_key in the first fixture,
format/import issues) were corrected without altering application behavior.
The earlier validator error-priority failure and final candidate failures remain
in evidence. The installed Starlette/httpx deprecation warning remains unrelated.

Reproduce with a **new root/output/basetemp**; drivers refuse existing output
directories, and pytest clears its basetemp. The aliases below identify actual
historical evidence locations, not permission to overwrite them:

```powershell
$scalePython = 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe'
$scaleWork = 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work'
$prototype = "$scaleWork\graph-index-prototype-20261027"
$env:APP_ENV = 'demo'
$env:SCALE001_PROTOTYPE_ROOT = $prototype
$env:PYTHONPATH = "C:\Users\sai krishna\Projects\ProjectTrace-local;$scaleWork"
$env:SCALE_COMPAT_RUN = 'compatibility-4'
& $scalePython "$prototype\run_compatibility.py"
& $scalePython "$prototype\run_measurements.py"
& $scalePython "$prototype\run_publication.py"
& $scalePython "$prototype\compare_publications.py"
& $scalePython -m tests.graph_index_api_probe "$scaleWork\p74\test_owned_final_snapshot_prof0\owned\benchmark.db" "$prototype\api-2"

# p82 strict command is also stored verbatim with failure output in final-checks.json.
& $scalePython -m pytest -q "$prototype\test_candidate_contract.py" -p short_test_ids -o junit_family=xunit1 --basetemp="$prototype\p82" --junitxml="$prototype\candidate-contract-current.xml"

# Run once per mode, with unique basetemp/XML (p79 candidate, p81 baseline).
$env:SCALE001_INDEX_TEST_MODE = 'validated_partial' # 'baseline' for p81
& $scalePython -m pytest -q tests/test_graph_pages.py tests/test_indexed_workspace_queries.py tests/test_workspace_pagination.py tests/test_graph_impact.py tests/test_generations.py::test_visibility_scope_switches_in_one_session_and_rechecks_publication tests/test_generations.py::test_public_api_readers_never_return_unpublished_snapshot_or_source tests/test_generations.py::test_final_promotion_rejects_cancellation_replacement_and_access_revocation tests/test_generations.py::test_final_commit_failure_or_lost_acknowledgement_is_consistent -p tests.graph_index_pytest_plugin -p short_test_ids -o junit_family=xunit1 --basetemp="$prototype\p79" --junitxml="$prototype\candidate-regressions.xml"

& $scalePython -m ruff check backend analyzers tests scripts
& $scalePython -m ruff check $prototype
& $scalePython -m compileall -q backend analyzers tests scripts $prototype
git diff --check
```

New modules: `tests/graph_index_prototype.py` (guarded DDL/query experiment),
`graph_index_compatibility.py` (full typed SQL/write corpus),
`graph_index_measure.py` (fresh UPDATE/rollback profiler),
`graph_index_publication_probe.py` (real owned pipeline),
`graph_index_pytest_plugin.py` (explicit test-only installation), and
`graph_index_api_probe.py` (authenticated HTTP comparison). None is imported by
production code. Disposable drivers, real failing assertions, raw database copies,
all logs and XMLs remain under the prototype root. Compact receipts are
`docs/evidence/SCALE001_GRAPH_INDEX_PROTOTYPE.json` and
`docs/evidence/SCALE001_GRAPH_INDEX_PROTOTYPE_RAW.json.gz` (complete plans, raw
results, commands, profiles, hashes, failures and preservation manifest).

**VERIFIED:** owned large native-memory reduction; unchanged explicit-order
results/typed JSON projections; validated corpus writes; authenticated API/tenant
and private-generation checks; real owned output fingerprints; audit/graph/DB
integrity; original files/databases/three generations preserved; focused existing
atomicity/cancellation/lost-ack regressions and static checks.

**FAILED:** full sequence compatibility in all three candidate index designs;
malformed snapshot write semantics in plain partial / CASE. Lost selective
neighborhood seeks are also a confirmed performance defect. The earlier 50k
sanitizer refusal is still open and was not rerun or weakened in this task.

**NOT_RUN / BLOCKED:** production migration/reversal, SQLite runtime-version
matrix and exact per-index byte attribution (`dbstat` unavailable); full pinned
21,636-file workload, Linux 768,000,000-byte cgroup/zero swap, full large cold,
warm/incremental/cancellation/exhaustion/worker recovery/duplicate-delivery and
tenant-isolation acceptance. The measured Windows fixture results do not replace
any of those gates. No GitHub workflow was queried or dispatched in this task.

**Exact next smallest engineering task:** trace the existing mixed-kind query's
consumers and prototype a snapshot-excluding design that preserves its complete
returned sequence (including historical snapshots with graph-shaped fields),
with a failing-first raw-sequence regression. Do not alter or sort the expected
result merely to pass. If preserving that legacy sequence cannot be demonstrated,
any explicit deterministic-order contract change requires a separate decision.
Only after that compatibility blocker is resolved, close the nested UNION/query
predicate-eligibility gaps and rerun the same plan/read-latency corpus. No
production migration is justified by this experiment. Final snapshot
materialization/50k structural shape, large findings/ancestor replay envelopes
and downgrade/expiry remain separate unresolved tasks.

No commit, push, PR/main change, production migration, remote workflow, release
or full Linux qualification was performed. **SCALE-001 — NOT QUALIFIED.**


## Graph-index compatibility recovery — 2026-10-27

**Candidate decision: REJECTED. SCALE-001 — NOT QUALIFIED.** The repaired
implementation restores the exact frozen compatibility corpus, validation and
selective nested seeks, but a broader supported-looking mixed query still
returns a different complete sequence. Passing the historical corpus and
retaining the write-memory saving do not waive that failure.

Branch remains `codex/scale-001-local-continuation`; HEAD remains
`9e21509591bfa5457cc829ebd5637f95be68d573`. All application sources, the original
databases, earlier prototype source/evidence, and the previous report prefix are
frozen by this iteration's `preserved.json` (271 source hashes and four database
hashes). **Verified: all 271 source hashes, all four original database hashes, historical strict-test/evidence hashes and original report-prefix bytes match. The prior three PUBLISHED generations and two pointers are intact; original SQLite/FK, audit-chain and graph-ownership checks pass.** No production migration, commit, push,
PR/main change, remote workflow, release or pinned Linux qualification was
performed. All prototype writes require ownership of an exact resolved database
under `work/graph-index-recovery-20261027`.

## The five reproduced historical failures

`historical-reproduced.xml` reruns the original unchanged implementation and
unchanged strict file: **17 passed, 5 failed, zero skipped**, 108.314 seconds,
exit 1. Historical failure evidence is retained.

1. Plain partial-index mixed query: the original full
   `ix_records_graph_target` scan by organization/repository traverses kind,
   top-level snapshot ID, target and hidden rowid. The partial index cannot serve
   this mixed query because snapshots may match; SQLite chooses
   `ix_records_scoped_current` and traverses kind, created_at and rowid. The same
   179 rows occupy 52 different positions.
2. Validated partial-index mixed query: exactly the same read-side plan and
   52-position sequence failure. Snapshot validation alone does not repair it.
3. CASE-index mixed query: full index membership remains, but every snapshot's
   graph-expression keys are replaced by NULL. Historical snapshot rows with
   non-NULL graph-shaped fields expose eight changed positions.
4. Plain partial write contracts: excluding snapshot rows removes the original
   graph expressions' malformed-JSON rejection. Eighteen tested write/error
   results change, including constraint/error precedence cases.
5. CASE write contracts: snapshot expressions are short-circuited, causing the
   same eighteen changed write/error results.

The original `backend/domain.py::snapshot_record_query` has **no ORDER BY**
This is incidental index traversal, not a complete explicit ordering contract.
Nevertheless the user's requested sequence compatibility is tested literally;
the expected results were not sorted, redefined, or replaced.

## Exact opt-in implementation changes

New modules only; the v1 prototype and frozen tests remain byte-identical:

- `tests/graph_index_recovery.py`: disposable installation/read transformations,
  original-schema/rowid validation, repaired validation for every strategy,
  nested query guards, exact original mixed-shape traversal emulation and CASE
  affinity preservation.
- `tests/graph_index_recovery_plugin.py`: explicit dependency bindings to the new
  implementation for the frozen assertions. A binding receipt identifies each
  rebound callable; no assertion, fixture payload, expected row or frozen file
  is modified. The original installation functions are restored at teardown.
- `tests/graph_index_recovery_probe.py`: fresh-process owned same-value UPDATE,
  complete mixed-read, actual publication, three-phase control and HTTP probes.
- `tests/test_graph_index_recovery.py`: additional real compatibility, AST
  mutation/correlation, refusal, atomic-install and failure assertions.
  **The final added-test selection is 20 tests: 17 passed and three broader sequence assertions failed; none skipped.**

The `partial`, `validated_partial` and `guarded` labels retain their different
index strategies. The first two converge on validated partial indexes after
repairing the missing snapshot validation; CASE still has full membership and
CASE expressions. They are not all aliases for one implementation. The historical
17/5 result therefore remains distinct from **22/22 passed, zero skipped, against the explicitly bound repaired v2 subjects** against
explicitly bound v2 subjects. Passing the v2 subjects does not retroactively make
the rejected historical code pass.

### Validation, error precedence and atomicity

The proven validated candidate's BEFORE INSERT / BEFORE UPDATE OF data,kind
triggers are retained and added to the other two strategies. They run the same
multi-path JSON1 `json_extract` expression for snapshot writes, conditioned on
the actual NOT NULL columns being non-NULL. Native NOT NULL checks still reject
invalid rows with the original precedence; no guard is removed. No strict
`json_valid` substitution narrows JSON5/BLOB compatibility.

Installation is enclosed in an outer savepoint, including index recreation and
trigger creation. An injected trigger-creation failure must leave the complete
original sqlite_master schema unchanged. Tenant/FK constraints and the other snapshot-identity/summary index definitions remain unchanged. Read behavior is evaluated separately below.
All **229/229 frozen write cases per candidate** match in
`compatibility-final.json`, including malformed/empty/NULL/duplicate/type-varied
JSON, JSON5/JSONB, legacy values, failed updates, constraint errors, transaction
state and rollback. This is measured corpus equivalence, not proof for every
possible future SQLite version/constraint combination.

### Exact frozen mixed traversal

The recovery checks the old schema's unshadowed hidden rowid and target-index
`index_xinfo`: all ASC/BINARY keys, exact organization/repository/kind columns,
original CAST/JSON expressions and auxiliary rowid. WITHOUT ROWID or shadowed
rowid aliases are refused. A VARCHAR primary-key ID is not the hidden integer
rowid and cannot substitute for the original tie-breaker.

For exactly the original three root predicates (fixed static tenant/repository
equalities plus matching scope/top snapshot OR), with exactly the real Record
entity/table and no existing ORDER/GROUP/HAVING/DISTINCT, add:

```sql
ORDER BY records.organization_id COLLATE BINARY ASC,
         records.repository_id COLLATE BINARY ASC,
         records.kind COLLATE BINARY ASC,
         CAST(JSON_EXTRACT(records.data, '$."snapshot_id"') AS VARCHAR) COLLATE BINARY ASC,
         CAST(JSON_EXTRACT(records.data, '$."target"') AS VARCHAR) COLLATE BINARY ASC,
         records.rowid ASC
```

This matches the frozen index traversal including NULL-first behavior, original
VARCHAR affinity, Unicode/BINARY collation and the true rowid tie-breaker. Owned
fixtures deliberately reverse lexical IDs relative to insertion/rowid order;
pagination compares literal baseline slices for NULL, scalar, numeric/string,
boolean, Unicode, embedded-NUL and duplicate keys.

An initial broader shape recognizer was unsafe: appending an ID-IN predicate
can cause the original query to use a unique-ID seek, whose order differs from
target-index traversal. That was reproduced and the matcher was narrowed. It
does not silently impose target ordering on aliases, joined/projection queries,
explicit ordering or arbitrary extra WHERE clauses.

### Nested expression-index eligibility and CASE affinity

The v1 adapter inspected only root SELECTs. Neighborhood queries place the
kind restriction and endpoint predicates inside UNION subqueries, where SQLite
could not prove the partial-index predicate from the emitted SQL. V2 traverses
inner SELECTs explicitly and adds the exact redundant non-snapshot predicate
only when the same conservative static kind proof holds in that SELECT.
Tenant/repository predicates, joins, ordering and LIMIT/OFFSET remain intact.
Shared subqueries and correlation require their own tests; recursive CTEs and
runtime parameter overrides are conservatively refused.

CASE requires a matching guarded expression in the reader. Simply putting a
VARCHAR CAST inside CASE removes SQLite's original TEXT comparison affinity:
`CAST('1' AS VARCHAR)=1` is true, while
`CASE WHEN 1 THEN CAST('1' AS VARCHAR) END=1` is false. An intermediate recovery
variant demonstrably changed the frozen `scope_1` result from three rows to zero.
The final disposable CASE index and reader retain an **outer VARCHAR CAST** as
well, restoring affinity and expression-index matching. RHS values were not
silently converted to strings. This intermediate failure is preserved in the
development receipts.

Transformer-added predicates/order/CASE nodes are annotated and reconsidered
when an AST is subsequently changed. Proofs must not be trusted merely because
an earlier execution-options flag survived a changed bind, subquery or filter.
**The final current-worktree mutation, reproof and loader-option tests pass. Earlier bind-mutation and opaque LoaderCriteriaOption cloning failures remain preserved in their original receipts. The corrected adapter preserves opaque option identity; this did not cure the separate shared-ranked-subquery identity failure found by wider tests.** CASE proof for one SELECT must not rewrite
an unrelated inner SELECT that deliberately reads snapshots.

## Plans and statistics evidence

`compatibility-final.json` records zero row-sequence or write differences across
all 62 frozen queries and 229 write cases for all three repaired candidates.
`statistics.json` preserves complete SQL, binds, returned rows, hashes, plans,
seven timing samples and sqlite_stat1 before/after ANALYZE on disposable copies.
Original databases are not analyzed or otherwise modified.

| Shape | Original full indexes | V1 validated partial | V2 recovery |
|---|---|---|---|
| Node page | graph_snapshot tenant/repo/kind/snapshot-expression seek | Same after root guard | Same selective seek |
| Neighborhood UNION source | graph_source with snapshot and source expression equality | scoped_current tenant/repo/kind prefix only | graph_source with **both expression equalities** |
| Neighborhood UNION target | graph_target with snapshot and target expression equality | scoped_current prefix only | graph_target with **both expression equalities** |
| Neighborhood nested count | Same endpoint seeks in subquery | Prefix scan | Both endpoint seeks restored |
| Direct workspace count | Covering graph_snapshot expression seek | Same when root guard added | Same covering expression seek |
| Exact original mixed query | graph_target tenant/repo prefix; no ORDER BY | scoped_current prefix, changed sequence | Explicit legacy-key ordering; candidate temp B-tree |

All 62 corpus row fingerprints remain equal to frozen baseline both before and
after ANALYZE in every tested mode. The baseline mixed plan in this dataset
remains graph_target before/after ANALYZE. This observation is not a guarantee
for different statistics, database content or SQLite versions. The recovered
neighborhood plans preserve both selective expression keys in both UNION arms
before and after ANALYZE; no INDEXED BY hint or forced index selection was added.

`reverse_unordered_selects=ON` reverses the unmodified baseline's original mixed
and core implicit orders, while the recovered exact mixed ordering remains
stable. The core query remains implicit. This diagnostic confirms the limits
of incidental ordering; it is not justification for changing expected results.

## Confirmed broader failure — why corpus success is insufficient

The deliberately unmodified assertion for this variation remains a failure:

```python
snapshot_record_query(org, repo, snapshot).where(Record.version >= 1)
```

On the owned fixture this added predicate excludes no rows, yet it is outside
the narrow safe recognizer. Baseline and candidate each return 179 complete
rows, but sequences differ. Baseline SHA is
`e8bc1be8bbce71eb2e0cb87964e1fb8c761ede4ca9f214c2986ec3821eea7fd6`;
partial candidate SHA is
`af795c91c43dc23693ff758f28ec3ca9e2d6a7c545db1b5655b8c27be79e3d6d`.
All three recovered strategies fail this newly added exact-sequence gate.
The complete row set still matches; that does not satisfy the requested order
contract. The three failures must remain real failures, not xfail or sorted
comparisons. **recovery-acceptance-final2.xml retains all three failures with unchanged full-row assertions and complete failure output.**

### Additional final blocker: shared ranked-subquery identity

The wider unchanged regressions expose five **new service-query failures**:

- `test_large_graph_cannot_truncate_summary_or_paginated_claims`
- `test_summary_is_partial_when_published_snapshot_is_partial`
- `test_projection_rejects_stale_versions_and_is_transactional`
- `test_paging_search_status_grants_and_bounds`
- `test_concurrent_scoped_summary_reads_are_consistent`

The global test-only SELECT rebuild duplicates a shared ranked Subquery identity
used by `workspace_read.latest_jobs`. The generated SQL contains the same
`AS anon_1` ranked query twice, once as a joined FROM and once as an additional
comma FROM. SQLite raises `ambiguous column name: anon_1.position`. This is a
confirmed correctness/service-availability regression, not merely a plan or
latency risk. The frozen corpus's shared-subquery test does not cover this
ranked ORM shape. No attempt was made to suppress the error, weaken those tests
or continue patching the global rewrite until it appeared safe.

The earlier opaque-loader-option fix preserves one special option's identity;
it does not prove shared SQL AST identity is generally preserved. The five
workspace failures plus the three extra-version sequence failures require
rejection of this global AST design. Graph/private-record HTTP equivalence is
route-scoped evidence and cannot conceal these failing workspace endpoints.

Broadening the target-order rewrite again would recreate the independently
proven ID-IN failure. Refusing the rewrite is safe with respect to predicate
semantics but cannot preserve every original incidental traversal after changing
index membership/keys. This is a structural compatibility problem, not a missing
if-statement that should be patched until one fixture turns green.

## Fresh-process memory and runtime verification

**21/21 planned measurement children completed with exit 0. One earlier candidate publication setup failed with exit 1 and remains preserved: 22 distinct fresh-process attempts in total, not 22 successes**
The driver runs three fresh 30k processes per mode for each of same-value UPDATE,
complete mixed read and full owned cold publication (18 children), plus original
and candidate three-phase controls and one paired HTTP probe. The earlier failed
setup attempted to clone an opaque immutable LoaderCriteriaOption and failed
before analysis; after the option-identity fix, a new retry directory completed.
Forensics verify the failed database has integrity/FKs intact and zero records,
generations, pointers or COMPLETE snapshots. Earlier successful micro/mixed
children preceded this setup-only fix and retain their original provenance. Measurements run
sequentially, without concurrent test work, to avoid contamination. Existing
cache/resource/security limits remain unchanged.

Successful owned profiles retain 900 job seconds, 256,000,000 spill bytes, 1,000,000 sanitizer nodes, 256,000 descriptor nodes and 64,000,000 encoded stage bytes. Main/replay SQLite cache settings remain 32 MiB/1 MiB. No budget, crypto or isolation guard was enlarged or bypassed. These are owned Windows probes; the separate Linux ceiling is still 768,000,000 bytes with zero swap.

Values below come from the completed v2 receipts; earlier v1 figures are not substituted:

| 30k measurement | Baseline, 3 fresh runs | V2 validated partial, 3 fresh runs |
|---|---:|---:|
| Complete cold coordinator peak RSS (max bytes) | 524,705,792 | 347,119,616 |
| Snapshot UPDATE SQLite allocation peak (max bytes) | 350,651,800 | 167,279,520 |
| Snapshot UPDATE latency (median seconds) | 0.1392895 | 0.0623150 |
| Complete cold analysis (median seconds) | 76.7677314 | 133.4309199 |
| Complete mixed-read peak RSS / native allocation | 201,789,440 / 83,977,288 bytes | 310,513,664 / 197,360,368 bytes |
| Neighborhood latency / selective plan | 0.2541 ms / both endpoint expression seeks | 0.5600 ms / both endpoint expression seeks |
| DB allocated bytes / free pages | 64,991,232 bytes in cold publication; micro 64,987,136 bytes, 285 free pages | 64,974,848 bytes in cold publication; micro 64,987,136 bytes, 304 free pages |
| Index installation/maintenance cost | 0.0031158 s median validation/no-op install; unchanged full indexes | 0.1109764 s median candidate install; measured UPDATE maintenance above |

Additional measured costs, separate from the publication UPDATE table:

| 30k operation | Baseline (three fresh processes) | Validated partial (three fresh processes) |
|---|---:|---:|
| Same-value UPDATE median seconds | 0.2178515 | 0.0697810 |
| Same-value process peak RSS bytes | 399,798,272 | 194,899,968 |
| Same-value SQLite allocation peak bytes | 342,809,752 | 137,468,560 |
| Complete final publication path median seconds | 5.9220476 | 11.2431980 |
| Mixed complete query median seconds | 0.1139178 | 0.1732042 |
| Seven-sample neighborhood median milliseconds | 0.2541 | 0.5600 |
| Seven-sample node-page median milliseconds | 0.0790 | 0.4965 |

The shorter snapshot write therefore does **not** establish a complete-workload
speedup. Cold analysis is substantially slower in this sequential local sample;
complete mixed reading is slower and allocates more. The seven warm neighborhood
samples establish restored selective plans with equivalent results, but remain
small host/order-sensitive timings rather than a production latency claim.

Cold publication files differ by four 4,096-byte pages (16,384 bytes), while
copied same-value micro databases remain exactly 64,987,136 allocated bytes in
both modes. Their free pages increase from 285 to 304 after candidate rebuild.
No VACUUM, cache increase or storage-limit change occurred. This small observed
file-size difference is not evidence of a substantial storage benefit; dbstat
is unavailable, so per-index byte attribution remains blocked.

RSS and SQLite allocator peaks overlap and must not be summed. Fresh-process
RSS through the operation includes earlier copy/setup/DDL peaks; SQLite native
statistics are reset for the measured window. No pure-sort allocation claim is
inferred from an aggregate window that also performs JSON expression evaluation
and full-row reading. Full-row hash work is explicitly after the query interval.

The explicit mixed ORDER BY requires a temporary B-tree for candidate traversal.
The owned 30k snapshot participates in that query with 26,197,173 characters of
JSON. Native sorter memory, full-row payload duplication and potentially disk
spill must be reported rather than presumed bounded merely because index-write
memory improved. Main cache stays 32 MiB. **Three fresh mixed-read processes per mode returned all 1,777 rows with identical raw complete-row hashes (47cfa7ce1e124e900e00d76ba8d9df66e606447d240244d07d0443b17fce3bc1). Median query time worsened from 0.1139178 to 0.1732042 s. Candidate plans explicitly use a temporary B-tree for the last three ordering terms. Peak RSS through the query rises by 108,724,224 bytes; native allocation peak rises by 113,383,080 bytes. Those are overlapping measurements, not additive allocations or pure-sort attribution. Complete-row hashing runs after the measured query interval.** If dbstat
remains unavailable, exact per-index byte attribution stays BLOCKED; report
measured total page/file sizes and do not invent a disk saving.

All numbers are owned Windows development measurements. They do not establish
Linux process-tree/cgroup anonymous, file-cache or kernel-memory behavior under
768,000,000 bytes and zero swap. Metric-count scaling retains original metrics
but does not substitute for pinned full repository source coverage.

## Actual tests and acceptance state

Final combined current-worktree result: **61 passed, 8 FAILED, zero errors/skips
of 69 tests**, exit 1, in 466.896 seconds by XML (466.94 seconds subprocess wall
time). The frozen 22 passed; the added 20 yielded 17 passed/3 failed; the existing
27 yielded 22 passed/5 failed. Failed intermediate receipts remain preserved:

| Gate | Result / evidence |
|---|---|
| Historical unchanged v1 assertions | VERIFIED reproduction: 17 passed, 5 failed, 0 skipped, exit 1; `historical-reproduced.xml` |
| Frozen 22 assertions against explicit v2 subjects | 22 passed, zero failed/errors/skipped in recovery-acceptance-final2.xml; exact repaired-subject bindings in recovery-acceptance-final2-bindings.json |
| 62 frozen query sequences per repaired mode | VERIFIED zero differences in `compatibility-final.json` |
| 229 frozen write cases per repaired mode | VERIFIED zero differences in `compatibility-final.json` |
| Nested SELECT/UNION/correlation/shared references | Focused frozen neighborhood UNION/count, correlation, shared-reference and recursive-refusal tests pass; the wider workspace ranked-subquery regression still fails, as detailed below. |
| AST mutation / bind change / lifetime reproof | The final current-worktree mutation, reproof and loader-option tests pass. Earlier bind-mutation and opaque LoaderCriteriaOption cloning failures remain preserved in their original receipts. The corrected adapter preserves opaque option identity; this did not cure the separate shared-ranked-subquery identity failure found by wider tests. |
| NULL/type/collation/true-rowid pagination | Frozen sequences plus NULL/type/Unicode/BINARY/true-rowid tie-break and LIMIT/OFFSET tests pass; extra-version sequences fail in all three strategies. |
| Atomic DDL failure / original-schema refusal | Injected trigger-creation failure rolls back installation; original schema/rowid validation and original-database refusal assertions pass. No production schema is changed. |
| Broader extra-version sequence preservation | FAILED for all three recovered modes; expectations unchanged |
| Complete output fingerprints | 4/4 unchanged complete fingerprint comparisons pass: three 30k cold baseline/candidate pairs and the owned cold/warm/incremental control pair. |
| HTTP response bytes/status/headers/order | 20 requests per mode, complete response byte/status/content-type/payload equality. These graph/private-record routes do not exercise the workspace routes that failed wider regression. |
| SQLite/FKs/graph ownership/audit chain | Eight successful publication databases and four originals pass SQLite/FK, complete audit-chain and graph endpoint/tenant/generation ownership checks. Both three-phase controls have three PUBLISHED generations/two pointers; each scaled cold database has one PUBLISHED generation/one pointer. The preserved failed-setup database is also integral, with zero records, generations, pointers or COMPLETE snapshots. |
| Existing relevant regression suite | 22 passed and 5 FAILED of 27 existing regressions. All five failures are workspace pagination/summary SQL errors caused by duplicate shared-ranked-subquery identity. No skips or suppressed failures. |
| Ruff / compilation / diff checks | Ruff, changed-file formatting, compilation and git diff --check all exit 0; exact commands/stdout in static-checks.json. |
| All original source/database hashes and report prefix | Verified: all 271 source hashes, all four original database hashes, historical strict-test/evidence hashes and original report-prefix bytes match. The prior three PUBLISHED generations and two pointers are intact; original SQLite/FK, audit-chain and graph-ownership checks pass. |

Development history remains separately classified: the initial JUnit-option
mistake and parameter-helper/import error were harness problems; intermediate
CASE affinity and AST/bind mutation failures were real prototype defects and
were repaired without changing expected results. An earlier p86 test run was
interrupted while exercising a slow correlation fixture; the fixture was then
bounded to three owned centers and its final test passes. That interruption is
not represented as a completed passing run. An opaque LoaderCriteriaOption
setup-cloning failure was repaired by preserving option identity; its new focused
assertion passes. These corrections do not repair or waive the eight final
acceptance failures. The installed Starlette/httpx deprecation remains unrelated.


**VERIFIED:** exact historical failure reproduction; frozen query/write corpus
equivalence and selective endpoint plans before/after ANALYZE; original traversal
and affinity attribution; completed fresh-process memory/runtime comparisons;
raw owned mixed-query and complete publication fingerprints; HTTP equivalence
within its stated route scope; original-source/database/report-prefix preservation;
SQLite/FK/audit/graph checks and static checks.

**FAILED:** three broader complete-sequence assertions for extra predicates and
five existing workspace pagination/summary regressions caused by AST identity
damage. The earlier 50k inline snapshot's
1,000,000-node sanitizer refusal remains a separate unresolved failure and was
not weakened, combined with this task, or called fixed.

**NOT_RUN / BLOCKED:** production migration/reversal; rowid/SQLite-version and
planner contract across arbitrary production databases; bounded large-sort
acceptance beyond measured owned data; full pinned 21,636-file Linux cgroup /
zero-swap qualification and the complete cold/warm/incremental, cancellation,
memory/disk exhaustion, worker recovery, duplicate delivery, atomic publication
and tenant-isolation matrix. Existing downgrade/expiry and whole-snapshot
materialization concerns remain separate.

## Exact next smallest engineering task

First make the sequence contract explicit: inventory actual mixed-query
consumers and decide whether existing incidental traversal must be preserved for
every supported filter/plan or whether a separately reviewed deterministic
ordering contract is permitted. This iteration has no authorization to silently
change that contract. Under the current strict contract, **reject the partial
membership / NULL-substituted CASE design as a migration proposal**

Reject the global AST interceptor as a production direction: the confirmed
workspace alias-identity failure cannot be accepted merely because another
reader shape passes. Preserve the failing assertions for any follow-up.

The next bounded disposable alternative is a **full-membership compact scalar
projection**: retain every record's original graph-order keys, BINARY/NULL/type
semantics and row identity, while separating key maintenance from repeated
full-snapshot JSON expression evaluation. A materialized scalar-key representation
or isolated projection must prove exact old query membership/traversal, including
snapshot-shaped legacy rows, all write/error/rollback/tenant/atomicity contracts,
the extra-version failure, ID-IN counterexample and all five workspace ranked-query
regressions. It must also preserve selective
nested seeks without arbitrary query AST rewrites and demonstrate equivalent
statistics/planner behavior; no claim of success is made until measured. Simply
forcing an index or adding target ORDER BY everywhere is not a safe alternative.

Only prototype that alternative in owned copies after the contract review; do
not implement a production migration or claim qualification from this task.
Record any expected benefit as a hypothesis, separate from measured benefit.

## Evidence and exact reproduction entry points

Evidence summary: `docs/evidence/SCALE001_GRAPH_INDEX_RECOVERY.json`.
Complete compressed raw evidence:
`docs/evidence/SCALE001_GRAPH_INDEX_RECOVERY_RAW.json.gz`, 1,187,951 bytes,
SHA-256 `c46c0dce40d8c83747048865de4e2d12f4b02d2175846eda8527e7b150bdc838`.
It contains complete query/write results, plans and statistics, fresh-process
commands and their stdout/stderr, complete publication comparisons, HTTP output,
all intermediate/final test receipts, failed-setup forensics and preservation
manifest. It omits keys, credentials and database files.

Use fresh output directories and basetemps when reproducing: drivers refuse
existing targets and pytest clears its basetemp. These names identify preserved
historical runs and are not an instruction to overwrite them. Historical exact
commands and exits are in `measurements/recovery-runs.json`, the preserved
initial failed attempt, `regression-commands.json` and `static-checks.json`.
The opt-in binding manifest is `recovery-acceptance-final2-bindings.json`.

```powershell
$scalePython = 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe'
$scaleWork = 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work'
$recovery = "$scaleWork\graph-index-recovery-20261027"
$env:APP_ENV = 'demo'
$env:SCALE001_PROTOTYPE_ROOT = $recovery
$env:SCALE001_INDEX_TEST_MODE = 'validated_partial'
$env:PYTHONPATH = "C:\Users\sai krishna\Projects\ProjectTrace-local;$scaleWork"

& $scalePython "$recovery\run_compatibility.py"
& $scalePython "$recovery\check_statistics.py"
& $scalePython "$recovery\run_probes.py"
# The first driver stopped on the preserved option-cloning setup failure.
# After its correction, resume_probes preserved completed children and used
# a new retry directory for the failed child.
& $scalePython "$recovery\resume_probes.py"
& $scalePython "$recovery\compare_outputs.py"
& $scalePython "$recovery\final_checks.py"
& $scalePython "$recovery\package_recovery_evidence.py"
```

`final_checks.py` records the following final command verbatim (the resulting
exit 1 remains a failure):

```powershell
& $scalePython -m pytest -q "$scaleWork\graph-index-prototype-20261027\test_candidate_contract.py" tests/test_graph_index_recovery.py tests/test_graph_pages.py tests/test_indexed_workspace_queries.py tests/test_workspace_pagination.py tests/test_graph_impact.py tests/test_generations.py::test_visibility_scope_switches_in_one_session_and_rechecks_publication tests/test_generations.py::test_public_api_readers_never_return_unpublished_snapshot_or_source tests/test_generations.py::test_final_promotion_rejects_cancellation_replacement_and_access_revocation tests/test_generations.py::test_final_commit_failure_or_lost_acknowledgement_is_consistent -p tests.graph_index_recovery_plugin -p tests.graph_index_pytest_plugin -p short_test_ids -o junit_family=xunit1 --basetemp="$recovery\p94" --junitxml="$recovery\recovery-acceptance-final2.xml"
```

Static commands use `python -m ruff check backend analyzers tests scripts` plus
all seven new disposable driver files, changed-file `ruff format --check`,
`compileall -q backend analyzers tests scripts` plus those driver files, and
`git diff --check`. Every exact argv and exit 0 is in `static-checks.json`.
No final acceptance failure was converted to xfail, skip, changed expectation,
partial-result success, or a claimed GitHub CI result.

**SCALE-001 — NOT QUALIFIED.**


# 2026-10-27 — Full-membership scalar-key experiment (disposable only)

**Candidate decision: REJECTED. SCALE-001 — NOT QUALIFIED.**

Branch `codex/scale-001-local-continuation` and HEAD `9e21509591bfa5457cc829ebd5637f95be68d573` are unchanged.
This task added opt-in test/profiling code and evidence only. No production
module, migration, original database, historical expected result, existing
uncommitted checkpoint/map/export implementation, index on an original database,
generation or pointer was changed. There was no commit, push, PR action,
workflow dispatch, Linux qualification or resource-budget increase.

## Ordering contract and measured defects

`docs/SCALE001_GRAPH_ORDERING_CONTRACT.md` records eight original query shapes,
exact SQL/binds/rows/plans, BINARY/NULL/affinity behavior and source references.
The raw evidence includes `ordering-evidence.json`. `snapshot_record_query`
(`backend/domain.py:204`) has no ORDER BY. Its frozen unfiltered and
version-filtered 179-row results traverse the original graph-target index;
the ID-IN variant instead uses `uq_records_checkpoint_scope`. Its hidden rowid
tie-breaker is not the VARCHAR Record.id. A generic target/ID ORDER BY would
change existing results or bounded page membership and was not introduced.
Graph pages use explicit ID tie-breaking, while linked neighborhood nodes and
some impact hydration/seeds expose incidental order. Workspace ranking retains
one shared ranked subquery and its existing ordering/loader criteria.

The new full-membership table retains original key values, but changes the FROM
graph. The mixed query starts on `ix_records_scoped_current` and probes the
projection by INTEGER PRIMARY KEY instead of traversing original graph_target.
That changes 52 positions of the frozen mixed sequence. The extra-version
filtered case still fails. Exact row-set equality does not repair this failure.
The other two prior ID-IN/path filtered tests pass in this owned fixture.
Read-only keys-first JOIN/CROSS JOIN controls chose graph_class and also failed
the required order; no loop-order hint was installed in the candidate.

A further native write defect is retained as a failing regression: a
natural_key-only UPDATE changes the authoritative row while leaving the
projection's natural_key stale. `install` watches data/kind/id/tenant/rowid but
omits natural_key, which its indexed REPLACE cleanup depends on. The old
229-case corpus does not cover that mutation. Passing that corpus therefore
does not prove every supported write maintains the derived table.

`ScalarCompiler._group` also hides qualified `records.rowid` behind a joined
table-group alias. The original SELECT succeeds; the adapted SELECT fails with
`no such column: records.rowid`. Physical UPDATEs of rowid/_rowid_/oid reanchor
correctly, which does not fix the read namespace defect.
Qualified wildcard reads (`records.*`) and schema-translation/attached-schema
behavior are NOT_RUN. Physical eight-column INSERT/SELECT-star write tests do
not prove wildcard compatibility through a joined alias. The prototype compiler
hardcodes unqualified table names; it must not be advertised as a general
SQLAlchemy replacement across those untested schema paths.

The fixed scope expression now maps to the projection table. Consequently the
original small claim/finding summary expression indexes on records no longer
match the scoped aggregate. The unchanged covering-index regression test fails
and the plan uses a temporary GROUP BY. Selective graph endpoint seeks are
retained in the tested nested neighborhood queries; preserving those seeks is
not proof that all other access paths remain equivalent.

## Alternative controls and selected disposable schema

`alternative-indexed-comparison.json` compares physical extra metadata,
VIRTUAL/STORED generated metadata and a projection. Generated columns break the
supported `INSERT INTO records SELECT * FROM records` arity and change combined
NOT-NULL/malformed-JSON error priority. An ordinary extra column breaks actual
eight-value positional INSERTs used by existing migration/scope tests.
ALTER ADD STORED fails on populated SQLite tables. The STORED control rebuilt
only a minimal table: its database size is not comparable to the four full
clones. The first control script had a case-sensitive index-substitution bug;
its original receipt remains preserved and `alternative-pilot-correction.json`
distinguishes the corrected indexed controls. No erroneous pilot number is used
as the final memory baseline. An unconditional physical-column AFTER UPDATE
records two total_changes versus one baseline, but did not double measured WAL
bytes; write amplification is not inferred from change count alone.

A correlated projection lookup preserved its tested row set but lost selective
endpoint seeks. The main candidate therefore uses an explicit flat joined
table group, emitted by an owned-engine SQLite compiler without AST cloning,
session interception or model metadata changes. Named/runtime JSON paths stay
unchanged; only existing literal-path, string-valued IndexedText expressions
map to the five keys. Alias objects, security options, window/rank subqueries,
UNIONs and pagination AST identity remain intact. All five previous workspace
ambiguous-column failures now pass, but that does not excuse the new failures.

`scale001_graph_scalar_keys` has rid INTEGER PRIMARY KEY (the original hidden
rowid), unique authoritative id, organization/repository/kind/natural_key, and
complete nullable VARCHAR key_scope/key_snapshot/key_source/key_target/key_class.
Its id FK targets globally unique records.id with deferred ON DELETE CASCADE;
canonical native guards verify the exact tenant/repository/id/rid/key mapping.
The original eight records columns and original record FKs are unchanged.
The four full-membership graph indexes move to this table with the same leading
metadata, CAST affinity, BINARY ordering and complete keys. The metadata natural
key index supports bounded orphan cleanup for native REPLACE behavior.

Eight native triggers implement two JSON validations, three authoritative
insert/update/delete maintenance hooks, and three projection write guards.
Validation preserves the tested original JSON1 error precedence when required
NOT-NULL fields are absent. Multi-path native extraction plus a MATERIALIZED
one-row pack avoids four full-document index evaluations. It does not eliminate
all full-document parsing: validation and canonical write guards still parse.
Unchanged derived keys skip projection writes. Explicit delete maintenance and
indexed REPLACE cleanup handle NULL repositories, FK OFF and recursive-trigger
OFF cases. No privileged bypass flag or application-supplied projection data is
trusted. Savepoint admission rolls back on failures; SQLITE_INTERRUPT's automatic
transaction rollback is respected without masking the original cancellation.

Backfill passes only batches of 128 rowids to Python, then processes one record
per native statement. It does not build a Python all-record key dictionary or
copy non-key snapshot JSON into the side table. Memory processes one record at
a time, with the unchanged SQLite cache and a constant number of native
source/parse/pack buffers plus complete key bytes. The MATERIALIZED pack is
parsed once per invocation, not once per authoritative write: changed keys also
invoke validation and canonical-guard extraction; unchanged keys skip the
derived write/guard. It is **not** a fixed tiny bound independent of the largest
legal record/key. Native high-water measurements take precedence over an
assumed one-buffer estimate.
Object/array and very large string graph fields retain complete original CAST
values. Disk cost is O(rows' metadata plus complete indexed key bytes).
The 200k-key/500k-non-key fixture verifies no truncation. No cache, node, RAM,
checkpoint, sanitizer, spill or time limit was raised.

The separate 93-case native packed-cache value/error differential has zero
differences, including a 4096/4097-byte fallback boundary and JSON5/JSONB cases.
It is only an extraction control, not a proven production cache architecture,
universal malformed-JSONB proof or trigger/error-priority qualification.

## Actual tests and immutable-gate conflict

Final current-worktree candidate run: **99 discovered,
91 passed, 8 failed, 0 errors,
0 skipped**, exit 1. `scalar-final.xml` and
`validation-commands.json` contain exact provenance. This is local Windows
pytest, not GitHub CI on the published commit.

| Suite | Tests | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|---:|
| `tests\test_graph_scalar_reading.py` | 12 | 10 | 2 | 0 | 0 |
| `tests\test_graph_scalar_projection.py` | 38 | 37 | 1 | 0 | 0 |
| `tests\test_graph_pages.py` | 2 | 2 | 0 | 0 | 0 |
| `tests\test_indexed_workspace_queries.py` | 4 | 3 | 1 | 0 | 0 |
| `tests\test_workspace_pagination.py` | 6 | 6 | 0 | 0 | 0 |
| `tests\test_graph_impact.py` | 8 | 8 | 0 | 0 | 0 |
| `tests\test_generations.py` | 7 | 7 | 0 | 0 | 0 |
| `FROZEN_22_UNCHANGED_ASSERTIONS_SCALAR_SUBJECT` | 22 | 18 | 4 | 0 | 0 |

The original frozen 22 assertions are unedited. Three historical mode labels
refer to three independent copies of ONE scalar design, not three independent
architectures. Nine static guard-proof utility tests still exercise the old
unchanged utility, which this reader does not use. The original legacy assertion
requires exactly two snapshot-validation triggers, then partial-index
`WHERE kind != 'snapshot'` SQL. This contradicts eight necessary guards/full
membership. The actual failure stops at eight-versus-two; the later partial-index
assertion is a separate static conflict, not an executed additional failure.
Neither was faked or weakened. Full upgrade beyond that stop is NOT_RUN.
The other frozen failures are actual mixed-sequence mismatches, so the gate
conflict is not the sole reason for rejecting this candidate.

Current frozen corpus: baseline 62 queries and
229 write cases; candidate
62 queries and
229 write cases.
Candidate query differences: `['existing_mixed_implicit_order']`.
Candidate write differences: `[]`.
Before/after ANALYZE plans, statistics and reverse_unordered_selects controls
remain in the raw receipt; original frozen sequences were not sorted to pass.
After ANALYZE the candidate additionally changes the core implicit-order query:
`['existing_core_implicit_order', 'existing_mixed_implicit_order']`;
the original baseline has
`[]` differences.
This is a further measured planner-stability failure, not an unverified risk.

The original 37 new native write/security cases pass, covering exact 229 write/error
outcomes, tenant/key tampering, savepoint rollback, authorization denial,
interrupted backfill, NULL repository deletion/reinsert, identity/rowid changes,
REPLACE collisions across FK/recursive modes, eight-column SQL and large values.
An additional natural-key-only test fails and is preserved without changing the
candidate's measured implementation or expected coverage invariants.
Seven focused generation visibility/access-revocation/cancellation/final-commit/
lost-ack tests pass. Read tests cover aliases, shared rank identity, self/outer
joins, opaque security options and runtime paths, while retaining the failed
version and rowid assertions.

Earlier receipts remain preserved: the first 54-case run accidentally left its
20 wider existing tests in BASELINE mode. It must not be counted as candidate
regression evidence. Intermediate native failures exposed REPLACE orphan cleanup
and cancellation masking; those were fixed only in new disposable code. Two
new-test schema metadata/arity expectations and one invalid new JSON-path bind
were corrected as harness defects. No historical assertion or output changed.

## Three fresh-process measurements per mode

Original production-equivalent baseline means current preserved application
code with its original four full JSON expression indexes, not the rejected
partial/CASE prototype. These are owned Windows synthetic observation-volume
measurements on the existing 19-file fixture, not the pinned repository,
Linux/cgroup/parser-isolation qualification or production-readiness evidence.
MB uses 1,000,000 bytes. Native SQLite high-water and process RSS overlap; do not
add them. RSS high-water can include earlier setup allocations. Native UPDATE
counters reset at the actual statement boundary.
They are SQLite's process-global managed-allocation counters across active
connections during that window, not a separate per-database allocator.

| Measurement | Original baseline | Scalar candidate |
|---|---:|---:|
| Cold complete analysis, median seconds | 231.693675 | 334.602746 |
| Whole-process peak RSS, maximum MB | 524.480512 | 444.215296 |
| Snapshot UPDATE native SQLite peak, maximum MB | 350.661728 | 272.699832 |
| Snapshot UPDATE, median seconds | 0.461988 | 0.823101 |
| Final-snapshot path, median seconds | 34.506148 | 32.851358 |
| Same-value UPDATE, median seconds | 0.211390 | 0.081756 |
| Same-value UPDATE native peak, maximum MB | 347.138552 | 170.643360 |
| Mixed complete-row query, median seconds | 0.069811 | 0.064855 |
| Mixed process peak RSS, maximum MB | 206.057472 | 211.337216 |
| Mixed native SQLite peak, maximum MB | 88.310064 | 91.852264 |

All cold seconds, baseline: `[47.76241830000072, 231.6936745999992, 366.5187695000004]`;
candidate: `[224.53716539999914, 346.80331619999924, 334.6027460000005]`. These include substantial
inter-run/host variation; medians and all raw observations are retained rather
than selecting a favorable first result. Native execute timing excludes later
fetch/ORM/Python work. The initial pair's extra end-to-end time was mostly
outside the native execution intervals; it is not proven to be trigger time.
Further CPU/stack attribution would be needed before tuning that overhead.

Same-value UPDATE total_changes arrays: baseline
`[1, 1, 1]`, candidate `[1, 1, 1]`.
Per-process Windows read/write operations/bytes include an additional
update-plus-COMMIT window: zero writes before commit do not mean zero durable
writes. Actual publication UPDATE and atomic-COMMIT I/O are separately captured.
Database page/freelist/file sizes are in the summary/raw receipts; dbstat is
unavailable in this linked SQLite build, so exact per-index byte attribution is
NOT_RUN. No VACUUM was used to produce favorable sizes or renumber rowids.
Cold database file bytes, baseline:
`[64987136, 64974848, 64974848]`;
candidate: `[65572864, 65568768, 65568768]`.
Query plans and seven-sample latency distributions include filtered/page and
nested neighborhood lookup cases. Those small-fixture timings are not full-scale
query-latency qualification.

HTTP comparison requests per mode: `{'baseline': 20, 'validated_partial': 20}`;
complete body/status/content-type differences: `['neighbors-0', 'neighbors-1']`.
Both failing 200-status neighborhood responses have identical ordered edges
and complete node contents, but different node-array order. Baseline linked
nodes follow the old incidental path; the projection join returns ID order.
They remain HTTP compatibility failures. The probe collector's exit 0 denotes
successful evidence collection, not a passing response-equality assertion.
This scope includes graph pages/neighborhood, private unpublished rows,
authentication and cross-tenant denials, not every application route.
Four unmodified complete-output comparator results:
`[True, True, True, True]`
(three 30k cold pairs and one 147-metric cold/warm/incremental pair).
Comparator normalization is unchanged and explicit: known generated IDs,
administrative timestamps/durations and documented unordered identity sets;
claims, metrics, symbols/artifacts, quality, findings and graph content remain
included. This semantic fingerprint check does not override raw query-order
failures. Owned job PARTIAL status is preserved, not rewritten to COMPLETE.
Publication generation/pointer checks and exact native side-table coverage are
recorded separately for all eight fresh publication databases.

## Preservation, gates and next smallest task

VERIFIED in this limited owned environment: 275
preexisting Python source hashes, original tracked diff, all four original
database bytes, historical frozen assertions/evidence and original report prefix
remain identical. Original database SQLite/FK, audit-chain and graph-ownership
checks pass, including the earlier three PUBLISHED generations and two pointers.
Publication SQLite/FK/audit/edge checks and complete projection-key/owner equality
pass. No production encryption/HMAC implementation or safety guard changed.
Ruff, formatting, compileall and git diff checks are recorded with actual exits
in `validation-commands.json`; failing acceptance tests remain failures.
`post-validation-static-final.json` records the final repeated lint/format/compilation
and diff checks after the evidence-helper additions, without repeating tests.

FAILED: frozen mixed sequence compatibility, extra-version mixed order,
qualified hidden-rowid read namespace, existing summary covering-index gate,
natural-key-only projection maintenance, and the unchanged partial-specific
legacy implementation gate; two complete HTTP neighborhood response comparisons
also fail. No production
migration proposal is safe under these results.

NOT_RUN: universal JSONB/error behavior, arbitrary production planner/statistics/
SQLite-version/VACUUM stability, full legacy-to-head migration and downgrade,
production migration/reversal, and the pinned 21,636-file Linux 768,000,000-byte
process-tree cgroup/zero-swap workload. Full cold/warm/incremental deterministic
output, cancellation, memory/disk exhaustion, worker termination/recovery,
duplicate delivery, tenant/security and atomic-publication release gates remain
unqualified. Existing 50k sanitizer structure failure, whole-snapshot
materialization and downgrade/expiry concerns stay separate and unresolved.

**Exact next smallest task:** retain this rejection and capture a paired,
owned 147-metric CPU/compilation/fetch profile to attribute the measured overhead
outside native SQL. Before another schema prototype, review the frozen mixed
ordering contract alongside existing positional-SQL and legacy gate constraints.
A different direction should preserve original read SQL/physical traversal and
seek bounded write-side JSON evaluation reuse, rather than moving all reads
through a joined projection or returning to global AST rewriting. Its feasibility
is unproven; it requires its own value/error/sequence proof. No new stable ordering
policy or relaxed legacy test is authorized by this report. Production migration
and full Linux qualification require separate authorization and are not the next
automatic action for this rejected candidate.

## Evidence and reproducible commands

Summary: `docs/evidence/SCALE001_GRAPH_SCALAR_PROTOTYPE.json`.
Complete raw archive: `docs\evidence\SCALE001_GRAPH_SCALAR_PROTOTYPE_RAW.json.gz`,
533434 bytes, SHA-256
`59829dae010ff09113a1fa7a772045e85564258e7050ebf9d97a0feb190f347f`. It includes SQL, exact rows, error cases,
plans, all test failures, original failed attempts, command/stdout/stderr receipts,
source hashes and new reproduction-driver sources; it excludes keys/database
files. Root: `C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\graph-scalar-prototype-20261027`.
The first packaging attempt failed by treating its own empty redirected stdout
JSON file as an input receipt. No archive was admitted. That empty collector
file was preserved with a .log extension, the failed attempt was recorded, and
packaging was retried without redirecting JSON into its own input directory.
A second pre-admission packaging failure exposed Windows cp1252 decoding of a
UTF-8 reproduction source. The collector now reads source/contract JSON text
with explicit UTF-8; its failed attempt remains recorded. This did not rerun or
alter a workload or change any candidate result.

Run from the repository with the existing Python environment and fresh output
directories/basetemps. Never reuse historical pytest basetemps or overwrite a
recorded DB. Exact argv/env/exits are in the archive's validation and measurement
receipts. The drivers refuse existing output roots.

```powershell
$scalePython = 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe'
$scaleRoot = 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\graph-scalar-prototype-20261027'
$env:APP_ENV = 'demo'
$env:SCALE001_PROTOTYPE_ROOT = $scaleRoot
$env:SCALE001_INDEX_TEST_MODE = 'validated_partial'
$env:PYTHONPATH = 'C:\Users\sai krishna\Projects\ProjectTrace-local;' + (Split-Path $scaleRoot)
& $scalePython "$scaleRoot\run_measurements.py"
# Initial pre-DDL ownership refusal is preserved; corrected callback uses NEW paths.
& $scalePython "$scaleRoot\resume_measurements.py"
& $scalePython "$scaleRoot\finish_validation.py"
& $scalePython "$scaleRoot\package_evidence.py"
& $scalePython "$scaleRoot\append_report.py"
```

New repository code only: `tests/graph_scalar_prototype.py`,
`tests/graph_scalar_plugin.py`, `tests/graph_scalar_probe.py`,
`tests/test_graph_scalar_reading.py`, `tests/test_graph_scalar_projection.py`.
New documentation/evidence: this append, the ordering contract and the two
GRAPH_SCALAR_PROTOTYPE receipts. Prototype files are opt-in and application
modules never import them.

**SCALE-001 — NOT QUALIFIED.**


## Commercial V1 local continuation — 2026-10-29

This appendix records the local Windows development continuation on branch
`codex/scale-001-local-continuation`, unchanged HEAD
`9e21509591bfa5457cc829ebd5637f95be68d573`. It is not a Linux/cgroup result,
release approval, or certification of the dirty tree by historical CI.

### Expiry ownership and recovery correction

The local reaper could delete expiring encrypted analysis inputs, checkpoints,
or publication drafts while a live worker still owned the job lease. A related
expired input could leave a stale renewable queue token. `backend/retention.py`
adds transaction-local ownership checks coordinated with scheduling locks.
Checkpoint, draft, generation-chunk, and queue cleanup select bounded metadata,
recheck the lease under lock, and fence reclaimed work. Existing expiry/read
deadlines and cleanup page sizes are unchanged. Published receipts, snapshots,
history, encryption/HMAC formats, and schema 0026 were preserved.

Local test receipts: `retention-final.xml` (29 passed),
`retention-expanded.xml` (54 passed, one optional PostgreSQL test skipped),
`checkpoint-regressions.xml` (60 passed), and
`generation-regressions.xml` (34 passed). The skip means actual PostgreSQL row
lock behavior is not verified. Docker's local Linux daemon was unavailable and
no disposable PostgreSQL service was configured. A populated v2 database still
refuses downgrade; historical rows or markers were not rewritten.

### Local Commercial V1 workflow coverage

The final cold/warm/incremental owned workload completed three snapshots with
integrity check `ok`, zero foreign-key violations, three published generations,
and two pointers. Its output comparator returned `equal: true` against the
existing full cold/warm/incremental owned comparison. Separate cold output
comparisons against the profiled and quiet-profile runs also returned
`equal: true`. These results cover 147 owned metrics and fixture-scale output;
the jobs are PARTIAL under the existing repository coverage semantics and do
not establish pinned-repository completion.

The existing analyzer/security/graph result groups were respectively 95 tests
in `commercial-rules.xml`, 87 in `maps-and-exports.xml`, and 29 in
`security-and-graph.xml`. Frontend unit tests passed 49/49; production build
passed with 42 prerendered public routes. An owned browser run passed the
authentication drift and real ZIP-import flows. A new storage configuration
drift fixture adds a second narrow end-to-end path: a declared production
public ACL changes a documented “storage is private” claim from UNVERIFIED to
CONTRADICTED. The claim retains `DECLARED_CONFIGURATION` scope and explicitly
states that deployed runtime is unobserved. Its API regression command passed
7/7 selected tests; the owned browser test passed 1/1. Private, missing,
development-only, and commented declarations stay UNVERIFIED. No generic
configuration verifier or parser privilege was added.

Final Ruff check passed for `backend analyzers integrations workers tests
scripts integration_tests`; Python `compileall` passed for the same directories.
All commands were local. No commit, push, PR edit, remote workflow, merge,
deployment, or full Linux qualification occurred.

### Preserved blocker and next gate

The 50,000-metric snapshot reproduction still fails the original
1,000,000-node sanitizer guard. No guard or memory/time/checkpoint quota was
raised. Original graph indexes remain in place; disposable scalar/index
prototypes remain rejected. The original four owned databases were read-only
audited after this work: bytes match their captured SHA-256 values, SQLite
integrity is `ok`, foreign-key violations are zero, and published generation/
pointer counts are unchanged. The baseline audit checked 632 pre-existing
nonignored files; only four intentional post-baseline cleanup-function edits
were found among those existing paths.

ADR 0007's authenticated permanent snapshot-segment proposal remains
**PROPOSED** because the user requested proposal review first. No segmented
snapshot format, schema, reader, or admission policy was implemented. The next
engineering gate is review and explicit resolution of the proposed snapshot
contract, followed by an independently authorized implementation/validation
plan. PostgreSQL/Redis/Celery recovery and the full 768,000,000-byte, zero-swap
Linux pinned workload remain unverified. **SCALE-001 — NOT QUALIFIED.**

Detailed local status is in `PROJECTTRACE_PROGRESS.md` and
`docs/COMMERCIAL_V1_RELEASE_GATES.md`. Raw local receipts are packaged under
`docs/evidence/PROJECTTRACE_COMMERCIAL_V1_LOCAL_2026_10_29_RAW.tar.gz`; the
summary and package hashes are in the adjacent JSON receipt.


Preservation audit clarification: the final baseline comparison also sees this report's appended continuation sections as one intentional documentation change. The original prefix was byte-verified unchanged; the other four changed pre-existing source paths are limited to the lease-aware expiry cleanup functions.


ADR 0007 review follow-up: the proposal has now been reviewed. It is still PROPOSED and not approved: page-local node validation would admit logical snapshots above the current global 1,000,000-node limit, and validation/BASE-HEAD readers still materialize full arrays. Resolve that policy conflict and specify durable ownership, transaction recovery, and bounded readers before implementation. The detailed review is appended to `docs/adr/0007-bounded-published-snapshot-segments.md`.
