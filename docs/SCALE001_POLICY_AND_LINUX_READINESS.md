# SCALE-001 Policy and Linux Qualification Readiness

Assessment date: 2026-10-29\
Checkout: `C:/Users/sai krishna/Projects/ProjectTrace-local`\
Branch / HEAD: `codex/scale-001-local-continuation` / `9e21509591bfa5457cc829ebd5637f95be68d573`\
Status: **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**

This is a policy and environment readiness assessment. It changes no product code, migration, resource limit, checkpoint format, or sanitizer admission behavior. It does not authorize a full workload.

Machine-readable evidence: `docs/evidence/SCALE001_POLICY_AND_LINUX_READINESS.json`.

## Repository preservation

The expected checkout, branch, and HEAD match. Before this assessment, the dirty tree had 101 `git status --short` lines: 11 tracked modifications and 90 untracked paths. The complete path list and status fingerprint are preserved in `docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH.json`. Existing checkpoint, generation-context, publication, migration, test, report, and raw evidence work remains intact. This assessment creates only its report and evidence JSON and appends readiness notes to the existing progress and integrated-gate reports.

The four original databases were rechecked read-only. All hashes match their captured baselines; `PRAGMA integrity_check` returned `ok` and `PRAGMA foreign_key_check` returned zero rows.

| Original database | SHA-256 | Integrity | FK violations |
|---|---|---|---:|
| 10,000 | `465441f1dfd2c7d6ca3d7427c79dd55e57c350bee451b60a66b8e0e92f5a1d1b` | ok | 0 |
| 147 | `97aeda34f1cb1b1d67784926c2140c3c27063585ae135fbb39e22643edce94d6` | ok | 0 |
| 30,000 | `c7313fd66baa9e23ec5f5a7e9bdb8003554d086796c101be14f8d02d6ee5e9a4` | ok | 0 |
| Prior | `14a15885488462c687ce2581807ea56ecb2145b98bc58d67f6e2aad3ba9a5627` | ok | 0 |

## Owner decisions still required

No explicit product-owner decision was found. The existing checkpoint decision record remains pending and is not approval.

| Policy | Option A | Option B | Current status |
|---|---|---|---|
| Checkpoint | **CP-A:** keep v1 restoration and the 64,000,000-byte raw-envelope limit. Oversized results remain unsupported through this path. This preserves compatibility but does not resolve the observed VERIFYING failure. | **CP-B:** authorize a formal versioned-format investigation only. No implementation, migration, deployment, changed cap, or qualification is authorized by selecting it. | **PENDING_PRODUCT_OWNER_APPROVAL** |
| Sanitizer supported input | **SP-A:** keep the 1,000,000-node aggregate cap and document larger complete snapshots as unsupported. The demonstrated 50k snapshot has 1,115,947 nodes and remains rejected. | **SP-B:** authorize investigation only of another bounded admission policy, with resource/security analysis, defined limits, regression evidence, and separate approval before implementation. | **PENDING_PRODUCT_OWNER_APPROVAL** |

The decisions are independent. The product owner must select one checkpoint option and one sanitizer option, and clarify whether 50k snapshots are a release requirement. SP-A conflicts with promising completion for the demonstrated 50k fixture. CP-B or SP-B authorizes investigation only; neither permits implementation or limit changes.

The paged checkpoint candidate remains unadopted. Its owned-fixture values match after materialization, but v1 restores `files` as `list` and separate metric lists while the candidate restores `ReplayRows` and shared aliases; mutation behavior and aggregate quota accounting also differ. Synthetic 825-byte and 320,873-byte results do not identify the failed workload’s size. No field is proven safe to remove.


## Source-match status and failed result

GitHub run [40280429009](https://github.com/maninani12/ProjectTrace/actions/runs/40280429009) completed with failure on the expected ProjectTrace commit. Authenticated read-only artifact listing shows the same two existing, unexpired artifacts: candidate `12633028505` and baseline `12631224908`. No new artifact supplies a source ZIP, result object, checkpoint database, or ciphertext.

The source-match manifest records **9 VERIFIED_MATCH, 4 VERIFIED_MISMATCH, and 9 NOT_AVAILABLE** identities. The input commit and archive hash are identified (`b1fab2bc21c63335dead4daaaa28194c9878e9bf`, SHA-256 `95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257`, 158,981,993 bytes), but the earlier historical archive hash differs and `historical_input_reproduced` is false. Analyzer/parser signatures, effective profile/config, runner-seen lock digest, Python base digest, and final app image digest remain unavailable or mismatched.

The candidate ran 1,875.465 seconds and failed in `VERIFYING` with `GLOBAL_CHECKPOINT_BUDGET` at the existing 64,000,000-byte maximum. `actual=null` remains unchanged. Its cgroup peak was 768,000,000 bytes; swap was zero, OOM kills were zero, and the peak preceded checkpoint serialization. Recorded peaks were 582,090,752 coordinator RSS, 165,163,008 child RSS, and 661,950,464 process-namespace RSS. A final cgroup sample reported 492,396,544 anonymous, 226,136,064 file, and 49,414,144 kernel bytes. Post-exit SQLite integrity passed with zero FK violations; no generation or pointer was published. Baseline OOM evidence is separate from deliberate resource-probe OOMs.

The old result is not recoverable from retained artifacts. A new source-matched run could produce a new measurement only after missing runtime/config identity is captured; it cannot retroactively recover the old result. Do not estimate the missing size from synthetic fixtures.

## Linux/cgroup readiness

**Current local environment: NOT READY.** The host is Windows. Docker client 29.8.2 exists, but its `desktop-linux` server cannot be reached because the Docker Desktop Linux engine named pipe is absent. WSL2 lists only the `docker-desktop` distribution. `/sys/fs/cgroup/cgroup.controllers` is not visible to PowerShell. `DATABASE_URL`, test/PostgreSQL URLs, `REDIS_URL`, and `CELERY_BROKER_URL` are unset. No service was installed or started.

The workflow uses mutable `ubuntu-latest`. The Dockerfile defaults to mutable `python:3.14-slim`, runs an unpinned `apt-get update`/`libseccomp2` install, then installs version-pinned `requirements.lock` entries without artifact hashes. The previous run’s image digest and runner-seen lock digest were not retained. Compose uses mutable PostgreSQL and Redis tags. Therefore the previous run’s verified cgroup limits do not establish reproducible runtime identity for a new run.

The resource runner configures 768,000,000 bytes for both Docker memory and memory-swap (effective swap is zero), 2 CPUs, 64 PIDs, a private cgroup namespace, no network, dropped capabilities, no-new-privileges, a read-only archive mount, and a fresh output directory. It verifies actual `memory.max` and `memory.swap.max`, samples memory/CPU/I/O/pressure, uses a disposable SQLite database in the container, and removes only its owned container. PostgreSQL/Redis and broker recovery are separate acceptance work.

The artifact allowlist excludes the archive, database, key, ciphertext, and raw checkpoint payload. It retains sanitized receipts, per-file manifest metadata, resource samples, container envelope, and post-exit integrity results. The manifest contains inventory metadata, not source contents.

The driver lists cold, warm, incremental, exhaustion, cancellation, fresh-worker, and concurrent-tenant scenarios. Cold failed and warm/dependent scenarios were not run. The driver explicitly leaves remaining scenarios `NOT_RUN` and raises `PARTIALLY QUALIFIED`; cold/warm paths alone cannot satisfy release qualification.


### Missing prerequisites before a controlled run

1. Explicit CP-A/CP-B and separate SP-A/SP-B product-owner decisions; resolve whether 50k snapshots are a release requirement.
2. An approved Linux runner with a working Docker server and verified cgroup v2 at 768,000,000 bytes, zero swap, and complete descendant containment.
3. Immutable or fully recorded runner, Python, base/application image, OS-package, dependency-lock, analyzer/parser, and profile/config identities.
4. Fresh isolated storage and database, plus separate disposable PostgreSQL/Redis/Celery services for their acceptance gates. Never use the four original databases.
5. A fixture-validated, payload-free v1 byte counter using the historical `JSONEncoder(sort_keys=True)` defaults, `files=list(...)` normalization, and UTF-8 byte counting. Count the full result without retaining serialized chunks or changing the 64,000,000-byte limit.
6. A complete acceptance driver and evidence for cold publication, warm/repeat, incremental BASE/HEAD equality, cancellation, exhaustion, forced worker termination/recovery, duplicate delivery, tenant isolation, atomic pointer integrity, and database/broker recovery.

### Safe procedure once approved

Use the existing isolated runner convention, first running only the resource-envelope probe and manifest-only preflight. Require verified `memory.max=768000000` and `memory.swap.max=0`. Regenerate the authorized archive at the pinned OpenMetadata commit and check its recorded SHA-256; never execute imported repository code. Use a fresh runner-temp directory, read-only archive, and disposable database/storage. Validate a test-only byte counter on fixtures before one separately authorized measurement run. Retain aggregate byte counts, coarse field contributions, hashes, resource samples, sanitized stages, and post-exit integrity only. Do not retain source archive, database, source payload, checkpoint result, ciphertext, or keys. Measurement-only evidence is not performance qualification; if cold completes, run the full acceptance matrix.

The exact existing-workflow preflight commands, to use only after owner authorization and immutable runtime identity are established, are:

```bash
curl --fail --location --retry 2 --max-time 180 -o "$RUNNER_TEMP/openmetadata.zip" https://codeload.github.com/maninani12/OpenMetadata/zip/b1fab2bc21c63335dead4daaaa28194c9878e9bf
echo '95747f22ebf3d01232b1592551bc2bc1866b9bbe7322dd3bf1a97028b0592257  '"$RUNNER_TEMP/openmetadata.zip" | sha256sum --check
docker build -t projecttrace-scale-candidate -f infrastructure/Dockerfile .
python3 -m scripts.run_scale_cgroup --image projecttrace-scale-candidate --archive "$RUNNER_TEMP/openmetadata.zip" --output "$RUNNER_TEMP/scale/envelope-probe" --resource-probe
python3 -m scripts.run_scale_cgroup --image projecttrace-scale-candidate --archive "$RUNNER_TEMP/openmetadata.zip" --output "$RUNNER_TEMP/scale/manifest" --manifest-only
```

These steps only establish the archive and resource-envelope preflight; they are not full-workload qualification. Do not run them from the current Windows host.

No workload was run for this assessment. The prior approximately 1,875-second attempt was not repeated.

## Documentation and validation

Context7 was not exposed in the active tool inventory. Official documentation was checked instead: [Python 3.14 JSON](https://docs.python.org/3.14/library/json.html), [SQLAlchemy 2.1 Session](https://docs.sqlalchemy.org/en/21/orm/session_basics.html), and [cryptography Fernet 50.0.2](https://cryptography.io/en/50.0.2/fernet/). The Python page displayed 3.14.10 versus local 3.14.3; SQLAlchemy displayed 2.1.6 versus locked 2.1.3; Fernet matched 50.0.2. These pages confirm serializer chunk/default behavior, transaction rollback expectations, and Fernet authentication behavior. Repository contracts and tests remain authoritative. No ProjectTrace source or payload was sent to documentation services.

This assessment ran no pytest suite and no full workload. It performed read-only GitHub metadata queries, version/environment checks, evidence-hash checks, and read-only SQLite integrity/FK checks. The latest focused source-match/attribution result already recorded in the evidence trail was 5 passed, 0 failed, 0 skipped, 1 warning; it was not repeated. The historical 40-pass and 195-pass results, the separate older 233-pass result, and the corrected 38-setup-error attempt remain separate records.

## Recommendation

Keep both policy decisions pending until the product owner chooses. Do not implement a new checkpoint or sanitizer architecture and do not run the full pinned workload in the current environment. The next safe engineering action is a separately authorized readiness task to establish immutable runtime identity and a working approved Linux/cgroup environment, then validate the payload-free v1 counter on disposable fixtures. Only after the owner decisions and all preflight checks pass should one controlled measurement run be authorized. SCALE-001 and Commercial V1 release gates remain open.


### Historical evidence disagreements preserved

The integrated qualification JSON retains earlier top-level `final_report_sha256`, `final_regression_report_sha256`, and `final_progress_sha256` values that do not match any current Markdown report/progress file. The current regression report and progress hashes are recorded in its `evidence_sha256` index and in the new readiness record. Those older fields were left untouched as historical pointers. The previous 195-pass and 233-pass regression records also remain separate; their count difference is unresolved.

## CP-B/SP-B and latest artifact revalidation (2026-10-29)

The current task explicitly authorizes checkpoint-format and sanitizer-policy **investigation only**. It does not authorize production implementation, changed limits/admission, migration, a full-workload rerun, or release. The 64,000,000-byte raw v1 JSON budget and 1,000,000-node sanitizer cap are unchanged.

Authenticated GitHub CLI confirmed run `40280429009` completed with failure on published commit `9e21509591bfa5457cc829ebd5637f95be68d573`; both candidate and baseline jobs failed. I downloaded the two existing sanitized artifact bundles into external scratch storage and inspected their qualification receipts, stage samples, operation journal, cgroup samples, container envelopes, and post-exit receipts. Candidate: `GLOBAL_CHECKPOINT_BUDGET` in `VERIFYING`, 1,875.465 seconds, 18,756 parser artifacts, no published generation/pointer, SQLite integrity `ok`, zero FK violations, no OOM kill. Baseline: exit 137/OOM kill during `ANALYZING`, 3,747 parser artifacts, no publication. These are separate failure modes.

Candidate stage sample spans were 18.965 seconds archive replay, 133.315 seconds capture, 1,172.889 seconds analyzing, 24.834 seconds claim extraction, and 523.709 seconds verifying. The instrumentation measured `QUALITY_BUILD` at 183.295 seconds and `FINAL_IDENTITY` at 301.929 seconds inside verifying. The checkpoint save operation took about 2.069 seconds; its safe diagnostic still has `actual=null`. The first sampled candidate cgroup ceiling occurred during analyzing at 280.321 seconds, with anon 281,178,112 bytes, file cache 427,401,216 bytes, and kernel 58,966,016 bytes. At the final verifying sample those values were 492,417,024, 225,976,320, and 49,434,624 bytes. `memory.events.max` reached 75,479 while `oom` and `oom_kill` remained zero; swap remained zero. Cumulative I/O counters are available but cannot identify a responsible spill, SQLite file, or source path. No per-file parser throughput or exact result size was retained.

The current workstation still cannot reach Docker’s Linux engine. WSL exposes only `docker-desktop`; the visible cgroup has `memory.max=max` and `memory.swap.max=max`. PostgreSQL, Redis, and Celery test URLs are unset. No workload was run. Current registry metadata for `python:3.14.9-slim-bookworm` was verified on 2026-10-29 (OCI index `sha256:945c2676dc2b18e0c1f16879244122c57c0ffede60006bf3df159c507a31bcae`, linux/amd64 manifest `sha256:7dff173021016c8829ae58d5ce112ffc388073ebe67f351aeb6ba2909e35f847`); this is a possible immutable base reference, **not** the historical run’s image identity. The existing workflow still uses mutable `ubuntu-latest`, the Dockerfile uses mutable `python:3.14-slim` plus unpinned apt metadata, and `requirements.lock` pins versions without artifact hashes. A future reproducible build must record an immutable runner identity, final image digest, dated OS package snapshot and package manifest, plus a hashed dependency set/wheelhouse; retain the current cgroup memory/swap, process containment, network, PID, CPU, and parser-isolation checks.

The detailed receipts and provenance are in `docs/evidence/SCALE001_CP_B_SP_B_INVESTIGATION_20261029.json`. The historical failed result, checkpoint database/ciphertext, and source archive are still absent; source-match counts remain 9 verified matches, 4 mismatches, and 9 unavailable identities. **Linux qualification remains NOT RUN; SCALE-001 remains NOT QUALIFIED.**


## Local workflow reproducibility proposal (not applied)

The following is a reviewable proposal only; workflow, Dockerfile, dependency, and service configuration files were not changed.

| Target | Proposed qualification-only change | Reason / evidence to retain |
|---|---|---|
| `.github/workflows/scale-qualification.yml` | Keep the existing pinned action commit SHAs and source/archive checks. Replace the unpinned runtime identity assumption with a pinned, approved Linux runner image or capture runner release, kernel, architecture, Docker Engine, and cgroup version in each candidate and baseline receipt. Record the built candidate and baseline image IDs/digests and run the exact image IDs used by the resource harness. | `ubuntu-latest` does not identify the host kernel or Docker runtime used by a later run; the historical qualification retained no runner/image digest. This evidence is necessary to reproduce native allocator/cgroup behavior.
| `infrastructure/Dockerfile` and `baseline/infrastructure/Dockerfile` | Pin the Python base to an approved platform-specific or OCI-index digest; use a dated Debian snapshot and explicitly pinned `libseccomp2` package; record `python --version`, `dpkg-query` output, architecture, and base manifest digest in the sanitized receipt. | Current `python:3.14-slim` and `apt-get update` resolve mutable inputs. A registry digest observed on 2026-10-29 is a possible candidate reference, not the historical image identity, and needs approval/revalidation before use.
| `requirements.lock` install step | Add and review artifact hashes for the exact locked wheels, or consume an immutable wheelhouse; install with hash enforcement and record the lock/wheelhouse digest. | Exact version pins do not authenticate dependency artifact bytes; current lock has no package hashes.
| Disposable database/broker service definitions used by qualification | Pin PostgreSQL and Redis images by verified digest and record service image IDs/configuration. Keep these services disposable and isolated. | Mutable `postgres:17-alpine` / `redis:7-alpine` tags cannot reproduce native database/broker behavior across runs. Their gates are not covered by the SQLite-only workload receipt.
| Sanitized qualification receipt | Add the runner/runtime/image/dependency/service identities above without adding source content, result values, ciphertext, keys, or credentials. Preserve existing cgroup limits, zero-swap assertion, descendant containment, network isolation, and artifact allowlist. | Enables source/runtime comparison while maintaining the current privacy boundary and resource/security contract.

Before accepting this proposal for a run, verify that the chosen runner can enforce cgroup v2 `memory.max=768000000`, `memory.swap.max=0`, descendant containment, two CPU, 64 PID, private cgroup, and no network. The local host cannot do so: Docker's Linux engine is unreachable and WSL reports unlimited memory/swap. Do not dispatch a workflow or run the workload from the current environment.


## V1 checkpoint counter and local cgroup preflight (2026-10-29)

The historical v1 contract was verified in source: the complete envelope is encoded with `json.JSONEncoder(sort_keys=True)` and its defaults, `files` is normalized with `list(result["files"])`, and the raw UTF-8 byte limit is 64,000,000 before encryption. The new `backend/checkpoint_diagnostics.py` counts the same sorted `iterencode` fragments, asserts the relevant encoder settings and ASCII output, and returns only `schema`, `actual_bytes`, `limit_bytes`, and `over_budget`. It does not retain or log the serialized payload.

This remains a **tested helper only**. It is not wired into `jobs.py` or behind an environment flag, so default runtime behavior is unchanged. In this dirty worktree, `analysis_checkpoints.save` delegates to the encrypted paged writer: it uses encrypted aggregate storage quota and may consume `files` before returning a boolean. Recounting after a failure could consume a one-shot iterable or misrepresent the v2 quota result. Safe integration needs a replayable result contract or instrumentation before consumption and a separately reviewed contract. The helper still has boundedness caveats: it builds the same complete `files` list as v1, JSONEncoder sorts mapping entries into temporary lists, and one large scalar may become one large fragment.

One fresh-process Windows synthetic 10,000-metric serializer-only sample produced exactly 3,413,103 raw bytes in both the counter and v1-style bytearray reference. With built-in list files, counter/reference measured 0.680/1.664 seconds, traced incremental peak 99,391/3,730,544 bytes, and 1 ms sampled working-set increment 327,680/3,567,616 bytes. With generator files, measurements were 0.727/1.697 seconds, traced peak 2,615,431/6,250,720 bytes, and sampled working-set increment 3,919,872/6,762,496 bytes. The generator case still materializes the v1 list. These single-run Windows measurements exclude fixture construction, encryption and database I/O; sampled working-set RSS is not a high-water mark and neither case is the historical result or pinned workload.

Validation on the current dirty Windows tree: `tests/test_checkpoint_diagnostics.py` passed 9/9; the checkpoint/page/field-attribution/source-match/sanitizer/context/map selection passed 82/82. Each run had one existing Starlette/httpx deprecation warning, no failures or skips. Ruff, compileall, `git diff --check`, YAML policy parsing and Bash syntax checks passed. Generation/publication/recovery/queue tests were not rerun because the standalone helper does not touch those paths. The full pinned workload and Linux cgroup workflow were not run.

A local manual-only workflow is now present at `.github/workflows/scale-cgroup-preflight.yml`; it is `workflow_dispatch` only, requires contents read, pins checkout by commit SHA and the Python container by the previously recorded linux/amd64 digest. It records runner/runtime/image/lock identities and checks `memory.max=768000000`, zero swap and event deltas using the owned resource-envelope probe. That probe intentionally OOM-kills disposable children to prove enforcement; it is explicitly distinguished from an application OOM. The workflow passed YAML and `bash -n` static checks but was **not dispatched**. It does not install app dependencies; `requirements.lock` has no artifact hashes, and PostgreSQL/Redis/Celery remain separate untested gates.

Recheck found Docker Desktop's Linux engine unavailable (daemon pipe absent; service stopped), WSL `docker-desktop` cgroup v2 with `memory.max=max` and `memory.swap.max=max`, and PostgreSQL/Redis/Celery URLs unset. The WSL distro was returned to its original stopped state after inspection. The historical run `40280429009` remains unchanged: candidate `GLOBAL_CHECKPOINT_BUDGET` in VERIFYING with `actual=null`; baseline exit 137 in ANALYZING. Historical source-match status remains 9 verified, 4 mismatched and 9 unavailable; the result/checkpoint ciphertext remains unavailable.

Machine-readable evidence: `docs/evidence/SCALE001_V1_CHECKPOINT_COUNTER_PREFLIGHT_20261029.json` (SHA-256 `f736e86335eeb47dac90904390046ab73c365087ef4fa53586ac4e60839a8387`). The four original databases were re-opened read-only and retain their saved hashes, SQLite integrity `ok`, and zero FK violations. **SCALE-001 remains NOT QUALIFIED; Commercial V1 remains DEVELOPMENT IN PROGRESS.**


### Preflight fail-closed review

The final static review requires non-empty GitHub `ImageOS` and `ImageVersion` values and fails if `docker info` does not identify a Linux engine with cgroup v2. The exact 768,000,000-byte memory and zero-swap kernel file assertions remain in the resource probe step. Both embedded scripts still pass `bash -n`; the workflow remains undispatched.


### GitHub dispatch prerequisite

GitHub documentation requires a `workflow_dispatch` file to exist on the default branch before the manual run can be triggered. This local-only workflow is not yet on that branch, and this task prohibits changing `main` or the shared PR, so its run remains blocked by scope and was not dispatched. See [GitHub manual workflow guidance](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
