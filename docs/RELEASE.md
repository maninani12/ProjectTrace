# Release gates

## Passed locally

- Runnable React/FastAPI demo with deterministic source-derived records.
- Critical backend analyzer/security tests, frontend tests, TypeScript production build and browser workflows.
- SQLite fresh migrations, rollback/re-upgrade, local consistent-backup integrity and recovery reads.
- Dependency audits of the tested lockfiles.
- Visual review of primary views, desktop/mobile overflow checks and no browser application exceptions in the workflow.

## Not passed — do not call this production ready

- Docker/Compose execution, container scan, PostgreSQL/Redis deployment validation and production backup restore.
- Live GitHub App installation, fetch, private-source access inheritance, webhook-to-worker processing and check publication using real credentials.
- Live SonarQube/Wiz/cloud integrations; external AI evaluations and quotas.
- OIDC/SSO, invitation/member lifecycle, distributed limits, object storage/retention/deletion, encrypted storage policy, parser OS-level sandbox and enterprise operations.
- pgvector/hybrid semantic retrieval, richer language/taint coverage, complete domain schema and multi-component monorepo mapping.
- Population-level precision/recall, distributed load/failure/recovery tests and production security review.

The local MVP is functional and reviewable. The complete master specification is not delivered. This file distinguishes verified local behavior from remaining engineering work and credential/infrastructure gates.
