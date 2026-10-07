# Phase 2 — Analysis Coverage and Unsupported Language Inventory

Status: **COMPLETE — PHASE 2 CLOSED**. All closure conditions passed on 2026-10-07. Application/analyzer version remains 1.6.0. This closes the accepted-intake coverage phase, not production enterprise acceptance.

## Scope and files inspected

This verifies and hardens the existing implementation; no analyzer architecture was rebuilt. Inspected `analyzers/analysis_coverage.py`, `analyzers/code_quality/classification.py`, `analyzers/capabilities.py`, `analyzers/engine.py`, `backend/repository_store.py`, `backend/domain.py`, `backend/trust_api.py`, `frontend/src/EnterpriseTrust.tsx`, `tests/test_analysis_coverage.py`, `LANGUAGE_SUPPORT_MATRIX.md`, `ENTERPRISE_HARDENING_PROGRESS.md`, and `../ENTERPRISE_TRUST_VALIDATION.md`. Related quality gate, partition/cache, intake, UI unit/browser and Guide code was inspected and tested.

Changes are limited to inventory/classification, metadata parity, coverage calculations/gates, safe coverage projections, captured UI authority, verification and corresponding documentation. Native quality/security/cloud functionality remains ProjectTrace-owned; no SonarQube, Wiz or external AI dependency was added.

## Inventory, languages and states

Every file accepted into the complete small or enterprise intake is inventoried. Unsafe paths/traversal, symbolic links, normalized duplicate paths, excessive archive expansion/compression and aggregate quotas explicitly reject the intake. Directory entries are not repository files. Internal native-only views intentionally select parser inputs; they are not the complete captured inventory.

Python, JavaScript/JSX, TypeScript/TSX and Java have bounded syntax parsers and PARTIAL semantic maturity. Terraform, CloudFormation, Kubernetes, Compose and Dockerfile have bounded static configuration parsing with PARTIAL maturity. Unsupported source includes Go, Rust, C/C++, C#, Kotlin/Kotlin scripts, Ruby, PHP, Shell, PowerShell, SQL, Vue, Svelte and the other explicit extensions in the language registry. Makefile is inventoried as unsupported Make. A bounded first-line shebang labels a language without executing it or selecting an extensionless parser. Ambiguous text filenames/extensions remain UNKNOWN / UNSUPPORTED. Known docs/configuration names/extensions are non-source, with native scan status reported separately.

| State | Meaning |
| --- | --- |
| PARTIAL | Selected static observations; parser completion does not establish full semantic or security coverage |
| UNSUPPORTED | Unsupported/unknown source, unselected parser or unsupported encoding; absence of findings is not assurance |
| PARSE_FAILED | Source or IaC parser failure is visible and cannot count as completed parsing |
| EXCLUDED_GENERATED | Build/generated/coverage paths, generated filenames or bounded explicit generated headers |
| EXCLUDED_VENDOR | Dependency/environment paths or configured vendor patterns |
| SKIPPED_SIZE_LIMIT | Above the 512,000-byte parser budget; LOC and parse success remain unknown/unavailable |
| BINARY | Known binary formats or NUL-containing UTF-8 payloads; no source parser, unknown LOC |
| IGNORED_BY_POLICY | Explicit scope exclusions or unscanned known non-source entries |
| SUPPORTED | Reserved for a future qualified mature analyzer; no current emitter and no active UI filter |

Non-UTF-8 programming source, including UTF-16, remains an explicit unsupported encoding gap rather than disappearing. Unknown LOC is represented as null; language totals separately count unknown files. Exclusions cannot count as successful source parsing or contribute production Code Quality metrics. Other native static scans may still inspect excluded text; the per-file native scan field makes that distinction visible.

## Deterministic fixture and intake parity

The fixture in `tests/test_analysis_coverage.py` includes every requested language and all five IaC formats, Markdown/JSON, binary image and ASCII binary, UTF-8 NUL source, invalid UTF-8, oversized programming source and docs, unknown extension, extensionless shebang, Makefile, generated header, policy exclusions, and malformed Python/JS/TS/Java/Terraform/CloudFormation/Kubernetes/Compose/Dockerfile.

Both ZIP paths agree on language, kind, state, bytes, LOC, parser completion, native scan and source-denominator membership. Component metadata is enterprise-specific. The fixture captures **52 files, 25 programming source files, 4 parsed programming files and 16% source analysis coverage**. Exact states: PARTIAL 11, UNSUPPORTED 16, PARSE_FAILED 9, EXCLUDED_GENERATED 6, EXCLUDED_VENDOR 3, SKIPPED_SIZE_LIMIT 2, BINARY 3, IGNORED_BY_POLICY 2. Language counts and known/unknown LOC totals are checked against every inventory row.

The small route defaults to 1,000 entries and 10 MB archive/uncompressed limits. Enterprise defaults to 100,000 files, 512 MB compressed and 2 GB uncompressed, with configurable bounded aggregate quotas. Both retain the 512,000-byte per-file parser budget. Aggregate quota and compression safety rejection remain intentional architectural differences; equivalent accepted fixtures have equivalent coverage semantics. Oversized IaC remains labeled by an identifiable filename/extension and reported separately. A generated malformed IaC file retains its exclusion rather than overriding it with parse success/failure.

## Formula and gate behavior

`source_files` counts included first-party programming source/tests/examples, unsupported/unknown programming source, unsupported source encoding and oversized source. Vendor/generated/policy exclusions, binary and known docs/configuration/IaC are excluded. IaC coverage has its own format table. `source_files_parsed` counts completed selected source parsers in this denominator. The percentage is `100 × parsed / source_files`, captured to six decimals, or null when the denominator is absent. State counts describe all discovered files; language parsed counts can include IaC and are not the programming-source numerator.

Configured coverage gates compare unrounded ratios. Tests cover a 100% threshold with supported PARTIAL-maturity syntax (the coverage condition may pass), mixed/unsupported source and parser failures (fail), missing measurement (review required), and one gap among 20,001 files (cannot round to PASS). Every malformed source/IaC fixture fails or requests review under the configured coverage threshold. A coverage-condition PASS proves that metric only; it never upgrades analyzer maturity or establishes repository safety.

## Parser failures and caches

All nine malformed format fixtures expose PARSE_FAILED, never supported-clean. Failed observations are excluded from new reusable artifacts, retried on repeat analysis, and previously stored PT-PARSE-001 observations fail cache admission in both legacy and partitioned paths. Unsupported syntax, symbolic/unresolved constructs and parser budget limits remain visible diagnostics/PARTIAL gaps; these tests do not claim complete language validation.

## API, security and historical verification

`GET /api/trust/coverage` verifies repository and snapshot authorization before returning measurements. Checks cover latest/historical selection, state/search, pages over 50 entries without duplicate paths, invalid limits, foreign repository/snapshot IDs, denied then granted VIEWER access and cross-tenant searches/pagination. The response uses explicit inventory/diagnostic fields and redaction, excluding unexpected source, credentials and encrypted-input fields even if injected into a stored inventory. Secret-bearing source and malformed-source fixtures never return source bodies or secret values through coverage.

Legacy snapshots return LEGACY_NOT_MEASURED. Reads do not add coverage or alter their stored JSON. Existing measured snapshots retain their originally captured classifier/precision behavior; only new analyses use current semantics. The live saved-data comparison confirms all original 74 password hashes and 162 snapshot JSON values unchanged, 50 encrypted blobs intact, original analysis key unchanged, zero foreign-key errors and SQLite integrity OK. Testing used disposable private databases; no user account was reset and no customer ZIP was reimported.

## UI and infrastructure verification

The real Chromium workflow compares displayed snapshot, branch, commit, timestamp, analyzer/ruleset/profile/Quality Gate versions and coverage counts/percentage with the API. It exercises historical selection, unsupported language inventory, file paging/search/state filtering, limitations, all five infrastructure rows, resource/attempt/failure counts and parser diagnostics. UI unit checks keep legacy authority unmeasured and remove the unused SUPPORTED filter.

Each infrastructure row reports files, attempted analyzed files, static resource declarations, parse failures, maturity, STATIC authority, UNOBSERVED runtime and diagnostics. An attempted file may fail parsing; analyzed-file counts are not success counts. Imported repository coverage captures `customer_code_executed=false`, `external_llm_used=false`, and `source_sent_to_external_ai=false`. The frontend renders these captured fields and uses Not measured when absent. It does not infer runtime deployment evidence from IaC.

## Current tests and evidence

Final focused run: **141 passed in 302.95 seconds**, including coverage, Code Quality, enterprise trust, repository storage, trust controls, API, security hardening and streaming import. Complete backend regression: **324 passed in 311.20 seconds**. Frontend: **26 unit tests passed**, TypeScript check and production build passed, **41 public routes prerendered**. Final relevant Chromium workflows: **3 passed in 25.6 seconds**, without skips, flaky or unexpected outcomes. Ruff and whitespace checks passed; 89 documentation links resolved. One upstream TestClient deprecation warning remains. Intermediate failing runs were corrected and are not closure passes; private logs are retained separately.

The [Phase 2 receipt](../benchmarks/phase2-closure-verification.json) binds implementation hashes, [focused JUnit](../benchmarks/phase2-focused-closure.xml), [complete regression JUnit](../benchmarks/phase2-regression-closure.xml), [browser results](../benchmarks/phase2-browser-verification.json), [fixture inventory](../benchmarks/phase2-coverage-fixture.json) and [saved-data preservation](../benchmarks/phase2-saved-data-preservation.json). Older enterprise candidate reports/source archives retain their historical verification scope and are not regenerated or represented as current Phase 2 evidence.

## Limitations and deferred work

Coverage completeness applies to accepted intake, not universal semantic support. Explicit classification/shebang hints are not semantic language detection. LOC is unknown for binary, skipped and undecodable content. All current language/IaC analyzers remain PARTIAL; production precision, complete framework/type/flow support, full OS parser sandboxing, deployed runtime evidence, representative scale and live PostgreSQL/Redis/Celery/IdP/GHES/S3/Kubernetes acceptance remain outside this closure. Existing broader enterprise limitations remain in the validation report.

Next planned phase is **Phase 3: profiles and gates**, whose implementation already exists. After Phase 2 closes, continue verification of inherited/immutable profile and gate behavior without rebuilding it; completion of this local inventory phase does not close the entire enterprise program.

That continuation is recorded in [PHASE_3_VERIFICATION.md](PHASE_3_VERIFICATION.md): a required-parser condition was hardened and the latest complete regression passed 325 tests. The Phase 2 receipt retains the exact closure-run code scope; the subsequent Phase 3 receipt binds the final gate code and repeats all Phase 2 regression/browser coverage.
