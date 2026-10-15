# ADR proposal: durable repository analysis generations

Historical design proposal, 14 October 2026. The implemented 0024/0025 design, qualification and remaining limits are now documented in [Generation and learning](GENERATION_AND_LEARNING.md). This proposal is retained for traceability; it is not the current implementation-status declaration.

## Problem and requirements

Current file cache commits preserve completed native observations, but global analysis and graph publication still require a single execution/output transaction. Retrying that execution does not resume independent global stages. Increasing timeouts does not address the problem.

DUR-001: incomplete generation output is private. DUR-002: each work unit has immutable inputs and idempotent outputs. DUR-003: cancellation and supersession prevent publication. DUR-004: stale worker attempts cannot modify receipts/output. DUR-005: historical snapshot content and explicit snapshot selection remain stable. DUR-006: manifest, analyzer/parser/rule/profile versions and source revision are attributable. DUR-007: all relationships and object keys include tenant/repository scope. DUR-008: processing, reads and publication are bounded by measured budgets. DUR-009: coverage failures remain explicit and cannot become VERIFIED claims.

## Proposed additive persistence boundary

Reuse existing job Record, repository/user identities, SourceInventory, SourceInventoryFile, SourceBlob and parser artifacts. Do not duplicate source or user identities.

- AnalysisGeneration: composite tenant/repository identity, job reference, immutable inventory/manifest digest, configuration signature, source revision, state, cancellation and creation/publication timestamps.
- AnalysisWorkUnit: generation identity, stage, stable shard key, dependency references, lease token/attempt, lease expiry, retry budget and state; unique generation/stage/shard identity.
- StageReceipt: unique unit/input-signature identity, fenced producing attempt, immutable output digest, record counts, coverage and provenance. Store bounded payloads in tenant-encrypted artifacts; no raw source in job JSON.
- Private generation output: existing domain output shapes under explicit generation ownership, inaccessible to current public readers until promotion. Decide separate staging tables versus generation-qualified current tables only after enumerating every query/export/history path. Do not batch-commit unqualified records into public kinds.
- Published pointer: repository/branch scope and generation/snapshot identity, advanced with compare-and-swap under a short transaction. Preserve explicit historical snapshot reads.

Every foreign key must validate tenant/repository/generation together in PostgreSQL and SQLite. Use unique constraints for idempotence, not check-then-insert alone. Add reviewed migration 0021 only with backfill, preservation and downgrade tests; no existing migration is replaced. Existing snapshots remain readable during rollout.

## Stage graph

| Stage | Dependency and durable output |
|---|---|
| 1 Source admission | Authorization, limits, durable intake receipt |
| 2 Safe capture | Admission; retained encrypted bytes and validated inventory |
| 3 Inventory | Capture; immutable sorted file manifest and content hashes |
| 4 Source classification | Inventory; supported/excluded/generated/vendor/encoding scope |
| 5 File parsing | Classification; bounded per-component/file/byte shards and parser receipts |
| 6 Native analysis | Parsing; file-local native observations and coverage |
| 7 Finding normalization | Native observations; stable versioned finding identities |
| 8 Claim extraction | Classified documentation and observations; atomic scoped claims |
| 9 Verification | Claims plus normalized observations; evidence-backed status/uncertainty |
| 10 Evidence construction | Verification; private evidence records with source citations |
| 11 Graph correlation | Evidence; sharded typed nodes/edges and bounded join receipts |
| 12 Impact and history | Graph plus pinned previous published generation; explicit historical deltas |
| 13 Policy evaluation | Coverage, findings, claims and pinned policy revision |
| 14 Publication validation | All required receipts; scoped references/counts/digests/coverage/signatures |
| 15 Atomic publication | Validation; final scoped pointer and immutable completion receipt |

Capture can be safely restartable from the retained input receipt before fine-grained resume is available. Immutable manifest completeness must precede analysis. Native parser artifacts remain reusable but must match full input/configuration identity; profile-dependent global results cannot be inferred from a file cache hit.

## Leases, recovery and concurrency

Claim eligible work with a short transaction and tenant/repository admission controls. Persist a fresh fencing token and attempt before execution. Renewal and receipt insertion must condition on scope, state, token and cancellation, and verify affected rows. Do not retain database transactions during parser CPU or provider I/O. A crash before a receipt means the unit is replayed; a crash after a valid receipt means its dependent stages can continue without recomputing completed work. Lease expiry alone does not grant a stale attempt ownership. Receipt/output acceptance must atomically compare the active token.

Cancellation updates generation state and stops new claims; executing attempts cannot commit a receipt or pointer after cancellation wins. Cleanup is retention-governed and never deletes published historical generations. Revoke repository/feature access at dispatch, claim, receipt acceptance and publication. Worker identity is recorded and resolved through current governance; tenant context is not inferred from untrusted payload fields.

## Publication and reader migration

A short transaction locks the generation, checks cancellation/authorization and every required receipt, validates tenant-qualified references, verifies graph and coverage completeness, creates/links the final immutable snapshot, and advances the branch pointer conditionally. Partial coverage can publish only with an explicitly PARTIAL result, never a fully verified label.

Migrate workspace, direct record APIs, graph traversal, exports, finding history, policies, review actions, cache projections and source reads together. Audit direct record IDs and joins for staging leakage. Refuse readiness when a required receipt is missing, mismatched, stale or duplicated. Do not infer readiness merely from a worker's last stage string.

## Acceptance before activation

- Kill/restart before and after each receipt and between validation/pointer commit.
- Duplicate delivery and concurrent claims produce one accepted result per unit.
- Token replacement/cancellation/access revocation at each persistence boundary prevents stale output.
- Cross-tenant direct SQL/FK, API record access, graph traversal, exports and object keys fail closed.
- Published old snapshots are stable while a new generation is incomplete.
- Analyzer/profile/manifest changes invalidate only affected receipts and retain provenance.
- Upgrade populated migration-0020 databases without record loss; rehearse rollback before activation.
- Execute true PostgreSQL concurrency tests; SQLite simulation is additional evidence only.
- Pin controlled, PetClinic, OpenMetadata and TypeScript input revisions; measure cold/warm execution, peak memory, per-stage runtime, retries and bounded publication.

## Rollout and operational constraints

Ship disabled behind an operator-owned feature flag until reader isolation and PostgreSQL failure tests pass. Retain legacy atomic publication for small inputs during migration. Record queue depth, unit age, retries, coverage and publication duration without source/secret payloads. Backpressure caps pending/running units per tenant and repository. Encrypted artifact retention must outlive retry windows; cleanup must consult generation references.

Onboarding remains behind the P0 gates. Its learning resources should pin published snapshot and evidence IDs, and enforce prior/target repository access independently. A technology observed in a prior repository is not proof of participant competence. Both new-hire and internal-transfer workflows require persisted assignments, explicit knowledge evidence and scoped mentor review.

This proposal must be reconciled with existing domain.py persistence and all read paths before schema implementation. It does not establish completion of the requested durable pipeline.
