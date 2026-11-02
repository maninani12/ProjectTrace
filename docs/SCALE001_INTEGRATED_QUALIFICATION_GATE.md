# SCALE-001 Integrated Qualification Gate

Assessment date: 2026-10-29\
Release status: **SCALE-001 NOT QUALIFIED**; **Commercial V1 DEVELOPMENT IN PROGRESS**

## Executive assessment

The authoritative checkout is still at the requested branch and HEAD. Its existing dirty work is intact. No product owner has explicitly selected a supported-input policy. The recommendation to retain the 1,000,000-node aggregate sanitizer limit is not approval; the limit and admission behavior remain unchanged.

Two independent full-workload blockers are evidenced on published code: the baseline Linux container was OOM-killed in ANALYZING; the candidate avoided an OOM kill, reached VERIFYING, then failed because the complete analysis checkpoint exceeded its unchanged 64,000,000-byte budget. Neither run published output. The candidate receipt did not measure the exact checkpoint size: actual is null. The owned 50k Windows snapshot fixture separately exceeds the sanitizer's node cap; it is not the same workload as the pinned OpenMetadata CI input.

The six graph-index/scalar failures belong to rejected, opt-in disposable prototypes. They are not active production regressions, but remain failed compatibility evidence and were not hidden or counted twice. No code change is justified here. The immediate blocker is the supported-input policy decision; the full candidate still needs a bounded checkpoint path and complete Linux publication/recovery evidence.

## 1. Checkout and preservation

| Item | Verified value |
|---|---|
| Repository root | C:\Users\sai krishna\Projects\ProjectTrace-local |
| Branch / HEAD | codex/scale-001-local-continuation / 9e21509591bfa5457cc829ebd5637f95be68d573 |
| Origin | https://github.com/maninani12/ProjectTrace.git |
| Worktree | Pre-existing modifications and untracked files remain. No reset, clean, branch switch, stash, commit, push, PR edit, main edit, or workflow dispatch occurred. The exact starting status is in the JSON companion. |

Hashes verified at review start:

| Artifact | SHA-256 |
|---|---|
| docs/PROJECTTRACE_POST_SERIALIZATION_REGRESSION_REPORT.md | abc9be35b2942961651c6963d1b4a165b7579c06054309e7c20eee6a9a03a6a5 |
| docs/evidence/PROJECTTRACE_POST_SERIALIZATION_REGRESSION.json | 7e012325a21e62538457fb45f1e5f8fc8fe3b8ea07114799193a1cf26e585b09 |
| docs/evidence/PROJECTTRACE_POST_SERIALIZATION_REGRESSION_RAW_20261029.tar.gz | 32773275b70e22b6568adc04b46e53dcdd7cd43fd7e705ce932245ea7d2dbaff |
| docs/SCALE001_SUPPORTED_INPUT_BOUNDARY_PROPOSAL.md | a4602efd9d91e0668ea4b274e599d8524405dc32b8adf6d8869b4cb38b7bdb2a |
| docs/adr/0007-bounded-published-snapshot-segments.md | d38f27bf16882d7095b03407966d5479bc8fb8c100e9fa684b33354f414ac45a |
| PROJECTTRACE_PROGRESS.md | 2993565b85e5526e88ae88e2b7bb65815344071dff4bf446d2e2bfd55161ada3 |
| docs/COMMERCIAL_V1_RELEASE_GATES.md | 1608016634ef1309579a3398717ddcb9e84e02cc8321be94ffbeabd5c4745b30 |

### Original database preservation

Each database was opened with SQLite URI mode=ro&immutable=1. Only SHA-256, PRAGMA integrity_check, and PRAGMA foreign_key_check were run.

| Fixture | Captured SHA-256 matches | Integrity | FK violations |
|---|---|---|---:|
| 10k | 465441f1dfd2c7d6ca3d7427c79dd55e57c350bee451b60a66b8e0e92f5a1d1b | ok | 0 |
| 147 | 97aeda34f1cb1b1d67784926c2140c3c27063585ae135fbb39e22643edce94d6 | ok | 0 |
| 30k | c7313fd66baa9e23ec5f5a7e9bdb8003554d086796c101be14f8d02d6ee5e9a4 | ok | 0 |
| prior | 14a15885488462c687ce2581807ea56ecb2145b98bc58d67f6e2aad3ba9a5627 | ok | 0 |

The deterministic set-serialization source state still matches its receipts: backend/generations.py SHA-256 9be789e551064d085c95f50b1b1273994db5b6f4f2fce5689c9ed1546a9d4594; tests/test_json_export.py SHA-256 46a2291ebccf9a3d75a41c38d44ffae29c2a9e6f5039648eb86f6f44a4c9fe2. Prior evidence records four focused tests passing in eight fresh processes: default and PYTHONHASHSEED 0, 1, 2, 3, 7, 17, and 42. This proves only serialization determinism, not graph compatibility or full workload qualification.

## 2. Supported-input policy gate

The aggregate cap remains **1,000,000 visited nodes per complete logical sanitizer call**. The owned 50k fixture contains **1,115,947 nodes**, 115,947 over the cap.

The historical owned Windows run took 455.638 seconds end to end (451.567 seconds to final sanitization). It had 50,000 metric rows and 336 findings; serialized snapshot size was 42,856,474 bytes; sampled process peak RSS was 303,468,544 bytes; metric spill was 51,820,828 ciphertext bytes. Sanitization failed after 17.250 seconds with ValueError: Sanitization structure budget exceeded. There was no snapshot ID or published pointer, SQLite integrity was ok, and FK violations were zero. The receipt records **one STAGING AnalysisGeneration row**. Thus “no generation row existed” would be inaccurate; evidence supports “no completed/published generation or pointer.”

This was a constructed owned fixture (complete 30k snapshot fields with full metric rows cycled to 50k), not the pinned OpenMetadata Linux workload. Snapshot SQL persistence, Generation.validate, and BASE/HEAD comparison were not reached. It was not rerun in this review.

| Option | Meaning | State |
|---|---|---|
| A | Keep 1,000,000 aggregate nodes and, after approval, define larger logical snapshots as unsupported. This does not qualify the demonstrated 50k fixture; if 50k is a release requirement, the owner must resolve that conflict. | Recommended provisionally; PENDING_PRODUCT_OWNER_APPROVAL |
| B | Authorize a formal policy amendment investigation. Define the target and aggregate semantics, then measure successful persistence, validation, comparison, concurrency, recovery, disk, CPU, and memory. Complete threat/resource review before selecting any admission rule. | Not authorized or implemented |

No actual product-owner approval was found in the proposal, ADR 0007, readiness report/receipts, progress history, release gates, or relevant evidence. “Review proposal first” is not approval. Do not derive a new cap by adding a margin to 1,115,947. Do not implement segments, page-local counters, or a guard change while the decision is pending.

The pinned workload's eventual snapshot node count is **unknown**: its candidate run failed at the global analysis-checkpoint stage before snapshot creation/sanitization. Do not substitute the constructed 50k fixture's count.
## 3. Experimental graph-candidate disposition

The corrected broad Windows backend run had **1,059 passed, 6 failed, 21 skipped, 1 deselected, 0 errors**. The graph-only rerun had **64 passed, 6 failed, 0 skipped** and reproduced the same six. Count them once. These opt-in tests cloned disposable databases and directly called tests/graph_index_prototype.py or tests/graph_scalar_prototype.py. The active backend/analyzers/integrations/workers contain no imports of those prototypes. The current tracked production diff does not alter graph index definitions or snapshot_record_query.

| Failed assertion | Candidate path and observed difference | Classification |
|---|---|---|
| tests/test_graph_index_recovery.py::test_extra_version_filter_preserves_complete_baseline_sequence[partial] | Four partial indexes with WHERE kind != 'snapshot'; query also filters Record.version >= 1, which does not exclude snapshots. First sequence difference at row 49. | Rejected test-only candidate compatibility failure. |
| Same test [validated_partial] | Same partial indexes plus prototype malformed-snapshot write guards; first sequence difference at row 49. | Rejected test-only candidate compatibility failure. |
| Same test [guarded] | CASE-wrapped graph-expression indexes change SQLite traversal; first sequence difference at row 170. | Rejected test-only candidate compatibility failure. |
| tests/test_graph_scalar_projection.py::test_natural_key_only_update_preserves_projection_metadata | Scalar projection update trigger lists data/kind/ID/tenant/repository/rowid fields but omits natural_key; a natural_key-only update leaves projection stale. | Confirmed defect in rejected prototype, not active production. |
| tests/test_graph_scalar_reading.py::test_filtered_mixed_sequences_match_complete_baseline[version] | Opt-in ScalarCompiler replaces records with a join to the scalar-key table; sequence first differs at row 49. | Rejected test-only candidate compatibility failure. |
| tests/test_graph_scalar_reading.py::test_rowid_read_namespace_is_preserved | Candidate aliases the joined records/projection relation as records; records.rowid is no longer exposed and SQLite raises no such column: records.rowid. | Confirmed defect in rejected prototype, not active production. |

backend/domain.py:snapshot_record_query has no explicit ORDER BY. The frozen sequence is an observed baseline, not a complete SQL ordering guarantee; the tests nevertheless enforce it for candidate compatibility, so do not alter expected rows. Before reconsidering any candidate, define the supported ordering contract and prove complete result equality, tenant/legacy behavior, write/error/rollback semantics, pagination, rowid/alias behavior, output hashes, and query plans. The partial recovery receipt reports equality across 62 queries and 229 write cases, but that does not override the mixed-sequence failures. Both prototype evidence files say REJECTED.

## 4. GitHub run and constrained Linux evidence

### Run identities and source trees

- [Regression run 40280428892](https://github.com/maninani12/ProjectTrace/actions/runs/40280428892) completed successfully on ProjectTrace commit 9e21509591bfa5457cc829ebd5637f95be68d573. parser-isolation, broker-recovery, browser, and validate passed. This is published-base CI, not validation of the dirty local tree.
- [Constrained qualification run 40280429009](https://github.com/maninani12/ProjectTrace/actions/runs/40280429009) also used workflow head 9e21509591bfa5457cc829ebd5637f95be68d573. Candidate source was that ProjectTrace tree. Baseline production source was 243513ee9acb6e4ed66cd3582ba79dc5a787b084. The workflow copied the candidate qualification harness and analyzers/observation_store.py into the baseline checkout; that job is instrumented, not a byte-for-byte untouched tree.
- Both matrix jobs used the same pinned inert OpenMetadata archive: commit b1fab2bc21c63335dead4daaaa28194c9878e9bf, 158,981,993 bytes, SHA-256 95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257. Its receipt says the older historical archive hash was not reproduced. qualification.json source_commit names the upstream workload commit, not the ProjectTrace app commit.
- The manifest had 21,636 rows and SHA-256 081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89; 21,269 files retained text. Imported repository code was not executed.

### Environment and enforced resource bounds

The workflow uses runs-on: ubuntu-latest, resolved in both jobs to runner image ubuntu-26.04, release ubuntu26/20261012.163, Actions runner 2.338.0. The app container used Python 3.14.9, Linux 7.0.0-1017-azure, Docker Engine 29.4.2. Build logs resolve python:3.14-slim to base digest sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8. requirements.lock SHA-256 was 0331753af6ba66329bbb3be218c94da7e0634b8013b91d83ecbcb5f27c5b95aa.

The host harness created a private cgroup-v2 container with --memory 768000000, --memory-swap 768000000 (no extra swap), 2 CPUs, PID limit 64, network disabled, non-root UID 10001, and required SEC-002 parser isolation. It verified Docker HostConfig and actual /sys/fs/cgroup/memory.max=768000000 and memory.swap.max=0; all descendants were in the cgroup. This was a kernel-enforced boundary, not an RSS estimate. The separate envelope probe intentionally killed two 600 MB children (-9) in its own probe container; those are not application failures.

Reproducibility still has gaps: ubuntu-latest is mutable; the Dockerfile uses the mutable python:3.14-slim tag and apt-get update; the retained qualification artifact does not include the final app image digest or immutable runner image ID. The logs preserve the resolved runner release and Python base digest, but future qualification should record or pin runner, base image, apt snapshot, dependency, and final app image identities.
### Full workload results

| Measurement | Baseline | Candidate |
|---|---:|---:|
| Container exit / Docker OOMKilled | 137 / true | 1 / false |
| Last application stage | ANALYZING | VERIFYING |
| Cgroup memory.max / memory.peak | 768,000,000 / 768,000,000 bytes | 768,000,000 / 768,000,000 bytes |
| Swap max / final current | 0 / 0 | 0 / 0 |
| Final cgroup memory.events | max=2470, oom=5, oom_kill=2, oom_group_kill=0 | max=75528, oom=0, oom_kill=0, oom_group_kill=0 |
| Sampled coordinator / child / namespace RSS peaks | 694,599,680 / 126,205,952 / 748,523,520 bytes | 582,090,752 / 165,163,008 / 661,950,464 bytes |
| SQLite integrity / FK violations | ok / 0 | ok / 0 |
| Published generations / pointers | 0 / 0 | 0 / 0 |
| Post-exit job / parser artifact count | ANALYZING / 3,747 | FAILED at VERIFYING / 18,756 |

The baseline inner sampler's last row was at 767.449 seconds in ANALYZING before OOM termination. The workflow artifact's Docker inspect confirms OOMKilled; the database retains a stale ANALYZING row and cold remains RUNNING, not terminal success. These main-container OOM events are distinct from the separate envelope probe.

Candidate duration was 1,875.465 seconds. Stage times: VALIDATING 0.021591 s, PARSING 0.075049 s, ANALYZING 1,173.218985 s, EXTRACTING_CLAIMS 25.077880 s, VERIFYING 513.642960 s. It completed claim extraction. Warm, one-file change, multi-file change, exhaustion recovery, cancellation, fresh-worker recovery, and concurrent-tenant scenarios are NOT_RUN.

The candidate cgroup peak is authoritative. RSS peaks cannot be added to cgroup usage, and shared pages can be double-counted. At failure, memory.current was 767,979,520 bytes; memory.stat reported anon 492,396,544, file 226,136,064, kernel 49,414,144 bytes, and zero swap. Independent sampled maxima were anon 615,325,696, file 436,928,512, kernel 59,015,168 bytes; these happened at different times and must not be summed. memory.events.max=75,528 showed repeated limit encounters without an application OOM kill. The receipt does not attribute those peaks to particular Python objects or individual SQLite/filesystem operations.

### Candidate checkpoint failure and post-exit state

The candidate receipt classifies the failure as IntakeError / GLOBAL_CHECKPOINT_BUDGET at VERIFYING, with one global_analysis_checkpoints_oversize count. Its stack is qualify_scale_workload.py:173 → jobs.py:202 → domain.py:514 → jobs.py:182. At tested HEAD, jobs.save_checkpoint calls analysis_checkpoints.save. That function iter-encodes the complete envelope into a bounded bytearray and returns false once encoded bytes exceed ANALYSIS_CHECKPOINT_MAX_BYTES=64,000,000. It does not truncate; encryption/commit happens only after full serialization. The wrapper then raises the budget error. Exact overflow size is UNKNOWN: safe_budget_diagnostic.actual is null. Only “greater than 64,000,000” is established.

The operation journal attributes 183.296 seconds to quality aggregation, 301.930 seconds to final identity, then records the global checkpoint attempt around elapsed 1,862.988–1,865.057 seconds. VERIFYING totals 513.643 seconds. This 64 MB checkpoint budget is separate from the 1,000,000-node final sanitizer rule. persist_analysis invokes the saver before publication preparation and generation begin; post-exit confirms no generation rows or pointers, integrity ok, FK violations 0, and job FAILED at VERIFYING.

The post-exit receipt is read-only and explicitly not fresh-worker recovery. It does not report snapshot-kind row counts, leases, blob cleanup, or a successful subsequent operation. The disposable container is removed after evidence capture; the artifact contains no database. Therefore cleanup/retry safety beyond zero generations/pointers and database integrity remains unverified.

## 5. Existing local validation and separation

The last corrected Windows backend run (Python 3.14.3 / pytest 9.1.1) was **1,059 passed, 6 failed, 21 skipped, 1 deselected, 0 errors**. The graph-only rerun was **64 passed, 6 failed, 0 skipped**; it reproduces those failures and is not added to the backend count. The full JSON-export module contributed 69 passes. Frontend Vitest passed 49 tests in 12 files. Ruff, compileall, and git diff --check passed in the prior recorded run.

The 21 backend skips were 16 PostgreSQL tests without an explicitly disposable PROJECTTRACE_TEST_POSTGRES_URL and five Linux-only transport/lifecycle tests. The separate integration_tests invocation had 58 setup errors because its autouse fixture requires sys.platform == linux on Windows; four broker/service tests skipped without disposable Redis/PostgreSQL services. No platform guard was bypassed. GitHub's published-base regression later passed PostgreSQL/service and broker jobs, but that does not validate this dirty worktree.

The separate 50k guard regression passed because it asserts expected rejection; it is not successful publication. The historical 50k failure, direct sanitizer reproduction, and pinned OpenMetadata Linux run are distinct evidence. Serialization determinism, graph compatibility, and aggregate admission are separate gates.

No pytest suite, 50k workload, or remote workflow was run in this review. New executions were read-only Git/GitHub status and log inspection, hash verification, immutable SQLite integrity/FK checks, and final document/JSON validation.
## 6. Reproducible Linux qualification plan

### Gate 0 — explicit policy decision

Obtain a written, scoped product-owner choice before architecture or admission work:

- **Option A:** retain the 1,000,000 aggregate-node cap and state that larger logical snapshots are unsupported. If 50k remains a release requirement, Option A does not satisfy it; the owner must re-scope that requirement.
- **Option B:** authorize a bounded policy amendment investigation with a product target. Do not select a number arithmetically. Define complete-logical-snapshot semantics, encrypted storage quotas, bounded readers, recovery, and threat/resource evidence before proposing implementation.

Until recorded: preserve the 1,000,000-node cap, ANALYSIS_CHECKPOINT_MAX_BYTES=64,000,000, observation spill=512,000,000, repository analysis time=1,800 seconds, and current admission/publication behavior. Do not start a new snapshot or graph candidate.

### Gate 1 — freeze environment and inputs

For every baseline/candidate pair, record ProjectTrace commits, exact source differences, workflow SHA, upstream commit/archive SHA and full file manifest. Pin or record the resolved runner release, Actions runner version, kernel, Docker Engine, Python base image digest, final app image digest, requirements.lock SHA, and OS package/apt snapshot. The current workflow uses mutable labels/tags; treat changed identities as a new baseline. Keep the qualification container at 2 CPUs, 64 PIDs, network disabled, non-root, SEC-002 required, memory.max=768000000 and memory.swap.max=0.

### Gate 2 — admission and output correctness

On isolated disposable data, verify complete sanitizer values at 999,999, 1,000,000, and 1,000,001 nodes with exact acceptance/rejection and no page-local counter reset. Rejection, timeout, or cancellation must not create an incomplete COMPLETE snapshot or pointer. Keep the constructed 50k fixture (1,115,947 nodes) separate from the 21,636-file pinned workload. If policy amendment is approved, measure successful persistence, Generation.validate, BASE/HEAD comparison, and publication at its approved target; rejection-only measurements do not establish those costs.

For success, compare complete cold/warm/incremental output—claims, findings, evidence, metrics, symbols, graph edges, artifacts, identity/hash sets, and API responses. Record counts and final publication inventory. Existing checkpoint/spill limits stay unchanged unless policy explicitly says otherwise.

### Gate 3 — cgroup and resource receipts

Run each full workload in a fresh process under the verified cgroup. Record memory.current, memory.peak, memory.events, memory.stat, memory.pressure, swap, cgroup membership, coordinator/child RSS, CPU/I/O counters, SQLite allocation profile, checkpoint encoded size, spill bytes, disk growth, stage durations, and exact completion stage. Require hard memory.max=768000000, memory.swap.max/current=0, no OOM/OOM-kill, no process outside the cgroup, unchanged current budgets, complete output, and successful publication. Report memory.events.max encounters; do not sum independent memory.stat peaks or RSS shared pages.

The existing REPOSITORY_ANALYSIS_SECONDS=1800 and 60-minute workflow timeout remain unchanged. Numeric disk, CPU-time, or additional wall-time SLOs without an approved requirement are NEEDS_POLICY_DECISION. Recommend three independent fresh-process cold runs for stability, but the required repeat count is not currently approved.

### Gate 4 — failures, recovery, and services

For success, cancellation, timeout, malformed input, checkpoint/spill/disk exhaustion, and worker termination, inspect SQLite/FK, snapshot rows, generation states, pointers, audit links, source/parser artifacts, queue state, leases, temporary blobs/keys, and ownership. Prove rollback/fencing and prior published-generation integrity. After each interrupted/rejected attempt, start a fresh worker and complete a subsequent valid analysis. No partial generation or pointer may be marked COMPLETE or published.

Run existing Linux parser isolation and broker/worker recovery tests; run PostgreSQL only against an explicitly disposable service and Redis/Celery using existing CI conventions. Cover duplicate delivery/idempotency, worker restart, cancellation/exhaustion, and concurrent tenants. These are separate from the single-container SQLite cgroup run; report each environment independently.

### Pass/fail ledger

| Gate | State | Evidence / criterion |
|---|---|---|
| Checkout identity and preservation | VERIFIED | Expected branch/HEAD; dirty work retained; four DB hashes match; integrity ok, FK count zero. |
| Published-base regression CI | VERIFIED for that commit only | Run 40280428892, four jobs pass; not current dirty-tree CI. |
| Hard Linux cgroup and zero-swap enforcement | VERIFIED for both failed attempts | Docker/cgroup confirms exact ceiling; not workload qualification. |
| Baseline full cold publication | FAILED | Container OOM-killed, exit 137, ANALYZING; no output. |
| Candidate full cold publication | FAILED | GLOBAL_CHECKPOINT_BUDGET in VERIFYING; no output. |
| Local broad regression | FAILED | Six rejected graph-candidate assertions remain failed; 21 skips and Windows integration limits remain. |
| Set serialization determinism | VERIFIED at recorded source hashes | Focused prior tests passed in eight fresh processes; this is a separate gate. |
| Complete cold output and publication | NOT RUN | Neither constrained run produced a complete generation/pointer. |
| Warm/repeat/incremental equivalence | NOT RUN | Requires successful cold publication. |
| Cancellation, exhaustion recovery, worker restart, subsequent valid retry | NOT RUN / NOT VERIFIED | Post-exit integrity is not recovery; leases and cleanup not fully recorded. |
| Tenant concurrency and dirty-tree PostgreSQL/Redis/Linux acceptance | NOT RUN | Published-base CI does not test current dirty work. |
| Supported-input policy | NEEDS POLICY DECISION | No owner approval; cap unchanged. |
| Successful 50k final snapshot | NOT RUN | Historical fixture rejected before persistence, validation, or comparison. |

## 7. Next blocking decision and safe action

The next required action is a written product-owner choice: accept Option A and its supported-input boundary (which leaves the demonstrated 50k fixture unsupported), or authorize a formal Option B policy/resource investigation. Option A is only the engineering recommendation; this report is not approval.

After the policy is recorded, address the measured global checkpoint overflow under the unchanged 64 MB limit with a bounded, authenticated, tenant-scoped, atomic, recoverable design, then rerun the actual Linux cgroup qualification. If that run reaches snapshot admission, measure the complete logical node count under the approved policy before snapshot architecture work. No gate is closed by this report.

**Final: SCALE-001 NOT QUALIFIED. Commercial V1 DEVELOPMENT IN PROGRESS.**

## 8. Checkpoint budget and recovery follow-up (2026-10-29)

### Provenance and exact failure

Authenticated GitHub CLI reconfirmed that regression run [40280428892](https://github.com/maninani12/ProjectTrace/actions/runs/40280428892) completed successfully across parser-isolation, broker-recovery, browser, and validate jobs at published head `9e21509591bfa5457cc829ebd5637f95be68d573`. Constrained run [40280429009](https://github.com/maninani12/ProjectTrace/actions/runs/40280429009) completed with both baseline and candidate workload jobs failed at that same published head. Its failed-job log lines confirm process exit 1; the sanitized artifact supplies the classification and resource detail.

The failed candidate source is the committed v1 implementation (`git show HEAD:backend/analysis_checkpoints.py`, SHA-256 `52d6bf8ac730a25103c0d9b727319d5671a505141e662f2ba6f2806578bafdaf`), not the current dirty local source. In that v1 writer, the outer envelope stores schema, job/tenant/repository IDs, signature, and the complete `result`; when `files` is present it first creates `list(result["files"])`. `JSONEncoder(sort_keys=True).iterencode(envelope)` is copied into one bytearray, and encoding stops with `False` when the next encoded chunk would cross 64,000,000 bytes. Encryption, digest assignment, receipt-row creation, and commit happen only after the full encoding succeeds. `jobs.save_checkpoint` turns the false return into `GLOBAL_CHECKPOINT_BUDGET`. `persist_analysis` calls it before `prepare_publication`, `begin_generation`, and snapshot/evidence publication.

The complete result tree includes findings, assets, quality metrics, code-quality output, analysis coverage, signals, dependencies, claims, file inventory, analysis and verification caches, reused counts, engine states, warnings, and documentation count. `result.quality_metrics` and `result.code_quality.metrics` are the same collection in the analyzer result and are both visited by the v1 JSON encoder; this is a confirmed redundant projection in the object graph, but the failed receipt does not report how many bytes it contributed. The source inventory also contains durable file/path metadata, but its checkpoint share is not measured. Do not assign the overflow to one field: `safe_budget_diagnostic` explicitly records `actual=null`, `rows=null`, and `collection=null`. The only measured conclusion is that v1's complete uncompressed JSON exceeded 64,000,000 bytes.

The pinned workload provenance is OpenMetadata commit `b1fab2bc21c63335dead4daaaa28194c9878e9bf`, archive SHA-256 `95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257`, 158,981,993 archive bytes, and 21,636 files. The receipt says `historical_input_reproduced=false`; this is not claimed to reproduce the earlier intended historical archive.

### Memory and persistence are separate failures

Candidate operation samples show that cgroup `memory.peak` was already 768,000,000 bytes at CLAIM_VERIFIER start (elapsed 1,351.417 seconds). It remained at that peak at FINAL_IDENTITY start (1,546.905 seconds). GLOBAL_CHECKPOINT started at 1,862.988 seconds with `memory.current=765,235,200`, `anon=492,417,024`, `file=220,585,984`, and `kernel=52,162,560`; it ended at 1,865.057 seconds with `memory.current=703,918,080`, `oom=0`, and `oom_kill=0`. The cgroup peak therefore predates checkpoint serialization. These samples do not prove checkpoint serialization caused the memory peak.

The candidate's final cgroup receipt records `memory.peak=768,000,000`, `memory.current=767,979,520`, `memory.swap.max=0`, `memory.swap.current=0`, `memory.events.max=75,528`, `oom=0`, and `oom_kill=0`; final sampled `anon/file/kernel` were 492,396,544 / 226,136,064 / 49,414,144 bytes. Candidate runtime was 1,875.465 seconds. Stage times were ANALYZING 1,173.219 seconds, EXTRACTING_CLAIMS 25.078 seconds, VERIFYING 513.643 seconds. Operation times include QUALITY_AGGREGATION 183.296 seconds, FINAL_IDENTITY 301.930 seconds, and GLOBAL_CHECKPOINT about 2.069 seconds. Component memory peaks occur at different times and are not summed.

Failure receipt: `IntakeError / GLOBAL_CHECKPOINT_BUDGET`, stage VERIFYING, one oversize counter, 18,756 parser artifacts, zero published generations, zero published pointers, SQLite integrity `ok`, and zero FK violations. The post-exit evidence does not enumerate checkpoint rows, leases, temp objects, or blob ownership, and it does not test a fresh worker or subsequent operation. The v1 code path returns before writing a new receipt on over-budget encoding, but the receipt cannot independently verify cleanup or later usability. The baseline remains a distinct failure: exit 137, Docker OOM kill in ANALYZING, cgroup peak 768,000,000 bytes, with last recorded OOM counters `oom=5`, `oom_kill=2`.

### Existing dirty local candidate and bounded 64 MB probe

The existing dirty worktree already contains the paged encrypted checkpoint candidate (`projecttrace-analysis-checkpoint-v2`) and migration 0026. Those changes predate this follow-up and were not introduced or altered here. This task made no production-code change and added only `test_checkpoint_budget_failure_keeps_inventory_for_subsequent_valid_analysis` in `tests/test_checkpoint_pages.py`. It verifies that an over-budget job fails at VERIFYING without a snapshot, generation, pointer, admitted checkpoint or staged page; a new session then reuses the retained inventory, completes a valid analysis, publishes one generation/pointer, clears checkpoint parts, preserves the original failed job, and passes SQLite/FK checks. The test passed twice on independent disposable databases.

A scratch-only probe used synthetic deterministic base64 rows, an unnamed encrypted SQLite spill, the actual 64,000,000-byte setting, and aggregate-only output. At 1,200 rows (32,001,600 payload bytes), save succeeded with 42,676,028 encrypted bytes stored. At 3,000 rows (80,004,000 payload bytes), save stopped after 64,109,740 encrypted bytes had been attempted, returned false, and left zero durable page/manifest bytes. SQLite integrity was `ok`, FK violations were zero. The attempted count is bytes generated up to the first over-budget page, not the total hypothetical checkpoint size. These synthetic Windows measurements validate this local writer's aggregate guard and cleanup only; they do not estimate OpenMetadata compression, memory, or runtime.

Existing v2 tests exercise fresh-session replay, v1 receipt compatibility, aliasing, scope/HMAC integrity, cancellation, page tampering, row/page quotas, lost commit acknowledgement, subprocess exit before manifest admission, retry reclamation, and blocking real-job publication on budget failure. The existing migration 0026 and checkpoint format are not being approved for deployment by these tests. No resource limit was increased; the separate 1,000,000-node sanitizer cap is unchanged.

### Test results tied to current local source

The focused run against the final local checkpoint source passed 37 tests. A related generation/publication/recovery selection passed 195 tests and skipped one Linux-only unnamed-SQLite lifecycle case (672.23 seconds). The full backend command passed 995, skipped 91, deselected only the prohibited 50k profile, and emitted 9 warnings (1,299.87 seconds). Its 91 skips comprise 70 opt-in graph prototype cases, 16 PostgreSQL cases requiring an explicitly disposable URL, and 5 Linux-only cases. The graph prototypes remained inactive; their previously recorded six opt-in compatibility failures remain separate and are not counted as failures of this run. The full backend run preceded the new recovery-test addition; the final 37-test checkpoint rerun includes that test. Ruff and compileall passed on the current checkpoint code and test.

The first focused attempt without an explicit pytest base directory produced 36 setup errors because Windows denied enumeration of `C:\Users\sai krishna\AppData\Local\Temp\pytest-of-sai krishna`; test bodies did not run. The corrected run used dedicated scratch directories under `C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work`. The new recovery test's first mock omitted normal stage callbacks and therefore observed PARSING; the mock was corrected to emit ANALYZING, EXTRACTING_CLAIMS, and VERIFYING, after which the test passed. This was a test-fixture correction, not a product-code failure.

Commands (all used the documented Windows venv; all databases were disposable scratch databases):

```text
python -m pytest -q tests/test_analysis_checkpoints.py tests/test_checkpoint_pages.py --basetemp=<dedicated scratch>
python -m pytest -q tests/test_generations.py tests/test_publication_units.py tests/test_quality_spill.py tests/test_sanitization_aggregate_guard.py tests/test_generation_context.py tests/test_generation_maps.py tests/test_migrations.py tests/test_retention_recovery.py tests/test_recovery_boundaries.py tests/test_analysis_performance.py tests/test_repository_store.py tests/test_observation_store.py tests/test_timeout_recovery.py tests/test_queue.py tests/test_worker_failure.py --basetemp=<dedicated scratch>
python -m pytest -q -rs tests --deselect 'tests/test_snapshot_materialization_profile.py::test_owned_final_snapshot_profile[50000]' --basetemp=<dedicated scratch> --junitxml=<scratch>/full-suite.xml -o cache_dir=<scratch>/pytest-cache
python -m pytest -s -q <scratch>/test_checkpoint_64m.py --rootdir=<repository> --basetemp=<dedicated scratch>
ruff check backend/analysis_checkpoints.py backend/checkpoint_pages.py backend/jobs.py backend/domain.py backend/db.py backend/migrations/versions/0026_checkpoint_parts.py tests/test_checkpoint_pages.py
python -m compileall -q backend tests
git diff --check
```

The 50k sanitizer rejection workload was not rerun. No frontend suite was run because this follow-up changed only a backend test and backend evidence. PostgreSQL, Redis/Celery, Linux parser isolation, and local cgroup qualification were not available: the Docker Desktop Linux engine was stopped (`dockerDesktopLinuxEngine` named pipe absent; `docker-desktop` WSL distro stopped), and no disposable PostgreSQL/Redis URL was configured. No Windows RSS result is presented as Linux qualification. The supported local command, once a Linux cgroup-v2 Docker daemon and verified pinned archive are available, is `python -m scripts.run_scale_cgroup --image projecttrace-scale-candidate --archive <verified-openmetadata-zip> --output <new-scratch-output>` after building the current worktree image with `docker build -t projecttrace-scale-candidate -f infrastructure/Dockerfile .`; the helper verifies the 768,000,000-byte limit, zero swap, and descendant containment. Do not launch it until the local source and fixture are approved and the bounded candidate's end-to-end behavior is ready for its single full run.

All four original databases were rehashed and opened read-only: every captured SHA-256 matched, every `PRAGMA integrity_check` returned `ok`, and every `PRAGMA foreign_key_check` returned zero rows. The original four database files were not test fixtures and were not modified.

**Current verdict: the published-base v1 failure is precisely diagnosed; the local existing paged candidate passes focused correctness, quota, and recovery tests on Windows; full pinned Linux/cgroup qualification remains NOT RUN. The exact full-workload checkpoint size and whether the local candidate completes the pinned workload remain unknown. SCALE-001 NOT QUALIFIED. Commercial V1 DEVELOPMENT IN PROGRESS.**

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

## 2026-10-29 - checkpoint evidence revalidation

The checkpoint field-attribution test selection passed 40 tests with one warning (98.29 seconds); the related generation/publication/recovery selection passed 195 tests, with one Windows-inapplicable Linux unnamed-SQLite test skipped and one warning (829.40 seconds). An earlier record of 233 passing tests remains separate because the count difference was not resolved. Current dirty source hashes match the evidence record; all four original database hashes and SQLite/FK checks remain clean. Ruff, compilation, diff checks, and JSON parsing passed. No production code or limits changed. The full workload and Linux/cgroup qualification remain NOT RUN; SCALE-001 remains NOT QUALIFIED.

## 2026-10-29 - canonical checkpoint source-match and execution gate

Added the canonical docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH.json. It records the published ProjectTrace commit and run inventory identity, distinguishes the run archive from the earlier historical archive, and keeps the result/runtime/config gaps explicit. The failed result is unavailable (actual=null); no exact v1 byte count is asserted. The local Docker Linux engine is unavailable, WSL contains only docker-desktop, cgroup v2 is not exposed, and PostgreSQL/Redis/Celery endpoints are unset, so the full workload was not run. Context7 was not exposed; official versioned vendor docs were reviewed as recorded in the field-attribution report. Checkpoint and sanitizer owner choices remain separately pending. No production code or limits changed; SCALE-001 remains NOT QUALIFIED.

The canonical manifest and byte-attribution check passed 4 tests with one warning (5.16 seconds). Ruff, compilation and diff checks passed. This validates evidence/diagnostic fixtures only; it does not make the missing full-run result available or qualify the workload.

Final canonical manifest hash validation plus byte-attribution fixture: 5 passed, 1 warning (5.71 seconds). This remains local evidence validation only; full constrained qualification has not run.


## Post-reconciliation test rerun (2026-10-29)

Following the evidence hash repair, the focused source-match/attribution selection passed 5 tests, with no failures or skips and one Starlette/httpx deprecation warning (5.41 seconds). The integrated evidence references were then checked against current file bytes. No workload was rerun; SCALE-001 remains NOT QUALIFIED.


## Policy and Linux readiness assessment (2026-10-29)

Added `docs/SCALE001_POLICY_AND_LINUX_READINESS.md` and `docs/evidence/SCALE001_POLICY_AND_LINUX_READINESS.json` after verifying the expected branch and HEAD. Checkpoint CP-A/CP-B and separate sanitizer SP-A/SP-B choices remain pending explicit owner selection. The prior constrained result remains unavailable (`actual=null`); authenticated GitHub CLI lists only the existing candidate/baseline artifacts. Docker Linux, local cgroup v2, and PostgreSQL/Redis/Celery endpoints are unavailable, so no workload was repeated. The workflow’s mutable runtime inputs and missing full-matrix driver coverage are recorded. **SCALE-001 remains NOT QUALIFIED; Commercial V1 remains DEVELOPMENT IN PROGRESS.**

### Historical evidence disagreements preserved

The integrated qualification JSON retains earlier top-level `final_report_sha256`, `final_regression_report_sha256`, and `final_progress_sha256` values that do not match any current Markdown report/progress file. The current regression report and progress hashes are recorded in its `evidence_sha256` index and in the new readiness record. Those older fields were left untouched as historical pointers. The previous 195-pass and 233-pass regression records also remain separate; their count difference is unresolved.

## CP-B + SP-B investigation and run 40280429009 revalidation (2026-10-29)

The current task authorized CP-B checkpoint-format and SP-B bounded-admission **investigations only**. The production checkpoint limit remains 64,000,000 bytes of v1 raw UTF-8 JSON before encryption; the sanitizer cap remains 1,000,000 aggregate nodes. No production code, migration, admission behavior, limit, remote workflow, PR, or database was changed by this investigation.

### Verified candidate and baseline results

Authenticated `gh run view` reports run `40280429009` completed with failure on branch `codex/scale-001-local-continuation`, published HEAD `9e21509591bfa5457cc829ebd5637f95be68d573`. Candidate job `121432289978` and baseline job `121432290767` artifacts `12633028505` and `12631224908` were downloaded and inspected from scratch.

| Run side | Result | Time/stage | Memory / storage evidence | Post-exit |
|---|---|---|---|---|
| Candidate | `GLOBAL_CHECKPOINT_BUDGET`; cold scenario FAILED | 1,875.465 s; checkpoint failure in VERIFYING | cgroup peak 768,000,000 bytes, swap 0, OOM kills 0; process-tree RSS sampled peak 661,950,464 bytes; 75,479 `memory.events.max`; first cgroup ceiling sample in ANALYZING | 18,756 parser artifacts; zero generations/pointers; SQLite `ok`, FK 0 |
| Baseline | kernel OOM, exit 137 | stopped in ANALYZING; no terminal elapsed time | cgroup peak 768,000,000 bytes, swap 0; OOM kill confirmed | 3,747 parser artifacts; zero generations/pointers; SQLite `ok`, FK 0 |

Candidate sampled spans: archive replay 18.965 s, capture 133.315 s, ANALYZING 1,172.889 s, claim extraction 24.834 s, VERIFYING 523.709 s. The checkpoint writer was about 2.069 s of that VERIFYING span. Measured verification operations included quality build 183.295 s and final identity 301.929 s. Therefore the checkpoint guard explains the final rejection but not the large VERIFYING duration. It is measured that the cgroup hit its ceiling earlier in ANALYZING: at 280.321 s the sample was anon 281,178,112, file 427,401,216, kernel 58,966,016 bytes. At the final VERIFYING sample the charge was anon 492,417,024, file 225,976,320, kernel 49,434,624 bytes. Cumulative I/O was high, but cannot be attributed to a named spill/database path. These measurements do not establish full output or recovery.

The v1 receipt says `actual=null`; exact failed envelope bytes and field attribution remain unknown. The run archive identity is known, but the archive ZIP, failed result, checkpoint database, and ciphertext were not retained. The run used Python 3.14.9; the local test runtime is Python 3.14.3, and the historical final-image/apt/dependency-byte identities remain unavailable. Do not conflate the baseline OOM with the candidate’s application-level checkpoint-budget rejection or the deliberate resource-envelope probe.

### CP-B and SP-B investigation decisions

CP-B can investigate a versioned, paged writer that preserves exact v1 logical admission by counting the complete normalized v1 JSON stream before compression/encryption. It cannot make a result over 64,000,000 raw logical bytes admissible without a separate decision changing that unit. The current dirty paged candidate is not equivalent: `files` changes from list to `ReplayRows`, aliased metric collections restore as one shared object rather than independent JSON-decoded lists, and quota is measured in encrypted storage bytes. Preserve these differences; do not relax tests. Any implementation must also bound individual encoder fragments (not only page buffers), descriptors, aggregate temporary/durable bytes, replay memory, cancellation, cleanup, encryption/integrity, tenant fencing, and fresh-worker behavior.

SP-B investigation confirms the “50k” owned fixture means 50,000 metric rows and measures 1,115,947 nodes, rejected by the unchanged 1,000,000-node guard before later snapshot paths. No downstream successful persistence/validation/comparison cost is known. Do not select a threshold by adding a margin. A policy proposal must benchmark the full specified resource vector and include security/adversarial and recovery acceptance before explicit product/security approval.

### Local validation and release gate

Current dirty Windows worktree tests: checkpoint/sanitizer/context selection 82 passed, 0 failed, 0 skipped, 1 warning (42.42 s); generation/publication/recovery/queue selection 57 passed, 0 failed, 0 skipped, 1 warning (166.98 s). Ruff and compileall passed. These results apply to current local source, not the published GitHub commit or Linux. Four preserved databases still match their SHA-256 receipts and pass read-only SQLite/FK checks.

Linux qualification was NOT RUN: Docker Linux engine is unavailable; local WSL cgroup memory/swap are unlimited; PostgreSQL/Redis/Celery endpoints are unset. The workflow remains mutable at runner/base/apt layers. Warm, incremental, cancellation, exhaustion recovery, fresh-worker, duplicate delivery, tenant-concurrency, complete output equivalence, and successful atomic publication remain NOT RUN. Full release gates remain open. See `docs/evidence/SCALE001_CP_B_SP_B_INVESTIGATION_20261029.json` for exact artifact hashes, measurements, commands, environment and provenance. **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**


## 2026-10-29 — v1 byte-counter helper and manual cgroup preflight

The separate payload-free v1 byte counter matches the original `JSONEncoder(sort_keys=True)` envelope byte count and preserves `files` list normalization. It is not integrated into the production failure receipt: the local dirty writer delegates to the paged encrypted-storage path and can consume one-shot input before returning. No runtime limits, checkpoint policy, or sanitizer policy changed.

Local Windows synthetic 10,000-row results (3,413,103 raw JSON bytes in every mode): list-input counter vs bytearray reference was 0.680 vs 1.664 sec, 99,391 vs 3,730,544 bytes traced incremental peak, and 327,680 vs 3,567,616 bytes sampled RSS increment. Generator-input counter vs reference was 0.727 vs 1.697 sec, 2,615,431 vs 6,250,720 bytes traced peak, and 3,919,872 vs 6,762,496 bytes sampled RSS increment. This is a serializer-only synthetic profile, not a full-workload or Linux result. The helper still materializes the v1 files list and can hold encoder sort temporaries or a large scalar fragment.

Tests: byte-counter/privacy/boundary/drift selection 9 passed; checkpoint/page/attribution/source-match/sanitizer/context/maps selection 82 passed. One Starlette/httpx warning per command; no failures or skips. Ruff, compileall, diff-check, workflow YAML and embedded Bash syntax checks passed. The manual-only cgroup preflight workflow was added locally and not dispatched. Docker Linux remains unavailable; WSL reports unlimited memory/swap; app dependency hashes and separate PostgreSQL/Redis/Celery qualification remain open. Original DB hashes, SQLite integrity and FK checks are unchanged.

See `docs/evidence/SCALE001_V1_CHECKPOINT_COUNTER_PREFLIGHT_20261029.json` (SHA-256 `f736e86335eeb47dac90904390046ab73c365087ef4fa53586ac4e60839a8387`). Historical run `40280429009` and its `actual=null` receipt were not rewritten. The full pinned workload and all warm/incremental/cancellation/exhaustion/recovery/publication gates remain NOT RUN. **SCALE-001 NOT QUALIFIED.**


### Preflight fail-closed review

The final static review requires non-empty GitHub `ImageOS` and `ImageVersion` values and fails if `docker info` does not identify a Linux engine with cgroup v2. The exact 768,000,000-byte memory and zero-swap kernel file assertions remain in the resource probe step. Both embedded scripts still pass `bash -n`; the workflow remains undispatched.


### GitHub dispatch prerequisite

GitHub documentation requires a `workflow_dispatch` file to exist on the default branch before the manual run can be triggered. This local-only workflow is not yet on that branch, and this task prohibits changing `main` or the shared PR, so its run remains blocked by scope and was not dispatched. See [GitHub manual workflow guidance](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
