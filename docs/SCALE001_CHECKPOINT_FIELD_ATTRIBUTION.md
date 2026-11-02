# SCALE-001 checkpoint field attribution and v1 restoration review

Assessment date: 2026-10-29

Status: **SCALE-001 NOT QUALIFIED**; **Commercial V1 DEVELOPMENT IN PROGRESS**.

Decision: **No production field removal or checkpoint implementation change is justified by these measurements.**

## Scope and preservation

This disposable-data investigation measures the published v1 checkpoint byte contract and compares the already-uncommitted paged candidate. It adds test-only diagnostics and evidence. No production source, schema, migration, configured limit, candidate implementation, database, PR, branch, or remote workflow was changed.

- Checkout: `C:\Users\sai krishna\Projects\ProjectTrace-local`
- Branch / HEAD: `codex/scale-001-local-continuation` / `9e21509591bfa5457cc829ebd5637f95be68d573`
- Existing dirty work remains intact; full porcelain status is in the JSON companion.
- The four original databases were opened read-only. Their captured SHA-256 values still match; each SQLite integrity check returned `ok` and each foreign-key check returned zero violations.
- Historical source, current source and existing raw evidence hashes are in the companion JSON.

## Verified v1 contract

The historical source at HEAD (`backend/analysis_checkpoints.py`, SHA-256 `52d6bf8ac730a25103c0d9b727319d5671a505141e662f2ba6f2806578bafdaf`) defines `projecttrace-analysis-checkpoint-v1`. Its envelope contains `schema`, `job_id`, `organization_id`, `repository_id`, `signature`, and `result`. Serialization uses `json.JSONEncoder(sort_keys=True)` with default `ensure_ascii=True` and default separators (`', ', ': '`). Chunks are UTF-8 encoded and accumulated as raw bytes. If `files` exists, v1 shallow-copies the result and normalizes that field with `list(result['files'])`.

The admission check applies to the complete raw JSON envelope before encryption or durable persistence. The default maximum remains **64,000,000 raw JSON bytes**. Over-budget payloads fail without truncation. Ciphertext length is reported separately and is not the v1 admission unit. The historical loader decrypts, validates digest and envelope scope/signature, then returns the decoded `result`.

## Disposable fixture measurements

Fixtures contain only generated schema-shaped values. No repository content, file paths, raw JSON, result values, ciphertext contents, credentials, or arbitrary payload hashes were retained. The diagnostic executes the read-only v1 source from the expected HEAD in memory; it does not overwrite the dirty source. These measurements are not a reproduction of the pinned OpenMetadata failure.

### Small synthetic fixture

- Whole envelope: **825 bytes**, within the default maximum.
- `result` object: **582 bytes** = 548 member bytes + 34 brace/comma bytes.
- Envelope: 221 fixed-member bytes + 592 serialized `result` member bytes + 12 outer punctuation bytes = **825 bytes**.
- `files` normalization materialized 2 generated entries.
- Result and envelope accounting reconciled exactly.

### Representative synthetic fixture

The fixture covers all 17 top-level result fields: 800 quality metrics, 256 code-quality inventory entries, 240 claims, 160 findings, 240 signals, 100 dependencies, and 512 generated file keys. It is representative of shape only, not full workload volume or customer data.

- Whole envelope: **320,873 bytes**; **63,679,127 bytes** remain under the default cap.
- `result` object: **320,630 bytes** = 320,596 member bytes + 34 punctuation bytes.
- Envelope: 221 fixed-member bytes + 320,640 serialized `result` member bytes + 12 outer punctuation bytes = **320,873 bytes**.
- Result and envelope accounting reconciled exactly.

| Result field | Type | Entries | Small member bytes | Representative member bytes | Representative share of result |
|---|---|---:|---:|---:|---:|
| `analysis_cache` | object | 24 | 20 | 1,280 | 0.399214% |
| `analysis_coverage` | object | 2 | 81 | 81 | 0.025263% |
| `claims` | list | 240 | 12 | 10,220 | 3.187475% |
| `cloud_assets` | list | 64 | 18 | 2,502 | 0.780339% |
| `code_quality` | object | 3 | 111 | 144,509 | 45.070330% |
| `dependencies` | list | 100 | 18 | 4,406 | 1.374170% |
| `documentation_files` | number | - | 24 | 24 | 0.007485% |
| `engines` | object | 1 | 35 | 35 | 0.010916% |
| `files` | list | 512 | 45 | 10,761 | 3.356205% |
| `findings` | list | 160 | 14 | 8,822 | 2.751458% |
| `quality_metrics` | list | 800 | 21 | 126,611 | 39.488195% |
| `reused_files` | number | - | 17 | 17 | 0.005302% |
| `reused_verifications` | number | - | 25 | 25 | 0.007797% |
| `reverified_claims` | number | - | 22 | 22 | 0.006861% |
| `signals` | list | 240 | 13 | 8,303 | 2.589589% |
| `verification_cache` | object | 2 | 58 | 2,646 | 0.825250% |
| `warnings` | list | 16 | 14 | 332 | 0.103546% |

Nested `code_quality` contributions are: `metrics` 126,603 member bytes, `inventory` 17,823, and `summary` 61. Before serialization, `quality_metrics` and `code_quality.metrics` refer to the same input object. The v1 JSON writes both values, including the same 126,592-byte metrics value twice. That duplicate encoding is real for this fixture; it is not by itself proof that either field is safely removable.

### Admission boundary probe

A disposable writer was configured at **1,000,000 bytes for this test only**; the application's 64,000,000-byte default was not changed. The synthetic `warnings` member was sized around the temporary boundary. Result and envelope reconciliations passed for all three cases.

| Raw JSON envelope | Save result | Ciphertext bytes | `warnings` member bytes |
|---:|---|---:|---:|
| 999,999 | accepted | 1,333,412 | 999,219 |
| 1,000,000 | accepted at boundary | 1,333,432 | 999,220 |
| 1,000,001 | rejected before encryption/write | 0 | 999,221 |

At the boundary, `result` is 999,754 bytes (999,720 member bytes + 34 punctuation bytes). Its envelope uses 224 fixed-member bytes (the test scope identifiers are three bytes longer than in the small/representative fixture), 999,764 bytes for the serialized `result` member, and 12 outer punctuation bytes: exactly 1,000,000. In the adjacent cases, every other field contribution is identical and only `warnings` changes by one byte.

## Existing paged-candidate comparison

The same disposable logical result produced **320,876 raw v1 JSON bytes** and **427,916 v1 ciphertext bytes**. The candidate wrote 9 pages: 26,764 encrypted page bytes plus a 16,740-byte encrypted manifest, 43,504 encrypted bytes total. Its measured logical v1-sized representation was 320,876 bytes. Materialized values compare equal.

They are **not exact v1 restoration equivalents**:

- V1 restores `files` as a built-in `list`; the candidate restores it as `ReplayRows`.
- V1 restores the two metric projections as independent JSON-decoded lists; the candidate preserves a shared alias. A `quality_metrics` append does not mutate `code_quality.metrics` after v1 load, but it does in the candidate.
- These are type/identity and mutation-propagation differences even though immediate values compare equal. The candidate remains unqualified for exact v1 restoration semantics.
- The candidate aggregates encrypted page/manifest bytes. V1 admits on complete raw logical JSON bytes. These are different quota units. In the existing owned Windows profile, v1 rejected a 161,787,896-byte raw logical result while the candidate accepted it with 1,568,540 encrypted bytes across 322 pages. This is changed admission behavior, not evidence that compression can redefine the v1 cap.

The earlier owned profile is synthetic repeated text, not the pinned workload. It recorded v1 attempt peak RSS 208,044,032 bytes, candidate writer peak RSS 99,979,264 bytes, and candidate replay peak RSS 98,533,376 bytes. Candidate writing took 9.694 seconds versus 1.429 seconds for the v1 attempt. These historical measurements do not establish a full workload benefit or Linux/cgroup qualification.

## Redundancy and recovery assessment

| Rank / field | Measured impact | Reconstruction and compatibility assessment | Disposition |
|---|---:|---|---|
| `code_quality` | 144,509 bytes (45.070330%); nested metrics 126,603 bytes | Created by `analyzers/engine.py`; consumed during quality publication and snapshot persistence via `backend/domain.py` and publication units. `quality_metrics` shares the source object before serialization, but v1 restores separate lists. Analyzer/config/retry provenance is not proven reconstructible from a smaller durable source. | Do not remove. Requires versioned restore contract and downstream recovery proof. |
| `quality_metrics` | 126,611 bytes (39.488195%) | Copied into the snapshot quality projection by `persist_analysis`. Duplicate value bytes are demonstrated, but removal or aliasing changes exact v1 shape/mutation behavior. | No field removal justified; consider only a separately reviewed encoding optimization. |
| `files` | 10,761 bytes (3.356205%) | V1 explicitly normalizes to a list and publication preparation consumes paths. Rebuilding from inventory may change ordering; exact order is not guaranteed by the traced inventory query. | Keep until exact inventory/order and replay contract is proven. |
| `claims` | 10,220 bytes (3.187475%) | Used by verification and publication. Identity, order, duplicate behavior, evidence links, and restart/version behavior must remain exact. | No authoritative smaller reconstruction source proven. |
| `findings`, `signals`, `dependencies` | 8,822; 8,303; 4,406 bytes | Used in correlation, graph and publication. Reconstructing from projections risks multiplicity, identity and ordering. | Keep intact. |
| Caches and remaining fields | 2,646-byte `verification_cache`; 1,280-byte `analysis_cache`; others smaller | Used for checkpoint resume and downstream accounting. Retry/config/analyzer-version reconstruction is unproven. | Keep intact. |

No field satisfies the safe-reduction conditions of authoritative durable reconstruction, deterministic exact types/order, equivalence for all consumers and retry/config changes, and v1 restore compatibility. Synthetic byte attribution cannot identify which field caused the historical 64MB overflow.

## Validation executed

Environment: Windows, Python 3.14.3, pytest 9.1.1, Ruff 0.16.10. The full constrained workload was not repeated.

- Field-attribution diagnostic: **1 passed, 1 warning**, exit 0. `& 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe' -m pytest -q -s tests/test_checkpoint_field_attribution.py --basetemp 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\checkpoint-field-attribution-reconciled-20261029'`.
- Final focused selection: **38 passed, 1 warning, 23.25 seconds**, exit 0. `& 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe' -m pytest -q -s tests/test_analysis_checkpoints.py tests/test_checkpoint_pages.py tests/test_checkpoint_field_attribution.py --basetemp 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\checkpoint-attribution-final-verify-20261029\pytest'`.
- Related regressions from the previous run on unchanged source hashes: **233 passed, 1 skipped, 1 warning, 387.12 seconds**, exit 0. They covered generations, publication, spill, sanitizer, context/maps, migrations, recovery, repository/observation stores, timeouts, queue and worker failure. Skip: Linux unnamed-SQLite lifecycle only. Exact test file list is in the JSON companion.
- Ruff over checkpoint implementation, jobs/domain/database/migration and checkpoint tests: **passed**, exit 0.
- `python -m compileall -q backend tests`: **passed**, exit 0.
- `git diff --check`: **passed**, exit 0. JSON validity and new-document trailing whitespace checks passed after writing.
- Initial diagnostic attempt: one test failed because placeholder envelope identifiers had different serialized lengths from the persisted fixture identifiers; the test fixture was corrected and all exact boundary cases passed. Initial Ruff found import ordering and one unused import in the new test; both were corrected before final pass. These were diagnostic/test issues; no production code changed.

PostgreSQL, Redis/Celery, local Docker Linux/cgroup, fresh-worker service-backed recovery and tenant concurrency were not run: service URLs are unset and Docker's Linux engine is unavailable. Windows measurements do not qualify Linux/cgroups.

## Historical workload and release gates

The pinned constrained candidate receipt still records `actual=null` for v1 checkpoint bytes. It reached the 768,000,000-byte cgroup maximum before checkpoint save, then failed `GLOBAL_CHECKPOINT_BUDGET` in VERIFYING without an OOM kill. That earlier memory peak is not attributed to checkpoint serialization. The baseline had a separate OOM failure. Neither run published a generation or pointer. The exact full-workload field contributions remain **UNKNOWN**.

- Checkpoint raw-byte maximum: **64,000,000**, unchanged.
- Aggregate sanitizer limit: **1,000,000 nodes**, unchanged; the owned 50k fixture remains at **1,115,947 nodes** and over the cap.
- Option A remains **PENDING_PRODUCT_OWNER_APPROVAL**.
- The dirty paged candidate is not qualified for v1 type/mutation or admission equivalence.
- Cold publication, warm/incremental complete-output equality, cancellation/exhaustion, worker restart/duplicate delivery, concurrent tenant isolation, PostgreSQL, Redis/Celery, and Linux cgroup qualification remain open.
- SCALE-001 remains **NOT QUALIFIED**; Commercial V1 remains **DEVELOPMENT IN PROGRESS**.

## Exact next smallest task

Obtain a product-owner checkpoint admission/format decision and source-matched privacy-safe measurement strategy for the failed pinned result. Add a restore-contract test for v1 container types, alias/mutation behavior and full downstream retry output before considering a compatible encoding optimization. Do not remove a field or redefine the 64,000,000-byte raw admission limit based on these synthetic measurements.
## Final source-state and regression recheck (2026-10-29)

The authoritative checkout remains C:\Users\sai krishna\Projects\ProjectTrace-local, branch codex/scale-001-local-continuation, HEAD 9e21509591bfa5457cc829ebd5637f95be68d573. All recorded current dirty-source hashes match. The four captured databases were reopened with SQLite read-only/immutable URIs: all file SHA-256 values match their receipts, integrity_check returned ok, and foreign_key_check returned zero rows.

The initial revalidation command used a not-yet-created external --basetemp parent and exited 1 during setup (38 setup errors, 2 tests passed, 1 warning). No failing assertion ran. After creating only the external scratch directory, the same selection passed:

    & 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe' -m pytest -q -s tests/test_analysis_checkpoints.py tests/test_checkpoint_pages.py tests/test_checkpoint_field_attribution.py tests/test_checkpoint_source_match_manifest.py --basetemp 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\checkpoint-final-confirm-20261029\pytest'

Result: 40 passed, 0 failed, 0 skipped, 1 warning, 98.29 seconds, exit 0.

The documented generation/publication/recovery regression selection was also rerun with its exact test-file list and an external JUnit path:

    & 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe' -m pytest -q tests/test_generations.py tests/test_publication_units.py tests/test_quality_spill.py tests/test_sanitization_aggregate_guard.py tests/test_generation_context.py tests/test_generation_maps.py tests/test_migrations.py tests/test_retention_recovery.py tests/test_recovery_boundaries.py tests/test_analysis_performance.py tests/test_repository_store.py tests/test_observation_store.py tests/test_timeout_recovery.py tests/test_queue.py tests/test_worker_failure.py --basetemp 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\checkpoint-final-confirm-20261029\regressions' --junitxml 'C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\checkpoint-final-confirm-20261029\regressions\results.xml'

Result: 195 passed, 0 failed, 1 skipped, 1 warning, 829.40 seconds, exit 0. The skip is tests/test_observation_store.py::test_linux_spill_is_unlinked_and_reclaimed_on_worker_death (Linux unnamed SQLite lifecycle only). An earlier recorded run reports 233 passed and 1 skip; this rerun reports 195 for the command above. The count difference is unresolved, so these remain distinct run records and are not combined or substituted.

Ruff on checkpoint sources and focused tests, python -m compileall -q backend tests, git diff --check, and JSON parsing of the four qualification/evidence records all passed (exit 0). This recheck changed no production source, schema, migration, limit, database, or checkpoint candidate. The full pinned workload, local Linux/cgroup, PostgreSQL, and Redis/Celery were not run. The failed workflow's actual=null remains unchanged; full-workload v1 byte attribution is still unknown.

## Source-match readiness and documentation audit (2026-10-29)

The canonical source-match record is docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH.json; it retains the earlier run-specific evidence in SCALE001_CHECKPOINT_SOURCE_MATCH_MANIFEST_40280429009.json and adds current local runtime/dependency and execution-preflight results. It classifies the ProjectTrace run commit/tree, exact pinned input commit/archive used by that run, and candidate/baseline inventory identity separately from historical archive identity. The run archive SHA-256 is 95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257 (158,981,993 bytes); the earlier historical archive SHA is 027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914, and historical_input_reproduced=false. The common inventory manifest has 21,636 rows and SHA-256 081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89.

The constrained candidate failed GLOBAL_CHECKPOINT_BUDGET in VERIFYING at the existing 64,000,000-byte cap. Its exact raw JSON bytes are still null in the receipt. The retained job artifacts and logs contain no exact result object, source archive, checkpoint database, or ciphertext. Analyzer/parser versions and signatures, effective quality-profile lineage, runner lock digest, and final image digest are not available. No byte size is inferred from the synthetic fixtures. Candidate peak memory.current reached 768,000,000 bytes with zero swap and no OOM kill; the recorded peak preceded checkpoint serialization. The baseline's exit-137 OOM is a separate application run; deliberate resource-envelope probe kills are not classified as application OOM failures.

Current local preflight: Python 3.14.3; project lock pins SQLAlchemy 2.1.3, cryptography 50.0.2, pytest 9.1.1, Ruff 0.16.10 and the versions listed in the JSON evidence. The failed run receipt reports Python 3.14.9. Docker client 29.8.2 cannot contact the Docker Desktop Linux engine (exit 1); WSL lists only docker-desktop; no cgroup-v2 filesystem or PostgreSQL/Redis/Celery endpoint is available. The full workload was not run.

Context7 tools were not exposed in this session, so no Context7 library IDs could be resolved. Generic, read-only official documentation was checked instead; no ProjectTrace source or payload was sent:
- Python json, local 3.14.3; Python 3.14 JSON docs at https://docs.python.org/3.14/library/json.html, which currently render 3.14.10: JSONEncoder.iterencode yields string chunks; ensure_ascii=True and default separators apply unless overridden; sort_keys=True sorts keys. Exact patch-doc match is unavailable.
- SQLAlchemy 2.1.3; 2.1 Session docs at https://docs.sqlalchemy.org/en/21/orm/session_basics.html, current 2.1.6: transaction context commits on success/rolls back on exception, and a failed flush requires explicit rollback before Session reuse. Patch-exact documentation is unavailable; no transaction API was changed.
- cryptography Fernet 50.0.2; exact-version docs at https://cryptography.io/en/50.0.2/fernet/: Fernet authenticates and encrypts; decrypt verifies before returning plaintext, and Fernet holds the complete message in memory. Existing crypto code was not changed.

The disposable v1 diagnostic still measures a complete envelope by summing UTF-8 encoded chunks from the historical-default JSONEncoder(sort_keys=True).iterencode(...) and normalizes files with list(...). It retains no serialized payload. It cannot measure the failed workload without the missing result object. The current paged candidate remains unqualified because its ReplayRows and shared-list alias behavior differ from v1 and its aggregate quota uses encrypted page/manifest bytes rather than raw v1 envelope bytes.

No explicit checkpoint product-owner decision was found. CP-A (retain v1 semantics) and CP-B (investigate a versioned format only) remain choices awaiting owner selection; the sanitizer decision remains separate and pending. The 64,000,000-byte checkpoint cap and 1,000,000-node sanitizer cap remain unchanged. SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.

The canonical source-match manifest and byte-attribution diagnostic were rerun together after the final manifest was written: 4 passed, 0 failed, 0 skipped, 1 warning, 5.16 seconds, exit 0. Exact command and environment are in the JSON evidence. Ruff, compileall and git diff --check also passed.

The final evidence-hash assertion was added and rerun with the attribution diagnostic: 5 passed, 0 failed, 0 skipped, 1 warning, 5.71 seconds, exit 0. This run validates the canonical manifest's receipt, memory-sample, prior-review and owner-decision hashes; it does not measure the unavailable failed result.


## Post-reconciliation test rerun (2026-10-29)

After correcting the integrated evidence hash references, the focused manifest/attribution command was rerun with a pre-created ignored pytest temp directory: 5 passed, 0 failed, 0 skipped, 1 Starlette/httpx deprecation warning, 5.41 seconds, exit 0. This confirms the source-match and disposable byte-attribution checks after the evidence reconciliation; the failed workload result remains unavailable and no full workload was run.
