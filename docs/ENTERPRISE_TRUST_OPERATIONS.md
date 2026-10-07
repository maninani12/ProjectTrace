# Enterprise hardening operations

Use the current [21 buyer questions](../ENTERPRISE_TRUST_VALIDATION.md) for exact capability status. This is an additive hardening candidate; existing data and historical proof remain preserved. The earlier 1.6.0 operations guide is archived as `operations-enterprise-trust-1.6.0-before-hardening.md` and contains historical deferrals superseded by this work.

- [Private installation, managed secrets, TLS, queues, recovery and rotation](PRIVATE_DEPLOYMENT_GUIDE.md)
- [Upgrade and rollback boundaries](UPGRADE_ENTERPRISE_HARDENING.md)
- [Source egress, tenant controls, helper isolation and audit checkpoints](SECURITY_AND_DATA_EGRESS.md)
- [OIDC provisioning and GHES connections](OIDC_AND_GHES_CONFIGURATION.md)
- [Content inventories, incremental parsing and components](CONTENT_INVENTORY_AND_INCREMENTAL_ANALYSIS.md)
- [Quality profiles and explainable gates](QUALITY_PROFILE_AND_GATE_GUIDE.md)
- [Engineering Changes](ENGINEERING_CHANGES.md)
- [Large repository measurements](LARGE_REPOSITORY_BENCHMARK.md) and [controlled PR load](PR_LOAD_BENCHMARK.md)

Keep operator keys, databases, source blobs and backups private. Do not seed/reset an existing customer database to upgrade it. Default deployment source/AI egress remains disabled. Source, runtime and precision authority are explicit; partial coverage must never be treated as proof of a clean repository.
