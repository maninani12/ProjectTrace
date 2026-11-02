# SCALE-001 supported input boundary proposal

Date: 2026-10-29\
Decision state: **PENDING_PRODUCT_OWNER_APPROVAL**\
Recommendation: **OPTION_A — retain the existing aggregate guard**

This document is an internal proposal for product-owner review. It records an
engineering recommendation; it is not evidence of formal approval and does
not change current product claims or runtime behavior.

## Proposed policy

Keep the existing aggregate snapshot sanitizer limit at **1,000,000 nodes**.
The reproduced 50k fixture contains **1,115,947 nodes**, so the existing rule
rejects it by **115,947 nodes**. The counter applies to the complete logical
snapshot passed to the final sanitizer call. Resetting the counter per page
would change aggregate admission semantics and is not an acceptable workaround
under this proposal.

The current evidence does not justify a higher resource budget. The 50k run
was rejected before final snapshot SQL persistence, `Generation.validate`, or
BASE/HEAD comparison. Those successful-path costs, memory bounds, and recovery
behavior therefore remain unknown. A measured map-only improvement does not
resolve this admission failure.

Under proposed Option A, snapshots whose complete logical value exceeds the
existing aggregate cap are unsupported unless an explicitly approved policy
change is made. This describes the proposed supported-input boundary; it does
not claim that a product owner has approved it or that official supported-scale
claims have been updated.

## Product and operational impact

Large repositories whose assembled snapshot exceeds the cap cannot complete
analysis under the current rule, even when their serialized input size and
nesting depth are within other limits. The 50k fixture is one demonstrated
example, not a universal repository-size conversion: node count depends on the
complete logical snapshot and cannot be inferred from the repository's file
count alone. Product positioning should therefore avoid promising 50k support
or treating the 50k target as qualified while this decision is pending.

For the observed rejected run, the job ended `FAILED`, the generation remained
`STAGING`, there was no snapshot ID or published pointer, and the job exposed a
generic supported-limits error. Operators should expect that an over-limit
attempt fails before final snapshot publication; the exact resource cost and
completion time for other over-limit inputs have not been established. This
proposal does not request an error-message or runtime behavior change.

## Evidence required to revisit

A future policy change should be considered only after the product owner
defines the supported input target and explicitly approves the policy. The
engineering decision record should then include evidence for:

- a documented aggregate counting definition and admission behavior;
- successful complete snapshot persistence and validation at the proposed
  target, including BASE/HEAD comparisons;
- peak memory, CPU, elapsed time, disk growth, and serialized data at relevant
  boundaries under declared resource limits;
- cancellation, restart, retry, cleanup, and publication recovery behavior;
- database/backend coverage and concurrency/tenant-isolation results required
  by the release criteria; and
- updated support messaging and release gates after approval.

No per-page counter reset, larger cap, segmented storage, or alternate
admission path is proposed here.

## Approval search

The existing policy readiness report recommends Option A subject to explicit
product-owner approval. ADR 0007 records that its earlier page-local proposal
is still proposed and not approved. The reviewed current records contain no
explicit product-owner approval for Option A. Accordingly, the decision state
remains **PENDING_PRODUCT_OWNER_APPROVAL**.

## Qualification status

**SCALE-001 remains NOT QUALIFIED. Commercial V1 remains DEVELOPMENT IN
PROGRESS.** This proposal does not close any qualification or release gate.
