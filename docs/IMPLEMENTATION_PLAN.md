# ProjectTrace implementation plan

The existing ProjectTrace-AI is outside this project's scope. Project folder: ProjectTrace.

Build in dependency order, preserving an executable product at each step.

1. Foundation: FastAPI modular monolith, SQLAlchemy, Alembic, tenant and repository access controls, cookie sessions, CSRF, worker entry point, React/TypeScript design system.
2. Core: bounded untrusted-file ingestion, content-addressed snapshots, deterministic claim extraction/verification, provenance, evidence edges, history, drift, impact, grounded investigation.
3. Workflow: base/head comparison, policy gate, review and expiring exceptions, append-only audit, signed/idempotent GitHub webhook receipt.
4. Analysis: Python AST SAST/quality, conservative JS/Java pattern adapters, masked secrets, static IaC, manifest/lockfile dependencies, CycloneDX, cached OSV adapter.
5. Product: Northstar Labs deterministic fixture repositories (JWT-to-session PR, SAST, dependency, secret, infrastructure, API/architecture drift, clean system), explicit demo labelling, connected evidence inspector and all primary pages.
6. Validation: analyzer corpus, tenant/ACL/RBAC/CSRF/archive/webhook tests, migration upgrade/downgrade, frontend tests, browser workflow, dependency audit, measured performance.
7. Delivery: Compose, CI, threat model, operating and demo guides, release report documenting actual verification and remaining gates.

## Execution constraints

Docker is not installed in the execution environment. SQLite is an explicitly local development adapter; production design uses PostgreSQL. Container integration gates must be distinguished from native tests. Live SCM, cloud and optional security providers require authorized credentials; no provider is shown as connected without a tested connection. External AI is disabled by default. Semantic retrieval and enterprise identity must not be claimed before implemented and evaluated.

## Release gates

No repository execution; bounded input; current-snapshot evidence for each conclusion; tenant and repository ACL on every resource; secret redaction before persistence/display; validated mutations; transactional append-oriented audit; passing critical automated tests; visual demo review; honest integration and production status.
