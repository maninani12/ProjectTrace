# Enterprise hardening baseline

Inspected 7 October 2026 (Asia/Calcutta) before implementation under the new master prompt. Packaging ancestry at inspection: `663770fffd4b1f5f532b6bd7b59949eb1183a3ee`, plus existing uncommitted source. This audit uses source, routes, schemas and fixtures; prior validation reports are historical evidence only. The exact new prompt is preserved separately as ENTERPRISE_HARDENING_SPECIFICATION.txt.

## Inspected source and architecture

The repository is a modular monolith with workers. All backend/analyzer/integration/worker/script/test/migration modules, frontend route/module/test inventory, deployment files and CI workflow were inventoried. Critical persistence, comparison, fingerprints, classification, profiles/gates, authentication, transport, queue and trust projections were inspected directly. No AGENTS.md was found in the repository or checked workspace/Desktop trees. Existing local data and uncommitted edits must be preserved; no auto-commit/push or history rewrite is authorized.

| Capability | Current classification | Source evidence and gap |
| --- | --- | --- |
| Backend stack | IMPLEMENTED | FastAPI/Pydantic, SQLAlchemy, Alembic, Argon2, HttpOnly sessions, CSRF/origin checks; backend/main.py, security.py |
| Frontend stack | IMPLEMENTED | React/TypeScript/Vite, TanStack Query/Table, lazy React Flow, public prerender, Guide, login/import; frontend/src and scripts/build.mjs |
| DB model | PARTIAL | Record is authoritative for snapshots/evidence/findings/claims/graph/reviews; native/quality/cloud/audit/OIDC projections exist. No generic indexed FindingIdentity/Occurrence/History or Blob/SourceFile/component storage model |
| Queue/worker | PARTIAL | Durable jobs, encrypted retained input, Celery/Redis, retries/cancel/lease expiry. Admission scans tenant jobs and caps ten tenant/two repository active jobs; no global fair scheduler, supersession or concurrent 100-PR proof |
| Native analyzers | PARTIAL | CPython AST, Tree-sitter JS/JSX/TS/TSX/Java helpers, bounded HCL/YAML/JSON/Dockerfile helper, selected flow/security/secret/dependency/claim rules. No imported execution |
| Language support | PARTIAL | Eleven registry rows explicitly partial; unsupported-source inventory exists, but Trust & Coverage currently renders a capability registry rather than a full per-snapshot file/LOC/state summary |
| Rule model | PARTIAL | Versioned quality/native metadata, severities, selected STABLE/BETA labels, precision UNMEASURED and default blocking disabled. No complete qualification/promotion evaluation framework |
| Native fingerprints | PARTIAL | native-statement-v1 hashes normalized line text, rule/path/resource/explanation/occurrence; location excluded but formatting/multiline/path changes remain sensitive. Review carry uses whole-file security context |
| Quality fingerprints/history | PARTIAL | quality-symbol-v2 plus observation hash, QualityOccurrence, explicit BASE ancestry, resolution/reopen and conservative rename-as-new. No cross-format unified structural lineage or high-confidence file rename reconciliation |
| Quality gate | PARTIAL | PASS/WARNING/REVIEW_REQUIRED/FAIL; NEW_CODE/OVERALL, high/reliability/complexity/duplication, imported/parsed coverage. Results explain thresholds. Selected blocker/required parser/nesting conditions and full team inheritance/history models missing |
| Profiles | PARTIAL | Versioned NativeProfile, recommended/org/repository scopes, quality rule enable/severity/thresholds, audit and optimistic locking. Repository settings copy inherited complete configuration; no team profile/override-only model |
| IaC | PARTIAL | Five native formats; structural resource/static relationships, selected observations, paginated resources/findings. Local Terraform modules, full policy/selector/provider evaluation and other progressive checks missing; no template/build/provider execution |
| Authentication | PARTIAL | Local auth plus single-issuer code/PKCE/nonce/JWKS OIDC with explicit members and revocation. Controlled JIT/groups/provider administration/live IdP verification incomplete |
| GitHub | PARTIAL | GitHub App, signed/idempotent deliveries, bounded source fetch/check metadata; hardcoded api.github.com and deployment credentials. GHES and per-connection secret references/CA/approved transport unimplemented |
| Secrets | PARTIAL | Pattern/context masking, recursive metadata masking, encrypted queue/PKCE input, masked callback logs. No complete managed-key rotation/deletion/archive DLP or comprehensive secret recall |
| LLM | IMPLEMENTED | Disabled; deterministic Ask Engineering, interface/citation checks only. No external provider receives source |
| Source/limits | PARTIAL | 1,000 entries, 10MB total, 512KB/file; full dictionary/cache JSON in snapshots. No streaming/CAS/shards; oversize import rejected rather than indexed and skipped per file |
| Incremental/monorepo | PARTIAL | Unchanged parser/rule cache by content/version and scoped impact exist; repository has one configured component. No bounded whole-monorepo storage/partitioning/component discovery |
| Tenant isolation | PARTIAL | Organization/repository authorization, sensitive IDOR tests and ORM scope guards. Complete compound FKs/RLS and production cache/object/queue containment not proven |
| Audit | PARTIAL | New hash-linked events and optional HMAC head checkpoint; visible legacy unlinked rows. No automatic external immutable retention/rotation |
| Engineering Changes | UNIMPLEMENTED | Drift and graph impact already exist; no correlated EngineeringChange record/API/flagship screen |
| Private deployment | PARTIAL | Non-root backend/frontend Docker assets, Compose PostgreSQL/Redis/Celery/Nginx, backup scripts. Production Helm/object storage/secret manager/TLS/restore acceptance and image supply-chain qualification incomplete |
| Accuracy | UNMEASURED | Small owned synthetic labels exist: enterprise benchmark 22 cases/11 groups, previous quality corpus. No representative open-source/framework/design-partner accuracy or rule qualification |
| Large scale | UNMEASURED | Previous 3M synthetic input was rejected; previous 100 receipts were sequential, concurrency one. No successful large-repo or simultaneous analysis/fairness measurement |

## Verification baseline

Fresh full pytest and frontend unit/build checks were started after source inspection. Their actual results will be appended on completion before relying on the baseline. Previous release totals must not be presented as freshly passed tests. Backend fixtures use isolated temporary databases; live data is not a test reset target. Customer ZIPs/code/IaC remain inert. Browser workflows exist for public/auth/fresh ZIP, quality, native cloud, trust and CEO/mobile investigation; current source has eleven workflows.

Fresh baseline results, before structural identity implementation: **207 backend tests passed in 229.80 seconds**, with one Starlette/httpx deprecation warning. **22 frontend tests passed** across four files; TypeScript and production build passed, including 40 public routes. These measurements establish the starting state, not completion of the hardening specification.

## Operational availability

Local Windows API/UI are on 8011/5181. Docker is not on PATH; `wsl --list --quiet` reports WSL is not installed. SSH exists, but no current approved staging host/provider credentials have been supplied. Live GHES/IdP and production PostgreSQL/Redis/S3/TLS restore acceptance therefore need an approved environment; implementation and local controlled tests can proceed independently. These constraints do not justify declaring missing application architecture complete.

## Ordered implementation review

Follow the master's phase order: structural identity/migration first, then complete inventory/coverage, profiles/gates, accuracy/maturity, parser/native/IaC depth, full trust views, correlated Engineering Changes, enterprise identity/GHES, streaming/incremental components, measured scale/fair scheduling, security/audit and private deployment. Preserve the authoritative Record/Evidence Graph model; normalized projections must refer to it and remain scoped. Keep unavailable capabilities visibly partial and record real external blockers. Never relabel documentation or a UI as backend proof.
