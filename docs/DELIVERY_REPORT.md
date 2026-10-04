# ProjectTrace delivery report

Date: 4 October 2026. Project folder: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`.

**Status: working, tested local demo/static-analysis MVP. The complete industry master specification and production release gates remain incomplete.** The existing `ProjectTrace-AI` project was not modified. No commit, push, deployment, cloud resource creation or live check publication was performed.

## 1. Product summary

ProjectTrace connects engineering intent to source evidence, detects scoped contradictions and drift, and records ownership and human decisions. The Northstar Labs demo is deterministic and visibly labeled DEMO DATA. Counts are computed from stored current-snapshot records rather than generated marketing metrics.

## 2. Architecture

React/TypeScript/Vite, TanStack Query/Table and a lazily loaded React Flow view. FastAPI/Pydantic, SQLAlchemy, Alembic, relational evidence documents and optional Celery workers. SQLite is the tested native local adapter; PostgreSQL/Redis container configuration is supplied but unverified in this environment.

## 3. Repository structure

`frontend/`: application/design system, frontend tests and browser tests. `backend/`: scoped persistence, sessions, API, seed and migrations. `analyzers/`: bounded static engine. `integrations/`: GitHub/OSV transport and external-evidence normalization. `workers/`: optional provider tasks. `infrastructure/`: container/proxy configuration. `samples/`: safe data fixtures and real cached OSV responses. `tests/`: isolated analyzer/security/API/migration/backup tests. `scripts/`: startup/operator/benchmark/backup tools. `prompts/`: versioned AI boundary contract. `docs/` and `benchmarks/`: operating/reference material and expected results. No empty feature directories were created.

## 4. ProjectTrace core features

Bounded ZIP/text intake; content-addressed snapshots; deterministic atomic claim extraction/decomposition; evidence provenance/authority; explicit snapshot and analyzer/rule scope; claim history, drift, changed-file impact, grounded investigation, human reviews and audit.

## 5. Quality features

Python AST complexity/function-length checks and explicit parse failure reporting. No arbitrary maintainability score. Full JS/Java quality adapters, duplication/control-flow/technical-debt models are not implemented.

## 6. Security features

Python static rules for dynamic SQL, explicit shell execution, unsafe deserialization and weak digests; conservative JS/Java eval patterns. Rules retain CWE when appropriate, severity, confidence, source line, explanation, version and remediation. These are narrow static patterns, not full taint coverage or proof of exploitability.

## 7. Supply-chain features

npm lockfile and pinned Python requirement parsing; direct/transitive labels where known; exact-version cached OSV advisories with source IDs and provider severity. Other package versions are explicitly NOT_CHECKED. CycloneDX 1.5 export includes packages, available license names and known manifest-root relationships. Complete dependency reachability, Maven/Gradle, SPDX and license compliance are deferred. Dependency locks for this application are provided and audited.

## 8. Infrastructure features

Static privileged-container, root-user and public-storage-ACL detection. Imported IaC is not executed. Compose and container configuration are provided, with no claim of runtime cloud control verification.

## 9. Cloud features

The Cloud page explains the missing authorized inventory connection and links to static infrastructure evidence. Live cloud inventories, exposure/IAM models and cross-resource attack paths are not implemented.

## 10. Evidence Graph

Stored tenant/repository-scoped nodes and edges, supporting/documenting/contradicting/detection/dependency relationships, focus/relationship filters and node inspection. This is an evidence neighborhood, not fabricated runtime topology.

## 11. Claim Ledger

Verification status, severity, confidence, review state, owner and source are independent. Technology imports remain INFERRED; missing evidence remains UNVERIFIED. The demo authentication claim has actual AST-supported VERIFIED → STALE → CONTRADICTED history. Broad semantic extraction, runtime claims and full claim-type coverage remain future work.

## 12. Drift / impact

Same-repository base/head comparison records changed files and claim transitions. Unchanged file analyzer results reuse SHA-256/version cache entries; claims are reverified against combined current evidence. API/architecture absence creates uncertainty/review rather than invented disproof. Full graph-targeted selective claim scheduling is not implemented.

## 13. PR workflow

Demo PR #1842 has actual base/head fixture analysis, changed files, affected claims and advisory policies. GitHub code includes temporary installation authentication, bounded allowlisted tree/blob fetch, signed unique webhook receipt, optional worker processing and opt-in neutral check publication. There are no configured credentials here, so **live webhook-to-check verification is not passed**. Delivery acknowledgement is distinct from completed analysis/publication.

## 14. Policies

Default advisory policy v1 explains critical/high security and contradiction review outcomes. Gate recomputes from current review/exception records. Privileged risk acceptance requires expiry; expired exceptions no longer bypass review. Readable custom policy building and organization-specific merge enforcement are not implemented.

## 15. External integrations

GitHub transport contracts and selected mocked tests; OSV public query adapter and cached fixture response; external-provider normalization protocol. GitHub, SonarQube, Wiz, live cloud and external AI show NOT_CONFIGURED in the delivered local workspace. Live SonarQube/Wiz adapters and source-permission synchronization remain deferred. GitHub provider endpoints were checked against official [Git tree](https://docs.github.com/en/rest/git/trees) and [check-run](https://docs.github.com/en/rest/checks/runs) documentation; that does not constitute live integration verification.

## 16. Security controls

Explicit organization and repository ACLs across reads/investigation/graph/audit/exports; Argon2id; opaque rotating HttpOnly/SameSite sessions; logout invalidation; exact Origin and CSRF checks; role enforcement; optimistic review versions; unique provider mapping and webhook deliveries; bounded requests; safe in-memory ZIP reading; no repository execution; secret-pattern redaction; secure-header/proxy configuration; no external AI calls; validated future AI citation contract. Heuristic redaction can miss secrets, and the current parser has not been OS-sandboxed. Application audit is append-oriented, not DBA-tamper-proof.

## 17. Scalability controls

Content hashes/version-scoped same-repository reuse, bounded import limits, query limits, connection pre-ping, optional worker time limits/prefetch and local rate limits. Synchronous local imports, snapshot JSON payloads and in-process limits need production evolution. Distributed quotas, outbox/automatic dead-letter dispatch, fairness and queue saturation are not validated.

## 18. Test results

| Check | Actual result |
|---|---|
| Backend pytest | 49 passed; one upstream TestClient deprecation warning |
| Ruff | Passed |
| Python compile check | Passed |
| TypeScript + Vite production build | Passed; graph split into an optional chunk |
| Vitest / React Testing Library | 3 passed |
| Playwright desktop/mobile workflows | 2 passed, including primary page navigation and review/audit |
| pip-audit lockfile | No known vulnerabilities in checked dependency set |
| npm audit | 0 known vulnerabilities in checked dependency set |
| Alembic | Fresh SQLite upgrade, rollback and re-upgrade passed; provider uniqueness included |
| Local backup | Consistent copy/integrity/recovery reads passed; record and audit counts matched |
| Docker/PostgreSQL/Redis | Not executed; Docker unavailable |
| GitHub App live | Not verified; App ID/private key/installation ID/webhook secret absent |

Tests are isolated except browser review events in the labeled demo. The passing tests do not certify the entire master specification or establish a population-level scanner false-positive rate.

## 19. Performance measurements

Measured Windows/Python 3.14 local fixtures; no external provider calls.

| Workload | Runs/requests | Median | p95 |
|---|---:|---:|---:|
| Identity head static scan | 50 | 0.336 ms | 1.147 ms |
| 500-file static fixture | 20 | 33.980 ms | 44.999 ms |
| Same 500 files using prior cache | 20 | 6.505 ms | 19.832 ms |
| Workspace API, four concurrent clients | 20 | 31.58 ms | 57.38 ms |
| Grounded question API, four concurrent clients | 20 | 21.50 ms | 49.63 ms |

The 40-request API smoke load had zero errors; client throughput was 7.29 requests/second including connection setup. Small-sample p99/max values and the raw environment notes are in the benchmark JSON files. These are local measurements, not production capacity or enterprise-load claims. Fetch/queue/embedding/cloud timings are not measured because those services are not active.

## 20. UI/UX validation

Every primary navigation page was opened by Playwright and captured. The tested workflow had no browser application exceptions and no document-width overflow at desktop or 390-pixel mobile sizes. Visual checks covered overview, evidence/source inspection, graph, PR, mobile investigation and claim history. Horizontal scrolling is deliberate for dense tables and long source lines. Keyboard dialogs, textual status badges and skip-to-content navigation are present; a full independent accessibility audit is not complete.

## 21. Demo workflow

Open the labeled Northstar demo → authentication story → evidence/history → PR gate → findings/dependencies → drift → focused graph → engineering question → confirm with reason → audit. Bundled fonts and deterministic fixtures make the demo independent of live GitHub/LLM/cloud uptime.

## 22. Known limitations

The full enterprise domain schema, multiple components per repository, inherited/revoked SCM permissions, OIDC/SSO, object-storage lifecycle, deletion/retention UI, pgvector/hybrid retrieval, broad language parsing/taint analysis, custom policies, live cloud/provider integrations, distributed limits, parser isolation and full operations are incomplete. SCA refresh/coverage is narrow; no runtime reachability is claimed. Local passwords exist but production identity lifecycle is not complete. The native database and container configuration have different unverified deployment behavior.

## 23. Intentionally deferred features and blocked verification

Credentials/infrastructure block live provider and deployed-stack tests: Docker is absent, and none of the four required GitHub App environment values are configured. Additional enterprise implementation listed above is also deferred; it is **not** accurate to say credentials alone would complete the whole product. Production release remains blocked by both missing verification and remaining engineering.

## 24. Exact local startup

The dependencies and demo data are already installed in the Desktop project in this environment. From PowerShell:

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace'
& .\scripts\start.ps1
```

If the existing local servers are running, open http://127.0.0.1:5181 directly. Do not start duplicate servers. If scripts are restricted by local policy, use two foreground terminals:

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\frontend'
npm.cmd run dev
```

Fresh setup and separate CMD syntax are in README.md. Native API: http://127.0.0.1:8011; local interactive API reference: /api/docs. APP_ENV=production disables demo login and API docs.

## 25. Production deployment requirements

Complete the engineering gaps; validate TLS/identity/source grants; configure approved SCM installation credentials and least privileges; test migrations/restores against PostgreSQL; validate Redis queue/failure handling and isolated workers; implement source retention/deletion and object storage; run production security, load and recovery evaluations; scan/pin release images; validate staging E2E and backups; then approve the chosen deployment environment. No production-ready or industry-equivalent maturity claim is made.
