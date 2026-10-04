# ProjectTrace current implementation audit — version 1.2

Recorded 4 October 2026 from executable source and fresh checks. Historical reports are retained as prior observations, not validation of this release.

## Input and baseline

`ProjectTrace-main (1).zip` contained 104 files. All matched the existing ProjectTrace checkout after newline normalization. No repository replacement was needed; no commit or push was made.

Seven unparenthesized multi-exception handlers appeared in `backend/main.py`, `analyzers/baseline.py`, `analyzers/engine.py`, and `integrations/github/connector.py`. They are valid Python 3.14 syntax but fail on Python 3.11. They now use tuples. Ruff targets Python 3.11 syntax to preserve that repair; runtime dependency support remains Python 3.14. Both interpreters compiled the project source successfully.

Before feature changes: Ruff passed, 55 backend tests passed, frontend build and six frontend tests passed, and three Playwright workflows passed. Final results are below. No uploaded application code, dependency installer, infrastructure command, or imported test ran.

## Classification

WORKING means verified within the named local scope. PARTIAL means useful bounded behavior with material gaps. UNVERIFIED means implemented/configured but not executed in the corresponding external environment. PLACEHOLDER/DEFERRED must not appear as connected or complete.

| Module | State | Executable evidence / files | Gap and risk | Repair or next validation |
|---|---|---|---|---|
| Local identity, sessions, CSRF | WORKING | `backend/security.py`, `backend/main.py`, API/security tests, password-login browser flow | Enterprise identity/SSO absent | Keep local identity; validate enterprise integration separately |
| Organization/repository isolation | WORKING | Server grants and scoped queries; cross-tenant tests for import, graph, jobs, metrics, caches, SBOM and review | Real PostgreSQL concurrency unverified | Run stack isolation/concurrency tests before deployment |
| ZIP intake and nonexecution | WORKING | `analyzers/engine.py`; path/symlink/ratio/size/count and malicious-input tests | Unsupported formats are skipped; static limits bound large repos | Preserve input bounds; add format adapters deliberately |
| Native analysis lifecycle | WORKING | `backend/jobs.py`; queued/failed/cancelled/partial tests; fresh real workspace browser test | Graph output stages publish at final atomic commit; no streaming progress channel | Poll persisted stages; benchmark long graph transactions |
| Analyzer failure propagation | WORKING | `analyzers/engine.py` independent engine states and safe diagnostics; injected-failure tests | Full process isolation not implemented | Add worker isolation and resource controls before high-risk workloads |
| Async source-import contract | PARTIAL | `backend/queue.py`, `workers/tasks.py`, `tests/test_queue.py`; API202, encrypted input, worker invocation, failure/retry/expiry tested | Real broker delivery, duplicate concurrent delivery and worker restart unverified | Run actual PostgreSQL/Redis/Celery stack |
| Input retention | PARTIAL | Migration0004, `AnalysisInput`, Fernet, completion/cancel deletion, expiry tests, Celery beat task | Scheduler runtime and key rotation unverified; no object-storage adapter | Operate beat and key lifecycle; validate restore/retention |
| Atomic documentation claims | PARTIAL | `analyzers/verifiers.py`; affirmative wording/alias/negation/fenced-text tests | Unsupported semantics/ADRs/runbooks may not extract; no LLM enhancement | Add extractors with expected evidence and false-positive tests |
| Deterministic specialized verifiers | PARTIAL | Technology/database/authentication/API/dependency/testing/CI/infrastructure/configuration registry and cache tests | Authorization/security-control/deployment classes need deeper signals; runtime is unobserved | Never infer implementation from class existence; add supported signal adapters |
| Stable claim/finding lineage | WORKING | `backend/domain.py`, semantic identity, version/history and review-continuity tests | Generic JSON records remain primary domain storage | Normalize gradually without replacing historical records |
| Consistency vs software drift | WORKING | First-snapshot consistency, base/head drift, removed support and analyzer-upgrade tests | Cross-version comparisons with changed source remain bounded static conclusions | Use source hashes and rule versions; retain analysis-change provenance |
| Evidence graph | PARTIAL | Persisted system/component/repository/snapshot/artifact/doc section/API/configuration/CI/policy nodes plus claims/findings/dependencies/evidence | System/component labels are metadata; full modules/classes/calls/cloud/ownership graph absent | Add only supported nodes/edges; never infer runtime topology |
| Graph impact / targeted reverification | WORKING | Reverse stored-edge traversal includes deleted base evidence; actual edge-ID tests; verifier input cache | Static associations; runtime reachability and targeted enterprise-scale scheduling absent | Benchmark representative repos; validate more supported relationships |
| Native Python quality | PARTIAL | AST complexity approximation, length, nesting, oversized class, bare exception tests | Duplication, reliable unreachable-code and framework quality coverage absent | Extend measured rules; no numerical quality score claim |
| Native JS/TS/Java quality | DEFERRED | Lexical security patterns exist; engine limitations explicitly disclose quality parser gap | Proper AST quality adapters absent | Add maintained parser adapters before claiming language quality coverage |
| Native SAST | PARTIAL | Python alias/assigned-SQL/shell/deserialization/digest/HTML/file/SSRF/tempfile/JWT pattern tests; limited lexical JS/Java checks | No complete CFG/interprocedural taint, exploitability proof, general authorization/randomness coverage | Incrementally add conservative source/sink/data-flow checks |
| Secrets | PARTIAL | Masked token/private-key/assignment patterns, URL/env redaction, test/example context, secondary-output privacy tests | Unknown secret forms can be missed; credential validity not tested | Evaluate precision/recall on authorized corpus; never show complete detected values |
| Dependency inventory | PARTIAL | npm/package-lock, requirements, pyproject/Poetry, uv, Maven/Gradle; pnpm/yarn resolved-stanza subsets | Not complete resolution; directness may be UNKNOWN; license often unavailable | Add format/version fixtures and transitive relationship support |
| Advisory coverage | PARTIAL | `backend/advisories.py`, `workers/advisories.py`; all five coverage states, cache/failure/dedup/evidence/policy tests | Live OSV transport verified for two packages only; live queue unverified; full imported-repo refresh disabled locally | Enable authorized package lookup with worker; retain NOT_CHECKED/UNKNOWN_VERSION/CHECK_FAILED |
| SBOM | PARTIAL | CycloneDX export, duplicate component-ID and Maven purl tests | Declaration/root relationships; incomplete ecosystem/runtime/license scope; SPDX deferred | Preserve coverage metadata; improve resolved relationships |
| Native IaC/static cloud | PARTIAL | Anchored privileged/root/public-ACL rules; safe Terraform/Kubernetes fixture cases | Host namespace/capabilities/ingress/encryption/IAM/securityContext semantics mostly absent | Add structured static adapters; never execute IaC |
| Live AWS/Azure/GCP cloud | DEFERRED | Connections schema/status and static-vs-live Cloud UI | No credentials or inventory transport; no CNAPP completeness | Implement read-only APIs with authorized accounts and current official contracts |
| Unified findings/risk | PARTIAL | Normalized fingerprints, rule/version/scope, observed evidence, review state; SCA merges manifests/providers | No deployed risk-path reachability; provider-wide dedup/live correlation absent | Keep explainable factors and provenance; avoid invented severity math |
| PR intelligence | PARTIAL | Base/head snapshots, static delta/impact/advisory gate; GitHub task/check adapter | Private live GitHub PR/check flow unverified | Validate least-privilege App installation with credentials |
| Human review/exceptions/policy | WORKING | Optimistic version checks, role/expiry controls, malformed-expiry fail-closed, unchanged-evidence review reuse; refreshed advisory policy graph | Enterprise policy administration/WORM audit absent | Validate policy configuration and archive controls later |
| Audit trail | WORKING | Append-oriented scoped events, analysis/review/retry/cancel/rule-change/advisory tests | DB administrator can mutate history; no tamper-evident storage/export | Preserve application history; implement enterprise archival separately |
| Ask Engineering | PARTIAL | Scoped deterministic retrieval, evidence IDs, unsupported-answer behavior, browser tests | Keyword baseline; no PostgreSQL FTS/pgvector/hybrid synthesis | Add hybrid retrieval with metadata/graph/freshness and verified citations |
| External AI | DEFERRED | Disabled local setting; no-AI pipeline tested | Structured semantic enhancement and provider invocation absent | Add optional structured contracts with existing-ID validation |
| Optional external evidence | PLACEHOLDER | `integrations/providers.py` normalization contract; Connections says native analysis independent | SonarQube/Wiz/CodeQL/Snyk/Semgrep/Trivy live transports absent | Preserve NOT_CONFIGURED/DEFERRED status; use official APIs and credentials |
| Browser routing/status/inspection | WORKING | React Router paths + old-hash redirects; 15 unit tests, desktop/mobile/browser back/reload tests | Not exhaustive accessibility/usability coverage | Retain calm visual hierarchy; test representative engineering workflows |
| PostgreSQL/Redis/containers | UNVERIFIED | Compose/CI/Dockerfiles, admission locks, Redis atomic rate policy | No Docker/native servers/installed WSL on host | Run migrations/concurrency/queue failure/retry/recovery/restart on real stack before production claim |
| Observability | PARTIAL | Safe structured request/job/stage IDs, elapsed times, cache/provider state; scoped metrics API | Exported tracing/metrics/alerts and traffic capacity absent | Add telemetry backend and validate source/secret exclusion |
| Enterprise identity/retention | DEFERRED | Explicit limits in documentation/settings | OIDC/SSO/SAML/SCIM/advanced RBAC absent | Requires chosen identity/deployment/retention policy |

## Final validation evidence

- Compilation: Python3.14.3 and Python3.11.0, source modules/tests/scripts.
- Ruff: all checks passed.
- Backend: **108 passed**, one upstream Starlette/httpx TestClient deprecation warning; final run98.50s.
- Frontend: TypeScript/Vite build passed; **15 unit tests passed**.
- Playwright: **3 passed**, final56.8s; real password-login/import/native-analysis/review/SBOM/evidence/graph/Ask/second-snapshot/drift/impact/policy/audit/isolation workflow and desktop/mobile demo workflows; zero page errors.
- Migrations: fresh upgrade/downgrade/base/re-upgrade passes; user's preserved DB is0004, integrity `ok`, no foreign-key violations.
- Dependency audits: pip-audit locked Python set reports no known vulnerabilities; npm audit reports0. These are time-specific advisory checks, not security certification.
- Native synthetic corpus: **22/22 expected cases passed**, four false-positive traps with zero forbidden findings. General false-positive rate remains unmeasured.
- Live OSV fixed-endpoint transport: lodash4.17.20 returns5 advisories; fastapi0.142.2 returns0 at the recorded lookup time. This does not validate all imported dependencies or broker behavior.

The initial fresh real browser workflow ran against a migrated SQLite database before Northstar seeding. Later demo/mobile tests seeded only the demo organization. User source was never inserted into Northstar.
