# Code Intelligence audit and release scope

Date: 6 October 2026. Request: `CODE_QUALITY_SPECIFICATION.txt` (the supplied 155-section execution prompt). The industry constitution remains the permanent product direction. This audit uses the inspected 1.4.0 checkout and preserved `ProjectTrace-1.4.0-source.zip`; the preceding product report is archived in `validation-public-1.4.0.md`.

## Actual starting state

The 1.4.0 public product, authentication, fresh ZIP imports, Guide, reviews, graph, drift, PR gates, durable queue and native security/cloud boundary worked. Its API/UI release was 1.4.0 and native analyzer 1.3.3. The last verified baseline was 132 backend tests, 22 frontend tests and nine browser workflows, plus 38 exact prerendered public routes. Those results are historical baseline evidence, not fresh 1.5 tests.

Existing quality was useful but incomplete: seven syntax/metric/exception/duplicate rules; Python AST and installed JavaScript/TypeScript/TSX/Java grammar adapters; function length, nesting and branch approximations; exact normalized function-body hash comparison; common finding records and review actions. Existing owner/policy/source graph, content-hash caches, repository grants and NativeProfile provided the right foundation. They were retained.

The previous Code Quality screen used the shared generic finding view and small metric summaries. It did not provide a separate native quality gate, explicit quality model/baseline semantics, meaningful block groups, imported coverage counters, captured quality trends, documented hotspot factors, or scoped indexed quality queries. Line-dependent finding identity and strict source evidence review carry could lose continuity after harmless movement. Coverage was unavailable; source could not legitimately imply coverage. No complete CFG, type resolution, framework semantics, author history, runtime reachability or population precision was established.

## Changes and proof map

| Prompt phase | Implemented release scope | Evidence and remaining boundary |
|---|---|---|
| 1. Foundation | Explicit source/test/example/generated/vendor/config/unsupported/encoding inventory; Python AST + isolated grammar observations; symbol/range/hash/parser versions | Scope, parser failure, encoding and redaction tests. Four languages remain PARTIAL maturity; no universal symbol/type/CFG model. |
| 2. Metrics | Function decisions/contributors, ProjectTrace cognitive approximation, span, nesting, parameters, statement counts; file bytes/physical/comment/logical counts and class spans | AST/grammar fixtures and source inspector. Logical counts are language-specific syntax counts; no proprietary score compatibility. |
| 3. Rules | Twelve owned rules with dimensions, stable/beta status, examples, enabled/severity/threshold controls | Twelve labeled positive/negative/generated cases. Six stable/six beta; restricted Python reliability rules; no added rule-count credibility claim. |
| 4. Findings | Offset-independent fingerprints, separate machine delta/review, retained first seen, removal/reintroduction, safe review carry and bounded history | Movement, changed-body, rename, resolution/reopen and expired accepted-risk tests. Renames create new identities; repeated identical anchors use order. |
| 5. Duplication | Native token-window matching/extension, local binding normalization, literal/operator retention, substantial spans, grouped occurrences | Positive/negative/budget tests and side-by-side browser workflow. Function blocks only; bounded work, no semantic clone proof. |
| 6. BASE/New Code | Caller/configured BASE, branch ancestry, new/existing/resolved/reopened, worsening on changed lines, model-change annotations | History and worsened-existing-complexity tests. Model upgrades do not count unmatched old identities as fixes. |
| 7. Coverage | LCOV, Cobertura/coverage.py XML, JaCoCo XML; exact mapped lines/branches, revision declarations, provenance, unavailable/partial/invalid states | Parser/security fixtures and real browser import. Producer execution/authenticity are not independently verified. |
| 8. Gates | Separate explainable NEW_CODE/OVERALL quality conditions, captured profiles, organization defaults/repository overrides, review/expiry handling, combined current PR gate | API/CLI/profile/RBAC/CSRF/expiry/PR tests. Local advisory output; no live SCM check publication. |
| 9. Hotspots | Explicit complexity/finding/duplicate/observed-change ranking with owners | Factors returned by API and displayed in UI. ProjectTrace snapshot history only; no invented Git change frequency/authors. |
| 10. Trends | Captured counts/coverage/duplication with model annotations over 7/30/90-day snapshot windows | Paged branch-scoped API and browser workflow. Maximum 200 observed snapshots; no reconstructed Git history. |
| 11. Graph | Source/function/owner relationships, linked quality policy results, shared-evidence claim links, PR/impact traversal | Dedicated graph/PR/impact test plus existing graph suite. Relationships describe observed static evidence, not runtime causality. |
| 12. Hardening | Observation cache, parser signature/config-aware baseline, indexed occurrence projection, pagination, bounded source windows, additive migration, SARIF/JSON/CSV/CLI, measured benchmark and authorized reads/writes | Fresh release validation. Enterprise scale, production concurrency, complete accessibility and live external providers remain unverified. |

The phases are not blanket enterprise completion claims. The verified release is a bounded native Code Intelligence capability, with the explicit maturity and limits shown in the product. The permanent constitution remains broader than this release.

## Deliberate limits

Whole-source intake stays at 1,000 ZIP entries / 10 MB total / 512 KB per file. Ten-thousand and fifty-thousand file repositories are rejected; separately measured classifier throughput does not prove full analysis at that scale. SQLite is the local single-writer adapter; PostgreSQL is the production adapter. Existing PostgreSQL/Redis/Linux worker evidence remains labeled with the older tested versions. No new enterprise load, production restore, live GitHub/cloud integration or complete semantic analysis is claimed.

Dependency audits are time-specific. SARIF is validated locally against the official vendored OASIS schema; its acceptance by a live host is unverified. Missing coverage remains null/unavailable. Imported user application code, dependencies, build scripts and tests were never executed. No SonarQube or Wiz dependency was introduced.
