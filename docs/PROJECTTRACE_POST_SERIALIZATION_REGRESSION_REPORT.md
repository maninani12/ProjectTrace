# ProjectTrace post-serialization regression report

Date: 2026-10-29\
Scope: audit and local regression testing of deterministic set JSON serialization.\
Result: **serialization-focused checks pass; broad regression closure is not green.**

## Fix reviewed

`Generation.encoded` previously turned a set into a JSON list with `list(value)`, exposing hash-dependent iteration order. The production change adds `_set_item_key`, which uses Python's standard JSON encoder with the existing `encoded` callback, ASCII escaping, compact separators, and sorted object keys to define a stable ordering key. It sorts only the members of sets and emits the existing `{"$set": [...]}` shape.

The fix leaves tuple encoding, dictionaries and their insertion order, ordered lists, set membership, and sanitizer behavior unchanged. It does not sort graph traversals or other collections. Canonical keys are not emitted as values; they only order the existing set members. A tuple inside a set remains a native JSON array, matching the serializer's prior behavior. The new test covers string and mixed scalar/tuple members and checks the exact JSON text. An unsupported object inside a set still raises the established `TypeError`.

Legacy generation receipts still decode serialized set lists into Python sets; existing legacy replay and generation/context tests passed. The v2 context writer continues to store set rows using its existing unordered collection path; this task did not change that storage layout or claim cross-run equality of encrypted page digests. No signature, generation identity, schema, snapshot format, or sanitizer policy code was changed. Existing snapshot/replay tests passed. The full suite reports no failures in `tests.test_json_export`.

## Preservation and environment

- Branch: `codex/scale-001-local-continuation`
- HEAD: `9e21509591bfa5457cc829ebd5637f95be68d573`
- Python 3.14.3, pytest 9.1.1, Ruff 0.16.10; Windows local environment.
- Tests used the documented venv and scratch SQLite databases, source/blob directories, pytest roots, and encryption keys. The graph opt-in source database was copied into a new disposable root; its SHA-256 matched the source copy. Candidate DB writes and ownership markers stayed under that root.
- The four preserved databases still match their recorded baseline hashes: 10k `465441f1dfd2c7d6ca3d7427c79dd55e57c350bee451b60a66b8e0e92f5a1d1b`; 147 `97aeda34f1cb1b1d67784926c2140c3c27063585ae135fbb39e22643edce94d6`; 30k `c7313fd66baa9e23ec5f5a7e9bdb8003554d086796c101be14f8d02d6ee5e9a4`; prior `14a15885488462c687ce2581807ea56ecb2145b98bc58d67f6e2aad3ba9a5627`.
- Existing aggregate-guard, policy-readiness, ADR, release-gate, and prior determinism evidence hashes are recorded and verified in the companion JSON. No dependency manifest, cap, admission behavior, schema, migration, or release gate changed.

## Serialization and focused test results

The selection was `tests/test_json_export.py -k 'typed_context_export_replay_mutations_and_snapshot_integrity or generation_set_encoding_is_deterministic or unsupported_types_and_keys_still_rejected'`.

| Environment | Result |
|---|---:|
| Default randomized hash seed | 4 passed |
| `PYTHONHASHSEED` 0, 1, 2, 3, 7, 17, 42 | 4 passed for each seed |

The exact-output assertion passed in every process, so the tested set JSON was byte-for-byte identical across the listed seeds. Both original replay cases passed and retained their semantic equality checks. The new unsupported-set-member assertion confirmed serialization still raises `TypeError`.

The original historical full export/sanitizer result remains **116 passed, 2 failed**. The failures were the two typed-context replay variants whose `$set` arrays serialized as `[`b`, `a`]` before save and `[`a`, `b`]` after replay. That history is preserved in the earlier readiness evidence; it has not been rewritten. The current broad backend run passed all **69** `tests.test_json_export` cases. Sanitizer aggregate-boundary tests also passed; the 1,000,000-node limit is unchanged.

## Broad local regression inventory

The repository's documented `python -m pytest -q` test path is `tests/`. Collection found 1,087 cases. The run deselected only `tests/test_snapshot_materialization_profile.py::test_owned_final_snapshot_profile[50000]`, the previously recorded full 50k final-snapshot rejection workload. All other selected tests ran.

| Gate | Outcome |
|---|---:|
| Broad backend pytest run | 1,055 passed; 9 failed; 21 skipped; 2 errors; 1 deselected; 51:51.81 |
| JSON export module | 69 passed; 0 failed/errors/skipped |
| Non-50k final snapshot profile cases | 3 passed |
| Opt-in graph recovery/scalar modules, corrected isolated root | 64 passed; 6 failed; 0 skipped; 2:42.22 |
| Frontend Vitest | 12 files, 49 passed; 146.65 s |
| Ruff | passed |
| Python compilation | passed |
| `git diff --check` | passed |
| Companion JSON parsing | passed with Python's standard JSON parser |

The exact inventory for all 99 backend test modules, including per-module pass/fail/error/skip counts, is in `docs/evidence/PROJECTTRACE_POST_SERIALIZATION_REGRESSION.json`.

### Failure and error triage

Three failures in the first broad run came from an incomplete opt-in scratch layout: the graph recovery tests expected a sibling `graph-index-prototype-20261027/compatibility-4.json`. I added that fixture under scratch only and reran all 70 opt-in graph recovery/scalar tests. Those three setup failures then passed.

The corrected opt-in run's remaining six failures match existing rejected-candidate evidence in `SCALE001_GRAPH_INDEX_RECOVERY.json` and `SCALE001_GRAPH_SCALAR_PROTOTYPE.json`:

- `test_extra_version_filter_preserves_complete_baseline_sequence` for partial, validated-partial, and guarded experimental graph indexes;
- `test_natural_key_only_update_preserves_projection_metadata` for the experimental scalar projection;
- `test_filtered_mixed_sequences_match_complete_baseline[version]` and `test_rowid_read_namespace_is_preserved` for experimental scalar graph reads.

These failures concern the previously rejected graph-index/scalar candidates, not `Generation.encoded`. They remain failures and are not counted as passes in this report. The broad run's six candidate failures correspond to these same assertions.

The broad run reports two errors from one `test_parser_sandbox::test_helper_protocol_rejects_excessive_structure` case: setup and teardown both failed because Windows rejected an environment variable longer than 32,767 characters. This is a host process-environment limit, not a serialization failure.

The separate `integration_tests` invocation produced 58 setup errors because its autouse fixture asserts `sys.platform == "linux"` on every test. Four broker tests skipped because no disposable Redis/PostgreSQL CI services were configured. I did not bypass the platform guard. The backend run's 21 skips comprise 16 PostgreSQL tests requiring `PROJECTTRACE_TEST_POSTGRES_URL` and five Linux-only transport/lifecycle tests.

## SCALE-001 and remaining gates

No 50k final-snapshot rejection workload was rerun. The existing evidence remains: cap 1,000,000 nodes; 50k fixture 1,115,947 nodes; rejected before final SQL persistence, `Generation.validate`, or BASE/HEAD comparison. The supported-input proposal remains `PENDING_PRODUCT_OWNER_APPROVAL`; this task found no new approval record.

The broad backend suite is not green, so this is not full regression closure. PostgreSQL, Linux parser/isolation, broker recovery, and browser end-to-end tests were not established on this Windows environment. The six historical graph candidate failures remain unresolved and unrelated to the serialization change.

**SCALE-001 remains NOT QUALIFIED. Commercial V1 remains DEVELOPMENT IN PROGRESS.**

## 2026-10-29 authoritative worktree reconciliation

The checkout is now directly available at `C:\Users\sai krishna\Projects\ProjectTrace-local` on `codex/scale-001-local-continuation`, HEAD `9e21509591bfa5457cc829ebd5637f95be68d573`, with `origin` set to `https://github.com/maninani12/ProjectTrace.git`. It is intentionally dirty. The earlier note above saying the active workspace could not expose this checkout describes the staging step and is superseded by this verification; no reset, clean, branch switch, commit, push, PR change, or workflow dispatch occurred.

The staged report and JSON still match their recorded SHA-256 values (`cf21a2…e993` and `dd2c79…61e2`). The repo report already existed with SHA-256 `82f02b…d897`, so this section was appended without replacing its earlier history. The companion evidence JSON did not exist in the repo; it was created from the staged JSON and extended with this reconciliation. The staged originals remain unchanged. The prior source and policy artifact hashes match; the ADR, release-gate, and policy-readiness files are present under their current names and retain the staged hashes.

The four original SQLite fixtures were rechecked read-only after testing. Their SHA-256 values still match the captured baselines: 10k `465441f1dfd2c7d6ca3d7427c79dd55e57c350bee451b60a66b8e0e92f5a1d1b`, 147 `97aeda34f1cb1b1d67784926c2140c3c27063585ae135fbb39e22643edce94d6`, 30k `c7313fd66baa9e23ec5f5a7e9bdb8003554d086796c101be14f8d02d6ee5e9a4`, and prior `14a15885488462c687ce2581807ea56ecb2145b98bc58d67f6e2aad3ba9a5627`. Each reports SQLite integrity `ok` and zero foreign-key violations. Tests and their scratch databases, blobs, uploads, keys, temporary files, and pytest cache were kept outside the repository.

`backend/generations.py` and `tests/test_json_export.py` still match the hashes recorded with the deterministic set-serialization evidence. The only source edit in this reconciliation is in `tests/test_parser_sandbox.py`: the two excessive-structure parameters now have short explicit pytest IDs (`depth-overflow`, `node-budget-overflow`). The 1,000,001-delimiter input and its assertion are unchanged. This avoids Windows failing to set pytest's `PYTEST_CURRENT_TEST` variable for a 1,000,073-character automatically generated test name; it does not change parser behavior or weaken coverage.

### Reconciled local results

- Focused serialization selection: **4 passed** in each of eight fresh processes (default and `PYTHONHASHSEED` 0, 1, 2, 3, 7, 17, and 42). The exact set encoding and replay assertions remained stable.
- Excessive parser-structure test: **2 passed** after adding short IDs.
- Owned opt-in graph modules with the required disposable-root layout: **64 passed, 6 failed, 0 skipped** in 141.6 seconds.
- Corrected broad backend run: **1,059 passed, 6 failed, 21 skipped, 1 deselected, 0 errors** in 23m07s. The full JSON-export module contributed 69 passes. The deselected case was the one 50k rejection-profile case, run separately below.
- 50k final-snapshot guard regression: **1 passed** in 69.5 seconds. This test passes because the unchanged sanitizer rejects the complete snapshot; the generation remains STAGING, published pointers are zero, SQLite integrity is `ok`, and foreign-key violations are zero. It is not successful 50k publication or SCALE qualification.
- Frontend Vitest: **12 files, 49 tests passed**. Ruff, Python compilation, and `git diff --check` passed.

The first broad rerun used a pytest temp directory outside the graph prototype's explicit ownership root and correctly failed closed: 997 passed, 68 graph-test setup errors, 21 skipped, and one deselected. Those errors said `Refusing copy outside explicit disposable ownership root`. The rerun placed pytest's temp directory under the existing disposable prototype root (still outside the repository); it removed those setup errors without bypassing the guard. The three earlier missing-`compatibility-4.json` errors likewise came from incomplete scratch setup and did not recur.

### Failure and error disposition

The staged broad run's nine failures were three disposable-fixture setup failures plus the same six rejected graph-candidate assertions reproduced by the 64/6 opt-in run. The corrected current broad run has only those six failures; they are not failures in the active serializer or production graph implementation:

- `test_extra_version_filter_preserves_complete_baseline_sequence[partial]`, `[validated_partial]`, and `[guarded]` return a different mixed-kind row sequence (first shown difference at row index 49) after the experimental partial-index rewrite.
- `test_natural_key_only_update_preserves_projection_metadata` leaves a projection row `(5565,)` after a natural-key-only update, violating the frozen record/projection equivalence contract.
- `test_filtered_mixed_sequences_match_complete_baseline[version]` returns a different mixed-kind row sequence (first shown difference at row index 49) under the scalar-read candidate.
- `test_rowid_read_namespace_is_preserved` fails with `no such column: records.rowid` under that candidate.

These six failures are the same six identities in the staged broad run and corrected opt-in run; they are counted once. They remain recorded as rejected-candidate failures. No expectations or production graph paths were changed.

The staged broad run's two error events were setup and teardown of one parser test with the oversized generated ID. The test-ID correction resolves both: the current broad run has zero errors and the targeted test passes both cases. The earlier separate `integration_tests` attempt remains platform-limited: its Linux-only autouse fixture produced 58 setup errors on Windows, and four broker cases skipped without disposable Redis/PostgreSQL services. It was not treated as passing or rerun by bypassing its platform guard.

### GitHub Actions on the published base commit

These are remote results for published HEAD `9e21509591bfa5457cc829ebd5637f95be68d573`, not tests of the dirty local tree. [Regression run 40280428892](https://github.com/maninani12/ProjectTrace/actions/runs/40280428892) completed successfully; parser-isolation, broker-recovery, browser, and validate jobs all passed. [Constrained run 40280429009](https://github.com/maninani12/ProjectTrace/actions/runs/40280429009) failed in both baseline and candidate jobs. The candidate receipt records `IntakeError / GLOBAL_CHECKPOINT_BUDGET` at `VERIFYING` after 1,875.465 seconds. The stage journal records 1,173.219 seconds in `ANALYZING`, 25.078 seconds in `EXTRACTING_CLAIMS`, and 513.643 seconds in `VERIFYING`. The cgroup reached its unchanged 768,000,000-byte ceiling with zero swap and no OOM kill; coordinator/child peaks were 582,090,752 / 165,163,008 bytes. At the final sample it held 492,396,544 anonymous bytes, 226,136,064 file-cache bytes, and 49,414,144 kernel bytes. It retained 18,756 parser artifacts, 195,982 metric rows, 12,435,603 tokens, and 53,467 symbols. SQLite integrity passed, foreign-key violations were zero, and no generation or pointer was published.

The raw JUnit/log/profile receipts for the staged and reconciliation runs are bundled at [PROJECTTRACE_POST_SERIALIZATION_REGRESSION_RAW_20261029.tar.gz](evidence/PROJECTTRACE_POST_SERIALIZATION_REGRESSION_RAW_20261029.tar.gz). The companion machine-readable record is [PROJECTTRACE_POST_SERIALIZATION_REGRESSION.json](evidence/PROJECTTRACE_POST_SERIALIZATION_REGRESSION.json). Neither the 50k expected rejection nor the local Windows suite resolves the Linux cgroup failure, the six rejected graph-candidate tests, PostgreSQL/Redis qualification, or the remaining cold/warm/incremental and recovery gates.

**Regression evidence is reconciled; full regression closure is not green. SCALE-001 remains NOT QUALIFIED. Commercial V1 remains DEVELOPMENT IN PROGRESS. Option A remains PENDING_PRODUCT_OWNER_APPROVAL.**

## 2026-10-29 integrated SCALE-001 policy, graph, and qualification review

The authoritative checkout remains at C:\Users\sai krishna\Projects\ProjectTrace-local, branch codex/scale-001-local-continuation, HEAD 9e21509591bfa5457cc829ebd5637f95be68d573. The existing dirty worktree is preserved. This review made no source, schema, migration, graph-index, admission-policy, or runtime-limit change.

No explicit product-owner decision was found in the supported-input proposal, ADR 0007, policy-readiness records, progress log, release gates, or relevant receipts. Option A remains an engineering recommendation only; policy is PENDING_PRODUCT_OWNER_APPROVAL, the aggregate sanitizer cap remains 1,000,000 nodes, and admission behavior is unchanged.

The six graph failures remain confined to rejected disposable candidates and count once in the corrected broad backend run. The production graph schema/query path is unchanged. snapshot_record_query has no explicit ORDER BY; the frozen tests nevertheless retain the observed baseline sequence as a strict candidate-compatibility comparison. The scalar trigger omission of natural_key and loss of records.rowid through its candidate join alias are defects in that test-only prototype, not the current application path.

The authenticated constrained workflow evidence distinguishes two failures: the baseline container exited 137 with Docker OOMKilled=true; the candidate was not OOM-killed and instead failed GLOBAL_CHECKPOINT_BUDGET during VERIFYING. Both used an enforced 768,000,000-byte cgroup with zero swap. SQLite/FK checks passed, but the receipts do not establish lease cleanup or a successful retry. Warm, incremental, cancellation, exhaustion recovery, fresh-worker recovery, tenant-concurrency, and successful publication remain unrun.

The integrated assessment and Linux qualification plan are in docs/SCALE001_INTEGRATED_QUALIFICATION_GATE.md and docs/evidence/SCALE001_INTEGRATED_QUALIFICATION_GATE.json. SCALE-001 remains NOT QUALIFIED; Commercial V1 remains DEVELOPMENT IN PROGRESS.

## 2026-10-29 — checkpoint budget and retry follow-up

The published-base constrained run 40280429009 tested HEAD `9e21509591bfa5457cc829ebd5637f95be68d573`, whose v1 writer serializes the complete analysis envelope into one bytearray and returns `False` when the plaintext JSON would exceed the existing 64,000,000-byte limit. `jobs.save_checkpoint` converts that return into `GLOBAL_CHECKPOINT_BUDGET` before publication preparation or generation admission. The sanitized receipt records `actual=null`, `rows=null`, and `collection=null`; the full result size is therefore still unknown. No payload was logged or recovered from the discarded database.

The candidate reached the cgroup ceiling before the checkpoint save: at `CLAIM_VERIFIER` start (elapsed 1,351.417 seconds), `memory.peak` was already 768,000,000 bytes; at `FINAL_IDENTITY` start (1,546.905 seconds), it was still at that peak. `GLOBAL_CHECKPOINT` ran from 1,862.988 to 1,865.057 seconds, with OOM counters remaining zero. The checkpoint budget error and the earlier memory pressure are separate findings; the receipt does not attribute the peak to the checkpoint.

The current dirty worktree already contains the paged checkpoint candidate and migration 0026 from prior work. No production code or migration was changed in this follow-up. One recovery test was added to `tests/test_checkpoint_pages.py`: after an over-budget real job fails at VERIFYING, a new session reuses the retained inventory for a successful analysis and publication. It passed twice. A privacy-preserving scratch probe at the actual 64,000,000-byte cap admitted 32,001,600 payload bytes at 42,676,028 encrypted bytes and rejected an 80,004,000-byte synthetic payload after 64,109,740 attempted encrypted bytes; the rejected attempt left zero durable parts or manifest. This Windows/SQLite result validates the local aggregate guard only, not the pinned workload or Linux cgroup behavior.

Final current-worktree checkpoint selection: 37 passed. Related recovery/publication selection: 195 passed, 1 Linux-only skip. Full backend suite: 995 passed, 91 skipped, 1 deselected (the prohibited 50k rejection profile), 9 warnings; the graph candidate tests remained opt-in skips in this run, so their previously recorded six failures are retained separately. Ruff and compileall passed. Docker Desktop's Linux daemon is stopped and no disposable PostgreSQL or Redis URL is configured, so no local cgroup, PostgreSQL, or Redis/Celery qualification was run. See the integrated gate for exact commands, source hashes, recovery assertions, CI evidence, and remaining gates.

## 2026-10-29 - checkpoint field attribution and v1 restore comparison

- Added disposable schema-shaped v1 byte attribution. The small 825-byte envelope and representative 320,873-byte envelope reconciled exactly at result and envelope levels. Full per-field contributions, fixture provenance, and the 999,999 / 1,000,000 / 1,000,001-byte test boundary are in `docs/SCALE001_CHECKPOINT_FIELD_ATTRIBUTION.md` and its JSON companion. These are synthetic measurements, not the pinned workload.
- The v1 maximum remains 64,000,000 raw JSON bytes. The 1,000,000-byte boundary was an isolated test setting. No production limit, schema, migration, or persistence behavior changed.
- Candidate values match v1 after materialization for the measured fixture, but restore semantics differ: `files` is `ReplayRows` instead of `list`; metric projections retain aliasing instead of v1's independent JSON-decoded lists. The candidate's encrypted aggregate quota also differs from v1's raw JSON admission unit. No field is proven safe to remove.
- Focused checkpoint tests: 38 passed, 1 warning. Ruff, compileall, and `git diff --check` passed. Related regressions on unchanged sources: 233 passed, 1 Linux-only skip. PostgreSQL, Redis/Celery, Docker Linux/cgroup, and full pinned qualification were not run.
- No production source changed. All four original databases still match captured SHA-256 values and pass SQLite/FK checks. **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**

## 2026-10-29 - source-matched checkpoint measurement and owner policy gate

- Inspected completed GitHub run 40280429009 through authenticated GitHub CLI. The run tested ProjectTrace HEAD `9e21509591bfa5457cc829ebd5637f95be68d573`; its failed candidate artifact was `12633028505`. Candidate and baseline artifacts contain the same exact 21,636-entry inventory manifest, SHA-256 `081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89`, expanded size 330,420,155 bytes.
- The attempt used OpenMetadata commit `b1fab2bc21c63335dead4daaaa28194c9878e9bf`, archive SHA-256 `95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257`, 158,981,993 bytes. Its recorded historical archive hash is `027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`; the receipt explicitly says `historical_input_reproduced=false`. These hashes are not conflated.
- The downloaded artifacts contain no source ZIP, database, checkpoint ciphertext, or failed result object. The checkpoint receipt still has `actual=null`; no exact byte count or field attribution can be recovered. Analyzer/parser signatures, effective quality profile lineage, runner lock digest, Python base-image digest in the raw artifact, and final application image digest are not retained. The prior lock digest is the Windows CRLF file hash and is not treated as runner evidence. The exact input manifest can be verified, but a source-matched result measurement is NOT AVAILABLE.
- No workload reproduction was launched because the result object is absent and the local Docker Linux cgroup environment is unavailable (`docker info` exit 1; Linux engine pipe unavailable). The recorded run used memory.max 768,000,000 bytes, swap.max 0, and no candidate OOM kill; its peak preceded checkpoint serialization. The existing 64,000,000-byte checkpoint limit and 1,000,000-node sanitizer limit are unchanged.
- Added `docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH_MANIFEST_40280429009.json` with explicit `VERIFIED_MATCH`, `VERIFIED_MISMATCH`, and `NOT_AVAILABLE` identity fields and a safe one-run follow-up procedure. Added `docs/SCALE001_CHECKPOINT_POLICY_DECISION.md` and its JSON companion with CP-A (retain v1) and CP-B (investigate a versioned format only). No explicit product-owner approval was found; checkpoint policy remains **PENDING_PRODUCT_OWNER_APPROVAL**. The distinct sanitizer policy also remains pending.
- The source-match test initially failed because it used the wrong manifest field name; after correction, both source-match tests passed. The combined selection recorded 39 passed and 1 failed (the test assertion typo); all 38 existing checkpoint tests in that invocation passed. Ruff, compileall, and `git diff --check` passed. Prior related regressions remain 233 passed, 1 Linux-only skip on unchanged product source. No production change, commit, push, PR edit, or workflow dispatch occurred.
- **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.** The exact checkpoint result, source-matched byte measurement, Linux cgroup reproduction, and complete recovery/tenant/service gates remain open.

## 2026-10-29 - checkpoint source-state revalidation

Current local revalidation passed: focused checkpoint/source-attribution selection 40 passed; related generation/publication/recovery selection 195 passed, 1 Linux-only skip, 1 warning. The earlier recorded 233-pass result is retained as a distinct run because the count difference is unresolved. Ruff, compileall, diff check, JSON validation, source hashes, and four read-only original-database hash/integrity/FK checks passed. The workflow receipt still has no checkpoint result object (actual=null); no v1 byte count is inferred. No production source, limit, or database was changed.

## 2026-10-29 - canonical source-match and runtime gate

The new canonical source-match manifest records 9 verified matches, 4 verified mismatches and 9 unavailable identities. The actual failed result/checkpoint is not retained; its v1 size remains unknown. Local Docker/WSL/cgroup preflight failed, so no pinned workload was rerun. The candidate's 768,000,000-byte cgroup peak preceded checkpoint serialization and did not include an OOM kill; the baseline OOM and envelope-probe OOM cases remain distinct. Current local Python 3.14.3 differs from the run's 3.14.9, and runner lock/image/config identity is incomplete. Context7 was unavailable, with official vendor documentation fallback recorded in the field-attribution report. CP-A/CP-B and the separate sanitizer decision remain pending; limits and production code are unchanged.

Latest canonical manifest plus v1 byte-attribution validation: 4 passed, 1 warning. Ruff, compileall and git diff check passed. No production code changed; the full pinned workload remains unrun.

Final canonical source-match evidence hash assertions and byte-attribution test passed: 5 passed, 1 warning (5.71 seconds). The run did not access a failed result object or alter production behavior.


## Post-reconciliation test rerun (2026-10-29)

After the integrated hash references were corrected, the focused source-match/attribution selection passed 5 tests, 0 failed, 0 skipped, with one deprecation warning in 5.41 seconds. This is local evidence validation; the actual failed checkpoint result and exact v1 byte count remain unavailable.
