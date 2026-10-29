# ProjectTrace continuation audit — 24 October 2026

## Audited baseline

- Repository: `maninani12/ProjectTrace`, public, default branch `main`.
- Starting commit: `1518e918dfe7360c833c7414724026260422bc71`, “Add ProjectTrace onboarding and generation architecture” (15 October).
- The branch API returned only `main`. Recent history includes `46efd42`, `07ae2b2`, `312156a` and earlier native-platform work. No existing branch was deleted or rewritten.
- The pull-request collection returned no existing PRs.
- Created local branch `codex/auth-drift-verification` from the exact baseline. Remote branch creation failed with HTTP 403: `Resource not accessible by integration`. The connected account is **Maninani21**; repository owner is **maninani12**. Reported repository permissions are pull=true, push=false.
- React/TypeScript/Vite frontend; FastAPI/SQLAlchemy modular backend; owned static analyzers; encrypted source inventory; durable local/Celery jobs; generation publication; evidence and domain Records. Alembic has a continuous 0001–0025 migration lineage, including tenant integrity (0023), private generations (0024) and onboarding (0025). No migration is added or modified in this continuation.

## Current implementation and unfinished work

The Claim Ledger, snapshot history, Evidence Graph, native Code Quality, security/IaC analysis, Administration and both Learning modes (new hire and internal transfer) already exist. The deterministic JWT → session fixture and verification also already exist. This continuation completes presentation and reproducibility, rather than replacing those systems.

Direct source inspection includes `analyzers/verifiers.py` and `backend/domain.py` for verdict/evidence/history, `backend/engineering_changes.py` for BASE/HEAD capture, `backend/generation_visibility.py` for publication filtering, and `backend/onboarding.py` for both learning modes. Learning requires distinct participant/mentor/manager identities, independently authorized source/target projects for transfer, mentor assessment before manager completion, and a fresh revision when target source changes. Administration, graph and quality APIs remain in `backend/admin_api.py`, `backend/graph_api.py` and `backend/quality_api.py`; none are replaced by the demo.

Existing release gates remain: bounded global analysis memory on large repositories, full parser filesystem/network isolation, real broker recovery qualification, representative accuracy, and production deployment/DR qualification. Prior documentation claims of passing suites are historical evidence; they do not supersede this run. See `SDLC_ACCEPTANCE_2026_10_15.md` and its SCALE-001 failure description.

## Failing Actions run and query change

Inspected [run 38679755262](https://github.com/maninani12/ProjectTrace/actions/runs/38679755262), job 116241369154. Python 3.14 compilation and Ruff passed. Pytest reported **1 failed, 596 passed, 2 skipped**. The failure was `test_infrastructure_read_seeks_snapshot_and_class_indexes` at `tests/test_indexed_workspace_queries.py:70`: SQLite chose `uq_records_checkpoint_scope` primary-key probes instead of the expected `ix_records_graph_class` expression seek. Subsequent frontend/browser/build stages were skipped, so that run supplies no passing evidence for them.

The infrastructure resource query used `Record.id IN (SELECT CloudAsset.id ...)`. Generation visibility adds private-publication predicates to both ORM models; the resulting membership list allows the planner to drive primary-key probes and bypass the intended snapshot/class seek. Changed membership to a **correlated EXISTS** on the same asset ID and tenant/snapshot. Both generation visibility predicates and existing tenant/repository checks remain active. The original index-plan test and its assertion are unchanged. No index is forced, visibility filter disabled or test marked xfail.

The original query-plan tests also passed in the local Python 3.12 / SQLite 3.53.1 baseline. Therefore the CI-specific planner choice is established by its actual logs, not claimed as a reproduced local failure. The changed query passes the unchanged local assertion; confirmation on the original CI runtime remains blocked until the branch can be published.

## Implemented changes

- Bounded captured `claim_comparisons` in Engineering Changes: original document reference and location, BASE/HEAD claim IDs, verdicts, explanations, supporting/contradicting source IDs, paths and hashes. Source remains in the existing evidence store and is opened through the authorized reader. Historical projections without references remain readable.
- Side-by-side comparison UI using the existing evidence inspector, with explicit unknown/truncated states. No current source is substituted for old evidence.
- Canonical verifier evidence/dependency order and a versioned cache fingerprint. Reordered discovery cannot reorder the displayed evidence; removing positive evidence invalidates reuse.
- Small independent `samples/auth-drift.json`, a loopback-only API demonstration script supporting durable queued completion, backend accuracy/isolation/recovery regressions, frontend comparison tests and a browser scenario with screenshot capture.
- Minimal security fixes in the existing lock file: certifi 2026.10.19, filelock 4.2.1 and opentelemetry-api 1.45.1, using the initial audit's reported fixed versions. `pip check` confirms compatible installed requirements. No audit finding is ignored or waived.
- [Senior architect demonstration guide](AUTH_DRIFT_DEMO.md), plus claim-ledger and architecture updates. Existing fixture, features, auth, policy limits and migrations are retained.

## Verification

The final handoff records the authoritative JUnit report, explicit exit code, raw logs and API proof. Runtime: Python 3.12.14, SQLite 3.53.1 and Node 24.22.1. The configured CI Python 3.14 environment was not available locally.

| Check | Result |
| --- | --- |
| Focused auth drift + infrastructure query + engineering changes | 16 passed (32.58 s) |
| Frontend unit/component tests | 49 passed |
| TypeScript and Vite production/prerender build | Passed; 42 routes rendered |
| Ruff and Python compilation | Passed |
| Native analyzer benchmark | 33/33 labeled checks passed; 7 false-positive traps, none triggered; synthetic scope only |
| API demonstration against disposable migrated DB with local worker | Passed: VERIFIED → CONTRADICTED; both source versions/hash references retrieved; runtime UNOBSERVED |
| Fresh disposable SQLite upgrade to 0025 | Passed; populated databases not downgraded or deleted |
| Full backend suite | 593 passed, 16 skipped, 0 failures/errors; 609 JUnit cases; exit 0; 869.010 s. Skips: 14 disposable-PostgreSQL checks and 2 Windows-only checks. |
| Backend dependency audit | Passed after 3 pin updates: no known vulnerabilities; `pip check` found no broken requirements. Initial 5-advisory failure is retained separately. |
| Frontend dependency audit | No reported vulnerabilities |
| Browser acceptance | BLOCKED: launch fails because Chromium is absent. Chromium and headless-shell downloads returned unusable HTML/truncated archives, not ZIPs. No browser test or screenshot is claimed as passed. |
| PostgreSQL integration / real Redis-Celery broker / Docker builds | Unavailable in this environment; no corresponding local services or Docker binary |
| Remote CI / PR | BLOCKED by GitHub write permissions/account mismatch |

A new recovery test initially failed because an in-memory tuple was compared with its JSON list representation after a Session restart. Refreshing the persisted baseline before capturing its expected value fixed the test setup; production behavior and preservation assertions were retained. An initial API demo attempt incorrectly expected synchronous analysis; the script/browser scenario now wait for the existing durable queue. Failed attempts remain in the handoff evidence and are not counted as passing checks.

## Release and publishing blockers

1. Reconnect GitHub as **maninani12**, or grant **Maninani21** write access to this repository and ensure the connection permits Contents and Pull requests writes. Then publish the prepared branch and create the proposed draft PR. No PR URL exists yet; main is untouched.
2. Run the unchanged Actions pipeline on its configured Python 3.14/Node 24/PostgreSQL runtime, including the infrastructure query-plan regression, migration tests, dependency audits, browser scenarios and image builds.
3. Provide a usable Chromium installation/download path and rerun browser acceptance. No screenshots were fabricated.
4. Resolve the existing scale/isolation/production qualification gates before calling the product release-ready. These predate this change.

Backend dependency findings from the initial `pip-audit -r requirements.lock` and the applied pin updates:

| Package | Original locked version | Updated version (audit-reported fix) | Advisory IDs |
| --- | --- | --- | --- |
| certifi | 2026.7.22 | 2026.10.19 | PYSEC-2026-4320 |
| filelock | 4.0.10 | 4.2.1 | CVE-2026-112940, CVE-2026-112913, CVE-2026-112907 |
| opentelemetry-api | 1.45.0 | 1.45.1 | CVE-2026-114603 |

The full final suite runs after installing these exact updated pins, with Python 3.12 as the available local interpreter. The first full run returned exit code 0 but retained no final summary; it is not counted as a passing full suite. The rerun records 609 JUnit cases (593 passed, 16 skipped, no failures/errors) and an explicit exit-code artifact of 0. Original failure and audit evidence remain alongside final results.

No public deployment, force-push, merge, database deletion, branch deletion or migration rewrite was performed. Imported fixture source was only parsed as data; a sentinel regression verifies that source-side file writes never execute.
