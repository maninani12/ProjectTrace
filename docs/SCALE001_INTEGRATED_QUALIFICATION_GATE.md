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


## 2026-11-02 — Local CI repair/profiling addendum

Current remote run 41429161593 on e2afa09ccfd45f8a7551b5ed8b2868d6297c299e confirms baseline OOM in ANALYZING and a different candidate ANALYSIS_TIME_BUDGET failure. Its 1658.306790s PARTITION_PARSE dominates 1808.034993s ANALYZING. It did not reach the older candidate VERIFYING/checkpoint rejection discussed in this historical assessment; neither current attempt published a generation/pointer.

Uncommitted local corrections address pinned-history checkout, explicit immutable evidence byte-representation provenance, current/peak process memory labeling and missing counters, and stale PostgreSQL head acceptance. Focused cases pass with real isolated PostgreSQL: 6 passed; surrounding 127 passed; final telemetry refinement 17 passed; final immutable-provenance 7 passed. All selections have zero failed/skipped and overlap; actual corrected Linux execution remains outstanding. Original receipts/manifests and pre-existing Windows runtime fixes are byte-identical. New byte provenance is in docs/evidence/CI_EVIDENCE_BYTE_REPRESENTATIONS_20261102.json.

Bounded 48-file Windows mixed-language profiling and small packet-gate probes are scoped observations, not full-workload extrapolation or a demonstrated performance improvement. No production analysis optimization, graph/scalar prototype, CP-B or SP-B implementation was adopted. See docs/evidence/CI_REGRESSION_REPAIR_ANALYSIS_PROFILE_20261102.json for exact tests, profiles, source hashes and remaining unknowns. No budget, tenant/parser/security boundary, remote job or release status changed. Next task is authorized bounded Linux affected-test/telemetry/packet profiling; SCALE-001 NOT QUALIFIED and Commercial V1 DEVELOPMENT IN PROGRESS.


## 2026-11-02 — Separate Linux/host-profile outcomes

Linux validation remains BLOCKED/NOT_RUN because no authorized Linux kernel/runtime is available on this Windows host. The existing required-mode gate refuses execution with LINUX_REQUIRED. Codespaces inspection requires additional unapproved scope; no account permissions, privileged OS features or remote workflows were changed. No corrected Linux test, Landlock/seccomp denial or Docker SEC-002 result is inferred.

Byte-exact 703-file execution tree SHA-256 9f5e40f6703b91809b5c4e3847c57d2986d8a93ad139c9bc81b9ce6f31b2359d was verified before/after bounded host profiling. Windows protocol/privacy/instrumentation tests passed 26 cases (0 failed/skipped, 1 warning). Three host repetitions per mixed-language/config fixture measure parent decode/privacy and development helper roundtrip costs only. Required Linux native worker startup, kernel boundaries and real Linux input/DB waits remain unmeasured. No production optimization was justified, no duplicated logical projection was removed and no limits/policies changed.

See docs/evidence/LINUX_VALIDATION_BLOCKED_PARTITION_HOST_PROFILE_20261102.json and local outputs/linux-partition-20261102/ for exact source/measurement scope, prepared copy, counts and blockers. Added documentation is a later full-tree version, not a tested Linux tree. Prior baseline OOM, candidate timeout and 91.72% partition-stage observation retain their original source/date and are not requalified by host timings. Next task: an authorized Linux environment, source parity, exact affected tests/required denials and then native substage profiling. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


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


## 2026-11-03 — Bounded HCL frequency evidence; full-scale attribution remains unknown

The unchanged required-mode repository partition path launches one fresh IaC worker per partition with uncached IaC inputs (bounded100 files/2MB); valid artifact reuse launches0 IaC workers. Seven owned topologies directly measure0/1/1/1/2/1/4 cold starts and2->1 grammar opens per worker. Local cold restricted Docker paired-median analysis savings17.86–22.46% (n3) are material for those fixtures; native matched results are mixed. The prior native5.84% causal claim is superseded because27 valid candidate-only app bytecode caches predate its comparison; all old evidence/caches remain preserved and the new matched rerun uses0 app pyc on both source copies. This does not alter the verified grammar-count, correctness or Docker/security evidence.

Retained remote IAC376 is a file-packet count, not worker/preparation telemetry. Actual affected starts, processed IaC inclusion/component boundaries, cache/runtime state and critical-path preparation share are unavailable. Consequently no full-workload savings estimate or qualification change is supported. Historical run41429161593 baseline job125223103299 remains exit137/OOM at768000000 bytes/zero swap; candidate125223102927 remains ANALYSIS_TIME_BUDGET1808.034993s versus1800, PARTITION_PARSE1658.306790s, no published generation. Its partition-loop timeout did not measure later global finalization; local global timings cannot be assigned to it. Next bounded target is native packet decode/expansion/privacy/reconciliation, with exact invocation/byte/node/row/cache/preparation counts; CONTAINED_NATIVE494.503276s includes transport265.378116 and packet validation226.605416s. No second optimization, limit/security/publication change, full workload or remote dispatch occurred. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED. Receipt:docs/evidence/HCL_WORKLOAD_FREQUENCY_PARTITION_ATTRIBUTION_20261103.json; raw/report:local outputs/partition-attribution-20261103/REPORT_20261103.md.


## 2026-11-03 — Native packet substage measurements do not establish full-scale recovery

Unchanged qualified candidate source/image underwent bounded exact-packet replay and actual required-worker checks. A1,224,056-byte genuine generated-worker response (83,110 expanded logical visits) admits in120.814ms native/123.105ms Docker median (n5): roughly64% bounded decode/JSON construction and36% sanitizer/privacy/copy. Wide shapes shift about48–50% into sanitizer work. No duplicate file-packet decode or dispensable projection accounting/copy was proven; no production optimization, node/byte/depth cap, security/tenant/publication or resource limit changed. Intended69 distinct packet/privacy/isolation/history/recovery cases pass; one earlier portable mode-signature failure is retained and characterized, not relabeled as a pass. Complete samples/hook overhead and process versus cgroup memory labels remain in local outputs/native-packet-20261103/REPORT_20261103.md; receipt:docs/evidence/NATIVE_PACKET_PROCESSING_ATTRIBUTION_20261103.json.

Historical native packet validation226.605416s lacks per-packet shape/substage/allocation counters; local percentages are not a full-workload estimate. Baseline OOM768000000 bytes/zero swap and candidate1808.034993s ANALYSIS_TIME_BUDGET versus1800 remain unresolved, with no published generation. The approved26-file GitHub backup uses [skip ci] to avoid the existing push-triggered full SCALE workload; unchanged approved file-tree contents were verified remotely, and no remote CI pass is claimed. New profiling documentation remains uncommitted. Next bounded milestone is representative sanitized token-heavy response sampling with exact byte/node/unique-text counters and semantic/admission equivalence before optimization. No full workload or remote dispatch occurred. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


## 2026-11-03 — Packet shape scaling complete; persistence/memory is the next target

The bounded packet-shape milestone is complete on unchanged candidate execution tree bdcdf6e5cfb4e51dda47f74b1f8c9848f77d54f63bc401664d87820be4125d82 / image5844e12de488849fc30492d0ef0f88cf8585312d381091eda8fd0c438f4c75bc. Actual HEAD remains5ec424b88a53dee5fe5fa85fdf041ee0395d5773; prior707-file dirty Windows tree e5bec94f02e80f7c3d25906a8642f83ebc13f298d339513d5a129248959903df was snapshotted. All94 active pins and704 native/194 image payload source files verify per coordinator; profiling source remains0 app pyc. Original27-cache trees, runtime/database/backups and all prior evidence are preserved. Only this appendix and a new sanitized receipt are added; no production change, commit, push, workflow dispatch or full SCALE run occurs.

Seventy ordinary/adversarial plus7 boundary fixtures produce6874 benchmark gate calls (5986accepted/prefix,888expected refusal), with exact fixed-byte output/error equality across native/Docker. n5 ordinary plain/observed coordinators retain first encounters and3 correlated same-process repeats; final allocation n3 excludes sampler/proc I/O, separate RSS n1 is a window lower bound. Both earlier memory diagnostic attempts remain explicitly superseded for traced peaks; ordinary timing is unaffected. Focused82 distinct tests finish81passed/0failed/0errors/1Windows-only long-path skip. Real required Linux isolation/failure, finding identity/history, tenant/checkpoint/publication replay checks remain distinct from portable development-parent protocol tests. Untimed12-case/111-packet alias checks preserve independent mutable observation/cache copies. Twelve timed mixed claims/findings analyses match cold/warm;4 extra analyses prove cross-platform differences occur only in parser_signature fields that intentionally include Python build identity. Fixed-byte replay needs no exclusion.

The genuine1,215,014-byte/83,110-visit D500 packet admits in124.247ms native/120.757ms Docker, about62–64% decoder/materialization and36–37% sanitizer/privacy/copy. The synthetic4,532,765-byte/720,028-visit token shape takes743.278/761.068ms with80.108/80.109MiB traced peak (transport-admission stress, not certified producer/workload frequency). Similar1.19MB token graphs take193.357/194.659ms and21.326MiB, demonstrating shape-dependent amplification. Token/reference growth is approximately linear in these finite ranges; equal131KB text spans4.279–21.506ms native as privacy triggers vary. No duplicate decode, removable privacy/accounting/copy pass, nonlinear defect or safe correction is established. Sub-millisecond depth/small fits are noisy. No new speedup or constrained-memory qualification is claimed.

Stored historical evidence retains180 native stream-gate spans/226.605416s/max4.380129s,11,154,917 token entries,168,858 metric rows and402,123,856 ciphertext spill bytes/97.147434s, but no per-packet byte/node/depth/type/reference/time/memory distribution or large-packet frequency. Token-only sensitivity scenarios are labeled hypothetical and are not full-run estimates. Historical e2afa09 run41429161593 baseline125223103299 OOM768000000 bytes/zero swap and candidate125223102927 ANALYSIS_TIME_BUDGET1808.034993s versus1800 remain unresolved; neither published. No historical sanitizer/checkpoint rejection is inferred from expected local fixture refusals.

This fulfills the previous packet-shape next step. The next different, higher-value milestone is bounded multi-partition memory-lifetime and persistence attribution: typed metric/token serialization/encryption/spill, ParserArtifact JSON/SQL and coordinator graph release/RSS at partition boundaries. Historical spill97.147s/cache writes43.973s/OOM motivate this without presuming a leak or removing evidence. Source/input/checkpoint/sanitizer/time/memory/swap/security/tenant/publication limits stay unchanged. Receipt:docs/evidence/PINNED_WORKLOAD_PACKET_SHAPES_20261103.json; full local report/raw/summaries:outputs/pinned-packet-shapes-20261103/REPORT_20261103.md. Final documentation-inclusive source manifest is separate. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


## 2026-11-03 — Partition lifetime, typed spill and ParserArtifact investigation complete

Unchanged candidate execution tree bdcdf6e5cfb4e51dda47f74b1f8c9848f77d54f63bc401664d87820be4125d82/image5844e12de488849fc30492d0ef0f88cf8585312d381091eda8fd0c438f4c75bc completes292 matched primary actual pipeline calls over8 synthetic cases (2–210files, up to2000metrics, three sequential partitions and existing two-helper concurrency). Source/pins verify704 native/194 image payload files and94 active versions; profiling app pyc remains0. Original27-cache tree/control image/data/backups and all dirty documentation are preserved. HEAD/last authenticated remote remain5ec424b88a53dee5fe5fa85fdf041ee0395d5773; no commit/push/stage/dispatch occurs. Starting708-file Windows raw tree95ab289aeb6dacee8ad7583e4a464acfdb180e1e7a0eb79d9174a98daced431d is preserved; later709-file documentation-inclusive identity is separate.

No accumulating partition view/ParserArtifact ORM identity-map/idempotency defect is established. Dense20-file/2000-metric cold analysis takes3.079s native/4.264s Docker (plain n3); spill0.226580/0.229772s and cache-write0.073041/0.074997s exclude commit. Cache JSON is2925480bytes; native typed ciphertext about2.84MB plus SQLite/index overhead. Traced peak27.313/27.387MiB occurs in native work/admission; approximately14.1MiB current at partition return drops to0.46MiB after frame release. Three-partition post-release current remains around0.47–0.54MiB, identity map0 and no live partition views remain. RSS retains database/allocator/library state and is not a leak proof; no unspilled control/whole-job leak absence or peak-saving percentage is claimed. Necessary attempt-wide rows and independent cache representations remain intact. No production optimization is implemented.

Original read-only Docker C case fails exit1/OOMKilled=false. Exact bounded reproduction verifies SQLite extended6410 SQLITE_IOERR_GETTEMPPATH with zero cgroup OOM/max events. Only supplying SQLITE_TMPDIR before interpreter start resolves the measured launch; same image/root/caps/memory/swap/kernel policy completes all matched cases. Initial native/unmatched Docker/probe failures are retained, not relabeled PASS. Existing64MiB /dev/shm is a bounded lab temp location, not proposed storage for historical402MB spill; historical launcher lacks a read-only-root request. Matched-launch filesystem/network/environment/crash denials pass, child environment remains exactly the3 authorized keys. No app/image/security/cap/cache budget changes.

New isolated disk SQLite and PostgreSQL17.11 B/D/G comparisons preserve exact semantic and complete artifact identities. Six deliberate spill/pre-commit process-death/post-commit interruptions recover without duplicate delivery or publication; three extra PG codec runs correct missing per-connection instrumentation without changing serializers. Main292, extended10, recovery12 successful and codec6 calls have distinct scopes. All collected130 test executions are128passes/1retained wrong-parent-mode assertion failure/1Windows-only skip across129distinct targets; intended contexts finish128passes/0failures/errors/1skip. The single parent-hook case passes unchanged in CI's development mode. Real PostgreSQL14 and required Linux18 selections pass; Ruff and318-file compilation pass in CI's7 directories. Current test source caches318files and is never a performance subject. Prior full SEC-002 remains tied to unchanged source/image; no changed-runtime gate result is inferred. The new PG fixture DB/schemas remain private; the server is restored stopped.

Historical e2afa09 run41429161593 remains baseline OOM768000000bytes/zero swap and candidate ANALYSIS_TIME_BUDGET1808.034993s versus1800, neither published. Storage-module Git blobs match current, but no synthetic timing extrapolation or failure replacement is supported. Candidate retained cgroup peak768000000/max13600/oom0 and268120064file-cache bytes motivate the next system-level milestone: a bounded complete job under CI's2CPU/768MB/zero-swap with disk-backed SQLite and qualified private disk temp storage, tracking reclaim/PSI/I/O plus checkpoint/publication/replay ownership. No more isolated packet/spill microbenchmarks or full50k workload are implied. All sanitizer/checkpoint/time/memory/swap/security/tenant/BASE-HEAD/publication constraints remain unchanged.

Receipt:docs/evidence/PARTITION_MEMORY_PARSERARTIFACT_20261103.json. Full raw/report:outputs/partition-memory-20261103/REPORT_20261103.md, summary.json/findings.json. Six documentation/receipt backup candidates are reviewed in local BACKUP_REVIEW.md; fresh commit/push approval is required and not requested/executed here. Commercial V1 DEVELOPMENT IN PROGRESS; SCALE-001 NOT QUALIFIED.


Additional correctness finding: independent-process E-few-large output equivalence FAILS despite identical cache artifacts. Four full-pipeline hash-seed coordinators (8 further analyses) prove PT-QUALITY-013 findings at positions2/3 swap paths with seeds0/3 versus1/2; complete row multisets/fingerprints and every other global field remain identical. core.py:64 creates a set and core.py:234 iterates it unsorted. This existing global finding-order defect is not corrected or normalized away, is separate from retention/persistence, and was not reached by the historical timeout. Pytest counts above do not represent a PASS for this new differential check. The next smallest corrective milestone is stable PT-QUALITY-013 emission with fresh-process and publication/replay/order regressions; then the system-level resource-pressure lifecycle investigation described above. No production change is included.


## 2026-11-03 — PT-QUALITY-013 deterministic ordering and bounded complete-job qualification

The previously open file-finding order regression is corrected in new analysis: `analyzers/code_quality/core.py` now iterates `sorted(selected)` only in the PT-QUALITY-013 block. Unique repository-relative paths supply the complete key; surrounding rule/severity groups, row contents, duplicate handling, fingerprints, observation hashes, evidence provenance and cache keys are unchanged. The original failure and all earlier records remain preserved. Four fresh seeds across nine before/after scenarios prove identical corrected ordered output/serialization and exact before/after finding-row contents. Four fresh publication coordinators per implementation change from three native/published/snapshot-API-array order variants to one; the separately SQL-ordered quality findings API was already stable.

New 711-file executed source `fb7fc13d6335283e4ecc7949162d54a99dccdc8d3aaa3de7346298e2597f51f7`, new image `sha256:acc7dd075d1065291354e3572acb876e20725eb2654e357bef969e781fb56cb0`, 194 runtime files and all 94 active pins verified. Final intended tests: **337 PASS, 0 FAIL/ERROR, 1 Windows-only SKIP**, including 14 new determinism/replay tests and 64 required Linux isolation tests; Ruff, 320-file compilation and whitespace pass. Both new-image SEC-002 probes and matched in-job denials pass. All 417 retained pytest executions are 409 pass/7 fail/1 skip: original expected failure plus three corrected test-pointer mistakes and three corrected harness evidence-directory omissions; logs/source identities remain explicit. Existing TestClient deprecation is retained. No historical image result substitutes for changed-source qualification.

An original-version owned-database clone proves cross-version compatibility: corrected code reuses one old global checkpoint/four stage receipts without re-analysis, preserving old staged order, IDs/evidence IDs, receipt digests and published snapshot bytes. New analysis emits canonical order with stable EXISTING deltas. Cached snapshots and old staged receipts are deliberately not rewritten or silently reordered.

Six ordinary fresh-container sequences (113/313 synthetic files, n3 each) publish cold/warm/eight-file HEAD jobs, plus a separate three-job allocation sequence and one allocation-owner cold diagnostic: 22 complete publications in this resource phase. Actual kernel limits: 768000000-byte memory, zero swap, two CPUs; 1800s analysis, 64000000-byte checkpoint and 1000000-node sanitizer unchanged. Disk SQLite and validated private ordinary-disk anonymous temp storage replace the earlier lab-only tmpfs workaround. Moderate complete-job medians: **28.516s cold, 21.895s warm, 29.108s HEAD**. Highest ordinary sampled charge **270905344 bytes**, lifetime cgroup peak **271167488**, during lexical_diff/CORRELATING; memory max/OOM events, memory PSI, swap and reclaim increments all zero. No memory-pressure cause is reproduced. Largest sampled I/O stall is 88021us/112107us during commit/CORRELATING; cgroup physical I/O counters and CPU clocks remain separate. All tracked spill owners release; residual traced sites include lazy imports/SQL compilation, with no material retention/performance defect established. Cold fixture quality gate REVIEW_REQUIRED, warm/HEAD PASS; every job COMPLETED with consistent typed quality counts and immutable publication. No PostgreSQL/broker or GitHub-hardware equivalence is inferred; PostgreSQL stays stopped.

Historical e2afa09 baseline OOM and candidate ANALYSIS_TIME_BUDGET1808.034993s/1800 remain unresolved; neither published. The new bounded success is not SCALE-001 qualification. Next smallest milestone: one bounded, identity-pinned authorized workload slice through the same full-job telemetry to test actual packet/observation shape and CPU/I/O/cache pressure. No full workload, speculative optimization, cap/security/tenant/publication change, remote dispatch, commit/push or deployment occurred. Ten source/test/documentation/receipt files are prepared for a separately authorized backup review. Receipt: docs/evidence/PT_QUALITY013_COMPLETE_JOB_20261103.json; full local report/raw: outputs/determinism-job-20261103/REPORT_20261103.md. Final documentation-inclusive source manifest is separate. Commercial V1 **DEVELOPMENT IN PROGRESS**; SCALE-001 **NOT QUALIFIED**.


## 2026-11-04 — Identity-pinned real source slice publishes PARTIAL results; no production change

Source is public maninani12/OpenMetadata, HEAD `b1fab2bc21c63335dead4daaaa28194c9878e9bf`, verified direct parent BASE `848435caaf8e3f1b7352ccbecea0b1be64c57391`, identical Git tree `98be740cd54db8653ce735946b6fd6bd5986e5e3`. The retained source archive was absent; one authorized public immutable download matches158981993bytes/SHA95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257. A predeclared96-file/2MB stratified selection verifies92files/1263844bytes/34791lines, manifest `0d740db72afe28a130034b1e10c6022618d5ecc1519f44d5701103f5abb5ce8a`, against the retained21636-entry manifest. Only selected whitelisted regular members are extracted/analyzed; no entire workload or repository code executes. HEAD is a real empty commit, so no changed-file incremental result is claimed.

Cold BASE25.403420s, warm BASE19.866242s and recovered HEAD7.487428s publish **PARTIAL**, all gates REVIEW_REQUIRED. HEAD deliberately fails after HISTORY at15.378962s, then reuses one global checkpoint/182 publication units/7 stage receipts; combined22.866390s is retry cost, not normal HEAD latency. Immutable old snapshots, duplicate same-snapshot delivery, ordered full native finding hashes,88 ParserArtifact hashes and private DB integrity verify. Source/evidence audit checks270 records/282 native references, preserving original input hashes and exact redacted bytes;15 records across5paths have privacy-transformed evidence. An initial failed provenance check incorrectly equated original and redacted digests; its receipt remains, and the qualified read-only audit verifies the actual contract. No raw source/secret values, DBs or keys are exported.

Two selected GitHub workflow YAML files trigger the existing unrendered-template guard and remain uncached: warm88hits/2misses, one repeated IaC invocation. This is a source-admission policy observation, not proof of malformed YAML. Warm/HEAD preserve26 unresolved native identities as ANALYZER_BASELINE/NOT_OBSERVED,68 EXISTING; quality54EXISTING/13BASELINE. Source65/65 syntax parsing is not full semantic coverage. Real native findings94 (67quality/18IaC/9secret-pattern), metrics1358/tokens75755/symbols311, cold typed ciphertext2862836bytes, cache JSON4889423bytes. Cold native90packets/4978889wire bytes/max388132; decode0.420981s/privacy0.367836s within0.811440s native admission. Actual helper overlap2 versus prior synthetic1.

Same qualified image `sha256:acc7dd075d1065291354e3572acb876e20725eb2654e357bef969e781fb56cb0` and194 runtime hashes/all94 pins verify against current712-file source `9f11d367353666c1c504149728fa98cb9c4dca446af5afae1f53ab039efd393d`; no application/test/workflow/dependency code changes. Kernel limits remain768000000bytes/zero swap/two-core quota,1800s analysis,64000000-byte checkpoint,1000000-node sanitizer, unchanged Landlock/seccomp/tenant/publication rules. Highest ROI sample415088640bytes at PARTITION_NATIVE/ANALYZING; lifetime417972224 includes setup/earlier jobs/verification. No memory max/OOM/PSI/reclaim increments. Cold CPU24.975349s, short quota throttle20827us; cold device15.4MBreads/94.0MBwrites, I/O PSI1.224801s. Larger real metric/token/artifact/findings density and shifted memory stages make313-file synthetic results nonrepresentative of every cost. No nonlinear defect or full-scale extrapolation is justified.

Recovery leaves9 encrypted stores alive at the probe boundary. A separate bounded owned-DB clone reproduces9→0 after explicit diagnostic GC (3341objects); anonymous temp4657152→0bytes, RSS unchanged183545856bytes. This demonstrates delayed cyclic reclamation, not a permanent leak; automatic GC latency under long-lived pressure is unmeasured. No production GC/cleanup optimization is introduced. Focused tests65PASS/0FAIL/0ERROR/0SKIP,2existing Starlette warnings; Ruff/320-file compilation/whitespace pass. Prior same-runtime Linux64/SEC qualification is preserved, with a current required-mode denial probe; no unnecessary image rebuild/full gate repetition. PostgreSQL remains stopped.

Historical full OOM and candidate1808.034993s/1800 timeout remain unresolved. Next smallest action: pin a non-empty real BASE/HEAD change for this same slice and state expected PARTIAL/template/identity acceptance before genuine incremental qualification. Eleven source/test/documentation/receipt candidates are prepared for consolidated secret-reviewed backup; no staging/commit/push/PR/dispatch/deployment/migration occurs. Raw source, archives, DBs/keys/blobs, telemetry and helper copies remain excluded. Receipt:docs/evidence/REAL_WORKLOAD_SLICE_20261104.json; full local report/raw:outputs/real-slice-20261104/REPORT_20261104.md. Commercial V1 **DEVELOPMENT IN PROGRESS**; SCALE-001 **NOT QUALIFIED**.


## 2026-11-04 — Authentic modified-file BASE/HEAD qualification; PARTIAL boundaries preserved

Authenticated read-only public OpenMetadata objects verify direct parent BASE `bcfe0e03c51d910954e107079334042b31df090b` (tree `90b6cfb7a668c82960b07758ab62ca88f19b75e4`) and HEAD `3367668465f50fa6d6b7237818c86f05dba8aee4` (tree `d7e6b94b36e3f399bb9053d2b68ba7d19b69bb9d`). Full untruncated Git trees differ at exactly2 modified TSX paths,0added/deleted/renamed. A predeclared94-file slice retains92 prior paths plus both changes; BASE1269961bytes/34933lines and HEAD1274861bytes/35078lines, all blobs checked by Git SHA-1 and SHA-256. Six small immutable blob fetches supplement the retained source archive; no clone, source execution or full workload. Current713-file raw tree `db3ffa5ea7bbf5fbd0e2321cfc451360c738f1acd0062ce78e8338f5e659644f` and all eleven pending changes are preserved. Same qualified image acc7dd075d1065291354e3572acb876e20725eb2654e357bef969e781fb56cb0/194 runtime hashes/94 pins verify; no application/test/workflow/dependency change or new image build.

Cold BASE24.984078s, warm BASE20.144717s and normal genuine HEAD21.551803s publish PARTIAL/REVIEW_REQUIRED. HEAD explicitly selects cold BASE while latest pointer is warm BASE. Separate HEAD-vs-warm attempt deliberately fails after HISTORY15.854445s, preserves the previous HEAD pointer, then recovers8.858530s (24.712975s combined), reusing1global checkpoint/186publication units/7unchanged stage receipts with re-analysis forbidden. All4generations publish immutably; duplicate delivery adds no generation. Changed-file sets exactly match the2Git changes. Warm90hits/2misses, changed88/4; misses are exactly2modified paths plus2existing template-policy YAML refusals. Original90 ParserArtifacts remain byte-identical;2new rows add93126JSON-text bytes.368evidence records verify original provenance plus exact redacted bytes;68supported unchanged native predecessors and18implementation claim predecessors per comparison remain stable. No source packaging reset or false resolution is observed.

The real Popover function span44→90 crosses unchanged80-line PT-QUALITY-002 threshold. Native findings94→95 and QUALITY67→68; the new HIGH structural observation is visible and native history INTRODUCED. Its QUALITY delta remains ANALYZER_BASELINE/new_code=false/summary.new=0 because existing snapshot-level conservative comparison policy withholds NEW when other QUALITY identities are unresolved (quality_domain.py48–70/core.py361–373). This is an explicit qualification limit, not a NEW-code PASS or a bypassed missing observation. The prior26unresolved identities persist:11ambiguous structural anchors (5IaC/6quality) and15LOW fallback (8secret-pattern/7quality);52NOT_OBSERVED current/unmatched-prior events are not verified removals. Two GitHub-expression YAMLs continue to hit the unchanged unrendered-template guard and remain uncached. Zero documentation claims from7unchanged Markdown inputs; real added/deleted files, changed documentation and real resolution are not exercised.

Existing2CPU/768000000-byte/zero-swap/1800s/64000000-byte/1000000-node/security/tenant/provenance/publication policies remain unchanged. Normal HEAD sampled420671488bytes/lifetime424321024; highest later interrupted/recovery sequence450293760sampled/451342336lifetime. All memory max/OOM/PSI/reclaim increments0; no resource rejection reproduced. Cold/HEAD kernel CPU24.728625/20.778530s, devicewrites95076352/163504128bytes; IO PSI0.979555/1.088999s. Cgroup I/O/commit/global timing scopes remain distinct; shared-container cache/file charges and extra fourth publication prevent causal comparisons with prior92-file/3publication peaks. No full-scale speedup claim or optimization. Replay again leaves9probe-visible stores, consistent with prior deferred cyclic reclamation; no forced-GC policy change.

Focused tests123PASS/0FAIL/0ERROR/0SKIP,2existing Starlette warnings; Ruff/320-file compilation/whitespace pass. Same-runtime Linux64/SEC qualification is preserved and current required-mode denial probe passes. PostgreSQL stays stopped. Two post-run audit reader/partition-assumption mistakes are retained separately; final immutable read-only audit verifies all368records without workload rerun or DB writes. Twelve consolidated source/test/doc/receipt backup candidates are secret-reviewed; no staging/commit/push/PR/dispatch/deploy/migration occurs. Local pinned-source qualification is not live GitHub provider qualification.

Historical full baseline OOM and candidate1808.034993s/1800 timeout remain unresolved; neither published. Next smallest qualification: one authentic bounded added/deleted and claim-rich change with supported HIGH-confidence identities; separately review intended mixed-confidence QUALITY NEW-code counter contract before any targeted policy correction. Receipt:docs/evidence/REAL_NONEMPTY_INCREMENTAL_20261104.json; full report/matrix/raw:outputs/incremental-real-20261104/REPORT_20261104.md. Commercial V1 **DEVELOPMENT IN PROGRESS**; SCALE-001 **NOT QUALIFIED**.


## 2026-11-04 — Authentic added/deleted implementation claims and independent QUALITY contract audit

Track A verifies public OpenMetadata direct parent BASE `dc77e98b1edc5fd5d2e439f3f35a9d18faca345f` (tree `b62603efd7c7a1a59f0c1d92463a8df1b83b4538`) and HEAD `7a86e0974a58d4d4c9f2e526058351ea41c15420` (tree `6f16977dd4af58a4c00a10e1704996229c1e8a57`) with authenticated read-only complete Git trees. Whole upstream diff2added/2deleted/163modified; bounded slice2added/2deleted/3modified/70unchanged,75files each,952493→959772bytes/26489→26642lines. Eleven small immutable blobs supplement retained source; all selected Git SHA-1/SHA-256 identities verify. No clone/full workload/source execution. Cold22.842272s/warm18.098660s/HEAD21.212644s publish PARTIAL/REVIEW_REQUIRED. Explicit cold BASE remains selected while pointer is warm. Separate HEAD-vs-warm HISTORY interruption16.038143s preserves old pointer, resumes6.658786s (22.696928s total), reuses1global checkpoint/148publication units/7receipt digests without re-analysis. Four immutable publications, duplicate same-snapshot/no-new-generation and DB integrity verify.

The actual added testing claim and removed per-file SQLAlchemy import claim match pre-job source-grounded expectations:16implementation claims before/after,15valid predecessors/1introduction/1CLAIM_REMOVED drift per HEAD comparison. Old source/evidence remains available; no inference that a removed import vanished repository-wide or from deployment.292evidence records/216native references verify original commit/path/hash plus exact redacted bytes. Native57→51 and QUALITY48→42; all43HIGH BASE identities account for37preserved predecessors (34unchanged/3MOVED) plus6supported RESOLVED events. No new native finding arises in added Java files. Four resolutions are in deleted metadata_ext.py, two in modified sampler/config.py.14LOW fallback identities remain unresolved/28NOT_OBSERVED, never credited as removals. QUALITY.resolved stays0 under existing global uncertainty, while native resolutions remain visible. This smaller slice omits prior ambiguous-anchor files;14versus26 is composition, not a matcher fix. Both unchanged template refusals persist. Seven Markdown files yield0documentation claims; authentic changed documentation/correlation remains unqualified. Three changed files do not acquire fabricated changed claims.

Track B establishes consistent backend semantics: native INTRODUCED/RESOLVED are relative history observations; new_code and QUALITY resolution credit require stricter trusted source/model/identity evidence. summary.new counts true new_code; deltas and typed rows match published QUALITY records. Mixed unresolved QUALITY stays REVIEW_REQUIRED; an unrelated UNVERIFIED claim does not automatically override every configured advisory gate. One presentation defect is reproduced and corrected only in frontend/src/WorkspaceApp.tsx: false new_code now says “Not attributed to new code”, replacing the unsupported “Outside changed lines”. True label/history/API/counters/matching/confidence/historical records stay unchanged. Before UI regression1PASS/1FAIL; final10UI tests PASS. New12backend contract/API/claim/replay fixtures and existing123tests give135PASS/0FAIL/0ERROR/0SKIP,3existing Starlette warnings; Ruff/321-file compilation/TypeScript/isolated client build/whitespace pass. All retained169pytest/Vitest executions are158PASS/11FAIL/0SKIP: intentional UI reproduction plus corrected JSON/path/gate test assumptions are preserved separately, with initial type/import-format failures. No backend defect or speculative optimization is established.

Starting714-file raw tree `1045b188d6482dccf5462e4feacbf5654ab89785c55c72cc79517248057d52ca`/twelve pending files is preserved; current716-file tested source `43103333298f8137779aca884ceb61aef7e8a0b5e8bf4a5aaeeacdf07d20307b` includes the UI wording and two new test files. Qualified backend image acc7dd075d1065291354e3572acb876e20725eb2654e357bef969e781fb56cb0 verifies194 unchanged backend/runtime hashes/all94pins and current required-mode denials. The changed UI is tested/built separately and not attributed to an old image PASS. No parser/security boundary changed, so no new SEC image is needed. Existing2CPU/768000000bytes/zero swap/1800s/64000000bytes/1000000nodes/Landlock/seccomp/tenant/provenance/publication limits remain unchanged. Highest later sampled435974144bytes/lifetime439906304; normalHEAD410136576/413454336. Memory max/OOM/PSI/reclaim deltas0. NormalHEAD kernelCPU20.653034s, physical writes124776448bytes, IO PSI0.962141s. Raw phase/worker/packet/spill/cache/commit scopes stay distinct; lower file count/different claims and extra publication prevent a full-scale speedup/regression claim. PostgreSQL stays stopped; source/data/images/history preserved.

Sixteen consolidated backup candidates are reviewed; no staging/commit/push/PR/dispatch/deployment/migration. Raw source/archives/Git bodies/DBs/keys/blobs/traces/helpers/build/test artifacts stay excluded. Local pinned objects do not qualify live GitHub provider behavior. Historical full baseline OOM and candidate1808.034993s/1800 timeout remain unresolved; neither published. Next smallest milestone: authentic bounded documentation-claim modification with supported implementation correlation. Receipt:docs/evidence/REAL_ADDED_DELETED_QUALITY_CONTRACT_20261104.json; separate Track B contract:outputs/claim-quality-20261104/QUALITY_CONTRACT.md; report/matrix/raw:outputs/claim-quality-20261104/REPORT_20261104.md. Commercial V1 **DEVELOPMENT IN PROGRESS**; SCALE-001 **NOT QUALIFIED**.


## 2026-11-07 — Latest constrained CI and bounded identity lookup

At 34655e84ac14fd3911a3cdfe78f5f8fd63c97284, validation 42353740209 passed all four jobs. Constrained run 42353740097 produced verified failures under 2 CPU, 768,000,000 bytes and zero swap.

| Job | Termination | Retained evidence |
| --- | --- | --- |
| Baseline 128347188546 | ANALYZING, exit 137, Docker OOMKilled=true | Verified artifact 13566983448, zero published generations, SQLite integrity ok |
| Candidate 128347188290 | VERIFYING, exit 1, IntakeError / GLOBAL_CHECKPOINT_BUDGET, no OOM | Verified artifact 13567826657, maximum 64,000,000 bytes, actual=null, zero published generations, SQLite integrity ok |

Candidate FINAL_IDENTITY measured 283.746 s on the application timer and 281.982 s of cgroup CPU in the corresponding operation bracket. The subsequent global checkpoint attempt took 47.176 s. The failed Boolean admission receipt does not identify a row, manifest or aggregate byte rejection site. The historical 1,800-second time guard remains a distinct outcome.

On two matched bounded OpenMetadata slices, the original required-mode coordinator repeatedly authenticated and decoded every raw metric per helper batch. In the larger slice, the private indexed correction reduced 5,312 metric point reads to 1,754 plus two ordinal lookups. Large-cold FINAL_IDENTITY wall and cgroup CPU fell from about 1.185 s to 1.009 s and 1.008 s respectively. Source reads, ordered structural identities, publication semantics, resource limits and security policy were preserved. The local scope did not reproduce full CI memory pressure or checkpoint rejection. Warm index maintenance has a measurable cost. Full cold publication and warm, incremental, cancellation, exhaustion and recovery qualification remain open. The next bounded milestone is rejection-site and byte attribution for the v2 checkpoint encoder. Receipt `docs/evidence/SCALE001_FINAL_IDENTITY_PROFILE_20261107.json`.


## 2026-11-07 — OpenAPI deadline attribution

At 200905bb4b7fcf8ab5e42c07c9f7f6c2c280a617, validation 42373565157 passed. Constrained 42373565217 failed baseline OOM and candidate ANALYSIS_TIME_BUDGET. The candidate published no generation. It consumed 1,769.329 seconds before claim extraction, with 1,598.843 seconds in native partition parsing. OpenAPI extraction accounted for 26.269 seconds. The deadline check fired after the final contained helper batch returned and before its one pending result was consumed. The final file path and per-batch duration are unavailable. Neither FINAL_IDENTITY nor checkpoint admission was reached.

Matched cold and warm jobs on the verified OpenMetadata archive preserved four API claims and ordered evidence. The largest slice opened 37 JSON sources once each during OpenAPI extraction, and a contained companion probe measured one decode per source. The main bounded OpenAPI costs are helper startup and transport. No actionable OpenAPI defect was established. Linux passed 133 development and 105 required tests. The current runtime matches the existing 196-file SEC-002 image manifest.

**SCALE-001 remains NOT QUALIFIED. Commercial V1 remains DEVELOPMENT IN PROGRESS.** Next profile the dominant cold native partition work with separate transport, validation, cache persistence and cgroup reclaim attribution. [Sanitized receipt](evidence/SCALE001_OPENAPI_ANALYSIS_BUDGET_20261107.json)
