# Backup and recovery

Local SQLite: `python -m scripts.backup <new-backup-path>` uses SQLite's consistent backup API, refuses to overwrite a backup and checks database integrity. Recovery verification in this delivery opened the copied database and compared organization/user/repository/domain-record/audit counts. This validates local backup readability, not a production disaster-recovery SLA.

Production PostgreSQL: take a transaction-consistent pg_dump, retain encryption and access policies, restore to a separate staging database, apply the appropriate migration revision, compare relational counts/integrity and run scoped API smoke tests. Object storage must be restored to matching source-version identities. No PostgreSQL restore or object-storage recovery was run here.

Choose RPO/RTO from business requirements after measured restore drills. No RPO/RTO guarantee is claimed. Rollback migrations were tested on a disposable local database; rollback a customer database only with an approved recovery plan and validated backup.


## Content-inventory upgrade

New snapshots reference encrypted source blobs. A database-only backup cannot restore those sources. Use `python -m scripts.recovery_bundle` to back up the local DB plus recorded encrypted blobs into a fresh private bundle; restore validates manifest paths/hashes, database constraints and decrypted content identity before creating a fresh destination. Retain analysis keys separately. See PRIVATE_DEPLOYMENT_GUIDE.md for exact commands and key rotation. Do not attach a private bundle to a source release. Managed PostgreSQL/object-store recovery and RPO/RTO remain unmeasured.
