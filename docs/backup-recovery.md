# Backup and recovery

15 October 2026 extension: back up generation ownership, receipts, publication pointers and learning tables together with Records, source objects and the encryption key ring. A database-only restore cannot recover encrypted source/learning text without the corresponding keys. Published history survives expiry of private recovery chunks. See [generation recovery](GENERATION_AND_LEARNING.md); local dump/restore evidence does not qualify production RPO/RTO or complete object/key recovery.

Local SQLite: `python -m scripts.backup <new-backup-path>` uses SQLite's consistent backup API, refuses to overwrite a backup and checks database integrity. Recovery verification in this delivery opened the copied database and compared organization/user/repository/domain-record/audit counts. This validates local backup readability, not a production disaster-recovery SLA.

Production PostgreSQL: take a transaction-consistent pg_dump, retain encryption and access policies, restore to a separate staging database, apply the appropriate migration revision, compare relational counts/integrity and run scoped API smoke tests. Object storage must be restored to matching source-version identities. The 2026-10-09 private local staging drill restored a fresh PostgreSQL 17.11 dump into a separate database with identical table row fingerprints/counts; all 214 copied encrypted local source blobs decrypted to their content digests using the separately retained key. The original database was not replaced. This verifies that small local staging set, not managed production or cloud object-storage disaster recovery. See the [current audit](../PROJECTTRACE_PRODUCT_AUDIT_AND_READINESS.md) for commands, timings and limitations.

Choose RPO/RTO from business requirements after measured restore drills. No RPO/RTO guarantee is claimed. Rollback migrations were tested on a disposable local database; rollback a customer database only with an approved recovery plan and validated backup.


## Content-inventory upgrade

New snapshots reference encrypted source blobs. A database-only backup cannot restore those sources. Use `python -m scripts.recovery_bundle` to back up the local DB plus recorded encrypted blobs into a fresh private bundle; restore validates manifest paths/hashes, database constraints and decrypted content identity before creating a fresh destination. Retain analysis keys separately. See PRIVATE_DEPLOYMENT_GUIDE.md for exact commands and key rotation. Do not attach a private bundle to a source release. Managed PostgreSQL/object-store recovery and RPO/RTO remain unmeasured.
