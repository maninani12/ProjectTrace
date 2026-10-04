# ProjectTrace repair and smart-waste analysis report

Historical version1.1 report. Current version1.2 capabilities, reanalysis and fresh validation are in [DELIVERY_REPORT_V2.md](DELIVERY_REPORT_V2.md).

Date: 2026-10-04. ProjectTrace was repaired in place at `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`. The user's smart-waste ZIP was treated as untrusted source data. None of its setup scripts, application code, dependencies or tests were executed. The ProjectTrace source ZIP was safely extracted for inspection; working implementation and existing database data were retained. A SQLite backup preceded the additive migration.

## Your repository results

The real ProjectTrace organization, accessible with the existing `admin@projecttrace.local` login, now contains the analyzed repository **smart-waste-management-system**. The separately imported **smart waste** entry was also reanalyzed with the corrected engine, preserving its previous snapshot/history. Northstar remains a separate demo organization. Choose one repository with the global selector to avoid counting the same source twice.

| Result | Value |
|---|---:|
| Supported text files analyzed | 40 |
| Implementation claims | 75 |
| VERIFIED from supported static syntax/configuration | 32 |
| INFERRED from imports/manifests/cookie signals | 43 |
| Documentation claims matching current templates | 0 |
| Native findings | 4 |
| Dependency declarations across manifests/locks | 297 |
| Unique package names by ecosystem | 261 |
| npm declaration rows | 244 |
| PyPI declaration rows | 53 |
| Persisted graph nodes including claims/evidence/dependencies | 530 |
| Persisted graph edges | 600 |
| Historical drift on the first snapshot | 0 |
| Job state | COMPLETED |
| Parser/manifest warnings | 0 |

VERIFIED describes the stated static fact, not observed application/runtime behavior. Declaration counts include occurrences in multiple manifests and locks; they are not 297 distinct installed packages. The project's README does not match the deliberately narrow documentation templates; implementation evidence now populates the ledger independently. General semantic README extraction remains deferred.

All 297 dependency rows have NOT_CHECKED vulnerability coverage. No CVE or clean security assessment is invented. ProjectTrace's optional cached OSV data covers exact lodash 4.17.20 only; that fixture produces real advisory findings in the integration test but does not establish full current advisory coverage for this user's repository.

## Findings and interpretation

Paths below are relative to the uploaded archive root `smart-waste-management-system-main/`.

| File:line | Native finding | Severity / confidence | Recommended review |
|---|---|---|---|
| `backend/main.py:472` | `transition` branch approximation 16, threshold 10 | MEDIUM / HIGH | Split independent workflow transitions into focused helpers while preserving authorization, transaction and state-machine rules. |
| `backend/seed.py:15` | `seed` branch approximation 13, threshold 10 | MEDIUM / HIGH | Separate account/configuration/example-data seeding responsibilities; retain idempotency. |
| `migrations/versions/001_initial.py:12` | `upgrade` exceeds 80 lines | LOW / HIGH | Review as migration scaffolding; a long schema migration may be intentional. Avoid rewriting an applied migration merely for this style rule. |
| `tests/test_workflow.py:16` | Credential-shaped assignment | CRITICAL pattern severity / MEDIUM confidence | This occurs in a test fixture. The value is masked and has not been authenticated against a service. Confirm that it is test-only and record a FALSE_POSITIVE review if appropriate; a pattern hit does not prove a live leaked secret. |

Two previous SQL warnings were false positives: SQLAlchemy `execute(select(...))` and literal SQL passed through `text(...)` were considered dynamic SQL merely because they were calls. The rule now checks interpolation/concatenation/format construction rather than flagging every expression call. No supported native SQL-injection indicator remains in this scan. This is not a full taint-analysis or exploitability assessment.

## What was broken and why

1. Claim extraction only recognized four narrow Markdown patterns. The user's ZIP had 136 syntax signals but zero claims because syntax signals never generated implementation claims.
2. The header hardcoded Analysis complete, even for an empty organization; snapshots also hardcoded COMPLETED after parsing failures.
3. ZIP imports did not persist an analysis job or durable errors. Unexpected worker/scope exceptions could escape without recording failure.
4. A first-snapshot contradiction was classified as drift with no historical comparison. There was no existing-repository ZIP update action in the interface.
5. Repository filters applied to only some tables. Ask Engineering also defaulted to the demo repository `identity`, causing an authorization error in real organizations.
6. Safe SQLAlchemy expressions were flagged as injection. Ranged Python requirements and additional manifest formats were ignored.
7. The graph persisted file/claim/finding edges but lacked repository/snapshot/component/artifact/documentation/API structure.
8. The Integrations and Cloud screens foregrounded unavailable providers, and every empty table used the same generic message.
9. Authentication-read requests consumed the strict login rate-limit bucket during browser refreshes, blocking subsequent legitimate demo/login checks.

## Repairs and native product behavior

- Added deterministic implementation claims from supported Python AST routes/framework/database configuration, cookie hints, selected imports, dependency declarations, testing/CI/IaC evidence. Existing documentation templates and atomic compound decomposition remain active without an LLM.
- Added durable native jobs with queue/stage history, IDs, timestamps, completion/partial/failure/cancellation semantics, warnings, errors, analyzer counts and safe structured stage logging. Imported snapshot outputs remain atomic; failed repositories/jobs remain inspectable. Partial parser/manifests are explicitly reported.
- Added ZIP reanalysis of an existing repository using its latest snapshot as the base. Initial contradictions become CONSISTENCY findings; historical drift records transitions or removed claims only when a base exists. Snapshot impact references changed source-linked claims. Shared-evidence risk relationships are persisted without invented risk scores or runtime reachability.
- Persisted structural graph records and relationships for repository, snapshot, component, artifact, file evidence, Markdown sections, API endpoints, dependencies, findings and claims. UI consumes those records.
- Expanded dependency inventory for requirements/ranges/lock text, npm manifests/lockfiles, pyproject/Poetry, Maven POM and Gradle declarations. Known direct/transitive status is preserved; unknown directness is explicit. Malformed manifests yield warnings. XML entity declarations are rejected. Existing bounded exact cached OSV advisory attachment and CycloneDX export continue to work.
- Narrowed SQL detection; added conservative dynamic raw HTML and filesystem response indicators. Python quality metrics remain documented approximations; no arbitrary quality score is displayed.
- Extended masking to secret-key assignments, database URL passwords and environment secret assignments. Source evidence remains redacted; imported contents are never executed or sent to external AI.
- The header reads actual backend state. Empty states distinguish no repository, running, failed, cancelled, partial, filtered, no claims, no findings and no historical drift. Overview review state also respects material findings and incomplete analysis.
- A shared repository selector scopes module data, graph, questions and audit. Ask Engineering defaults to authorized scope. Hash routing uses clean slugs and preserves old bookmarks. Imports are contextual on Repositories/empty workspace; Upload new snapshot is explicit.
- Renamed Integrations to Connections, grouped SCM, Cloud Accounts, optional External Evidence and AI Providers. SonarQube/Wiz/CodeQL/Snyk/Semgrep/Trivy are optional enrichment adapters with deferred implementation labelled. Cloud separates native IaC Evidence from unconnected Live Cloud Inventory.
- Local self-service API organization registration is available outside production; existing credentials and workspace separation remain intact. Real ZIP/JSON imports are rejected in the Northstar demo organization. Existing real source/history were preserved.
- Added migration 0003 scoped-record index. Workspace queries select current snapshot records before the result cap and report truncation rather than silently presenting incomplete results as success. JSON record references remain application-enforced rather than normalized SQL foreign keys.

## Validation

Final checks: **55 backend tests passed, 6 frontend unit tests passed, 3 Chromium end-to-end workflows passed, TypeScript/Vite build passed, Ruff passed, pip-audit reported no known vulnerabilities, and npm audit reported zero vulnerabilities.** One upstream FastAPI/Starlette TestClient deprecation warning remains; it does not fail validation. Backend tests cover safe/unsafe analyzers, exact scoped evidence, authorization, tenant isolation, CSRF/origin, IDOR, archive traversal/symlinks/size/nested archives, source never executed, prompt injection treated as data, secret masking, invalid/replayed webhook, SSRF source identity rejection, review concurrency, policy exceptions, migrations upgrade/downgrade/upgrade, cached analysis, and durable failure propagation. The new fresh-database API integration creates the organization/user through the API, logs in, imports a ZIP, checks all native result categories/graph links, asks a grounded question, uploads a second snapshot and verifies drift/audit without manually inserting domain rows. A worker test checks that a bad actor scope is persisted as FAILED.

Browser tests exercise the actual import form, Claim Ledger, linked Evidence inspector, Ask Engineering, second-snapshot Drift and Audit Trail in a real workspace; the existing CEO/demo and mobile workflows visit all primary pages. The user's actual repository was separately viewed in the browser: 75 rows appeared and no page errors were observed. Exported screenshots were visually inspected.

ProjectTrace's own Python and npm dependency audits reported no known vulnerabilities at the time of these checks. This result applies to ProjectTrace's dependency locks, not the uploaded waste application's unchecked dependency inventory.

## Performance observations

The measured real ZIP upload plus persistence and scoped workspace fetch took 3,153 ms on this host. In 12 static-only measurements, full analysis median was 89.93 ms (max 122.97 ms); unchanged cached analysis median was 6.96 ms (max 10.34 ms), reusing all 40 files. Parsing results are cached by path, content hash and analyzer version; page loads read persisted results. Manifest inventory and claim verification are intentionally recomputed against the current scope. These are local measurements, not production service-level guarantees. Inputs remain bounded to 10 MB, 1,000 archive entries and 512 KB/file, with at most 1,500 claims and explicit workspace-cap warnings.

## External connectors and deliberate limitations

Native analysis, claims, evidence/graph, quality, supported SAST/secrets/IaC/dependencies, review/policies/audit and deterministic Ask Engineering work without an external provider. GitHub source/webhook/check code is credential gated and live end-to-end verification remains pending. SonarQube, Wiz and other external evidence adapters, live AWS/Azure/GCP inventory, and external AI are deferred/unconfigured. No external messages or publications occurred.

This remains a bounded static-analysis MVP: no full multi-language taint analysis, complete API framework coverage, arbitrary semantic documentation extraction, semantic/vector RAG, observed runtime/cloud topology, OIDC/enterprise directory inheritance, object-storage retention or WORM audit. Local ZIP execution is synchronous; intermediate stages are retained in job history but not streamed through a dedicated background local queue. Process-kill recovery/automatic stale-job reclamation is not implemented. PostgreSQL/Redis/Celery containers and live provider deployment were not validated because the current host has no verified container runtime. Do not describe this release as fully production ready. The user's uploaded application's runtime/tests were not executed.

## Exact native startup commands

From PowerShell, for the already installed checkout, use two terminals:

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\frontend'
npm.cmd run dev
```

Open http://127.0.0.1:5181. Sign in with your existing admin credentials below the demo button, then select smart-waste-management-system or smart waste in the global selector. Use Claim Ledger, Findings, Code Quality, Security, Dependencies, Evidence, Evidence Graph and Ask Engineering. To compare a future source version: Repositories → Upload new snapshot → Choose File → Analyze and compare snapshot. Do not create a separate repository when you intend historical comparison.

For a fresh installation, use README.md's virtual environment, locked dependency, Alembic and npm setup commands. Run `python -m backend.seed` only to initialize/update the explicitly separate Northstar demo. The source bundle excludes local data, backups, session credentials, virtual environments and installed packages. No commit, push, merge or deployment was performed.
