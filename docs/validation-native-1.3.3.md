# FINAL PRODUCT VALIDATION — ProjectTrace 1.3.3

Date: 5 October 2026 (Asia/Calcutta). Recorded UTC: 2026-10-04T22:05:59.766105+00:00.

ProjectTrace's native engineering-integrity capabilities work independently of SonarQube and Wiz. This is an evidence-backed native release with real service validation, not a claim that the entire enterprise master specification is complete. No public deployment, external AI call, provider PR publication or cloud resource modification was performed.

## Exact source and preservation

Base Git commit: `b358f36c9f4f14d1902b10b3e8ce731c48e521aa` (`Update project`). The delivered code is **this commit plus uncommitted changes**; no new commit, push or PR was created. Release/analyzer/API/UI version: **1.3.3**. The adjacent `ProjectTrace-source-manifest.json` supplies archive SHA-256 and SHA-256 for every packaged file, so the changed source can be identified independently of the base commit. The archive has one root folder, `ProjectTrace/`.

Latest supplied input: `ProjectTrace-main (2).zip`, SHA-256 `c47f7c77129212f3d877c1ac0f58a5bffef9b032c9b9f457f37e11ba843326b6`. All 123 input source files matched the existing baseline before development. Baseline compile/Ruff/108 backend tests/15 frontend tests/3 browser workflows and locked dependency audits passed before changes. The existing workspace was evolved in place. Historical reports remain historical; this report supersedes their runtime-validation status.

Original rows were checked by primary-key presence against the pre-migration consistent SQLite backup:

| Collection | Before | After | Missing original IDs |
|---|---:|---:|---:|
| organizations | 8 | 30 | 0 |
| users | 8 | 30 | 0 |
| repositories | 12 | 26 | 0 |
| records | 6516 | 17422 | 0 |
| audit_events | 493 | 1199 | 0 |

SQLite quick check: `ok`; foreign-key errors: 0. The additional rows include additive snapshots, native graph/profile data and isolated browser-test tenants. Existing local credentials remain unchanged. Real repositories remain separate from labeled Northstar demo data. Source history was preserved; mutable PR gates/reviews can evolve through existing workflows.

## Architecture

React/TypeScript/Vite/TanStack Query/Table/React Flow → FastAPI modular monolith → tenant/repository authorization → SQLAlchemy/Alembic PostgreSQL; SQLite is the explicit local adapter. Redis/Celery queues only job IDs while scoped raw inputs remain encrypted and expiring. Native Python AST, maintained Tree-sitter grammars, HCL2 and safe YAML produce ProjectTrace-owned findings, metrics and static inventory. Versioned claims/findings/edges/snapshots share the existing Evidence Graph/Claim Ledger. Migration 0005 adds NativeProfile, typed CloudAsset projections and a PostgreSQL full-text GIN index.

Native grammar extensions run in a bounded isolated helper process per uncached language batch. Only installed ProjectTrace code executes; repository contents are JSON data, never application code. Credential environment values/user Python paths are excluded. A 30-second timeout, syntax/input/result budgets and byte-based source locations protect the parent against the observed native parser failure. Process isolation is implemented; a full OS filesystem/network sandbox is still deferred.

Static flow, cloud declaration, cloud API and runtime authority remain distinct. Direct AWS read-only observations can enter the same authorized graph; deployment/runtime links require separate evidence. Ask uses authorized PostgreSQL full-text ranking, deterministic evidence and stored graph neighborhoods. Vector/embedding retrieval is NOT_CONFIGURED.

## Working functionality

- Preserved snapshot-scoped atomic claims, documentation/implementation origins, VERIFIED/INFERRED/UNVERIFIED/CONTRADICTED statuses, STALE history, stable identities and rule-only analysis provenance.
- Preserved deleted-file/reverse-graph impact, source inspection, grounded questions/citations, review/version conflicts, risk exceptions, ownership and append-oriented audit.
- Native four-language syntax metrics, source positions, cyclomatic/length/nesting thresholds, cognitive approximation and exact normalized duplicate bodies. Operators/punctuation are retained in duplicate fingerprints; comments/formatting are ignored.
- Bounded Python request/input → assignments/local helpers → modeled sink traces with contextual HTML sanitizer and SQL parameter handling. Modeled confirmed static flows are separated from contextual hotspots; runtime exploitability is unobserved.
- Versioned native rule registry and owner/admin organization/repository profiles, rule toggles/severity, observed SPDX license policy and new-findings gate scope. Profiles are captured in snapshots and applied after observation caches.
- Dependency/lockfile inventory subsets, explicit advisory coverage and CycloneDX SBOM. Optional exact-version OSV transport remains bounded; unchecked packages never become clean by default. Secret-shaped values are masked and fixture context remains visible.
- Structured Terraform, supported CloudFormation/Kubernetes/Compose/Dockerfile checks; declared assets/identities/workloads/exposure and actual-edge risk paths. Narrow production-storage privacy contradictions require explicit production-bound public declarations.
- Explainable PASS/WARNING/REVIEW_REQUIRED/FAIL gates with reasons, evidence IDs, claim contradictions, source deltas, existing/new/analyzer-baseline findings and human exceptions.
- Actual queued execution, multi-tenant admission, duplicate idempotency, encrypted retained input cleanup, cancellation/expiry, broker outage/retry and natural expired-lease recovery after forced worker termination.
- Native UX pages for Code Quality, Security, Dependencies, Secrets, Infrastructure, Cloud Assets, Cloud Identities, Exposure, Risk Paths, API Integrity, Reviews and Settings. Main connection cards have no competitor dependency.

## Language and rule coverage

| Surface | Implemented | Partial or unsupported |
|---|---|---|
| Python | AST functions/claims/quality; modeled assignment and bounded local-helper SAST flows; existing security rules | Complete CFG/path feasibility, cross-file/interprocedural framework analysis, all sanitizers |
| JavaScript/JSX | Maintained syntax grammar, function metrics, empty catch, exact body duplication, eval/raw HTML hotspots | Full symbol resolution, taint/CFG/framework models |
| TypeScript/TSX | Maintained TS/TSX grammars and corresponding metrics/hotspots | Grammar-specific partial syntax; full type/taint analysis |
| Java | Maintained syntax grammar; method/constructor/class metrics, empty catches, narrow eval-named invocation hotspot | Mature Java SAST, frameworks, call graph, overload/type resolution |
| Terraform | HCL2 declarations and literal JSON/jsonencode IAM policy data | Plans/providers/modules/reference evaluation and effective policy semantics |
| YAML/JSON | Supported CloudFormation, Kubernetes including CronJob, Compose structures | YAML aliases/anchors, unrendered Helm, unsupported resource shapes |
| Dockerfile | Explicit USER root/0 check and image declaration evidence | Complete image/layer/registry vulnerability scanning |
| C#, Go, Rust, C/C++ and other source languages | Generic supported text/config evidence where recognized | Native semantic quality/security adapters unsupported |

Registry: **31 native rules**: SAST 10, quality 8 (including parser error), IaC 9, secrets 1, license 1, cloud inventory 2. Each has ID/version/category/default severity/explanation/remedy, actual language coverage, concrete example and CWE/reference where applicable. Per-rule metadata is available through authenticated `/api/native/rules`; the small rule count is not a maturity or accuracy score.

Quality formulas are recorded per metric: Python complexity = 1 + recognized branch/loop/exception/ternary contributions + boolean operands minus one + match alternatives minus one; JS/TS/Java use recognized grammar branches/cases/short-circuit operators. Nested definitions are excluded from outer metrics. Function length is source span, nesting is syntax nesting, and cognitive complexity is explicitly a ProjectTrace approximation. Thresholds are >10 complexity, >80 function lines, >4 nesting, >200 class lines. Duplication needs matching normalized bodies of at least 30 syntax nodes/tokens. Near-duplicate detection, standardized debt/maintainability and broad symbol/dead-code analysis are deferred.

## Cloud providers and claim types

| Provider | Status | Verification |
|---|---|---|
| AWS | Implemented bounded direct read-only STS/S3/EC2/IAM SDK adapter; credential/account/repository checks and native ACL/ingress hotspots | SDK fixtures and actual missing-credential browser/API gates pass. **No live authorized account was connected; live provider proof is UNVERIFIED.** |
| Azure | Static resource-kind/configuration observations where supported | Live inventory/CSPM/identity adapter DEFERRED |
| GCP | Static resource-kind observations where supported | Live inventory/CSPM/identity adapter DEFERRED |
| Kubernetes/Compose | Supported static workload/security declarations and actual source references | Cluster/workload runtime inventory and active scanning unsupported |

AWS caps: 50 buckets/100 groups/100 roles, 30-second deadline and bounded SDK timeouts/retries; truncation/failure is PARTIAL. Credentials remain protected tenant-scoped host references. Federation, managed rotation, full pagination, effective IAM permissions/escalation, account-wide access-block/policy semantics and code-to-deployment mappings remain deferred. See `docs/CLOUD_READ_ONLY.md` for exact allowlisted reads and credential setup.

Claim types retain supported framework/database/authentication/API/dependency/configuration facts and declared documentation claims. Inferred imports are not runtime verification. The native cloud addition models narrow affirmative storage-privacy claims with explicit production scope. Unsupported general security/compliance/runtime claims, ambiguous environments and missing evidence remain UNVERIFIED. Similar resource names do not create deployment edges. Static risk paths are configuration risks, not demonstrated runtime attacks.

## Tests and security results

| Check | Final result |
|---|---|
| Python compileall | Passed |
| Ruff | Passed |
| Backend pytest | **131 passed**, 0 failures; one upstream Starlette TestClient deprecation warning |
| Frontend Vitest | **15 passed** across 3 files, 0 failures |
| TypeScript/Vite production build | Passed; main JS 422.83 kB / 127.01 kB gzip; lazy graph 180.00 kB / 58.16 kB gzip |
| Playwright Chromium | **4 passed**, 0 failures/flaky/skipped in final run; actual JSON evidence and screenshots saved |
| Native benchmark | **33/33 fixtures passed** |
| Locked Python audit | 0 known vulnerabilities reported at validation time |
| Locked frontend npm audit | 0 vulnerabilities reported at validation time |
| Real PostgreSQL/Redis/Windows workers | 13 checks passed |
| Real non-root Linux prefork | 7 checks passed |
| Actual forced crash/natural lease recovery | 4 checks passed |

Security tests cover scope/tenant/repository IDOR, CSRF/origins/RBAC, sessions, ZIP traversal/symlinks/limits, secret masking, source nonexecution, webhook signatures/replay, review concurrency, fake citations/grounding, native profile conflicts/audit/cache isolation, cloud account/region/read authority and parser-process failure classification. New tests verify large repeated TSX analysis/GC, exact byte-based locations and operator-preserving duplicate fingerprints. This is a bounded regression/security suite, not a penetration test or comprehensive security certification.

Resolved development failures: literal HCL jsonencode policy extraction; test selectors/migration expectations changed by additive native evidence; a native parser access violation discovered with the real ZIP; profile success-message refresh and profile-loading input races. The native parser is now isolated and source locations avoid Point accessors; real ZIP analyses and a 300-function repeated/GC corpus pass. Similar upstream native binding failures were reviewed, but the exact C defect was not proven: [upstream report](https://github.com/tree-sitter/py-tree-sitter/issues/487). The interrupted local validation job remains FAILED with an audit link to its replacement snapshot, preserving an honest failure history. A later crash validation recovered through actual Redis late-ack redelivery during a long host interruption; its strict scheduler-counter assertion failed even though one snapshot completed. That path is recorded separately. The validation runner was corrected to apply its two-second beat override after app configuration, and the lease-scheduler scenario was rerun. Final required automated checks have no unresolved failure.

## Benchmark precision and load

The corpus has 33 synthetic fixtures and 7 explicit false-positive traps. Explicit rule-presence labels: TP=22, TN=20, FP=0, FN=0. Within these labels only, precision/recall are 100%; finding instances, unlabeled outputs and general population security precision/recall are **UNMEASURED**. Zero trap failures cannot establish a real-world false-positive rate.

Static timings: Windows 11/Python 3.14.3, 12 measured samples per operation, median/p95 in milliseconds. p95 uses nearest rank; small-sample tails are illustrative. The 500-file corpus mixes 400 Python modules, 80 TypeScript files and 20 docs/manifests. Native TS batches use the isolated parser; cached observations avoid reparsing.

| Operation | Median ms | p95 ms |
|---|---:|---:|
| full zip and analysis | 1.711 | 4.137 |
| cached zip and analysis | 0.534 | 1.474 |
| incremental zip and analysis | 0.689 | 0.985 |
| python quality and sast combined | 0.560 | 1.466 |
| claim verification | 0.026 | 0.171 |
| cached claim fingerprint and verification | 0.034 | 0.048 |
| 500 file monorepo zip and analysis | 638.649 | 659.509 |
| 500 file monorepo cached zip and analysis | 64.379 | 84.819 |

These timings exclude API/database/graph persistence, queue delay and providers. API smoke load is 40 local requests, four concurrent clients, seeded current demo and SQLite: workspace p50/p95/p99 **261.04/344.78/344.78 ms**, Ask **160.45/348.43/348.43 ms**; **0 errors**, 12.12 seconds, 3.3 client requests/sec. This script includes client creation overhead; for each 20-sample route its reported p95/p99 are the maximum sample. It is not production capacity.

Real Linux prefork measurements include cold parser startup and QEMU emulation; the final small/100-file parallel check took **96.179 seconds**. Earlier warmed checks were faster. Actual natural-lease crash recovery took **138.266 seconds**. No saturation, weighted fairness, 10k-file unique monorepo, multi-replica throughput or production provider-load claim is made.

## PostgreSQL, Redis, Celery and migrations

Actual environment: isolated Alpine 3.24 QEMU VM, PostgreSQL **18.6**, Redis **8.8.0**, Python **3.14.8**, Celery **5.6.3**. A non-root Linux prefork worker used concurrency two and read-only ProjectTrace source. Only loopback host ports were exposed and validation credentials were disposable. Windows solo workers tested additional broker/cancellation/expiry scenarios; they are separate from Linux production-pool verification. Those 13 checks ran against release 1.3.0 before later parser/UI changes; the seven Linux prefork checks and four natural-lease crash checks ran against final release 1.3.3. The supporting JSON records retain those tested versions.

PostgreSQL migration upgrade → rollback → upgrade passed, including 0005 projections/profile scope/index and actual full-text claim retrieval. SQLite fresh/rollback/re-upgrade passed in tests; the existing user database upgraded additively and passed integrity/foreign-key checks. A consistent preservation backup exists privately. Production backup restore and encryption-key rotation were not validated.

Redis PING, production distributed admission, real async 202 submission, two-worker duplicate delivery, actual broker shutdown/restart with retained input/retry, queued cancellation/input cleanup and actual beat expiry passed. Linux prefork proved multiple tenants/sizes, one atomic snapshot for duplicate delivery, graph/flow/assets/gate and tenant-scoped PostgreSQL retrieval. Forced kill during BUILDING_EVIDENCE rolled back the graph transaction, preserved encrypted input, waited natural 125-second lease expiry, recovered exactly once and removed retained input. Validation beat used two seconds; shipped recovery interval is 60 seconds and expiry interval is hourly. Recovery is bounded to two retained native FILE/ZIP attempts.

The supplied Compose images remain PostgreSQL 17/Redis 7 to avoid silently upgrading existing data volumes. **Docker/Compose builds, those exact versions and image scans were not run.** Actual service proof establishes the tested VM stack, not all production-host deployment gates. No installed host Docker/WSL or machine-wide PostgreSQL/Redis service was required.

## Actual user ZIP and browser/CEO trust

`smart-waste-management-system-main.zip` was read statically and reanalyzed into both existing repositories. No dependencies were installed from it and its application/build/tests were never executed.

| Repository | State | Files | Claims | Findings | Function metrics | Dependencies |
|---|---|---:|---:|---:|---:|---:|
| smart-waste-management-system | PARTIAL | 40 | 74 | 19 | 245 | 297 |
| smart waste | PARTIAL | 40 | 74 | 19 | 245 | 297 |

Each has 30 VERIFIED, 43 INFERRED and 1 UNVERIFIED claims; 268 dependencies remain NOT_CHECKED and 29 UNKNOWN_VERSION. Secret-shaped fixture evidence is masked. Native infrastructure inventories three declarations. Partial coverage records a TSX grammar diagnostic at `frontend/src/main.tsx:832` (plain JSX text containing an ampersand); it can be a grammar limitation rather than an application syntax error. No compile/runtime proof was attempted. Earlier source snapshots remain accessible, and analyzer upgrades are separate from source drift.

Browser workflows prove new real-workspace ZIP import/login, scoped claims/source/SBOM, secret redaction/review/audit, second-snapshot drift, cross-tenant rejection, canonical reload/back/hash routes, all major native pages, profile/license/new-findings persistence, static cloud risk and missing AWS credentials. The CEO demo retains the source-backed JWT-to-session contradiction/history and adds explicitly synthetic production-storage/public-ACL evidence. The four maintained demo repositories are synthetic. This existing Northstar workspace also retains an older local import; the banner labels the mixed historical workspace and repository provenance remains visible. Its older scan is historical until reanalysis. Existing data was preserved. New imports require a real workspace. Unsupported questions return insufficient evidence. Desktop/mobile overflow checks pass; current desktop cloud/risk/settings and completed mobile screenshots were visually reviewed. This is a focused UX review, not formal usability research.

## Product-owner questions

| Question | Evidence-backed answer |
|---|---|
| Analyze repositories without SonarQube? | YES: actual user ZIP and native fixtures/browser workflows. |
| Produce native quality findings without SonarQube? | YES: four-language metrics, native rule tests and real ZIP findings. |
| Perform native security checks without SonarQube? | YES within implemented modeled/static scope; not complete enterprise SAST. |
| Inventory dependencies/SBOM without SonarQube? | YES: real 297 declarations and browser SBOM checks; live advisory coverage remains explicit. |
| Analyze IaC without Wiz? | YES: maintained structured parsers, native rules and source fixtures. |
| Produce static cloud evidence without Wiz? | YES: scoped native inventory, actual graph edges and claim/risk fixtures. |
| Obtain direct live AWS/Azure/GCP context without Wiz? | AWS read-only adapter implemented; **live AWS proof UNVERIFIED** without credentials. Azure/GCP live adapters DEFERRED. No unsupported YES claim. |
| Feed Claim Ledger/Evidence Graph? | YES: actual shared source/finding/resource/claim edges and authorized graph retrieval. |
| Can a CEO use the product without competitor dependencies? | YES: actual browser demo and native-only core connection UI. |
| Can developers inspect important conclusions? | YES within implemented scope: versioned rule/formula/trace/source/authority/gate/owner/review records; limitations stay explicit. |

## Known limitations and deferred roadmap

1. Broaden labeled real-world/adversarial corpora, framework/type models, full CFG/cross-file taint and language-specific sanitizer resolution; measure finding-instance precision/recall. Expand exact language/rule coverage without claiming completeness from rule counts.
2. Verify authorized live AWS end-to-end and add federation/managed secrets, pagination, account policies, resource relationships, effective IAM permissions and escalation. Implement Azure/GCP directly, then evidence-backed deployment/runtime correlations and richer risk paths.
3. Harden all parsers with complete OS/network/filesystem/resource isolation, reproducible pinned/scanned images and worst-case budgets. Exercise shipped Docker versions and staging backup/restore/key rotation.
4. Add enterprise OIDC/SSO/invitations/permission lifecycle, managed object storage/retention/deletion, tenant fairness, distributed sustained load, monitoring/tracing and incident operations.
5. Expand normalized domain/graph schema, semantic vector retrieval with access filtering, richer monorepo component discovery and live GitHub/private-source/check-publication validation.

Historical competitor evidence adapters remain optional compatibility contracts only; no core native finding/claim/metric/cloud page requires their services. Complete SCA resolution/license legal conclusions, all secret formats, live provider maturity and runtime security remain partial. The permanent engineering integrity model remains CLAIM → CURRENT EVIDENCE → EXPLAINABLE DECISION → HUMAN OWNERSHIP → AUDITABLE ACTION.

## Supporting artifacts and reproduction

`ProjectTrace-source.zip` and per-file hash manifest; `ProjectTrace-native-benchmarks.json`; `ProjectTrace-native-api-load.json`; Python/frontend audit JSON; browser validation JSON/screenshots; user-repository and data-preservation JSON; three real-runtime proof JSON files; login/import guide. Imported raw source, databases, cloud credentials, session keys, private backups and VM credential files are excluded from deliverables.

From the extracted ProjectTrace root: follow README setup, run `python -m pytest -q --basetemp data/pytest-tmp`, `ruff check backend analyzers integrations workers tests scripts`, locked audits, frontend build/test and Playwright with both localhost servers running. Run `python -m scripts.benchmark_analyzers --output <absolute-output.json>` and `python scripts/api_benchmark.py` for bounded timings. Real runtime proof records include the exact tested environment/limits; reproducing service failure/recovery checks requires a disposable PostgreSQL/Redis/prefork environment and its own protected credentials.
