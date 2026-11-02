# SCALE-001 checkpoint policy decision record

Status: **CP-B investigation authorized; policy adoption and implementation remain pending approval**\
Decision scope: checkpoint format/admission only. The sanitizer supported-input policy is separate.\
SCALE-001: **NOT QUALIFIED**. Commercial V1: **DEVELOPMENT IN PROGRESS**.

No explicit checkpoint product-owner approval was found in the current policy proposal, readiness report, ADR, integrated gate, progress record or retained run evidence. No approver or approval date is recorded.

## CP-A - Retain v1 checkpoint semantics

Keep the `projecttrace-analysis-checkpoint-v1` restore behavior, the complete raw UTF-8 JSON envelope admission unit, the 64,000,000-byte maximum and current fail-closed behavior.

- **User impact:** A result above this checkpoint budget remains unsupported through this path and may fail before publication. CP-A preserves behavior; it does not solve the observed constrained failure.
- **Compatibility:** Keep old v1 checkpoints readable. Preserve v1 result types, `files` list normalization, ordering and independent decoded collection behavior. Any optimization must make the same complete raw-byte admission decision.
- **Resources and security:** Preserve encrypted storage, HMAC/digest and scope checks, tenant fencing, expiry, cancellation, atomicity, spill quotas and worker recovery. No limit increase or partial publication.
- **Still required:** Source-matched failed-result byte attribution; exact restore/downstream retry equivalence; Linux cgroup, cold/warm/incremental output, cancellation/exhaustion, broker/database, tenant concurrency and publication tests.
- **Current evidence:** Technically least disruptive, but not product-approved and does not complete the full workload.

## CP-B - Authorize formal checkpoint-format policy investigation

Authorize design and measurement work for a versioned alternative that may use paged or streamed encrypted storage. This is investigation only. It does not authorize implementation, migration, deployment, a changed limit or qualification.

- **User impact:** Could inform future support for results that do not fit v1. It makes no availability or workload-success promise.
- **Compatibility:** Define a versioned format, preserve v1 reads, plan writer/reader rollout, persisted-checkpoint compatibility and migration/rollback where required.
- **Resources and security:** Define aggregate logical admission separately from encrypted-storage overhead. Prove memory, disk, CPU/time and cleanup bounds. Preserve encryption/HMAC, tenant/scope checks, integrity, expiry, cancellation, atomicity and recovery.
- **Still required:** Source-matched result size; exact type/order/alias/mutation behavior; cold/warm/incremental output equality; quota and interrupted-write cleanup; fresh-worker/duplicate-delivery recovery; tenant concurrency; PostgreSQL/Redis-Celery and Linux cgroup acceptance.
- **Current evidence:** The dirty candidate lowers memory in an owned synthetic fixture but differs in container/alias semantics and quota unit. The failed result object is absent. This does not support adoption.

## Product-owner choice

- [ ] **CP-A** - Retain v1 semantics and admission policy.
- [ ] **CP-B** - Authorize formal checkpoint-format policy investigation only.

Approver: **Not recorded**\
Decision date: **Not recorded**\
Decision state: **PENDING_PRODUCT_OWNER_APPROVAL**

## Separate sanitizer policy

The supported-input/sanitizer decision independently remains **PENDING_PRODUCT_OWNER_APPROVAL**. The 1,000,000-node cap and admission behavior are unchanged. This record does not choose sanitizer Option A or B.

## Release status

The checkpoint maximum remains 64,000,000 raw bytes; the sanitizer limit remains 1,000,000 nodes; the owned 50k fixture remains over it at 1,115,947. The historical receipt remains `actual=null`. No production source, schema, migration, limit or release gate changed. **SCALE-001 NOT QUALIFIED; Commercial V1 DEVELOPMENT IN PROGRESS.**

## CP-B investigation authorization and finding (2026-10-29)

The current task authorizes **CP-B investigation only**. It does not approve a new checkpoint format, changed admission unit, migration, deployment, or qualification. SP-B investigation is separately authorized; its sanitizer policy and supported-input decision remain pending. The limits remain 64,000,000 bytes of complete v1 raw UTF-8 JSON before encryption and 1,000,000 sanitizer nodes.

Authenticated inspection of [run 40280429009](https://github.com/maninani12/ProjectTrace/actions/runs/40280429009) and fresh downloads of its candidate/baseline artifacts confirm the candidate failed with `GLOBAL_CHECKPOINT_BUDGET` in `VERIFYING`, after 1,875.465 seconds. The historical writer stops when the complete normalized v1 JSON envelope crosses 64,000,000 bytes. The safe receipt intentionally retains `actual=null`; exact size and per-field attribution remain unknown. The measured `GLOBAL_CHECKPOINT` operation was about 2.069 seconds, versus about 523.709 seconds for the whole `VERIFYING` stage. The principal measured time inside that stage was `FINAL_IDENTITY` at 301.929 seconds, followed by quality building at 183.295 seconds. This is a separate runtime issue; it does not establish a checkpoint serialization bottleneck for the whole stage.

The dirty paged candidate remains unsuitable for adoption: tests establish value equality only after materialization, while v1 returns a built-in `list` for `files`, independent decoded metric lists, and independent mutation behavior. The candidate returns `ReplayRows`, preserves collection aliases, and accounts encrypted page/manifest bytes instead of the v1 raw-JSON admission unit. Compression or paging cannot make a raw v1 envelope above the current limit admissible without changing that unit. A future design must count exact logical v1 JSON before compression, retain v1 reads, bound all framing/staging/replay resources, and preserve list/dict types, order, duplicates, and mutation semantics. If a future proposal changes admission semantics to support an over-limit result, it needs a separate explicit policy decision.

Detailed measurements, provenance, artifact hashes, local test results, and Linux readiness are in `docs/evidence/SCALE001_CP_B_SP_B_INVESTIGATION_20261029.json`. **No production source or limit changed; SCALE-001 remains NOT QUALIFIED.**
