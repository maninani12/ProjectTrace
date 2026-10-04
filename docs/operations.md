# Operations

Native startup uses ports 8011/5181 and the local data/projecttrace.db adapter. /health is process liveness; /ready checks database/migration access and explicitly does not verify the worker. Provider state is separate from database readiness.

Review API errors by request ID without logging source or credentials. Signed webhook receipts are retained even when dispatch fails. Inspect job records through authorized record endpoints. Retry/cancel operations are scoped and do not silently delete source evidence. Celery has late acknowledgement, single-task prefetch and time limits; true crash recovery, dead-letter automation and tenant fairness have not been load-tested.

The startup script records API/UI logs under data. Stop only processes identified as this project's API/UI; do not kill other projects occupying default ports. Back up retained data before schema changes. See backup-recovery.md and RELEASE.md for verified/unverified operations.
