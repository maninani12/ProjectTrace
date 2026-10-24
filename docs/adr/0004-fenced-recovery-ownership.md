# ADR 0004 — Recovery respects committed outcomes and one lease authority

Status: implemented for review; acceptance is the current milestone PR's measured CI, not this document alone.

## Context

The database publishes a snapshot/generation and terminal job before Celery's worker cleanup and late acknowledgement. A process can die between those steps. The fair scheduler stores the authoritative fencing token/current lease in QueueEntry; the job JSON contains stage-time projections which may be older. The legacy recovery loop previously ignored that distinction. Celery maintenance also scanned local-runner leases.

The baseline new regression selection reproduced seven failures: five terminal outcomes reopened, one renewed lease overridden by fallback, and one local job recovered by Celery maintenance. Existing fresh-process/generation tests had covered crashes before promotion and lost commit acknowledgement, but did not close this post-commit cleanup gap.

## Decision

- Keep current data models, message contract (job IDs only), retained encrypted source, attempt budgets and published evidence intact.
- Recovery serializes with scheduler admission, locks candidate queue rows with SKIP LOCKED, refreshes the job under its row lock, and reconciles committed terminal states without editing job data/history/counters or enqueueing them.
- QueueEntry is the lease authority for scheduled jobs. Only jobs without any scheduler entry use legacy JSON-lease recovery; they retain the existing bounded retained-input fallback.
- Celery maintenance recovers only CELERY execution. The local runner retains LOCAL recovery responsibility. Neither can steal the other's expired work.
- Exhausted recovery and unavailable input have bounded, sanitized error codes/messages. At most two resumptions are permitted; the final exhaustion decision is retained in attempt history.
- Add a dedicated real Redis/PostgreSQL/prefork acceptance job. Failure gates live only in `integration_tests`, not application entry points/images. Natural database lease expiry is observed; production ACK, visibility and security settings are unchanged.
- Stack the new draft PR on the exact successful PR #1 branch. Do not merge PR #1 merely to establish an integration base.

## Consequences and limits

The fix preserves manually authorized retry of PARTIAL/FAILED outcomes: that API explicitly transitions the job to QUEUED and registers a new attempt. Automatic recovery cannot make that policy decision by overwriting a terminal job. Reconciliation waits for the stale queue lease to become eligible; it is not a new instantaneous terminal-bookkeeping sweeper.

PostgreSQL SKIP LOCKED avoids blocking/recovering a worker that is renewing/publishing under the queue-row fence. SQLite retains its single-writer local semantics. The scheduler-first lock order is preserved. No schema/migration, broker dependency or UI contract change is introduced.

Passing the selected failure tests does not prove natural Redis visibility-timeout redelivery at the default long interval, a production beat process, Redis failover/cluster/TLS/AOF-loss guarantees, live SCM/advisory-provider interruption, sustained capacity, or production disaster recovery. Those remain explicit follow-on qualifications. See the acceptance guide for the exact real vs injected portions of each test.
