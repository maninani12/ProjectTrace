# ProjectTrace Commercial V1 — durable local checkpoint

Status: **DEVELOPMENT IN PROGRESS**. **SCALE-001 — NOT QUALIFIED.**

Latest continuation: 2026-11-02 authorized GitHub backup and new-laptop handoff. See the dated entry at the end; historical test counts and environment blockers below apply to their recorded source and date.

## 2026-10-27 — Master directive, baseline established

- Branch: `codex/scale-001-local-continuation`.
- HEAD: `9e21509591bfa5457cc829ebd5637f95be68d573`; no commits/pushes/workflows authorized.
- Existing dirty tree: nine tracked files modified plus retained untracked
  checkpoint, generation-map, streaming-export and rejected experiment files.
- Fresh baseline hashes **632 existing tracked/untracked nonignored files**;
  this replaces historical source-count assumptions. No existing source was
  changed when recording the baseline.
- Four original databases remain byte-identical to the prior preservation
  evidence. Each passes SQLite/FK checks. The 147-metric and prior fixture each
  retain three PUBLISHED generations and two pointers; the 10k/30k fixtures each
  retain one PUBLISHED generation and one pointer.
- Baseline evidence/work root:
  `C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work\commercial-v1-20261027-01`.
  `baseline.json` contains all file hashes, database hashes, status and environment.

## Coordinated execution plan

1. Revalidate focused baseline checkpoint/recovery and documentation-verdict
   tests without enabling any rejected graph-index plugin.
2. Profile original production-equivalent snapshot serialization, compilation,
   parameter binding, fetch/hydration, native index evaluation and owned cold
   publication. Keep original graph indexes/read SQL. Stop index experiments
   unless a new measured removable redundancy is established.
3. Reproduce the 50k structural guard failure, trace all snapshot consumers,
   and write an architecture decision if segmentation crosses a persistence/API
   boundary. Do not deploy a speculative new snapshot contract.
4. Investigate expiry/downgrade and lease/recovery behavior with disposable
   fixtures; reproduce defects before changing production code.
5. Audit and validate the existing documentation-drift vertical slice and its
   React integration. Reuse existing modules and labeled fixtures.
6. Update the release matrix and this checkpoint after each completed milestone.

## Current verified / failed / not run

- VERIFIED: fresh preservation baseline and SQLite/FK integrity only for this
  new execution batch. Prior test outcomes remain historical until rerun.
- FAILED, historical: 50k inline sanitizer guard; graph-index experiments
  rejected (last experiment 91 passed / 8 failed plus HTTP ordering failures).
- NOT_RUN: new baseline tests/profiles, full pinned Linux cgroup qualification,
  PostgreSQL/Redis/Celery/Docker checks, browser acceptance, deployment/recovery
  on the target production host.
- No production module, migration or resource guard changed in this batch yet.

## Exact next action

Run the focused baseline tests and prepare the original-path profiler in the
new work root. Frontend dependencies are absent in this checkout; install only
the project's locked frontend development dependencies with lifecycle scripts
disabled before running its existing unit tests/build. Full pinned Linux,
remote workflows, commits/pushes and production changes still require approval.

## Milestone 1 — baseline and frontend validation

- Backend baseline: **67 passed**, 0 failed/0 skipped, 532.20 s pytest time.
  Commands/results: `baseline-tests.json`, `baseline-tests.xml` in the work root.
  Covers existing migrations, generation contexts, the 10k/50k map decryption
  regressions and captured documentation/authentication drift/recovery.
- Frontend: locked dependencies installed with lifecycle scripts disabled;
  **49 passed**, 0 failed/pending; production build passed and prerendered 42
  public routes. Node v24.16.0. This is not browser or deployment acceptance.
- Frontend package/lock/source remain unchanged. No rejected prototype plugin
  was enabled in the baseline tests.

## Milestone 2 — expiry ownership defect reproduced and corrected

- Confirmed: active/cancel-pending worker recovery input/checkpoints/drafts
  could be deleted by expiry; unowned expired queue tokens remained renewable.
- Correct red suite: **9 failed / 12 passed**. The initial 12-failure receipt
  includes three invalid-fixture failures correctly rejected by tenant guards;
  those were corrected to explicit disposable legacy-corruption fixtures.
- First corrected suite: **21 passed**, 0 failed/skipped, 15.95 s pytest time.
- New `backend/retention.py` shares transaction-local scheduler/queue-row
  ownership locking. Existing cleanup batch sizes and retention/read deadlines
  remain unchanged. Cancel-pending live owners stay protected until fenced.
- `analysis_checkpoints.py`, `publication_units.py`, `generations.py`, and
  `queue.py` now select bounded metadata for cleanup, recheck ownership under
  locks, preserve receipts/public history, and fence reclaimed input attempts.
  No receipt version/digest, snapshot, graph index, HMAC or encryption format
  was changed. Existing uncommitted code outside targeted cleanup functions is
  retained. New regression file: `tests/test_retention_recovery.py`.
- Remaining verification before treating this slice as complete: renewal-race
  tests, generation-page/history cleanup, wider scheduler/checkpoint/recovery
  suites, and real PostgreSQL lock behavior. No PostgreSQL result is claimed.

## In progress / next safe actions

- Original-index owned CPU profile: `tests/commercial_snapshot_profile.py`,
  fresh output `cpu-original-147`; instrumented timings are not baseline speed
  or Linux/cgroup qualification.
- Then run same-input original 30k SQLite components and the existing 50k
  fail-closed guard case. Do not resurrect rejected index designs.
- Complete lease/race tests and relevant regressions after profiling, using new
  basetemps. Record snapshot-segmentation and retained-v2 downgrade decisions
  explicitly; neither is resolved by raising guards or rewriting receipts.
- Audit/validate the existing documentation drift vertical slice, including an
  owned browser run if existing service ports/browsers permit safe isolation.

**SCALE-001 — NOT QUALIFIED. Commercial V1 — DEVELOPMENT IN PROGRESS.**

## Milestone 3 — recovery verification and compatibility boundary

- `retention-expanded.xml`: **54 passed, 1 skipped**, 92.50 s. The explicit
  skip is `test_retention_postgresql.py`: no disposable PostgreSQL service is
  authorized/configured. Real row-lock behavior is NOT VERIFIED.
- `checkpoint-regressions.xml`: **60 passed**, 75.63 s; checkpoint pages,
  v1/v2 load, key rotation, cancellation, publication units and context replay.
- `generation-regressions.xml`: **34 passed**, 204.74 s; all existing generation
  restart/publication/final-commit cases on the corrected code.
- Final focused `retention-final.xml`: **29 passed**, 13.18 s; adds both lease
  renewal races, terminal-history preservation, rollback after deletion,
  non-starvation behind 1,000 protected orphan pages, metadata-only selection
  and real admitted-v2 normal-expiry/downgrade refusal.
- An intermediate metadata-only test exposed a remaining `discard` full-row
  checkpoint SELECT. Replaced it with tenant-scoped DELETE; the test was not
  weakened. Current tests pass after this correction.
- New operations guide: `docs/CHECKPOINT_RETENTION_AND_ROLLBACK.md`. Retained v2
  history still blocks downgrade. No format flag or receipt was reset/deleted
  to simulate compatibility. Migration 0026 itself is unchanged.

## Milestone 4 — original-index profiling and structural decision

- Two owned 147-metric cProfile runs completed with original graph indexes;
  one disables the diagnostic background sampler. Both have profiling overhead
  and are not production speed measurements. JSON, compile/bind, fetch, typed
  hydration and crypto function counts/times are recorded in `cpu-attribution.json`.
- Fresh same-value 30k UPDATE: 0.511612 s, native SQLite peak 342,798,624 bytes,
  process peak 393,408,512 bytes in that micro-operation process. This is not a
  complete 30k analysis/cgroup measurement. All eight sequential component/
  reproduction commands exited 0 and retained the original indexes/data.
- Direct 50k snapshot sanitizer reproduction: original 1,000,000-node guard
  rejects it, peak RSS 126,091,264 bytes, 2.463443 s. This is direct guard evidence,
  not a fresh full-job publication attempt. No resource limit was increased.
- Stop speculative index redesign. Native expression evaluation still consumes
  substantial memory; Python-side object reuse cannot make the SQLite API stop
  parsing the full bound JSON while keeping those expressions/contracts.
- ADR 0007 proposes permanent authenticated segmented snapshots and lists all
  persistence/API/expiry/backup compatibility obligations. **User answered
  "Review proposal first". No approval to implement that format was given.**
  Do not implement segments, change snapshot formats or perform a migration.

## Milestone 5 — existing commercial workflow validation

- `commercial-rules.xml`: **95 passed**, 49.26 s: existing analyzer evolution,
  OpenAPI, authentication drift, accuracy guards and Engineering Changes tests.
- Existing browser auth-drift workflow passed (**1 passed**, 51.0 s) against
  fresh owned API/database/UI, not an existing private account. Current final
  browser run additionally exercises the real ZIP-import workflow.
- No frontend source or verifier behavior was rewritten. Reuse working modules.
- Release/module matrix: `docs/COMMERCIAL_V1_RELEASE_GATES.md` distinguishes
  narrow verified workflows, partial modules, unsupported generic configuration
  claims and production/distributed qualification gaps.

## Milestone 6 — supported storage configuration drift

- Reused the existing `storage_claims` parser/inventory path. It reports an
  explicit supported production public ACL as CONTRADICTED within declared
  configuration scope. Private, absent, development-only, commented, or
  unsupported declarations remain UNVERIFIED; no runtime claim is made.
- Added `samples/configuration-drift.json` and
  `tests/test_configuration_drift.py`. The fixture captures the same immutable
  documentation claim against private BASE and public HEAD Terraform. The API
  test verifies the UNVERIFIED → CONTRADICTED transition, source hashes and
  evidence, `DECLARED_CONFIGURATION` scope, unchanged BASE, no imported-code
  execution, and cross-tenant denial.
- Focused command receipt `configuration-drift-final.json`: **7 passed**,
  including the new classification/API tests and existing native-platform and
  Engineering Changes regressions. The first attempt failed during pytest temp
  directory setup because the shared Windows temp path was inaccessible; a
  second run exposed an invalid test expectation about evidence on an
  UNVERIFIED claim. The final test compares immutable snapshot hashes and passed
  without altering product behavior or relaxing assertions.
- Added `frontend/e2e/configuration-drift.spec.ts`. Owned browser receipt
  `configuration-drift-browser-command.json`: **1 passed**; the UI displayed
  BASE/HEAD statuses and opened the captured `main.tf` evidence. The test used
  an isolated SQLite backend and owned Vite process, stopped after completion.
- Final static receipts `ruff-final.json` and `compile-final.json`: Ruff passed
  across backend, analyzers, integrations, workers, tests, scripts and
  integration_tests; Python compileall passed for the same paths. The browser
  run compiled and exercised its TypeScript test.
- Updated `docs/COMMERCIAL_V1_RELEASE_GATES.md`: this narrow storage workflow is
  verified locally; generic file/key configuration assertions and runtime
  authority remain unimplemented/unverified. This does not certify commercial
  release or production accuracy.

## Current next safe checkpoint

The local receipts are packaged at
`docs/evidence/PROJECTTRACE_COMMERCIAL_V1_LOCAL_2026_10_29_REVIEWED_V2.json` and
`docs/evidence/PROJECTTRACE_COMMERCIAL_V1_LOCAL_2026_10_29_REVIEWED_V2_RAW.tar.gz`.
The final source/database audit passed; the appended SCALE report prefix was
byte-verified unchanged. The ADR 0007 review is recorded in the proposal:
segmentation per object cannot admit the reproduced 50k logical snapshot while
preserving a global 1,000,000-node cap. That policy conflict and the durable
transaction/reader contract must be resolved before implementation. SCALE-001
remains NOT QUALIFIED; Commercial V1 remains DEVELOPMENT IN PROGRESS.

## Milestone 7 — aggregate sanitizer guard investigation (2026-10-29)

- **STOP — SCALE-001 remains NOT QUALIFIED.** An exact structural count matching `analyzers.sanitization.metadata` over the complete owned 50k snapshot is 1,115,947 nodes, 115,947 above the unchanged 1,000,000 limit. The direct sanitizer rejects before publication.
- Boundary behavior confirmed in three fresh processes: 999,999 and 1,000,000 nodes accepted; 1,000,001 rejected with the existing budget error. The pytest regression file was added, but pytest is unavailable in the local Python installations; the equivalent direct assertions passed.
- Streaming or compact storage cannot make the complete logical value admissible under the existing count. Resetting counts per page is a policy change and is rejected. No candidate qualified; no broad candidate suite was run.
- Full report and machine evidence: `docs/SCALE001_AGGREGATE_GUARD_INVESTIGATION.md` and `docs/evidence/SCALE001_AGGREGATE_GUARD_INVESTIGATION.json`. No production behavior, schema, migration, database or sanitizer cap changed.
- Product/security policy decision remains open: either keep the cap and declare larger snapshots unsupported, or explicitly revise its semantics after resource-budget analysis, threat review, and new acceptance tests. SCALE-001 is NOT QUALIFIED; Commercial V1 is DEVELOPMENT IN PROGRESS.

## Milestone 8 — policy decision readiness and test recovery (2026-10-29)

- Restored testing with the existing documented external ProjectTrace venv (Python 3.14.3, pytest 9.1.1, Ruff 0.16.10; `pip check` clean). All databases, keys, blobs, and pytest temporary files were isolated in the task workspace. No packages or dependency files changed.
- New sanitizer boundary test: **3 passed**. Full 50k owned publication-failure regression: **1 passed**, 455.68 s; 451.57 s to final guard failure, 303,468,544-byte sampled process peak RSS, 0 published pointers, failed job, valid SQLite/FK checks. Independent exact count remains 1,115,947 nodes.
- Focused snapshot persistence/comparison: **4 passed**. Generation/context/maps: **104 passed**. Commercial rules/quality/pipeline: **105 passed**. Graph/security: **22 passed, 70 skipped** by explicit disposable-ownership markers. JSON export/sanitizer: **116 passed, 2 failed** on randomized set order; the two failures pass with `PYTHONHASHSEED=0`. Checkpoint/retention: **65 passed, 1 PostgreSQL test skipped** because no disposable PostgreSQL URL/service was configured.
- Ruff final, compileall, and `git diff --check` passed. One set-order determinism failure in the existing dirty-tree JSON export tests remains for separate disposition; it does not involve the sanitizer boundary.

## 2026-10-29 — deterministic set JSON and SCALE-001 policy gate

- The prior default JSON export/sanitizer run remains recorded as **116 passed, 2 failed**. Both failures were `test_typed_context_export_replay_mutations_and_snapshot_integrity[False]` and `[True]`, where equivalent set members appeared in opposite JSON array order. The historical rerun with `PYTHONHASHSEED=0` remains recorded as 2 passed.
- `backend/generations.py:encoded` now orders set members by their canonical JSON spelling. Tuple order, mapping insertion order, set contents, set storage/replay semantics, and sanitizer policy are unchanged. The original two cases and a new direct set-encoding regression passed in the ordinary environment and under `PYTHONHASHSEED` 0, 1, 2, 3, 7, 17, and 42.
- Follow-up gates: export/sanitizer 119 passed; focused snapshot persistence 4 passed; generation/context/maps 71 passed; graph/security 22 passed, 70 skipped by explicit disposable-ownership markers. Ruff, compileall, `git diff --check`, and JSON parsing passed. Full-repository tests were not run.
- Added `docs/SCALE001_SUPPORTED_INPUT_BOUNDARY_PROPOSAL.md` as an internal Option A proposal. No explicit product-owner approval was found; state remains **PENDING_PRODUCT_OWNER_APPROVAL**. No cap, admission, storage, schema, or release-gate change was made.
- SCALE-001 remains **NOT QUALIFIED**. Commercial V1 remains **DEVELOPMENT IN PROGRESS**.

## 2026-10-29 — post-serialization regression closure attempt

- The deterministic set encoder was reviewed without further production changes. Original replay cases, the set-order regression, and an unsupported-object-in-set assertion passed in the default environment and with `PYTHONHASHSEED` 0, 1, 2, 3, 7, 17, and 42 (4 passed per run). The full JSON export module also passed all 69 cases in the broad backend run.
- The broad backend run collected 1,087 cases; one known full 50k snapshot-rejection profile was deselected. JUnit recorded 1,055 passed, 9 failed, 21 skipped, and 2 errors (one parser test had setup and teardown errors from Windows’ environment-variable length limit). Three graph-candidate failures were caused by a missing scratch compatibility fixture and passed in a corrected 70-case rerun. The remaining six graph-candidate failures match prior rejected-candidate evidence; they are not serialization failures.
- Opt-in graph recovery/scalar tests ran under an isolated scratch root with a copied 147 fixture: **64 passed, 6 previously recorded candidate assertions failed, 0 skipped**. Original databases still match their baseline hashes.
- `integration_tests` could not run on Windows: its Linux-only autouse fixture caused 58 setup errors; four broker tests skipped for unavailable disposable Redis/PostgreSQL services. Vitest passed 49 tests across 12 files. Ruff, compileall, `git diff --check`, and JSON parsing passed.
- SCALE-001 remains **NOT QUALIFIED**; Commercial V1 remains **DEVELOPMENT IN PROGRESS**. The aggregate cap and pending Option A approval state are unchanged.
- New readiness package recommends retaining the current 1,000,000 aggregate cap and treating larger logical snapshots as unsupported unless product/security owners explicitly authorize a policy change. No new limit or admission behavior was implemented. Linux, PostgreSQL, broker, concurrency, and full Commercial V1 qualification remain unverified.
- Report and machine evidence: `docs/SCALE001_POLICY_DECISION_READINESS.md` and `docs/evidence/SCALE001_POLICY_DECISION_READINESS.json`. **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**

## 2026-10-29 — integrated post-serialization regression reconciliation

- Reverified the authoritative local checkout at `C:\Users\sai krishna\Projects\ProjectTrace-local`, branch `codex/scale-001-local-continuation`, HEAD `9e21509591bfa5457cc829ebd5637f95be68d573`. Preserved the existing dirty worktree, databases, and staged report/evidence originals. The staged SHA-256 values match their recorded values; integrated report/evidence and raw receipts are under `docs/`.
- Added short explicit pytest IDs to the existing excessive-parser-structure parameters. The 1,000,001-delimiter payload and assertions are unchanged. Both cases pass; the Windows setup/teardown environment-variable length errors no longer occur.
- Re-ran focused deterministic serialization checks: 4 passed in each of eight separate hash-seed processes. Re-ran the owned graph candidates: 64 passed, 6 failed; the exact failures remain rejected ordering/projection/rowid semantics, not active production behavior.
- Corrected broad backend run: **1,059 passed, 6 failed, 21 skipped, 1 deselected, 0 errors**. The six failures match the rejected graph candidates. The separate 50k profile passes only its expected fail-closed assertion at the unchanged 1,000,000-node sanitizer guard; it publishes zero pointers and does not qualify successful 50k processing.
- Frontend Vitest: 12 files / 49 tests passed. Ruff, Python compilation, and `git diff --check` passed. The four original SQLite databases still match their baseline hashes and pass integrity/FK checks.
- Published-HEAD GitHub regression run 40280428892 passed all four jobs. Constrained run 40280429009 failed at VERIFYING with `GLOBAL_CHECKPOINT_BUDGET` at the 768 MB ceiling, without OOM; no output was published. These remote results are not results for the dirty local tree.
- Full regression closure remains open: six rejected candidate tests remain visible, 21 platform/service-dependent tests are skipped, and PostgreSQL, Redis/Celery, Linux parser/cgroup and complete SCALE acceptance gates remain outstanding. Option A remains pending product-owner approval. **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**

## 2026-10-29 — integrated SCALE-001 release-gate assessment

- Reverified the authoritative checkout, branch, HEAD, evidence hashes, and four original SQLite databases using read-only SHA-256, PRAGMA integrity_check, and PRAGMA foreign_key_check. All captured hashes match; integrity is ok with zero FK violations.
- Searched current policy records for an explicit product-owner decision. None was found. Option A remains a recommendation only; policy is PENDING_PRODUCT_OWNER_APPROVAL and the 1,000,000-node limit/admission behavior are unchanged.
- Classified the six graph failures as rejected test-only candidate behavior. No production graph path or expected test result was changed, and the six failures remain counted once.
- Rechecked GitHub runs 40280428892 and 40280429009 plus failure logs. Published-base regression passed all four jobs. The constrained baseline was Docker-confirmed OOM-killed; the candidate failed the existing 64,000,000-byte global checkpoint budget in VERIFYING without OOM. Recovery was not tested.
- No tests, 50k workload, workflow dispatch, source edit, commit, push, or PR action was performed in this review. The integrated evidence and qualification plan are recorded in docs/SCALE001_INTEGRATED_QUALIFICATION_GATE.md and its JSON companion.
- SCALE-001 remains NOT QUALIFIED; Commercial V1 remains DEVELOPMENT IN PROGRESS.

## 2026-10-29 — checkpoint budget and recovery follow-up

- Confirmed the failed published-base run used v1's monolithic uncompressed JSON checkpoint serializer. Its safe diagnostic exposes only `>64,000,000` bytes; exact size, row count, and collection remain unknown. The error occurred before publication preparation or generation admission.
- The cgroup peak was already 768,000,000 bytes at CLAIM_VERIFIER start, before GLOBAL_CHECKPOINT. Checkpoint rejection is not evidence that checkpoint serialization caused the memory peak.
- Preserved the existing uncommitted paged-checkpoint candidate without production or migration edits. Added a focused same-database/new-session recovery test; it passed twice. A synthetic default-cap probe verified below-budget admission, over-budget fail-closed cleanup, and SQLite/FK integrity.
- Current local test results: checkpoint 37 passed; related recovery/publication 195 passed, 1 Linux-only skip; full backend 995 passed, 91 skipped, 1 prohibited 50k profile deselected. Ruff and compileall passed. Full-suite skips include opt-in graph prototypes, PostgreSQL service cases, and Linux-only cases.
- Docker Desktop Linux engine is stopped; no disposable PostgreSQL/Redis endpoints are configured. Full Linux cgroup qualification and broker/database service tests remain unrun. Existing CI remains published-base evidence only.
- Option A remains PENDING_PRODUCT_OWNER_APPROVAL; aggregate node guard remains 1,000,000. No workflow, commit, push, PR, or main change. **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**

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

## 2026-10-29 - checkpoint attribution final local recheck

Verified the same continuation branch and HEAD, preserved all dirty work, and rechecked four original databases read-only: hashes match, SQLite integrity is ok, and FK violations are zero. Focused checkpoint/source-attribution tests: 40 passed, 1 warning. Related generation/publication/recovery selection: 195 passed, 1 Linux-specific skip, 1 warning. The older 233-pass result remains separately recorded; the count discrepancy is unresolved. Ruff, compileall, diff check, and JSON validation passed. No production change or full pinned workload. SCALE-001 remains NOT QUALIFIED.

## 2026-10-29 - source-matched checkpoint readiness

Added the canonical checkpoint source-match evidence at docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH.json. The source commit and run inventory are verified, but the prior historical archive differs, the failed result and checkpoint storage are absent, and analyzer/profile/runner-image identities are incomplete. Local Docker Linux is unavailable, WSL exposes only docker-desktop, cgroup v2 and PG/Redis/Celery services are unavailable; the full workload was not run. Context7 was not exposed; official Python, SQLAlchemy and cryptography documentation fallback is recorded in the field report. Checkpoint policy and the separate sanitizer policy remain pending owner decisions. No production change, limit change, commit, push, PR edit, or workflow dispatch. SCALE-001 remains NOT QUALIFIED.

The final canonical source-match and v1 attribution check passed 4 tests, 1 warning (5.16 seconds); Ruff, compileall and diff check passed. Full-workload bytes remain unknown and the workload was not rerun.

Final evidence-hash and attribution check passed 5 tests, 1 warning (5.71 seconds). No full workload or production change.


## 2026-10-29 - post-reconciliation checkpoint test rerun

The source-match and attribution selection passed 5 tests, 0 failed, 0 skipped, 1 warning in 5.41 seconds after the integrated evidence hashes were corrected. The full workload remains NOT RUN and SCALE-001 remains NOT QUALIFIED.


## Policy and Linux readiness assessment (2026-10-29)

Added `docs/SCALE001_POLICY_AND_LINUX_READINESS.md` and `docs/evidence/SCALE001_POLICY_AND_LINUX_READINESS.json` after verifying the expected branch and HEAD. Checkpoint CP-A/CP-B and separate sanitizer SP-A/SP-B choices remain pending explicit owner selection. The prior constrained result remains unavailable (`actual=null`); authenticated GitHub CLI lists only the existing candidate/baseline artifacts. Docker Linux, local cgroup v2, and PostgreSQL/Redis/Celery endpoints are unavailable, so no workload was repeated. The workflow’s mutable runtime inputs and missing full-matrix driver coverage are recorded. **SCALE-001 remains NOT QUALIFIED; Commercial V1 remains DEVELOPMENT IN PROGRESS.**

## 2026-10-29 - CP-B and SP-B investigation

Revalidated completed constrained run [40280429009](https://github.com/maninani12/ProjectTrace/actions/runs/40280429009) and inspected candidate/baseline receipts. Candidate hit the unchanged 64,000,000-byte v1 checkpoint admission guard in VERIFYING after 1,875.465 seconds; the cgroup ceiling was already first sampled during ANALYZING. Candidate had no OOM kill and published no generation or pointer. Baseline was OOM-killed in ANALYZING. Both post-exit databases passed SQLite and foreign-key checks. The candidate receipt retains `actual=null`; exact failed checkpoint size and field attribution remain unavailable.

CP-B review found the dirty paged candidate is not v1 restoration-equivalent (list type, alias/mutation behavior, and quota unit differ), so it remains unadopted. SP-B confirmed “50k” means 50,000 metric rows and 1,115,947 aggregate nodes, rejected before downstream persistence/validation/comparison. Existing checkpoint and sanitizer limits remain unchanged; no policy or production implementation was approved.

Local Windows checkpoint/sanitizer/context tests: 82 passed. Generation/publication/recovery/queue tests: 57 passed. Ruff and compileall passed. These are local dirty-worktree regressions, not Linux qualification. Docker Linux/cgroup v2 and disposable PostgreSQL/Redis/Celery services are unavailable. Full Linux workload and remaining release matrix remain NOT RUN. Details and sanitized raw evidence are in `docs/SCALE001_INTEGRATED_QUALIFICATION_GATE.md` and `docs/evidence/SCALE001_CP_B_SP_B_INVESTIGATION_20261029.json`. **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**


## 2026-10-29 — v1 checkpoint byte counter and Linux preflight

Added a tested, payload-free v1 raw-byte counter and an undispatched manual-only cgroup preflight workflow. The counter preserves v1 encoder settings and file normalization but is not integrated with the dirty paged writer because its quota unit and input consumption make post-failure recount unsafe. Synthetic 10k serializer measurements reduced transient traced peak and runtime versus a bytearray reference; these Windows-only measurements do not qualify the pinned workload. Focused tests: 9 passed; checkpoint/sanitizer/context selection: 82 passed; Ruff, compileall and static workflow checks passed. Docker Linux and app services remain unavailable locally; the workflow was not run. Historical `actual=null` remains unchanged, no production limits changed, and **SCALE-001 remains NOT QUALIFIED**. See `docs/SCALE001_POLICY_AND_LINUX_READINESS.md` and `docs/evidence/SCALE001_V1_CHECKPOINT_COUNTER_PREFLIGHT_20261029.json`.


Preflight static review also now fails closed unless runner image identity is present and Docker reports Linux+cgroup v2; it remains undispatched.


GitHub requires a manual workflow file on the default branch before dispatch; this local-only preflight cannot run under the current no-main/no-PR scope.

## 2026-10-30 — storage-privacy evidence excludes Markdown code examples

- Confirmed a local false-positive path in `analyzers/lexical_worker.py:storage_claims`: the scanner toggled only on lines beginning with triple backticks. A literal `Production storage is private.` inside a tilde-fenced example was treated as authoritative prose and paired with a declared public production bucket, yielding `CONTRADICTED`.
- Added the regression first and ran it against the original scanner. Exact test `tests/test_configuration_drift.py::test_storage_privacy_ignores_tilde_fenced_documentation_examples` failed as expected: the scanner emitted a `storage_privacy` claim for the fenced example.
- The correction filters only this rule's line-oriented Markdown evidence: backtick/tilde fences close only with the same marker and at least the opening run length; indented code lines are excluded. Prose after a valid close is still evaluated. Resource kinds, assertion text, production scoping, status semantics, and declaration parser are unchanged.
- Evidence contract: only a literal supported assertion in Markdown prose can start this check; the comparison side is the existing supported declared-storage inventory. `CONTRADICTED` requires an explicit supported public declaration in the assertion's scope. An assertion without conclusive supported configuration remains `UNVERIFIED`; absent/unsupported evidence never becomes contradiction. The scanner does not emit `VERIFIED`, `INFERRED`, or `STALE` and makes no runtime/deployed-privacy claim. It has no separate result cache; the isolated wrapper supplies the Markdown batch and projected supported assets, binds per-file SHA-256 values, and checks returned path/line/schema. No configuration parser formats/resource kinds, cache, database, or API contract was added.
- Focused command: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe -m pytest -q tests/test_configuration_drift.py --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\projecttrace-drift-focused-71d537773f44431a9d0a2bc79f6ae` — **9 passed**, 1 third-party deprecation warning. Adjacent selection: same Python executable with `-m pytest -q tests/test_configuration_drift.py tests/test_engineering_changes.py tests/test_lexical_boundary.py tests/test_native_platform.py tests/test_security_hardening.py tests/test_analyzer_evolution.py tests/test_analyzers.py tests/test_auth_drift.py --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\projecttrace-drift-regressions-fdf7cadc8205441ab1d6e4d9523d5275` — **158 passed**, 1 warning. Full local command used that executable with `-m pytest -q --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\projecttrace-full-suite-ac098a25b33b44d09d0af055268e1af0` — **1,015 passed, 91 skipped**, 1 warning, exit 0 (19m 08s). This concise run did not print individual skip reasons; the skip count is not treated as service qualification.
- Before correction, the focused regression command used `tests/test_configuration_drift.py::test_storage_privacy_ignores_tilde_fenced_documentation_examples` and `--basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\projecttrace-drift-red-c7b06063e4be457888d9beb25a216283`; it exited 1 with the expected failed assertion. That test was then expanded/renamed to cover three code forms and fence re-entry.
- Static checks: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\ruff.exe check analyzers/lexical_worker.py tests/test_configuration_drift.py`, `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe -m py_compile analyzers/lexical_worker.py tests/test_configuration_drift.py`, and `git diff --check` returned 0. This is Windows local evidence on the dirty worktree; no GitHub workflow or Linux qualification was run.
- After moving the fence regexes to module constants, the exact current-tree rerun `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe -m pytest -q tests/test_configuration_drift.py --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\projecttrace-drift-final-1c2b51a2f2074dcd940aa4e5b48b3132` again passed **9 tests** in 5.37 seconds, with one deprecation warning. The whitespace scan across the two Python files and both updated Markdown files passed.
- Existing dirty work was preserved. Branch and HEAD remain `codex/scale-001-local-continuation` / `9e21509591bfa5457cc829ebd5637f95be68d573`. No commit, push, PR, migration, or workflow action. **Commercial V1 remains DEVELOPMENT IN PROGRESS; SCALE-001 remains NOT QUALIFIED.**

## 2026-10-30 — Linux parser-isolation preflight for storage-privacy fix

- Re-reviewed the full implementation diff and current storage/API tests. The worker accepts backtick and tilde fences with up to three leading spaces; a closing fence must use the same marker and a run length no shorter than the opener. Four-space/tab-indented code is excluded. A matching close resumes prose checks; a shorter/mismatched fence does not close; EOF inside a fence suppresses remaining candidate assertions. Only the existing `.md` sentence pattern and four storage inventory kinds are used. The public assertion, declared-production matching, `CONTRADICTED`/`UNVERIFIED` semantics, source-hash checking, parent schema/line checks, tenant handling, and parser security policy are unchanged.
- Added `test_storage_privacy_examples_preserve_isolated_worker_contract` to `integration_tests/test_lexical_isolation.py`. It exercises the public `analyzers.lexical.storage_claims` wrapper and its result/source identity contract for backtick/tilde fences, short and mismatched closing markers, a trailing-text malformed closer, indented and unclosed examples, a longer valid closer, ordinary supported prose, and declared-public evidence. The file is already included in the `parser-isolation` Linux job in `.github/workflows/ci.yml`; no workflow was changed.
- Windows checks: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe -m pytest -q tests/test_configuration_drift.py --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\projecttrace-isolation-preflight-97d9d645bc094212a10e40ebaf73bfbc` passed 9 tests, 1 third-party warning (16.11 seconds). `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe -m pytest --collect-only -q integration_tests/test_lexical_isolation.py::test_storage_privacy_examples_preserve_isolated_worker_contract` collected 1 test but did not execute it. An in-process direct-worker plus parent-wrapper contract probe passed for the same cases; this did not invoke OS isolation. Ruff, `py_compile`, and `git diff --check` passed for the worker and test files.
- Linux environment preflight: `wsl.exe --list --verbose` reports only `docker-desktop`, stopped, WSL version 2; there is no user Linux distribution. Docker context is `desktop-linux`, but `docker info` fails because `dockerDesktopLinuxEngine` named pipe is absent. There is no runnable local Linux engine, so the exact uncommitted source has NOT been executed under Linux.
- Existing `.github/workflows/ci.yml` parser job uses `ubuntu-latest`, `PROJECTTRACE_PARSER_ISOLATION=required`, runs the actual parser/archive/lexical isolation and security regressions, builds and probes the non-root container, and uploads evidence for seven days. This is tooling configuration, not a result for the current dirty source. No matching downloaded Linux runner artifact was found in the worktree; the historical SCALE cgroup receipts are not parser-isolation results.
- The 30 October full-suite command used concise `pytest -q` without `--junitxml`; its 91 skips were counted, but that run retained no test identifiers or reasons. The temp run tree contains no XML/log, and `.pytest_cache` contains node IDs/last-failure data, not skip reports. Five retained `benchmarks/*.xml` reports are dated 25 October, contain 66–325 tests each and zero skips, and cannot identify the later 91. Exact skipped identifiers/reasons are therefore UNAVAILABLE, not inferred and not treated as tests never collected.
- No full-suite rerun was performed for skip recovery. No workflow was dispatched, no commit/push/branch change occurred, and no isolation or resource policy changed. **Commercial V1 remains DEVELOPMENT IN PROGRESS; SCALE-001 remains NOT QUALIFIED.**

## Linux parser-isolation qualification preflight - 2026-10-30

- Identity remained branch `codex/scale-001-local-continuation`, HEAD `9e21509591bfa5457cc829ebd5637f95be68d573`; no branch, commit, or remote change. The tracked and untracked worktree remained dirty and was preserved.
- Read-only environment check: WSL `3.0.3.0`, kernel `6.18.54.1-1`, default WSL version 2. The only registered distro is `docker-desktop` (Stopped, WSL 2), not a usable Ubuntu/user distro. Docker CLI and Docker Desktop executable are installed; `com.docker.service` is Stopped (Manual), `desktop-linux` points at the absent `dockerDesktopLinuxEngine` named pipe, and `docker info` fails. No Linux process or container can be run here without starting/configuring services or establishing a distro; neither was authorized or attempted.
- `.github/workflows/ci.yml` `parser-isolation` is `ubuntu-latest`, a 35-minute job, Python 3.14, and `PROJECTTRACE_PARSER_ISOLATION=required`. The evidence directory is `${{ runner.temp }}/sandbox-evidence`; the lock file is installed before tests. Exact job commands:
  ```sh
  pip install -r requirements.lock
  mkdir -p "$PROJECTTRACE_SANDBOX_EVIDENCE"
  pytest -q integration_tests/test_parser_isolation.py --tb=short --junitxml="$PROJECTTRACE_SANDBOX_EVIDENCE/results.xml"
  pytest -q integration_tests/test_archive_isolation.py tests/test_archive_safety.py --tb=short --junitxml="$PROJECTTRACE_SANDBOX_EVIDENCE/archive-results.xml"
  pytest -q integration_tests/test_lexical_isolation.py --tb=short --junitxml="$PROJECTTRACE_SANDBOX_EVIDENCE/lexical-results.xml"
  pytest -q tests/test_auth_drift.py tests/test_repository_store.py::test_partitioned_global_claims_and_network_policy_match_legacy tests/test_repository_store.py::test_unchanged_observations_require_no_source_decryption tests/test_repository_store.py::test_new_syntax_failure_is_not_persisted_as_reusable_artifact --tb=short --junitxml="$PROJECTTRACE_SANDBOX_EVIDENCE/regressions.xml"
  docker build -t projecttrace-sec002 -f infrastructure/Dockerfile .
  mkdir -p "${RUNNER_TEMP}/sandbox-evidence"
  printf '%s' 'OWNED-HOST-SENTINEL' > "${RUNNER_TEMP}/sec002-sentinel"
  docker run --rm --read-only --network none --cap-drop ALL --pids-limit 64 --security-opt no-new-privileges --mount "type=bind,src=${RUNNER_TEMP}/sec002-sentinel,dst=/run/sec002-sentinel,readonly" -e APP_ENV=production -e PROJECTTRACE_PARSER_ISOLATION=required -e PROJECTTRACE_PROBE_SENTINEL=/run/sec002-sentinel -e DATABASE_URL=OWNED-SECRET-NOT-FOR-PARSER projecttrace-sec002 python -m scripts.parser_isolation_probe > "${RUNNER_TEMP}/sandbox-evidence/container-probe.json"
  ```
- The test step uploads sandbox evidence for seven days. There is no job-level RAM/CPU ceiling; parser workers enforce their own limits described below.
- Runtime requirements read from the implementation: Linux x86_64/aarch64; Landlock ABI 3 or newer; `libseccomp.so.2`; working capability-drop, `PR_SET_NO_NEW_PRIVS`, seccomp filter and `/proc/self/status` behavior. The worker uses Linux `resource` limits, nonblocking pipe IPC and process-group termination. Normal parser helpers are capped at 512 MiB address space and 25 CPU seconds (IaC: 384 MiB and 10 CPU seconds); the parent protocol defaults to 30 seconds, 32,000,000 input bytes and 16,000,000 output bytes. The app image installs Debian `libseccomp2`; Python dependencies are pinned in `requirements.lock`. The code verifies actual kernel denials; a flag-only or mocked wrapper run is insufficient.
- Windows-only safe checks in this pass: `python -m pytest -q tests/test_configuration_drift.py` — **9 passed**, one Starlette/httpx deprecation warning; collection of `integration_tests/test_parser_isolation.py` and `integration_tests/test_lexical_isolation.py` — **50 collected**, not executed. This confirms test discovery only. No Linux parser test, IPC, denial probe, Docker build, or container probe ran. Earlier recorded 158 related passes and 1,015 passed/91 skipped full suite are Windows results, not Linux qualification.
- SHA-256 identities for the relevant current dirty-source inputs (hex, exact bytes): `analyzers/lexical_worker.py` `ded53c0e81b2b46d3851e6323e7fb9b0b0baf68c306e23dad25314af9c2a663d`; `integration_tests/test_lexical_isolation.py` `9e1a5bb31e77e0a46650547551de74127bda9529664a758e5307ec6536b58694`; `tests/test_configuration_drift.py` `030557e9c507c338a0ba4b05fd161ac7a56d2d56e132a29878d093f85708d604`; `analyzers/lexical.py` `6d1dbc783e03b7543c0c9b2968267ec13625e1f252f7a9a295961bc544298ee4`; `analyzers/sandbox.py` `e53298b9c06a458a4b3b6617bdc067d8c578dabe36ef6e189e6f583a367d19f3`; `analyzers/isolated_worker.py` `f2a4abddcb7b4a66b0bf904d4d0d6ed5eb85e299d54c2ad67726bba7a7409670`; `integration_tests/test_parser_isolation.py` `1a44408276f296f3e1835f962e897d6dff23cccd6d5bb8bdf612fad674b68ffc`; `.github/workflows/ci.yml` `a6fa9e41c733031f05518860f0da80ad1fc65c6dea2be488236a5c4d7b96fb54`; `requirements.lock` `0331753af6ba66329bbb3be218c94da7e0634b8013b91d83ecbcb5f27c5b95aa`; `infrastructure/Dockerfile` `caad258aac6d7dd9058691027cdc950d9f35b0c6f9ae3defe4176026ad87fdc1`; `backend/process_limits.py` `1247beec3ae6ccdf203e00883b3212b158128f5b4e24e712c6392aa587eb4d9b`.
- Next step is to provide an already-usable Ubuntu WSL2/Linux runtime with these kernel interfaces and locked dependencies, or separately authorize an exact-source remote qualification path. Do not use the existing CI checkout as evidence for this dirty source. **Linux parser-isolation qualification remains NOT RUN; SCALE-001 remains NOT QUALIFIED.**

## Linux parser-isolation execution - 2026-10-30

- This follow-up supersedes the immediately preceding preflight statement that Linux execution was NOT RUN. The source was copied from the unchanged Windows checkout into a unique Ubuntu home directory, not from GitHub and not with git archive: /home/sai_krishna/projecttrace-linux-qualification-20261030-2zdhvg3c. The copy contains the 679 paths from git ls-files --cached --others --exclude-standard (41,379,093 bytes), including tracked modifications and nonignored untracked files. Every file was SHA-256 checked while copying and checked again before test setup. Tree digest: e100b089ef6a5ddaa27327bed51097d94b81aa44d5cf2ff1484dfa27d857eb07. Full per-file manifest: /home/sai_krishna/projecttrace-linux-evidence-20261030-yqe4r2f8/source-copy-manifest.json. The .git directory was excluded; the tested parser/security suites do not depend on it.
- Linux runtime: Ubuntu 24.04.5 LTS WSL2, x86_64, kernel 6.18.54.1-microsoft-standard-WSL2; Landlock ABI query returned 7; libseccomp.so.2 loaded successfully; /proc/self/status was available. Python 3.14.10 was installed user-scoped with Astral uv 0.13.6 after reviewing the official https://astral.sh/uv/install.sh installer. The 95 dependencies in the existing requirements.lock were installed into the copied tree .venv. No system packages or project dependency files were changed; libseccomp.so.2 was already installed. Logs: python314-install.log, locked-dependencies-install.log, linux-environment.json in the Linux evidence directory.
- With PROJECTTRACE_PARSER_ISOLATION=required, the four existing parser-isolation CI pytest commands all passed on the Linux copy: parser isolation 18 passed (28.39 s); archive isolation and safety 18 passed (13.43 s, one Starlette/httpx deprecation warning); lexical isolation 32 passed (42.41 s); security/repository regressions 13 passed (81.01 s, one deprecation warning). Aggregate: 81 passed, 0 failed, 0 errors, 0 skipped. JUnit files are parser-isolation.xml, archive-isolation.xml, lexical-isolation.xml, and security-repository-regressions.xml.
- Additional Linux checks: focused required-worker Markdown regression 1 passed (1.62 s); tests/test_configuration_drift.py 9 passed (60.08 s, one deprecation warning); Ruff and py_compile on the lexical worker and related tests passed; pip check reported no broken requirements. The focused test is included in the 32-test lexical suite and is not double-counted in the 81.
- Actual OS boundary evidence: every parser and lexical integration test entered the autouse required_boundary fixture, which asserts Linux, required mode, and a fresh real worker attestation. host-denials.json records denied filesystem read/write, /proc, metadata, O_PATH, network to loopback/public/link-local addresses, exec, and fork; no_new_privileges=1, seccomp mode 2, denial errno values were only EPERM/EACCES, and the child environment contained only LANG, LC_ALL, and PROJECTTRACE_PARSER_ISOLATION. Timeout, CPU, worker crash, malformed output, memory exhaustion, and output-budget tests passed. The development-versus-required analysis compatibility test passed with meaningful results and engine states equal; small fixture wall time was 1.04 s development / 4.24 s required, not a production throughput claim. The new storage-privacy regression passed over actual worker IPC.
- Container security probe: NOT RUN. Docker CLI in the Ubuntu distro reports Docker Desktop WSL integration is unavailable; the Linux engine is unreachable. No Windows service was started and no system setting was changed. Therefore the Linux worker/parser suites are verified, while the Docker image gate is still open.
- Reproduction commands, concise console results, parsed JUnit summary, denial summary, source manifest, environment identity, dependency logs, and raw JUnit reports are under /home/sai_krishna/projecttrace-linux-evidence-20261030-yqe4r2f8; see reproduce-linux-pytest.sh and linux-test-console-summary.txt. The source copy was isolated from the authoritative Windows worktree; no source code changed in this qualification pass.
- The Windows branch and HEAD remained unchanged. Linux parser/worker test gate: PASS; container probe: NOT RUN; overall parser-isolation release gate: PARTIAL. SCALE-001 remains NOT QUALIFIED and Commercial V1 remains DEVELOPMENT IN PROGRESS.

## Docker container security gate recheck - 2026-10-30

- The Linux source copy was rehashed immediately before this check: 679 files, tree SHA-256 e100b089ef6a5ddaa27327bed51097d94b81aa44d5cf2ff1484dfa27d857eb07. Dockerfile SHA-256 caad258aac6d7dd9058691027cdc950d9f35b0c6f9ae3defe4176026ad87fdc1; requirements.lock SHA-256 0331753af6ba66329bbb3be218c94da7e0634b8013b91d83ecbcb5f27c5b95aa.
- Exact CI build command: docker build -t projecttrace-sec002 -f infrastructure/Dockerfile .
- The Dockerfile uses python:3.14-slim, installs libseccomp2 and requirements.lock, and runs as projecttrace uid 10001. The base image is referenced by a mutable tag, not a digest. No image was built, so no image ID or resolved base-image digest exists.
- Exact CI runtime restrictions: --read-only, --network none, --cap-drop ALL, --pids-limit 64, --security-opt no-new-privileges, read-only sentinel bind mount, APP_ENV=production, PROJECTTRACE_PARSER_ISOLATION=required, and the sentinel plus disposable DATABASE_URL environment. scripts/parser_isolation_probe.py verifies the parent reads the sentinel and the child cannot read/write filesystem data, access proc/metadata/O_PATH, use network/exec/fork, or inherit database/key environment variables; it also checks NNP and seccomp.
- Read-only Docker state: Docker Desktop 4.94.0.241994 is installed; Windows service com.docker.service is Stopped (Manual). The active desktop-linux context endpoint npipe:////./pipe/dockerDesktopLinuxEngine is unavailable. Ubuntu WSL docker info exits 1 and reports that Docker Desktop WSL integration is unavailable. The settings-store JSON had no WSL integration key. No service was started and no integration/system setting was changed.
- The image build and restricted container probe were NOT RUN. Evidence: /home/sai_krishna/projecttrace-linux-evidence-20261030-yqe4r2f8/docker-gate-recheck.json and docker-gate-recheck.txt. Minimum user authorization needed: start Docker Desktop and enable WSL integration for Ubuntu-24.04, or provide another already-running Linux Docker engine. Then run the exact build and probe from the verified source copy.
- Linux parser/worker pytest acceptance remains PASS (81 passed, 0 failed, 0 skipped); container acceptance remains NOT RUN. Overall parser container gate is BLOCKED pending an available authorized engine. SCALE-001 remains NOT QUALIFIED.

## Docker engine connectivity retry - 2026-10-30

- Recomputed the verified Linux source-copy digest: e100b089ef6a5ddaa27327bed51097d94b81aa44d5cf2ff1484dfa27d857eb07; it matches the expected digest.
- Read the copied .github/workflows/ci.yml. Exact build command: docker build -t projecttrace-sec002 -f infrastructure/Dockerfile . . Exact restricted runtime command is retained in docker-gate-current-check.txt and the workflow.
- From Ubuntu-24.04, docker info exited 1. Exact output: The command docker could not be found in this WSL 2 distro. We recommend to activate the WSL integration in Docker Desktop settings.
- Stopped before build and container probe. No service, WSL integration, source file, or system setting was changed. The existing 81-test Linux result was not repeated.
- Recheck evidence: /home/sai_krishna/projecttrace-linux-evidence-20261030-yqe4r2f8/docker-gate-current-check.txt. Docker container qualification remains BLOCKED; SCALE-001 remains NOT QUALIFIED.

## 2026-10-30 — Docker SEC-002 container security gate execution

**PASS for the verified Linux source copy in Ubuntu-24.04.5 WSL2.** This supersedes the earlier Docker `BLOCKED / NOT RUN` entries, which correctly described the pre-authorization state. Docker Desktop 4.94.0.241994 was started, WSL integration was enabled specifically for Ubuntu-24.04, and that distro was restarted. The Docker Linux engine became available (Engine 29.8.2, linux/amd64). The offered Docker Desktop 4.97.0 update was not installed.

- Source: `/home/sai_krishna/projecttrace-linux-qualification-20261030-2zdhvg3c`; expected tree SHA-256 `e100b089ef6a5ddaa27327bed51097d94b81aa44d5cf2ff1484dfa27d857eb07`. All 679 files listed in the retained source-copy manifest still match by path, size, and SHA-256; zero listed files were changed or missing. Dockerfile SHA-256 `caad258aac6d7dd9058691027cdc950d9f35b0c6f9ae3defe4176026ad87fdc1`; `requirements.lock` SHA-256 `0331753af6ba66329bbb3be218c94da7e0634b8013b91d83ecbcb5f27c5b95aa`.
- Reproduced CI build: `docker build -t projecttrace-sec002 -f infrastructure/Dockerfile .` — exit 0. Image ID and local repo digest: `sha256:1bc662ae93992f671f766f20c404f64e03c9277970e6d937c8241d127b497914`; image config user `projecttrace`, actual UID 10001, platform linux/amd64. The Dockerfile's mutable `python:3.14-slim` base resolved for this build to index digest `sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8`, with linux/amd64 manifest `sha256:ec6a14df5b63e3fbb3498e3240f7f640c230f9dca67683d23265db3866697f2d`. The base tag was not changed or pinned.
- Reproduced the workflow's hardened container probe with `APP_ENV=production`, `PROJECTTRACE_PARSER_ISOLATION=required`, the workflow's dummy `DATABASE_URL`, the read-only sentinel bind mount, `--read-only`, `--network none`, `--cap-drop ALL`, `--pids-limit 64`, and `--security-opt no-new-privileges`. Exit 0; stderr empty. The probe asserted read/write/proc/metadata/O_PATH/exec/fork denials, all three network denials, NNP=1 and seccomp=2. Its parser child environment omitted `DATABASE_URL` and `ANALYSIS_INPUT_KEY`.
- A second ephemeral container using the same restrictions verified actual runtime state: UID 10001; `CapEff=0000000000000000`; `NoNewPrivs=1`; `Seccomp=2`; `/sys/fs/cgroup/pids.max=64`; only `lo` network interface; root mount read-only with a denied write probe; sentinel mount marked read-only.
- Existing Linux parser/worker pytest result (81 passed) and configuration-drift result (9 passed) were not repeated. No GitHub workflow was dispatched. Application source, branch, and HEAD were not changed; only this evidence documentation was appended. Current branch/HEAD remain `codex/scale-001-local-continuation` / `9e21509591bfa5457cc829ebd5637f95be68d573`.

Raw evidence directory: `/home/sai_krishna/projecttrace-linux-evidence-20261030-yqe4r2f8`. Summary receipt: `docker-container-qualification-20261030.json`; retained build log: `docker-build-sec002-20261030.log`; image inspect: `docker-image-inspect-20261030.json`; resolved base inspect: `docker-base-image-inspect-20261030.txt`; engine identity: `docker-engine-info-20261030.txt`; probe output/stderr: `container-probe-20261030.json` / `container-probe-20261030.stderr.txt`; runtime restriction output: `container-restrictions-20261030.txt`; source manifest recheck: `docker-source-recheck-20261030-173338.json`.

This completes the local Docker SEC-002 image build and container probe gate for this source copy. It does **not** qualify the full pinned SCALE-001 workload or the complete release. **SCALE-001 remains NOT QUALIFIED; Commercial V1 remains DEVELOPMENT IN PROGRESS.**

## 2026-10-31 — Commercial V1 public GitHub BASE/HEAD workflow

- Product audit confirmed the existing extraction, claim verification, supported storage-privacy drift, immutable snapshot, Engineering Changes, source-evidence and frontend comparison modules were already present. The customer-facing gap was that public GitHub import always created a new repository, so users could not submit a later pinned public commit into the same repository through the UI and obtain a BASE/HEAD comparison.
- Extended the existing public import flow with an optional authorized `repository_id`. Existing destinations are restricted to the same `GITHUB_PUBLIC` provider and canonical owner/repository. Admission freezes the latest visible snapshot as `base_id`; idempotency includes the destination, and the worker revalidates tenant/repository scope and preserves the frozen BASE on retries. The UI now distinguishes the new-repository baseline action from importing/comparing a later snapshot.
- A codeload-shaped regression established a separate correctness defect: changing only `main.tf` reported all eight fixture paths as changed because GitHub's pinned ZIP root included the commit identity. A read-only codeload fetch of `octocat/Hello-World` returned `Hello-World-7fd1a60b01f91b314f59955a4e4d4e80d8edf11d/README`, confirming the root changes across commits. New public captures now require the exact `{repository-name}-{full-commit-sha}/` root and lazily store paths relative to that root. Generic ZIP imports are unchanged. Existing BASE hash maps with the legacy root are compared through a bounded compatibility projection; historical snapshot/evidence rows are not rewritten. `comparison_snapshot` now includes the provenance needed for that projection.
- The pre-correction regression failed as expected: `test_public_api_continuation_compares_pinned_snapshots_and_preserves_tenant_scope` reported eight changed paths instead of only `main.tf`. Final backend command from the repository root: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe -m pytest -q tests/test_public_github.py tests/test_repository_store.py tests/test_configuration_drift.py tests/test_engineering_changes.py tests/test_auth_drift.py tests/test_streaming_import.py --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\projecttrace-product-maturity-release-final-20261030` — **66 passed**, 0 failures, one Starlette/httpx deprecation warning (214.19 seconds). It covers import idempotency, cross-tenant/provider denial, inert source handling, historical-root BASE comparison, stable repo-relative evidence paths, and the expected storage-privacy `UNVERIFIED` → `CONTRADICTED` transition.
- Legacy hash comparison uses a lazy `Mapping` view over the existing BASE hash dictionary. It retains only the source dictionary reference and root prefix; it does not copy the up-to-200,000-entry hash index. Checkpoint receipts still serialize the original concrete hash dictionary, preserving the generation-context writer contract and recovery compatibility.
- An intermediate run caught two issues before final validation: the bounded BASE projection did not receive provenance from `comparison_snapshot`, then its lazy `Mapping` was passed into the concrete generation-context serializer. The projection now selects `source_provenance`; `persist_analysis` uses the view only for comparison and stores the original dict in its checkpoint. The focused public tests and the final 66-test selection pass.
- From `frontend/`, `npm run test` passed **51 tests across 12 files**; `npm run build` exited 0 and prerendered 42 public routes. Python static checks passed: Ruff on the changed Python files, `py_compile` on the changed Python files, and `git diff --check`.
- The change preserves claim statuses and supported evidence semantics; missing/unsupported evidence remains non-contradictory. No generic configuration scanner or source execution was introduced. The public archive adapter validates isolated ZIP parser output and changes only the proven codeload root prefix. Encryption, tenant authorization, parser policy and resource limits were not changed.
- The prior Linux parser/worker (81 passed) and Docker SEC-002 probe results apply to the separately verified Linux source copy before this product delta. The exact current working-tree delta has **not** been requalified under Linux/Docker. No GitHub workflow was dispatched. Full SCALE-001 workload, warm/incremental, cancellation/exhaustion/recovery and production-corpus accuracy gates remain open. Branch/HEAD remain `codex/scale-001-local-continuation` / `9e21509591bfa5457cc829ebd5637f95be68d573`; no commit or push. **Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.**


## 2026-10-31 — Explicit captured BASE for public-import comparisons

VERIFIED locally for the described fixtures; Commercial V1 remains DEVELOPMENT IN PROGRESS and SCALE-001 remains NOT QUALIFIED.

Audit: preserved the existing dirty branch `codex/scale-001-local-continuation` at `9e21509591bfa5457cc829ebd5637f95be68d573`. Read progress/release/SCALE-001 gate evidence and inspected the public admission endpoint, worker, snapshot visibility controls, comparison/evidence readers, import dialog and regression fixtures. Existing extraction/verdict/configuration/graph modules were reused. The retained Ubuntu receipts independently confirm 81 Linux parser/worker passes, 9 configuration passes, and the Docker SEC-002 build/probe PASS for tree digest `e100b089ef6a5ddaa27327bed51097d94b81aa44d5cf2ff1484dfa27d857eb07`. Those receipts predate the public-import delta and do not certify the current dirty tree.

Customer workflow improvement: the public-import dialog now displays its captured BASE snapshot ID, branch/ref and commit, and explicitly submits that snapshot. The API accepts optional `base_snapshot_id`, requires a target repository, selects only an authorized same-tenant/same-repository snapshot through existing unpublished-generation visibility controls, and binds BASE to the idempotency fingerprint. The dialog retains captured BASE references across workspace refresh and failure/retry. The worker's existing frozen `base_id` path is reused. Legacy callers omitting the field retain latest-snapshot admission. Different HEAD refs are allowed as explicit snapshot comparisons; automatic branch-aware baseline selection is not claimed. For a destination with no displayed snapshot, the UI explains legacy latest-at-admission/baseline behavior.

Files changed in this milestone: `backend/main.py`, `frontend/src/WorkspaceApp.tsx`, `frontend/src/ImportFlow.test.tsx`, `tests/test_public_github.py`, new `frontend/e2e/public-base.spec.ts`, both progress/release documents, and `docs/evidence/COMMERCIAL_V1_EXPLICIT_BASE_20261031.json`. Earlier uncommitted changes were preserved. No source-execution, encryption, parser policy, resource limit, checkpoint admission, schema/migration, or publication algorithm changed.

Exact local validation (Python executable `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe`; backend commands from repository root):

- `python -m pytest -q tests/test_public_github.py --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\pt-base-final-20261031 --junitxml=C:\Users\SAIKRI~1\AppData\Local\Temp\pt-base-final-20261031.xml` — 23 passed, zero failed/skipped, one Starlette/httpx deprecation warning, 66.96 seconds. Covers explicit older BASE despite newer snapshots, legacy latest selection, unknown/wrong-kind/cross-tenant BASE denial, BASE without destination, idempotency conflicts, existing provider/tenant/no-execution checks and real worker drift comparison.
- Initial combined `python -m pytest -q tests/test_public_github.py tests/test_generations.py --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\pt-explicit-base-20261031 --junitxml=C:\Users\SAIKRI~1\AppData\Local\Temp\pt-explicit-base-20261031.xml` — 56 passed, 1 failed, zero skipped, one warning, 565.37 seconds. All 34 generation tests passed, including private-reader visibility, forced worker exits, cancellation/revocation/replacement, corruption, atomic commit/lost acknowledgement, and every stage restart. The one public-test failure came from adding too many API calls to a single rate window; negative cases were moved to a separate fresh-client/database test and the final 23-test public run passed. No limiter was disabled or raised.
- From `frontend/`, `npm run test -- --reporter=json --outputFile=test-results/public-base-unit-20261031.json` — 52 passed, zero failed/pending. Focused `npm run test -- src/ImportFlow.test.tsx` — 5 passed. `npm run build` — exit 0, TypeScript compiled, 42 public routes prerendered.
- Browser environment: `PROJECTTRACE_E2E_ISOLATED_API=1`, `PROJECTTRACE_PYTHON` set to the executable above; Vite on 127.0.0.1:5181 and the existing owned backend fixture on 8011, with disposable migrated/seeded SQLite databases. `npx playwright test e2e/public-base.spec.ts --output=test-results/public-base-complete-20261031` with `PROJECTTRACE_E2E_RESULTS=test-results/public-base-complete-20261031/results.json` — 1 passed, 22.2 seconds test time. This is real API baseline creation plus a mocked public repository projection and provider-failure response; it proves displayed/submitted BASE and failure retention, not live GitHub ingestion. Initial harness failures (wrong endpoint interception and pending response lifetime) were corrected by capturing API fixture responses before navigation and waiting for route cleanup. No application bypass was added.
- `npx playwright test e2e/public-base.spec.ts e2e/configuration-drift.spec.ts --output=test-results/public-base-20261031` — the existing real API configuration-drift browser test passed (41.0 seconds); the initial public UI fixture failed, as retained in that report. The real API test verifies immutable BASE/HEAD IDs, UNVERIFIED/CONTRADICTED semantics, declared-state limitations and HEAD source inspection.
- `ruff check backend/main.py tests/test_public_github.py`, `python -m py_compile backend/main.py tests/test_public_github.py`, and `git diff --check` — exit 0. Ruff used the sibling `ruff.exe` in the Python environment above.

Evidence receipt: `docs/evidence/COMMERCIAL_V1_EXPLICIT_BASE_20261031.json` retains changed-source SHA-256 values, every backend case outcome from both JUnit reports, browser report paths/scopes, and frontend results. Browser logs remain in the named ignored test-results directories; disposable databases and keys were not copied into documentation.

NOT_RUN: Linux/Docker validation of the current product delta, live public-GitHub browser ingestion, real PostgreSQL/Redis/Celery integration for this delta, full release/security matrix and full constrained SCALE-001 workload. The earlier security image pass is historical and remains valid for its exact source copy only. Remaining product gaps include complete legacy archive-root claim/evidence identity continuity (hash normalization alone is not a full historical citation migration), selecting arbitrary historical/branch-specific BASEs in the UI, and production-corpus accuracy measurements. Next smallest milestone: reproduce old-format public snapshots with real prefixed claim/evidence paths and prove a complete comparison without false claim removal or changed identities, before broadening public history selection. Preserve existing immutable evidence and source paths; do not rewrite history to hide mismatches.

No commit, push, remote workflow, PR edit, production migration or deployment occurred.


## 2026-10-31 — Legacy public snapshot claim/evidence continuity

**VERIFIED for the owned compatibility fixtures below. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.** Branch and HEAD remain `codex/scale-001-local-continuation` / `9e21509591bfa5457cc829ebd5637f95be68d573`. Earlier dirty work and historical evidence are retained; no commit, push, remote workflow, migration or deployment occurred.

### Reproduced defects and supported history

The original public worker passed isolated `archive_items` output directly into `capture`, preserving codeload paths such as `repo-{full-40-hex-commit}/docs/README.md`. The modern worker strips the exact pinned codeload wrapper and marks its inventory `GITHUB_REPOSITORY_RELATIVE`. Earlier hash-only compatibility did not normalize path-derived claim keys, evidence signatures or the repeated raw-key lookup in Engineering Changes. A test using actual capture, persisted claims/evidence and publication first failed because an unchanged modern HEAD claim had `previous_version_id=None` against a prefixed BASE. A second regression proved an already-contradicted documentation claim's `PT-CONSISTENCY-001` finding received a new identity solely from the layout change.

The new corpus creates historical layouts through the original raw-item capture shape, then publishes modern HEADs. It does not rewrite a modern snapshot's hash map to pretend it is historical; that older incomplete test simulation was replaced by these complete persisted fixtures. Both legacy→modern and modern→legacy sequences are covered over four published snapshots each, including actual changed evidence, genuine removal/addition, duplicate README basenames in separate directories, nested paths, and distinct literal `a b.md` versus `a%20b.md` paths. Percent escapes are not URL-decoded into Git path aliases. Malformed/unknown layouts are defensive fixtures, not invented claims about production history.

### Compatibility behavior and bounds

- `backend/public_snapshot_paths.py` establishes equivalence only from scoped public provenance, the exact repository/full-SHA codeload wrapper, canonical safe relative paths and the complete hash-path layout. A scoped inventory's existing relative-path marker prevents stripping a real directory that merely resembles an archive root. Missing provenance for a known public repository, invalid commits/repositories, foreign inventory references, mixed roots and unknown claim-key schemas never authorize a guessed alias.
- `backend/domain.py` compares hashes and claim identities through that view. Historical claim IDs, keys, paths and evidence rows are not rewritten. New versions retain the confirmed predecessor and logical identity. Evidence signatures and old-source lookup compare equivalent paths without inventing content changes or STALE history. Impact lookup/traversal maps the BASE namespace for comparison while retaining stored graph records.
- Engineering Changes follows a HEAD claim's confirmed `previous_version_id` within the selected BASE's captured claims before its existing key fallback. Original documentation/evidence IDs, hashes and literal historical paths remain inspectable. The related documentation-consistency finding is reconciled only through that actual predecessor claim and rule, with ambiguous candidates rejected.
- Unresolved layouts and duplicate/unknown historical claim identities are explicit PARTIAL warnings/metadata; removals are withheld where identity cannot be established. This does not turn unsupported evidence into CONTRADICTED or change the supported verdict vocabulary.
- The path resolver retains only prefix/state metadata and scans existing bounded inventories; it creates no global cache or duplicate source-content store. Evidence aliases replace comparison-dictionary entries one at a time. Claim and predecessor indices are transient O(number of captured claims), subject to existing admission/source guards. No performance or full-workload memory claim is inferred; the additional claim-ID index still needs whole-pipeline qualification. Raw dictionaries, rather than resolver objects, remain in generation receipts. No resource guard or checkpoint admission/format was changed.

Implementation/test files for this milestone: `backend/public_snapshot_paths.py`, `backend/domain.py`, `backend/engineering_changes.py`, `backend/snapshot_context.py`, `tests/test_public_snapshot_continuity.py`, `tests/test_public_github.py`, `frontend/src/ClaimComparisons.test.tsx`, these two documentation files and the dated evidence receipt/raw archive.

### Executed validation

Python executable for the commands below: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe`; backend commands ran from the repository root. The source SHA-256 values captured before the final current-source run still match afterward.

- Final current-source command: `python -m pytest -q tests/test_public_snapshot_continuity.py tests/test_public_github.py tests/test_configuration_drift.py tests/test_engineering_changes.py tests/test_generations.py::test_final_promotion_rejects_cancellation_replacement_and_access_revocation tests/test_generations.py::test_public_api_readers_never_return_unpublished_snapshot_or_source tests/test_generations.py::test_final_commit_failure_or_lost_acknowledgement_is_consistent --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\pt-continuity-current --junitxml=C:\Users\SAIKRI~1\AppData\Local\Temp\pt-continuity-current.xml` — **54 passed, 0 failed/errors/skipped**, one Starlette/httpx deprecation warning, **227.97 seconds**. This includes 14 new continuity cases and actual private-stage interruptions after CLAIMS/CORRELATION, replay with the original BASE, duplicate delivery, explicit-BASE/legacy-caller behavior, tenant denial and selected existing publication/cancellation/revocation/visibility/commit-failure tests.
- The earlier broader command added the complete `tests/test_generations.py` selection to the continuity/public/configuration/Engineering Changes tests, using `--basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\pt-continuity-final` and its matching JUnit path. It completed **78 passed, 1 failed**, one warning, 716.60 seconds. All 34 generation cases passed at that intermediate source state. The failure was a defensive fixture attempting an illegal cross-tenant inventory write; the existing ORM guard correctly rejected it. The fixture was corrected by creating a valid foreign repository/inventory, then testing rejection at the comparison boundary. The final current-source 54-test result supersedes that fixture failure. This is not reported as a full 34-test current-source generation rerun.
- Initial failures retained: fixture tuple-return misuse before the product reproduction; missing claim predecessor in the real historical/modern comparison; an in-session tuple versus persisted JSON-list equality fixture issue; the invalid foreign-inventory setup; and the separately reproduced new consistency-finding identity. No guard, assertion or expected production verdict was weakened to resolve them. Intermediate 43-, 46-, and 54-pass reports are retained and are not added together as unique coverage.
- From `frontend/`: `npm run test -- --reporter=json --outputFile=test-results/legacy-continuity-unit-20261031.json` — **53 passed, 0 failed/pending**. New component coverage verifies literal prefixed/percent-containing paths and the original evidence inspection ID. `npm run build` — exit 0, TypeScript compilation passed, 42 public routes prerendered.
- Browser environment: `PROJECTTRACE_E2E_ISOLATED_API=1`, `PROJECTTRACE_PYTHON` set to the executable above, Vite on 127.0.0.1:5181 and the existing disposable owned API fixture on 8011. With `PROJECTTRACE_E2E_RESULTS=test-results/legacy-continuity-browser-20261031/results.json`, `npx playwright test e2e/configuration-drift.spec.ts e2e/public-base.spec.ts --output=test-results/legacy-continuity-browser-20261031` — **2 passed, 0 failed/skipped**, 41.0 seconds. These cover real API documentation/configuration drift and the mocked public-provider UI/failure fixture. Historical-path presentation is covered by the component test; these browser results are not a live public-GitHub or historical-provider browser qualification.
- `ruff check backend/public_snapshot_paths.py backend/domain.py backend/snapshot_context.py backend/engineering_changes.py tests/test_public_snapshot_continuity.py tests/test_public_github.py`, the matching `python -m py_compile` selection, and `git diff --check` — exit 0. Ruff is the sibling executable in the Python environment above.
- Read-only post-test SQLite checks on both direction fixtures used `mode=ro&immutable=1`: each retains four PUBLISHED generations, one published pointer, integrity `ok` and zero foreign-key violations. Unchanged and evidence-changed HEADs contain zero false CLAIM_REMOVED records. The tests verify genuine removal/addition, retained BASE snapshot data and original document ID/path/hash citations.

Evidence: `docs/evidence/COMMERCIAL_V1_LEGACY_CONTINUITY_20261031.json` contains source hashes, individual backend outcomes, frontend/browser summary and publication/integrity checks. `docs/evidence/COMMERCIAL_V1_LEGACY_CONTINUITY_20261031_RAW.json.gz` retains the raw owned JUnit reports (including failures) and frontend/browser reports. No databases, encrypted source blobs or keys were added to the repository.

### Remaining gates and next task

NOT_RUN: current-tree Linux parser/Docker SEC-002 requalification, live GitHub provider/browser qualification, PostgreSQL/Redis/Celery acceptance for this delta, full constrained SCALE-001 workload and full Commercial V1 release matrix. Earlier Linux/Docker passes remain scoped to the older source digest. Unknown provenance, shortened/legacy.zip roots and repository-rename equivalence are conservatively unresolved rather than auto-migrated. Comprehensive native finding and quality-metric history continuity across this boundary remains unqualified; the confirmed related documentation-consistency finding is covered, not arbitrary vendor/native issue equivalence.

Next smallest milestone: extend the same owned legacy/modern corpus to native finding and quality-history classification, reproduce any actual mismatch before changing those matchers, and then qualify the exact consolidated source under Linux isolation/Docker. No generic scanner, history rewrite, rejected graph/checkpoint prototype or resource-policy change is authorized by this result.


## 2026-10-31 — Native finding and quality-history continuity

Status: **DEVELOPMENT IN PROGRESS**. **SCALE-001 — NOT QUALIFIED.** Branch and HEAD remain `codex/scale-001-local-continuation` / `9e21509591bfa5457cc829ebd5637f95be68d573`. Earlier dirty work is preserved. This is a bounded local product-correctness milestone, not Linux, live-provider, performance or release qualification.

### Reproduced defects

The initial owned persisted-snapshot selection failed **12/12 tests**: ten native identity comparisons reset logical identities across full-SHA codeload roots versus repository-relative paths, and two Engineering Changes comparisons concealed real cyclomatic regressions. Identical bodies in different nested files prevented the existing unique-file-rename fallback from correcting raw-path mismatches. Native structural reconciliation, history movement checks, quality metric comparison and Engineering Changes each compared raw paths independently.

A separate malformed-provenance reproduction failed **1/1**: conservative history events did not prevent the quality gate from returning PASS. Read-only inspection of the mixed-root fixture additionally found quality delta counters `ANALYZER_BASELINE:1, EXISTING:1` while both published quality findings were `ANALYZER_BASELINE`; counters had been captured before final normalization. Two new interruption reproductions failed **2/2**: restored CORRELATION lost the published unresolved-history warning, and restored POLICY incorrectly published COMPLETED instead of PARTIAL. These are retained failures, not skipped qualification gates.

### Changes and contracts

- `backend/finding_history.py` reuses scoped public-snapshot path equivalence at reconciliation and lifecycle projection. Keys include canonical full path, rule and supported structural identity; every ancestor obtains its own scoped resolver. A layout-only change emits SEEN while actual movement, supporting-context changes, resolution, introduction and reopening retain existing semantics. Unsupported schemas, ambiguous identities and unproven layouts produce NOT_OBSERVED rather than invented introduction/resolution.
- `backend/public_snapshot_paths.py` validates public repository/full-SHA provenance before trusting a repository-relative marker. It does not decode URLs, match basenames or rewrite stored paths. Existing tenant/repository inventory checks are retained.
- `backend/domain.py` preserves confirmed native predecessor/concept identity, invalidates review context for real evidence/severity changes, and marks unresolved findings with the existing ANALYZER_BASELINE delta plus additive `identity_resolution`. Quality counters are recomputed after final normalization. On replay, unresolved-history warnings are reconstructed from the saved comparison state; final snapshot warnings use the current list. Receipt formats, admission rules and security/resource budgets are unchanged.
- `backend/quality_domain.py` and `backend/engineering_changes.py` compare metrics in their proven BASE/HEAD namespaces. Reopened quality findings follow confirmed ancestor matches. Unknown history cannot count as verified NEW/resolved or silently pass the quality policy.
- `analyzers/code_quality/core.py`, `backend/quality_api.py` and `frontend/src/CodeQuality.tsx` add a REVIEW_REQUIRED comparison-identity condition and an additive overview flag/alert. Parsing may be COMPLETE while finding introductions/resolutions remain unverified. Existing verdict/status vocabularies, source-evidence classifications and authorization are preserved.

No historical paths, fingerprints, evidence IDs, source hashes or snapshot data are rewritten. BASE immutability is asserted against the captured persisted snapshot. Transient finding/metric comparison indexes remain O(captured findings/metrics), under existing guards; no bounded full-workload memory claim is inferred. No schema, migration, parser-security, encryption, checkpoint-admission or limit change was made by this milestone.

### Coverage and scope

New persisted tests cover both legacy-to-modern and modern-to-legacy comparisons with identical basenames and identical bodies in distinct directories: Python mutable defaults (PT-QUALITY-011), Java empty catch (PT-QUALITY-006), JavaScript/TypeScript eval (PT-SAST-005), Python shell invocation (PT-SAST-002), synthetic Python credentials (PT-SECRET-001), Compose privileged containers (PT-IAC-001), and Dockerfile root users (PT-IAC-002). Incidental existing IAC rules can also appear in these fixtures; this is not qualification of the entire native registry.

Additional coverage includes true additions/resolutions/context changes, severity override, ancestor reopen, real metric regression, invalid/missing provenance, mixed roots, ambiguous statements, unsupported identity schemas, actual history/quality/source APIs, cross-tenant denial, private CORRELATION/POLICY interruption, duplicate delivery and selected existing publication/cancellation/access-revocation/commit-failure guards. Historical source citations retain literal old paths. New tests are in `tests/test_native_snapshot_continuity.py`, `tests/test_native_history_uncertain_layouts.py`, `tests/test_native_history_recovery.py`, `frontend/src/QualityHistory.test.tsx` and `frontend/e2e/native-history.spec.ts`.

The browser native-history fixture uses real owned API analysis/history and a deliberately controlled overview response to exercise unresolved-history presentation. It does not claim live GitHub or legacy-provider browser qualification. External CLOUD/SCA/LICENSE findings, arbitrary vendor schemas, all remaining native rule variants, repository rename equivalence and cross-version in-flight semantic receipt upgrades remain unqualified. Unknown layout/schema identity remains conservatively unresolved, not automatically migrated.


### Executed validation and source attribution

Python executable: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe`; Ruff is the sibling `ruff.exe`. Backend commands ran from the repository root. The 13 milestone implementation/test hashes recorded before the final run match afterward. The receipt preserves the previous pre-replay manifest separately.

- **Final current-source backend: 59 passed, 0 failed/errors/skipped**, one Starlette/httpx deprecation warning, **665.75 seconds**, exit 0. This includes all 31 new native/uncertain-layout/recovery cases, existing public-claim continuity, quality-spill and selected generation publication/cancellation/access-revocation/visibility/commit-failure cases. Exact command:

  `& "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\.venv\Scripts\python.exe" -m pytest -q tests/test_native_snapshot_continuity.py tests/test_native_history_uncertain_layouts.py tests/test_native_history_recovery.py tests/test_public_snapshot_continuity.py tests/test_quality_spill.py tests/test_generations.py::test_final_promotion_rejects_cancellation_replacement_and_access_revocation tests/test_generations.py::test_public_api_readers_never_return_unpublished_snapshot_or_source tests/test_generations.py::test_final_commit_failure_or_lost_acknowledgement_is_consistent --basetemp C:\Users\SAIKRI~1\AppData\Local\Temp\pt-native-current --junitxml=C:\Users\SAIKRI~1\AppData\Local\Temp\pt-native-current.xml`

- **Broader intermediate backend: 101 passed, 0 failed/skipped**, one warning, 647.58 seconds. That selection additionally covered all public-GitHub, finding-identity, configuration-drift and Engineering Changes cases plus selected existing quality-history/API tests. It preceded the final counter and replay-warning fixes; it is not reported as 101 current-source passes. Its complete command and individual outcomes are retained in the receipt. The intermediate 57-pass result preceded the replay fix and is likewise kept distinct. Counts from overlapping selections are not added together.
- The final focused replay rerun passed **2/2**, 12.77 seconds by JUnit, before being included again in the final 59-case selection. Original 12-case, unknown-provenance and two replay failures remain in the raw bundle. The complete shell invocations for every early intermediate reproduction were not separately retained; their exact JUnit case identities, outcomes, failure text and durations are available. No unavailable invocation is fabricated.
- Frontend, from `frontend/`: `npm run test -- --reporter=json --outputFile=test-results/native-history-unit-20261031.json` — **54 passed, 0 failed/pending**. `npm run build` — exit 0, TypeScript compiled, **42 routes prerendered**. Frontend source is unchanged since those executions.
- Chromium, from `frontend/`, with `PROJECTTRACE_E2E_ISOLATED_API=1`, `PROJECTTRACE_PYTHON` set to the executable above and `PROJECTTRACE_E2E_RESULTS=test-results/native-history-browser-20261031/results.json`: `npx playwright test e2e/native-history.spec.ts e2e/configuration-drift.spec.ts --output=test-results/native-history-browser-20261031` — **2 passed, 0 failed/skipped**, 69.60 seconds report duration. This used the owned disposable API/database fixture and Vite on 127.0.0.1:5181. It preceded the backend-only final counter/replay fixes. The native browser test verifies real API baseline/history continuity and deliberately controlled unresolved-overview presentation; configuration drift uses the existing real API fixture. No live provider or legacy-provider browser pass is claimed.
- `ruff check analyzers/code_quality/core.py backend/public_snapshot_paths.py backend/finding_history.py backend/domain.py backend/quality_domain.py backend/engineering_changes.py backend/quality_api.py tests/test_native_snapshot_continuity.py tests/test_native_history_uncertain_layouts.py tests/test_native_history_recovery.py`, matching `python -m py_compile`, and `git diff --check` — exit 0.
- Post-test read-only SQLite checks (`mode=ro&immutable=1`) passed for **45 owned fixture databases**: integrity `ok`, zero FK violations and zero invalid published pointers. **82 published snapshot quality-counter comparisons** matched the actual final finding deltas; **16 unchanged native layout-direction fixtures** retained equivalent numerical metric values under canonical paths. Complete per-fixture state/count/hash summaries are in the receipt. Intentional STAGING/ABANDONED generations in failure tests remain private and are not counted as publication failures. These are disposable local test databases; no original database or production migration was modified.

Receipt: `docs/evidence/COMMERCIAL_V1_NATIVE_QUALITY_CONTINUITY_20261031.json`. Raw owned JUnit reports, including failures, frontend/browser reports and database-check summaries: `docs/evidence/COMMERCIAL_V1_NATIVE_QUALITY_CONTINUITY_20261031_RAW.json.gz`. No database files, encrypted source blobs or keys are included.

### Remaining gates and exact next milestone

**VERIFIED:** the owned persisted continuity, actual-change, uncertainty, API/tenant and replay/publication scopes above; current final backend selection and unchanged frontend-source checks. **FAILED current selected tests:** none. The earlier defects are recorded as corrected reproductions, not erased. **NOT_RUN:** current-tree Linux parser/worker and Docker SEC-002 requalification; live GitHub/provider and historical-provider browser workflow; real PostgreSQL/Redis/Celery acceptance for this delta; external vendor/native-registry completeness; cross-version in-flight semantic receipt upgrade; full Commercial V1 corpus/release matrix and constrained SCALE-001 qualification. Historical Linux/Docker successes apply only to the older source digest, not this delta.

Next smallest milestone: establish a new complete source manifest for the consolidated dirty tree, create a verified isolated copy in the existing Linux environment, and rerun the required Linux parser/worker and SEC-002 container gates without committing or dispatching remote workflows. Then qualify a real public-GitHub explicit BASE/HEAD/native-history workflow with authorized live-provider evidence; owned or mocked fixtures are not a substitute. Unknown historical layouts/schemas remain explicit review cases. No new generic configuration scanner or rejected architecture prototype is needed.

No reset/clean/stash/branch switch, commit, push, PR action, remote workflow, deployment, production migration or resource-policy change was performed. **Commercial V1 — DEVELOPMENT IN PROGRESS. SCALE-001 — NOT QUALIFIED.**


## 2026-11-02 — Authorized GitHub backup and laptop handoff

The owner explicitly authorized safe staging, commits and normal pushes of this existing continuation to `https://github.com/maninani12/ProjectTrace` on `codex/scale-001-local-continuation`. This supersedes earlier no-commit/no-push instructions only for this backup. Main/shared PR branches, force pushes, merges, deployments, production migrations and manual workflow dispatch remain excluded.

Initial actual HEAD was `9e21509591bfa5457cc829ebd5637f95be68d573`; fetched origin continuation had the same tip (ahead/behind 0/0). Original audit inventoried 692 tracked/safe-untracked files (41,775,839 bytes), including 26 modified tracked and 110 untracked files. Ignored inventory contained 10,411 files, predominantly dependencies, build/test outputs, caches and runtime storage. There were no nested repositories, submodules, symlinks or case collisions; largest project file was under 4 MB, so LFS was not required. These are pre-handoff-document counts, not final commit counts.

All relevant source, tests, migration 0026, CI, configuration templates, investigation/prototype code and safe receipts are retained. Existing rejected/opt-in experiments remain unqualified and are not adopted by committing the backup. The original dirty bytes are preserved locally; normal Git `core.autocrlf=true` text normalization can produce different blob hashes from historical Windows byte manifests. Historical source receipts are not rewritten or relabeled as evidence for a new Linux run.

New guide: [PROJECTTRACE_NEW_LAPTOP_HANDOFF.md](docs/PROJECTTRACE_NEW_LAPTOP_HANDOFF.md), including clone/setup/start/verification commands, migration and service requirements, environment names, source-scoped test history, qualification limits and local-only artifacts. Selected original Linux/SEC-002 receipts are copied into a portable evidence bundle after secret inspection; the original WSL source/evidence directories remain intact. The precise final commit and remote confirmation are recorded by the documentation follow-up and migration receipt; no push success is assumed from local commit creation.

Executed for this backup: repository/remote/ignored-file inventory, archive-aware focused secret checks, `ruff check backend analyzers integrations workers tests scripts integration_tests` (pass), `python -m compileall -q backend analyzers integrations workers scripts tests integration_tests` (pass), `python -m alembic heads` (0026), and whitespace/staged-completeness/remote checks. No long pytest suite, dependency upgrade, original-database migration, current Linux/Docker gate or full workload was rerun. Latest 59/54/2 backend/frontend/browser results remain their dated historical source evidence, not tests newly executed for the handoff. A local scanner attempt with a slow unconstrained identifier expression was stopped and restarted with bounded matching; no source or evidence was discarded.

Existing databases, encrypted source/blobs/uploads, input and provider keys, operator settings, virtualenvs, caches, generated frontend/browser artifacts, original raw profiling databases and WSL image/source environments are excluded from Git and remain on the old laptop. A separate consistent encrypted recovery-set transfer is necessary to move existing application users/history. GitHub code continuity is not an application-data backup. Nothing excluded was deleted.

**Commercial V1 — DEVELOPMENT IN PROGRESS. SCALE-001 — NOT QUALIFIED.** Next engineering milestone remains a new complete source manifest and real Linux required-worker/SEC-002 requalification, then live provider and distributed/service acceptance. Normal push-triggered CI may run automatically; no workflow is manually dispatched for this backup.

Staged whitespace check initially failed on seven pre-existing untracked files. Original bytes were retained in the local audit folder; six Markdown reports use equivalent backslash hard breaks and redundant EOF blank lines were removed, including one test-file EOF. No application logic changed. The handoff receipt records before/after hashes and the final rerun.

Source consolidation commit: `effb91c209e3841a90683d20b1d8d9e726d4357b` (113 files added, 27 modified, 0 deleted relative to the pre-backup HEAD). A documentation-only follow-up records this SHA and the guide; both commits are pushed together once to avoid duplicate push-triggered runs. Final remote-tip confirmation is recorded outside the self-referencing commit in the migration receipt/chat. All 695 safe project files are tracked; application source remains as preserved by the consolidation.

## 2026-11-02 — New-laptop runtime finalization (uncommitted local delta)

Imported branch/HEAD: `codex/scale-001-local-continuation` / `e2afa09ccfd45f8a7551b5ed8b2868d6297c299e`. All 695 tracked files initially matched the restore manifest. The original restricted sandbox denied Windows CIM inspection; inspection works under the current Windows user. Existing API/Vite identities were recovered using the unchanged PID/creation-time/command verifier. The original Vite process belonged to the earlier sandbox account, and PowerShell Stop-Process without Force raised NullReferenceException. No elevation, Force option or OS-policy change was used.

The local development controller now requests Vite shutdown through an operator-owned PID-matched file, analogous to the existing graceful API stop. A development-only Vite plugin closes the server before exiting; production builds and Vitest mode do not install its watcher. The controller validates the project process identity and watcher before draining the API, retains registration on timeout, and does not invoke process termination. Vite's supported config reload installed the watcher into the original running server. Actual managed stop freed both ports and removed the old record; restart recreated verified API/UI identities and passed API/database/local-runner and UI-proxy readiness. Existing data was preserved; a consistent pre-finalization SQLite backup remains outside tracked source. Browser smoke creates only labeled synthetic tenants in this fresh local installation.

Local final checks: 13 backend passed (4 focused controller regressions + 9 configuration-drift), 54 frontend unit tests passed, one real-Vite shutdown integration passed, and two Chromium tests cover documentation drift and explicit BASE/provider-failure presentation. The provider projection/failure is mocked, so this is not live GitHub qualification. Ruff, compilation, TypeScript/build (42 routes), Git whitespace and SQLite integrity/FK checks passed. Exact final results and source hashes are in the enclosing restore chat's `outputs/RESTORE_FINALIZATION_REPORT.md` and accompanying JSON/XML artifacts. One initial Node test harness expected a route installed behind Vite's terminal middleware; its liveness assertion was corrected, and the real shutdown test passed. No application failure was hidden.

At the latest CI snapshot, imported-commit parser-isolation, broker-recovery and browser jobs succeeded; validate and constrained candidate remain pending. Constrained baseline failed in full-workload execution with outer exit 1. Logs/artifact downloads require authenticated GitHub access (403/401); the current credential helper supplies none. Current-run OOM/checkpoint/sanitizer attribution and exact inner assertion remain unverified. Historical baseline OOM, candidate GLOBAL_CHECKPOINT_BUDGET and separate sanitizer-limit failures are comparison evidence only. No workflows were dispatched or rerun, and no full workload was launched locally.

This authorized local runtime fix is uncommitted; no push, merge, production migration, parser/tenant policy, resource-budget or lockfile change occurred. Current remote CI is not qualification of this local delta. Commercial V1 remains DEVELOPMENT IN PROGRESS; SCALE-001 remains NOT QUALIFIED. Next smallest step is authenticated read-only retrieval of final CI receipts, followed by exact-source Linux/SEC-002 qualification of the revised manifest.

## 2026-11-02 — Authenticated imported-commit CI triage

User-approved GitHub CLI device login succeeded with system-keyring storage. Authenticated read-only retrieval established final outcomes for exact imported commit `e2afa09ccfd45f8a7551b5ed8b2868d6297c299e`. All six complete job logs and six artifact ZIPs were retained locally; independently computed ZIP hashes match GitHub's published digests. The enclosing chat's `outputs/CI_FAILURE_TRIAGE_20261102.md`, `outputs/github-ci.json` and `outputs/ci-triage-20261102/` contain timestamps, exact excerpts, hashes, classifications and limitations. No application code or existing runtime fix was changed in this triage; only release/progress documentation is appended.

Regression run 41429161579 completed FAILURE: broker-recovery job 125223102234, browser 125223102491 and parser-isolation 125223102584 succeeded; validate 125223102616 failed at pytest, exit 1, with **1075 passed, 6 failed, 72 skipped, 0 errors**. Failures are a historical git-show precondition against a depth-1 checkout, an LF/CRLF-sensitive historical receipt digest, three export-profile process-peak assertions (415477760/415477760/434118656 versus 190000000), and stale PostgreSQL migration-head expectation 0025 versus actual 0026. The first two export profiles already report the failed high-water value before export. These do not establish an export-allocation regression or loss of PostgreSQL records. Classification: Other verified failure (mixed CI/test preconditions and acceptance assertions); detailed attribution remains bounded by retained evidence.

Constrained run 41429161593 completed FAILURE. Baseline job 125223103299 is a **verified resource/OOM failure**: artifact 13134327416 (`scale-full-baseline-41429161593`, ZIP SHA-256 `702a4b635de95711ea01bed767409fd1ff18b9ed771a5252d80dc3f9922737f7`) records main container exit 137, OOMKilled true, kernel memory peak 768000000, zero swap, oom=2/oom_kill=2; last application sample is ANALYZING at 770.739s. The host wrapper exits 1. This independently reproduces the older baseline OOM category, rather than inferring it from history.

Candidate job 125223102927 is **Other verified failure: configured analysis-time-budget timeout**. Artifact 13136111081 (`scale-full-candidate-41429161593`, ZIP SHA-256 `a9434eaa108ae23a2c05e381fd39e18d4fe5ca57a344e3eb681ec9148550b00a`) records TimeoutError at ANALYZING, durable job error ANALYSIS_TIME_BUDGET, 1808.034993s ANALYZING under the existing 1800-second guard, container exit 1/OOMKilled false, oom=0/oom_kill=0 and peak 768000000. It fails before the older candidate's VERIFYING/global-checkpoint rejection; neither a current checkpoint nor sanitizer rejection is established. Current container Python 3.14.10 differs from historical 3.14.9, so no single-change causal performance regression is claimed.

Both constrained post-exit receipts have SQLite integrity ok, zero FK violations and zero published generations/pointers. Baseline terminal cleanup is interrupted by OOM; candidate cold FAILED; later scenarios remain NOT_RUN. No fresh-worker recovery or complete SCALE-001 acceptance follows. All resource, time, checkpoint, sanitizer, tenant and parser limits remain unchanged. No remote workflow was rerun/dispatched and no full workload was run locally. Current remote evidence does not certify the uncommitted Windows runtime delta. Next smallest corrective milestone: repair the focused CI/test preconditions and validate Linux export measurement semantics without relaxing thresholds; then use bounded ANALYZING profiles before any authorized full qualification. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


## 2026-11-02 — Bounded CI regression repair and analysis profiling

All 699 starting files and dirty changes were preserved externally; branch/HEAD remain codex/scale-001-local-continuation / e2afa09ccfd45f8a7551b5ed8b2868d6297c299e. All pre-existing Windows lifecycle code/tests remain byte-identical. No commit/push/dispatch or full constrained run occurred.

Corrections: validate checkout now retains history for the pinned serializer (depth-1 failure and exact complete-history source digest were independently reproduced in a disposable bare object store); a new dated LF/CRLF provenance record binds both exact digests without changing historical receipts or manifests; migration acceptance compares actual revisions to Alembic heads, preserving successful migration/record assertions. The stale PostgreSQL 0025 assertion was reproduced against a fresh isolated PostgreSQL 17.11 cluster before correction. The test cluster was stopped afterward; no application database was migrated by tests.

Unix ru_maxrss was mislabeled as current RSS. VmRSS/current and VmHWM/address-space peak are now separate from retained getrusage peak, with explicit units/source/scope. Export probes capture before/during/after process counters; the 190000000-byte ceiling remains and requires kernel high-water availability. Missing Windows or namespace counters remain unavailable, not fabricated zero. Synthetic tests verify labels, units, missing-versus-zero and owner/child attribution. Corrected Linux export execution is NOT_RUN on this Windows laptop.

Local outcomes (overlapping selections, not summed): six focused cases 6 passed/0 failed/0 skipped/2 warnings; surrounding selection 127 passed/0 failed/0 skipped/2 warnings; final missing-CPU refinement selection 17 passed/0 failed/0 skipped/2 warnings; final immutable-provenance selection 7 passed/0 failed/0 skipped/1 warning. Ruff and compilation pass. No frontend behavior changed. Exact commands, measurements, warnings and hashes: docs/evidence/CI_REGRESSION_REPAIR_ANALYSIS_PROFILE_20261102.json and the enclosing chat's outputs/ci-repair-20261102/.

Remote candidate cost: PARTITION_PARSE 1658.306790s / ANALYZING 1808.034993s (91.72%), 180 partitions; OBSERVATION_SPILL 97.147434s; CACHE_WRITE 43.972884s; CACHE_LOOKUP 0.305198s. Nested syntax/native transport and packet validation overlap these costs and must not be summed. Claims/global graph/verification/global checkpoint/publication were not reached. The operation journal has zero rows because its probe excludes ANALYZING, not because operations cost zero. No causal N+1, allocation regression or memory-to-CPU tradeoff was proved.

A bounded 48-file owned Python/JS/TS/Java Windows fixture completed cold/warm/one-change analyses with cProfile and actual CPU/RSS/I/O/SQL observations. Before wall 11.653218/9.699081/11.150864s; final 10.869245/10.191189/9.732916s. SQL counts 8091/8045/8355 and findings/graph counts match between sources; parser cache hits 0/48/47, misses 48/0/1. These single profiled runs do not prove speedup or Linux equivalence. Small packet-gate probes retain independent observation/cache projections and existing budgets. No production analysis optimization or rejected prototype was adopted.

Next smallest milestone: authorized bounded Linux execution of the affected tests and labeled telemetry, then representative packet decode/privacy profiling before any source-specific optimization. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED. Existing 768000000-byte/zero-swap/1800-second/64000000-byte checkpoint/1000000-node guards and CP-B/SP-B policy boundaries are unchanged.


## 2026-11-02 — Linux availability and bounded host partition profiling

Two separate outcomes: A, Linux validation BLOCKED/NOT_RUN; B, Windows host substage profiling completed, required Linux worker/startup/security profiling still unavailable. WSL is not installed; no Docker/Podman engine or configured SSH host was found; Codespaces inspection returned HTTP 403 requiring unapproved codespace scope. No host feature, administrator setting, account permission or workflow was changed. Required-mode preflight refuses the Windows host with LINUX_REQUIRED. No Linux case or Landlock/seccomp/Docker probe was represented as passed/skipped.

All 703 input files were copied byte-exactly into a new safe snapshot. Before/after profiling deterministic tree SHA-256: 9f5e40f6703b91809b5c4e3847c57d2986d8a93ad139c9bc81b9ce6f31b2359d. Every path/size/hash and raw LF/CRLF count is recorded outside tracked source. A byte-verified source tar and verified history-only Git bundle prepare the same dirty source for a future authorized Linux copy; no Linux transfer/parity is claimed. Documentation/evidence added afterward is a separate, untested full-tree manifest; executable source remains identical.

Actual existing parser functions generated bounded owned Python/JS/TS/Java/Terraform/Compose/Markdown observations, emitted the real packet format and passed the parent decode/expand/privacy gate. Three repetitions each of 7-file/4-function and 28-file/12-function fixtures retain semantic fingerprints and independent observation/cache copies. Median host parent protocol time: 0.0064608s / 0.0612525s. Development helper syntax/IaC roundtrips dominate this small Windows fixture; minimal valid controls measure combined startup/import/minimal-parse/pipe/teardown, not isolated Linux startup. Native Linux invocation, kernel denials, real repository-read/DB waits and Linux child allocations remain unavailable. No redundant decode was observed: one decode/metadata call per native packet; duplicated logical projections are required by independent copies and node accounting.

Host portable protocol/privacy and instrumentation correctness selection: 26 passed, 0 failed/errors/skipped, 1 warning. These are not a substitute for the six corrected Linux cases or required security selections. Allocation/cProfile diagnostic runs are separate from normal timing repetitions; only counts/metrics/hashes were exported, no raw packets/source/credentials. An exploratory empty IaC control was rejected by its existing admission guard, retained, then corrected to a minimal valid one-file fixture without changing the guard.

No production optimization or source/test/CI change was implemented. All earlier dirty fixes and historical receipts are preserved; only this dated documentation/receipt is added to the checkout. Detailed commands, counters, environment, exact manifests, blocked Linux selections and remaining unknowns are in docs/evidence/LINUX_VALIDATION_BLOCKED_PARTITION_HOST_PROFILE_20261102.json and the enclosing chat's outputs/linux-partition-20261102/. Next milestone: obtain an explicitly authorized Linux runtime, verify the prepared source, then run exact affected tests and required denial probes before attributing the Linux bottleneck. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED; all existing limits and isolation/publication policies are unchanged.


## 2026-11-02 — Approved WSL installation; Windows restart required

After explicit user approval for WSL2/Ubuntu 24.04, the official Microsoft command `wsl.exe --install --no-distribution --web-download` ran through standard Windows UAC, exited 0, and installed WSL. The installer explicitly states: "Changes will not be effective until the system is rebooted." Recorded feature state is VirtualMachinePlatform=2 (enable pending), legacy WSL1 component=0 (disabled). No BIOS/boot/security-policy or account-permission changes were made; WSL1 was not enabled. No automatic reboot or cross-reboot continuation was configured.

Post-install `wsl --version` reports WSL 3.0.3.0 and packaged kernel 6.18.54.1-1; this is package inventory, not a running guest-kernel qualification. Status still reports WSL2 cannot start before pending feature activation. Do not infer a firmware defect from this pre-reboot message. No distribution is installed and no Ubuntu first launch occurred. Docker remains absent; its installation/integration is outside the WSL approval. No Docker Engine was installed inside a guest.

Both existing API/UI listeners (8011/5181) remained present with the same PIDs after installation. A private SQLite online backup passes integrity_check with zero foreign-key violations; original services, data, keys and dirty fixes were preserved. Actual branch/HEAD remain codex/scale-001-local-continuation / e2afa09ccfd45f8a7551b5ed8b2868d6297c299e.

The 704-file pre-install source tree SHA-256 4e80588936570a127a2bb20496fe41a237bc3b2a7f752cef4b437f068285e509 was captured byte-exactly and verified again after approval. This addendum changes three documentation files only; the final full-tree manifest/archive is separately recaptured in local outputs/linux-restore-20261102/final/. Neither capture was transferred to or tested on Linux. Historical 703-file Windows execution evidence remains unchanged.

Current-source Linux outcomes: six corrected regression cases NOT RUN; required parser/archive/lexical/repository/configuration security NOT RUN; Landlock/seccomp/no_new_privileges denials NOT RUN; Docker SEC-002 NOT RUN; native Linux worker profiling NOT RUN. No pytest selection executed during this setup milestone; no pass, failure, skip or warning count is claimed. Earlier Windows-only measurements and remote baseline OOM/candidate timeout retain their original scope. No production optimization, full SCALE-001 run, remote workflow dispatch, commit or push occurred. All memory/swap/time/checkpoint/sanitizer/security/tenant/publication limits remain unchanged.

Next action requires the user to restart Windows, then return to the same chat. Read the durable local outputs/linux-restore-20261102/SETUP_AND_RESUME.md and install receipts; recheck WSL readiness, boot time, actual Git/source hashes and application listeners. Within the existing explicit approval, install Ubuntu-24.04 in the original Windows account once WSL2 is ready, verify a new Linux copy against the final raw-byte manifest, then run bounded corrected regressions and real required-mode security acceptance before native profiling. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


## 2026-11-02 — Current-source Linux validation completed; Docker bootstrap blocked

After the approved Windows restart, Ubuntu 24.04.5 LTS was installed under WSL2. Actual guest kernel: 6.18.54.1-microsoft-standard-WSL2; Python 3.14.10 from a digest-verified official actions/python-versions Ubuntu24.04 x64 asset; all 94 active requirements.lock pins verified. A password-locked non-root guest qualification account (UID 1000) is now the default guest user; Windows account permissions were not changed. PostgreSQL 17.11 used a fresh private guest-only loopback fixture, preserving the Windows application database. The fixture's final control state is shut down.

The 704-file execution tree SHA-256 1f139df4d6a1e44cc87f5b409e5fa1b6beb3910e3d3e31930cac3d8fc40b221a was verified for exact paths, sizes and original file bytes on Windows and in the new isolated Linux copy before/after execution; complete pinned serializer history was imported without a network clone, checkout/reset or copied credentials. All existing runtime/CI/test fixes remained uncommitted and unchanged. These are new actual Linux results, separate from the older 703-file Windows execution evidence. This later append-only documentation version has a separate final manifest and is not mislabeled as the execution tree.

| Linux selection | Passed | Failed | Errors | Skipped | Warnings |
|---|---:|---:|---:|---:|---:|
| six-corrected | 6 | 0 | 0 | 0 | 5 |
| corrected-surrounding | 83 | 0 | 0 | 0 | 4 |
| parser-required | 18 | 0 | 0 | 0 | 0 |
| archive-required | 18 | 0 | 0 | 0 | 1 |
| lexical-required | 32 | 0 | 0 | 0 | 0 |
| repository-required | 13 | 0 | 0 | 0 | 1 |
| security-configuration | 33 | 0 | 0 | 0 | 1 |

Selections contain 203 case executions and 198 distinct JUnit case identities; overlapping selections are not additional unique coverage. Warnings are Starlette/httpx deprecation, existing Alembic path_separator deprecation and pytest record_property/xunit2 compatibility. No dependency or production code was changed to silence them. All six originally failing cases now pass locally on Linux; the old GitHub runs were not rerun or relabeled successful.

Required real workers demonstrate Landlock ABI 7, seccomp mode 2 and no_new_privileges=1; retained receipts assert filesystem/read/write/proc/metadata/O_PATH/exec/fork/network denials and absence of DATABASE_URL/ANALYSIS_INPUT_KEY from child environment. Required integration tests additionally exercise tenant isolation, worker CPU/memory/timeout/output/IPC failures and archive/lexical fail-closed behavior. Portable/unit security assertions are not substituted for those real integration denials.

The byte-identical prior 28-file owned fixture completed three real required-mode timing repetitions plus a separate allocation/cProfile diagnostic. Median total native-observation wall 1.479223s; parent CPU 0.130111s; all reaped worker CPU 1.558089s. Syntax roundtrip 0.142714s; IaC 1.044148s; native 0.141707s. Median native parent packet gate 0.052287s, including 28 decodes, expansions and privacy passes once each. Required/development observations and instrumented/uninstrumented required outputs match; input order and independent observation/cache objects are preserved. CPU/components overlap; do not sum as wall time. RSS sampling is a lower bound; allocations cover only instrumented parent Python, not native/child allocators. Startup-to-attestation includes imports, trusted grammar preparation, enforcement and denial probes. Windows development helper timings are a different platform/boundary. No production optimization or full-workload extrapolation is established.

Separate Docker approval included per-user WSL2 Desktop 4.97.0 and agreement acceptance. The official installer signature/digest was verified and installation exited 0, but engine bootstrap fails reading the installed docker-wsl-cli.iso.sha256 through its WSL-mounted Windows path. Windows sees the 64-byte sidecar; Ubuntu and docker-desktop report ENOENT for that path. One supported bounded restart failed; Desktop was stopped without reset/unregister/data removal. The immediate local container infrastructure failure is verified; its underlying path-visibility cause is unknown, and no checksum mismatch, firmware defect or application regression is inferred. Image build, image ID/base digests and SEC-002 container assertions are NOT RUN. No second Docker Engine, permission/security bypass or OS policy workaround was installed.

Evidence and exact commands: local outputs/linux-qualification-20261102/REPORT.md, linux/* logs/JUnit/denials, linux/native-profile.json, profile-summary.json, source manifests and docker-sec002.json. Windows API/UI were restored after reboot and remain ready. Existing 768000000-byte/zero-swap/1800-second/64000000-byte/1000000-node qualification policies are unchanged; these bounded WSL tests are not a constrained SCALE-001 container run. No commit, push, remote workflow dispatch, production acceptance or live GitHub success is claimed. Next smallest milestone: repair the verified Docker Desktop Windows-to-WSL resource-path visibility, then execute the unchanged SEC-002 build/probe. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


## 2026-11-03 — Docker bootstrap repaired; current-source SEC-002 PASS

Docker's failed apparent per-user installation was captured in the Codex MSIX package's private AppData/registry view. Native file handles resolved the apparent resource path to the package LocalCache; WSL returned ENOENT for the apparent path and read the physical package-cache sidecar with the identical SHA-256. The ISO itself matched its unchanged sidecar, excluding the suspected corruption/checksum mismatch. This was an independently verified logical/physical installation-path mismatch, not a firmware or application-parser regression.

Approved bounded repairs retained all data/configuration backups: an elevated native-path guard aborted without installing because its view was still redirected; an approved custom-location official-installer attempt exited -5 because its path must match the existing registration. One explicitly approved on-demand task then ran as the same non-admin interactive user. Its fresh view had no real install/file/registration at the expected path. The same verified Docker Inc-signed 4.97.0 installer exited 0 and established the real per-user installation. Post-install native handles resolved to normal AppData, and Windows/Ubuntu could both read it. Only that completed temporary task was removed. No uninstall/reset/purge/Windows service/feature/security-policy/mount/checksum bypass or competing Ubuntu Engine was used; the original shadow copy and both verified VHD backups remain preserved.

Supported Docker Settings UI applied one explicit Ubuntu-24.04 integration selection. Earlier manual file edits had targeted the inactive configuration view and were restored; earlier alias/name hypotheses are superseded by the verified view mismatch. The UI-persisted IntegratedWslDistros value was verified and aligned in both views for consistent future starts, preserving unrelated settings. Windows desktop-linux and Ubuntu default contexts reach the same Linux/amd64 Engine 29.9.2, ID e3ebaa0b-7243-40e6-8ec3-aaddda8b2fcc; Ubuntu CLI is supplied by Desktop integration.

The exact 704-file Docker execution/build tree SHA-256 is 38b4e502d3bd1a3e6a7800080103c3004a844795cce976102e4984db9ce992d6; Windows/Linux paths, sizes and original byte hashes matched before/after build and probes. The earlier 1f139df4d6a1e44cc87f5b409e5fa1b6beb3910e3d3e31930cac3d8fc40b221a Linux test tree differs only in the three previously recorded documentation edits. This new append-only documentation version has a separate final manifest. All executable/CI/test/runtime-fix files remain unchanged and uncommitted on e2afa09ccfd45f8a7551b5ed8b2868d6297c299e / codex/scale-001-local-continuation.

Exact CI Docker build and unchanged scripts.parser_isolation_probe succeeded. Docker API image ID (OCI index descriptor) is sha256:4b43c5f01dc36f7ab325f485e9f8c8f1f2a4a0b6b2d0b26ece9994d0e94a81f9; built linux/amd64 manifest sha256:8fd99380518b72a44d7e16d6e431f2daa5ffb0ec2ea0ba460e983b7c71897c50; image config sha256:64c688f143389248711f4b31c92954450d3d3c822ce70a21d2866ee891ac774a. Python 3.14-slim base index sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966; linux/amd64 base manifest sha256:ec6a14df5b63e3fbb3498e3240f7f640c230f9dca67683d23265db3866697f2d. The base's four rootfs layers match the built image prefix; image Python is 3.14.10 and USER is projecttrace/UID 10001.

SEC-002 PASS requires the successful build, existing probe and completed mandatory supplemental/inspect assertions. Observed outer UID/EUID 10001, effective capabilities 0, Seccomp=2, NoNewPrivs=1, kernel pids.max=64; root write EROFS=30; sentinel write denied errno 13 with inspected read-only mount. Read-only root, network none, all caps dropped, no-new-privileges, PID limit 64 and all filesystem/proc/metadata/O_PATH/exec/fork/network denials pass; both synthetic secret names are present in the parent and absent in parser children. One initial external supplemental helper failed at import before assertions because its /run entrypoint lacked /app on sys.path. Only that owned helper was corrected and rerun on the same immutable image; no image rebuild, app change or security relaxation occurred. The failed and both successful containers/logs are retained. CI --rm was omitted solely to honor the no-container-deletion restriction.

No previously passing Linux suite, 28-file profile, remote CI or full SCALE-001 workload was rerun. All original memory/swap/time/checkpoint/sanitizer and parser/tenant/publication limits remain unchanged. SEC-002 boundary acceptance does not establish full SCALE-001 resource/performance/recovery/publication qualification or live GitHub success. Complete commands, logs, approval outcomes, hashes and restrictions: local outputs/docker-sec002-20261102/REPORT_20261103.md and linux/SEC002_FINAL_RESULT.json. Next smallest milestone: isolate trusted IaC grammar preparation versus enforcement/startup costs on bounded representative partitions under this exact qualified image before considering an optimization. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


## 2026-11-03 — Bounded IaC startup/grammar profiling complete; no production correction

Required-mode profiling used the unchanged retained 704-file source tree 38b4e502d3bd1a3e6a7800080103c3004a844795cce976102e4984db9ce992d6 and exact qualified image sha256:4b43c5f01dc36f7ab325f485e9f8c8f1f2a4a0b6b2d0b26ece9994d0e94a81f9. All 704 retained source files and all 194 Dockerfile-copied payload files verify unchanged. Existing uncommitted application/CI/test/runtime fixes remain preserved on e2afa09; later progress/release text has a separate final manifest.

Eight owned scenarios cover small/moderate Dockerfile and Compose, Terraform, invalid/unsupported input, synthetic privacy markers and a seven-file batch. Three fresh-coordinator samples and five repeated fresh workers per case distinguish process conditions without claiming cold disk or persistent worker state. Small-Dockerfile warm total medians: native1.116658s, restricted Docker2.203357s. Diagnostic preparation medians: native1.076687s, Docker2.120286s. Combined Landlock/seccomp setup is3.462ms/9.622ms; pure interpreter startup remains inseparable from helper/bootstrap imports. Batch Docker packet decode8.800ms and privacy2.611ms are much smaller than preparation.

Two HCL Lark.open calls occur per diagnostic IaC worker, including Dockerfile/Compose-only inputs. The installed python-hcl2 8.1.4 API uses _get_parser, while bootstrap assigns api.parser; installed source plus call counts prove that binding does not reuse the explicitly prepared grammar. A separate three-repetition follow-up measures Docker cache-disabled build890ms and second package-cache-requested build878ms. The image package cache is absent before/after; read/write attempts occur on its read-only filesystem. Native has a pre-existing cache and its second open is57ms. These environment/cache differences are not pure container overhead.

Main matrix184 IaC executions, follow-up6: all168 main and6 follow-up comparisons match uninstrumented controls, with ordering and synthetic-token exclusion. All8 cross-environment case identities match. Four plain/diagnostic real kernel-denial probes pass, including Landlock ABI7, seccomp2/nnp1 and child secret isolation. Docker inspect/runtime checks preserve UID10001, zero capabilities, network none, PID64, nnp and read-only root/sentinel/helper. Main and follow-up containers exit0/OOMKilled=false and are retained. Prototype helper failures are explicitly documented/excluded. These are harness executions, not a new pytest suite; the prior203 Linux executions and completed SEC-002 suite were not needlessly repeated.

No production optimization, new image, validated speedup or full SCALE-001 result is claimed. Stored remote baseline remains exit137/OOM at768000000 bytes/zero swap; candidate remains ANALYSIS_TIME_BUDGET at1808.034993s versus1800, with PARTITION_PARSE91.718733%. Remote IAC376 is a file-analysis count, not a worker-start count; remote preparation attribution remains unproved. Next smallest corrective milestone: test and repair the pinned HCL factory binding in a separately manifested candidate, verify one loader plus equivalent output/failures/privacy/order/limits, then qualify a new restricted image. Full report/raw evidence/commands: local outputs/iac-startup-20261103/REPORT_20261103.md. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED. All qualification caps, resource limits and publication/tenant rules remain unchanged; no commit/push/remote dispatch or full workload run occurred.


## 2026-11-03 — HCL prepared-parser correction passes bounded local qualification

The pinned python-hcl2 8.1.4 API uses internal _get_parser; the old api.parser assignment is unused. The focused old-source regression records the expected2-versus1 loader failure. The correction avoids private alias/global monkey patches: a fresh worker owns one cache-disabled trusted HCL grammar and passes an explicit callback using public parse/transform/serialize stages to both infrastructure HCL sites. Newline, serialization options, errors, ordering, identities and privacy behavior match the control in the tested surface; default third-party bindings and installed files remain unchanged.

Executed candidate704-file tree: bdcdf6e5cfb4e51dda47f74b1f8c9848f77d54f63bc401664d87820be4125d82. The only production byte differences copied into Docker are analyzers/isolated_worker.py and analyzers/infrastructure.py; integration_tests/test_parser_isolation.py adds the focused regressions to the existing required CI selection. All other701 pre-task source files match exactly before later documentation. Preserved qualified control source38b4e502d3bd1a3e6a7800080103c3004a844795cce976102e4984db9ce992d6 and imagesha256:4b43c5f01dc36f7ab325f485e9f8c8f1f2a4a0b6b2d0b26ece9994d0e94a81f9 remain untouched. Candidate tagprojecttrace-hcl-factory-candidate:20261103 resolves tosha256:5844e12de488849fc30492d0ef0f88cf8585312d381091eda8fd0c438f4c75bc; base index930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 is unchanged, with nine identical leading image layers and equal runtime/package versions.

Candidate Linux:161 distinct affected parser/IaC/archive/lexical/repository/security/privacy/identity cases pass, zero failures/errors/skips. Initial14 focused passes overlap the32-case parser selection, giving175 candidate case executions rather than175 distinct cases. Ruff/compilation pass. Candidate existing and supplemental SEC-002 container probes both exit0/OOMKilled=false and verify UID10001, capabilities0, seccomp2/nnp1, PID64, read-only root/sentinel, network none, Landlock ABI7 worker proofs, real filesystem/proc/metadata/O_PATH/exec/fork/network denials and child secret isolation. All original limits and policies remain unchanged.

New controlled comparison:332 owned fixture executions (316 main +16 large), nine main scenarios plus a169000-byte/1000-resource HCL case; control/candidate output identities match throughout. HCL opens are2→1 in32 contained diagnostic observations per subject. Fresh-coordinator n4 and repeated-fresh-worker n6 pairs alternate AB/BA; cache states are matched within each platform, with OS page cache uncontrolled. Repeated small-Dockerfile medians: native1.074981→0.993406s (paired median reduction5.84%); restricted Docker2.223121→1.337334s (39.91%). All50 ordinary small/moderate pairs per platform favor the candidate. One native large pair regresses1.773443→1.803892s (+1.72%); no reproducible native large speedup is claimed. Docker large improves in3/3 ordinary pairs. Sub-millisecond stage variation and all raw samples remain visible; no per-file/per-packet algorithmic speedup or full-analysis extrapolation is claimed.

Stored pinned workload manifest has no .tf/.tf.json names; Dockerfile/YAML/selected JSON still pays unconditional HCL startup. Remote artifact IAC376 counts file packets, not worker starts. Exact affected-worker frequency and aggregate savings remain unknown. Historical baseline OOM768000000 bytes/zero swap and candidate ANALYSIS_TIME_BUDGET1808.034993s versus1800 (PARTITION_PARSE91.718733%) remain unresolved full-scale evidence. Next smallest milestone: bounded IaC invocation/transport/preparation frequency and partition attribution before another full qualification decision. No full pinned workload, remote dispatch, commit/push/PR or deployment occurred.

Receipt:docs/evidence/HCL_PARSER_FACTORY_CORRECTION_20261103.json. Full report, commands, samples, JUnit, source/image identities and security receipts:local outputs/hcl-factory-20261103/REPORT_20261103.md. Later documentation/evidence-inclusive tree has a separate manifest; executable/test bytes remain identical to the candidate above. Existing uncommitted runtime/CI/telemetry fixes, original evidence, database and backups are preserved. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


## 2026-11-03 — HCL worker frequency and partition attribution completed

The bounded actual RepositoryFiles -> analyze_inventory path is measured on unchanged control704-file source38b4e502d3bd1a3e6a7800080103c3004a844795cce976102e4984db9ce992d6 and candidate704-file sourcebdcdf6e5cfb4e51dda47f74b1f8c9848f77d54f63bc401664d87820be4125d82, using the preserved control image4b43c5f01dc36f7ab325f485e9f8c8f1f2a4a0b6b2d0b26ece9994d0e94a81f9 and candidate5844e12de488849fc30492d0ef0f88cf8585312d381091eda8fd0c438f4c75bc. No production behavior, dependency, image or qualification limit changed. A–F owned cases measure0/1/1/1/2/1/4 cold IaC launches, with0 in all artifact-warm cases. Fresh workers process multiple completed file packets and terminate; typed artifacts, not workers, are reused. Direct diagnostic HCL opens remain2control versus1candidate per IaC worker, including Dockerfile/Compose-only input; other operations load0 HCL grammars.

Primary272 actual analysis calls pass control/candidate/mode/repetition/cold-warm semantic identity and synthetic privacy checks within each environment; an extra28 cross-environment calls match after normalizing only code_quality.parser_signature, whose full Python compiler/build input intentionally differs. Findings/order/evidence remain compared. Eight real denial probes and4 deliberate failure-propagation checks pass;1,760 observed/attributed worker proofs succeed. All70 primary Docker drivers exit0/OOMKilled=false under unchanged UID10001/read-only root+mounts/network none/cap-dropALL/nnp/PID64/required Landlock/seccomp boundary. These are harness executions, not additional pytest cases; prior175 executions/161 distinct test cases remain prior evidence.

Cold restricted Docker paired-median analysis savings are17.86–22.46% across the six IaC cases (n3 each); C mixed median4.837->3.996s, PARTITION_PARSE3.114->2.283s, IaC invocation2.244->1.379s. Native matched results are mixed/inconclusive; Docker D repetition2 regresses5.844s versus4.793s with several simultaneous operation slowdowns of unknown host cause. No-IaC and artifact-warm executions have no HCL cost. All slower pairs and instrumentation overhead are retained. The fixtures are bounded frequency/overhead cases, not full-scale memory/throughput acceptance.

Correction superseding the earlier native causal timing statement:27 valid candidate-only app bytecode caches predate the prior native comparison, while control has0. Source-only manifests and -B did not establish matching read-cache conditions. Earlier native1.074981->0.993406s/5.84% and50 favorable pairs remain raw observations but cannot be attributed exclusively to the HCL correction. The initial native matrix here is likewise excluded from causal timing. All caches/evidence remain intact; the matched rerun uses the already-existing byte-identical candidate build copy with0 app pyc, asserted before/after each run. Both immutable images also have0 app pyc. Direct grammar counts, semantic/test/security results and Docker evidence remain valid.

Historical run41429161593 at committed e2afa09 remains baseline OOM and candidate ANALYSIS_TIME_BUDGET1808.034993s/1800, with PARTITION_PARSE1658.306790s (91.718733%), no published generation. Its IAC376 counts completed files, not starts; missing inclusion/component/worker/preparation/cache telemetry prevents a full-workload HCL savings estimate. Local cold Docker materiality does not establish a fix for that timeout. Next smallest milestone: bounded representative native packet decode/expansion/privacy/reconciliation attribution; historical CONTAINED_NATIVE494.503276s includes packet validation226.605416s and transport265.378116s (nested scopes). No second optimization or full SCALE-001 rerun occurred. Existing dirty application/CI/test/runtime fixes, source copies, database and backups are preserved; no commit/push/dispatch/migration/deployment occurred. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.

Receipt:docs/evidence/HCL_WORKLOAD_FREQUENCY_PARTITION_ATTRIBUTION_20261103.json. Full local report/raw distributions/source/image/cache audits:outputs/partition-attribution-20261103/REPORT_20261103.md and summary.json. Final documentation-inclusive source manifest is separate from execution identity. Earlier evidence remains unchanged.
