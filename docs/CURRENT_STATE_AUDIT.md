# Current-state audit — 2026-10-04, before repair

Inspected the 92-file delivered ProjectTrace ZIP after bounded, path-validated extraction into a scratch directory, then inspected the active Desktop/ProjectTrace checkout (which contains the later empty-workspace login fix). The newly supplied smart-waste-management-system-main.zip is the repository to analyze, not a replacement ProjectTrace application. Its 55 entries expand to 338,038 bytes; repository scripts were read as data and never executed. Existing users, repositories, reviews and audit events must be preserved.

## Reproduced root causes

Running the existing `read_zip` and `analyze` on the user's ZIP gives **38 supported files, 0 claims, 6 findings, 228 dependencies, 136 syntax signals**. This is not an LLM failure, API tenant filter, serialization error or missing snapshot. `extract_claims` only recognizes four narrow Markdown sentence patterns. The actual README describes the framework, cookie sessions and database in other wording. Syntax signals never become implementation claims. Ranged Python requirements are ignored, while npm lock dependencies work. The SQL rule also flags `execute(select(...))` and literal SQL wrapped in `text(...)` as injection, despite lacking dynamic SQL construction.

The UI header hardcodes "Analysis complete". `persist_analysis` hardcodes snapshot COMPLETED even after PT-PARSE-001. ZIP imports create no job record. Exceptions roll back the whole request, leaving no durable failure record. A first-snapshot contradiction generates a drift record despite having no comparison. The UI has no ZIP reanalysis path for an existing repository. Its repository filter covers only some tables. Cloud and connection screens foreground unavailable optional providers. Every table shares a generic empty message. Graph edges are persisted, but structural repository/snapshot/component/API nodes are absent. JSON relationship references are application-enforced rather than SQL foreign keys.

## Module matrix

| Module | Current implementation / status | Missing or broken | Repair / validation |
|---|---|---|---|
| Import / safe ZIP | WORKING: `/api/archive/import`, `read_zip`, `validate_files` | No durable job; cannot update existing repository via ZIP UI | Persist jobs/errors, add snapshot upload to existing repository; malicious ZIP/API tests |
| Database | WORKING/PARTIAL: SQLAlchemy, Alembic 0001/0002, SQLite foreign keys, PostgreSQL configuration | Polymorphic JSON links lack SQL FK; workspace silently caps 5,000 records | Index scoped records, explicit truncation warning; migration and tenant tests |
| Analysis jobs | BROKEN for ZIP; PARTIAL Celery GitHub workflow | Hardcoded complete; only ValueError handled in native worker; failure metadata overwritten | Shared state model, durable failure, safe stage logs; injected failure tests |
| Evidence | WORKING: redacted file source/hash/provenance persisted | Signals not exposed as structural nodes | File/artifact/documentation/API nodes and relationships; graph referential checks |
| Claims | PARTIAL/BROKEN for user's source: deterministic doc templates only | Zero implementation claims despite syntax evidence | Implementation + documentation pipelines; auth/database/route/dependency claims; real ZIP regression |
| Verification | WORKING within narrow supported signals | Database configuration not detected; imports must remain inferred | Static configuration verification, honest confidence/coverage; JWT/session fixture |
| Code quality | WORKING/PARTIAL: Python AST complexity/length | Other languages lack quality parser; malformed Python reports completion | Keep documented Python coverage; partial job state on parse failures |
| SAST | WORKING/PARTIAL: SQL/shell/deserialization/weak digest and conservative eval patterns | SQLAlchemy expression false positives; no full taint analysis | Narrow SQL rule; add supported XSS/path indicators with limitations; safe/unsafe tests |
| Dependencies/SCA | PARTIAL: npm lock and pinned requirements | Ranged requirements/package.json/pyproject/poetry/Maven/Gradle ignored; real imports don't use cached advisories | Broaden inventory; exact cached OSV findings, fixed versions; offline inventory tests |
| Secrets | WORKING/PARTIAL: assignment/token/private-key masking | `.env.example` skipped; test credentials need human triage | Include environment examples, redact all persisted surfaces; leakage tests |
| Infrastructure | WORKING/PARTIAL: privileged/root/public ACL static rules | Limited policy set; Compose/Terraform context not exposed | Persist IaC evidence and distinguish live cloud; static-only tests |
| Cloud | PLACEHOLDER live inventory; static IaC exists elsewhere | Page mostly shows unavailable live provider | Native IaC section plus explicitly deferred live inventory |
| Drift | BROKEN semantics on first snapshot; WORKING status comparison with base | Initial contradiction mislabeled drift; removed claims not covered | Consistency finding first; temporal changes only with base; two-snapshot tests |
| Impact / risk | PARTIAL: changed hashes, affected PR claims, severity policy gate | No dedicated correlation record; no reachability | Persist scoped impact/risk relationships; no invented risk scores |
| Architecture / API | PARTIAL: architecture templates and Python routes; JSON OpenAPI missing routes | No graph endpoint nodes; contract mismatch only unverified claim | Persist endpoint nodes/consistency findings; unsupported frameworks remain explicit |
| Graph | WORKING/PARTIAL: stored claim/finding/file/dependency edges | No structural graph; empty graph has no clear guidance | Persist structural relationships and render scoped data |
| Ask Engineering | WORKING/PARTIAL: authorized deterministic keyword claims retrieval | Empty without claims; unsupported questions return insufficient evidence | Implementation claims make retrieval useful; no LLM requirement, no invented answers |
| PR intelligence | PARTIAL: demo and credential-gated GitHub code | Live installation/webhook/check E2E not verified | Keep optional SCM status honest; native snapshot comparisons independent |
| Policies/review/audit | WORKING: native advisory gate, optimistic review, privileged exceptions, audit | Fixed policy templates; no policy editor; audit not immutable/WORM | Retain working behavior, test new job audit events |
| Connections | PLACEHOLDER/PARTIAL: status inventory + GitHub API | Vendors look required; other adapters deferred | Connections groups SCM/Cloud/Optional External Evidence/AI; no core dependency |
| Auth / isolation | WORKING: Argon2, HttpOnly sessions, CSRF/origin, repo grants | No self-service signup/OIDC; seed org can receive real ZIP | Operator bootstrap; disallow real imports into demo org; tenant tests |
| Routing/import UX | PARTIAL: human-readable encoded hash; import button every page | No global scope, no existing-repo upload | Slug URLs, shared repo selector, contextual import/update |
| Demo | WORKING: deterministic Northstar fixtures, real AST/advisory results | Hardcoded labels leak into real-mode pages | Separate organization data and accurate mode labels |
| Observability | PARTIAL: request ID/duration logger | No pipeline stage IDs/durations | Structured safe pipeline logs + job history |
| Performance | PARTIAL: bounded input, file hash cache, paginated generic endpoints | Workspace cap silently drops older data; no local background queue | Scope current snapshots before cap; explicit coverage; measure ZIP/cached reanalysis |
| Deployment/CI | PARTIAL: inspected Docker/Compose, Celery/Redis, locked deps, pinned CI actions | Docker/PostgreSQL/Redis unavailable locally; no verified production release | Native verification; report container/live limitations |

## Actual pipeline trace

`ImportDialog.submit` → `api('/archive/import', raw ZIP)` → FastAPI `archive_import` → `read_zip` → `validate_files` → `import_repo` → Repository and Grant → `persist_analysis` → bounded validation/content digest/cache key → `analyze` → Python `python_analysis` / JS-Java patterns / secret-IaC rules → `dependencies` → Markdown `extract_claims` → `verify` → JSON OpenAPI comparison → `add(snapshot)` → `add(evidence)` for each file → claim/history/edge persistence → drift persistence (incorrect first-snapshot condition) → native and cached SCA findings → dependency records → `policy_gate` → optional PR record → `audit(ANALYSIS_COMPLETED)` → request DB commit → `onDone` invalidates workspace → GET `/api/workspace` → `current_snapshots` + current record scope → React page/table/inspector. No imported source executes. No external AI call occurs. Local imports are synchronous; Celery entry points serve configured jobs/provider deliveries.

## Frontend API matrix before repair

| Pages | Endpoint/data | Error state | Empty state |
|---|---|---|---|
| Overview, Systems, Components, Repositories | GET `/api/workspace`: real DB or explicit demo organization | Query error with retry | Zero cards / misleading healthy overview |
| Claim Ledger, Architecture | Same endpoint: current claim records | Shared query error | Generic "No results in this scope" |
| Findings, Code Quality, Security, Infrastructure | Same endpoint: native/cached finding categories | Shared query error | Same generic table message |
| Dependencies | Same endpoint; GET `/api/sbom/{snapshot}` | Shared query error | Dedicated inventory empty text |
| Drift | Workspace drift records | Shared query error | Same generic table message |
| Evidence, Evidence Graph | Workspace evidence + persisted edges | Shared query error | Sparse/blank graph |
| Ask Engineering | POST `/api/ask`: deterministic authorized retrieval | Visible mutation error | Honest insufficient evidence |
| Pull Requests | Workspace PR records; GET `/api/gate/{snapshot}` | Shared query/gate errors | SCM connection explanation |
| Policies | Workspace snapshots and live gate queries | Visible gate errors | No gates |
| Audit Trail | GET `/api/audit` paginated scoped DB | Visible query error | No events |
| Integrations | GET `/api/integrations`: status/config inventory | Visible query error | NOT_CONFIGURED cards |
| Cloud | Static interface linking Infrastructure | No live inventory workflow | Provider missing warning |
| Settings | Session + local theme preference | Shared query error | Not applicable |

## Security and release boundaries

ZIP limits/path/symlink/compression checks, source-as-data, masked source, scoped sessions/CSRF/repo authorization, signed replay-protected GitHub deliveries are present. Full interprocedural SAST, runtime verification, live cloud inventory, external evidence synchronization, semantic RAG, OIDC, object storage and WORM audit remain incomplete. Verify these boundaries with tests; do not equate a clean static scan with security certification. Inspection is complete before major repair edits.
