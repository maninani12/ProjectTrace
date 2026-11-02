# Checkpoint retention, worker ownership and rollback

Local validation scope: the uncommitted continuation work on schema 0026.
This is not production deployment or distributed-broker qualification.

## Retention and worker ownership

Input expiry, global checkpoints, publication drafts and generation recovery
chunks share the same transaction-local expiry ownership guard. Candidate
queries exclude scoped RUNNING leases; maintenance rechecks under the scheduler
admission lock and queue-row locks. PostgreSQL skips renewal-locked rows;
SQLite serializes writers. The real PostgreSQL regression uses the existing
unique-schema fixture and requires an explicitly authorized disposable database.
Windows tests alone do not verify PostgreSQL concurrency.

Cancel-pending active workers remain protected until their normal fence stops
them. Reaping unowned expired input preserves terminal job history and clears
stale queue tokens/leases, preventing an expired attempt from renewing after
cleanup. A malformed scope cannot authorize changes to another tenant's job.

This postpones removal while a worker owns recovery bytes; it does not renew
input/receipt TTLs or make expired data readable. Existing read-time expiry,
encryption/HMAC checks, checkpoint and row quotas remain unchanged. Maintenance
selects bounded identifiers/metadata instead of batches of ciphertext values.
Original cleanup batch sizes remain 1,000 and 250 rows as applicable.

## Receipt compatibility and schema rollback

Version 1 receipts remain readable by the new code. Paged v2 receipts remain v2
after normal private-context expiry. Their digest, dependency identity and
completion history are not rewritten. Snapshots, ownership ledgers, published
generations, pointers and audit history are not expiry garbage.

Migration 0026 intentionally refuses downgrade to 0025 while retained v2
receipts or pages remain. Expiring recovery pages does not make a v2 receipt a
v1 receipt. Resetting `format_version`, deleting historical receipts or weakening
the guard to force downgrade would falsely assert compatibility.

The new normal-expiry regression uses a real admitted v2 receipt, expires only
private chunks, then verifies that downgrade fails closed and preserves the
receipt and database/FK integrity. Empty/legacy-only downgrade support remains
covered by the existing migration tests. This establishes the current safe
boundary, not a reversible conversion of populated v2 history.

## Operator requirements before release

- Back up the database, encrypted object store and independently retained key
  ring as a consistent recovery set. Test restore into a new isolated target.
- Keep a matching schema/reader build. Do not assume older application code
  can interpret current v2 receipts or newer immutable snapshot formats.
- Use a forward fix if populated-history downgrade has not been proven safe.
  Any conversion/rollback plan requires explicit data-compatibility and recovery
  approval; preserving the latest history remains mandatory.
- Validate real PostgreSQL renewal locks, Redis/Celery outage/redelivery and
  process termination before claiming distributed recovery or production RPO/RTO.
- Permanent snapshot storage must never reference these expiring private
  recovery chunks; see proposed ADR 0007, pending user review.

No original database was migrated or modified by these tests.
