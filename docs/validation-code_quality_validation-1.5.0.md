# CODE QUALITY VALIDATION — ProjectTrace 1.5.0

Date: 6 October 2026, Asia/Calcutta. Recorded UTC: 2026-10-06T15:40:29.169805+00:00.

The verified release adds native, bounded Code Intelligence to the existing ProjectTrace product. It uses ProjectTrace-owned classification, metric formulas, rule metadata, duplication, coverage import, baseline history and gates. Python, JavaScript, TypeScript and Java have **PARTIAL language maturity**. A file parser may complete while the language capability remains partial. This is not a claim that the permanent industry/enterprise vision is finished.

## Exact source and preserved foundation

Base Git commit: `ae98c4a57472249f15ba191947d054673e1de74c`. The release is that commit plus the preserved 1.4 baseline and current uncommitted changes; no commit, push or PR was created. API/UI/native analyzer/rule version is 1.5.0. Migration 0006 adds quality projections and occurrence indexes without replacing authoritative Record findings, source, reviews, policies or graph relationships. Source ZIP and per-file manifest identify the delivered code under a single `ProjectTrace/` root. No credentials, source databases, retained uploads, dependencies, caches or private preservation backup are delivered.

The supplied master prompt is retained exactly in `docs/CODE_QUALITY_SPECIFICATION.txt`. The inspected starting state, gaps, implemented phase scope and remaining limits are mapped in `docs/CODE_QUALITY_AUDIT.md`. Historical public/native validations remain in `docs/validation-public-1.4.0.md` and `docs/validation-native-1.3.3.md`; earlier PostgreSQL/Redis/Linux worker evidence is not relabeled as fresh 1.5 verification.

## Structural model and formulas

Python uses the interpreter AST shared by quality metrics and observations; the existing security-flow pass remains separate. JavaScript, TypeScript/TSX and Java use installed Tree-sitter grammars in ProjectTrace's isolated helper. Imported source is inert JSON/text input. No imported build, install, test runner, repository hook, configuration code or application was executed.

Files carry classification, physical lines, bytes, content hash, parser state and supported syntax counts. Non-UTF-8 source and binary ZIP entries remain visible in the inventory without fabricated decoded source. Vendor, generated, configured exclusions, tests and examples receive explicit treatment. Unsupported language/override, parser gaps and work-budget exhaustion yield PARTIAL; no matching source yields NOT_AVAILABLE/applicability output. Generated parse failures do not distort the quality scope. Python class names include nested qualified ownership. Module/class/function/method/constructor/interface/field symbols are available where the native syntax exposes them; universal type resolution and unused-variable analysis are not implemented.

Cyclomatic complexity is `1 + recorded branch contributions`. Python counts if/loop/except/ternary, boolean alternatives and match alternatives; native grammars count their recorded if/loop/catch/case/ternary/short-circuit decisions. Nested definitions are excluded from a function's own decision counts. ProjectTrace cognitive complexity sums `decision contribution × (1 + enclosing syntax-control depth)` and adds direct same-name recursion for Python. This is a documented first-party approximation, not compatibility with a proprietary model. Function length is physical source span; nesting is syntax-control depth; parameters exclude Python self/cls where modeled. Contributors and source ranges are inspectable.

File logical statements are parser statement/declaration nodes, including nested constructs. They are not cross-language-equivalent logical LOC. Comment lines come from Python COMMENT tokens or grammar comment nodes. No inferred coverage, opaque quality grade, authored Git history or runtime reachability is presented.

## Owned rule registry

| Rule | Observation | Dimension | Default threshold | Maturity | Languages |
|---|---|---|---|---|---|
| PT-QUALITY-001 | Cyclomatic decisions | MAINTAINABILITY | 10 | STABLE | Python, JS, TS, Java |
| PT-QUALITY-002 | Function physical span | MAINTAINABILITY | 80 | STABLE | Python, JS, TS, Java |
| PT-QUALITY-003 | Control nesting | MAINTAINABILITY | 4 | STABLE | Python, JS, TS, Java |
| PT-QUALITY-004 | Class physical span | MAINTAINABILITY | 200 | BETA | Python, JS, TS, Java |
| PT-QUALITY-005 | Bare exception | RELIABILITY | — | BETA | Python |
| PT-QUALITY-006 | Empty exception handler | RELIABILITY | — | BETA | JS, TS, Java |
| PT-QUALITY-007 | Normalized duplicate block | MAINTAINABILITY | 50 tokens / 6 lines | BETA | Python, JS, TS, Java |
| PT-QUALITY-008 | ProjectTrace cognitive approximation | MAINTAINABILITY | 15 | BETA | Python, JS, TS, Java |
| PT-QUALITY-009 | Parameter count | MAINTAINABILITY | 7 | BETA | Python, JS, TS, Java |
| PT-QUALITY-010 | Unreachable following statement in same block | RELIABILITY | — | STABLE | Python |
| PT-QUALITY-011 | Mutable literal default | RELIABILITY | — | STABLE | Python |
| PT-QUALITY-012 | Identity comparison with value literal | RELIABILITY | — | STABLE | Python |

Six rules are stable and six beta. The UI registry includes versions, severity, examples, language limits, metric semantics, remediation and enabled/threshold controls. Duplicate-token thresholds are bounded at 30–10,000, retaining the six-line minimum; other numeric rule thresholds are 1–10,000. Reliability rules without a threshold reject that parameter. Organization defaults and repository overrides reuse audited NativeProfile with optimistic versions. Existing native settings survive quality-profile saves.

Twelve manually labeled positives, twelve negatives and twelve generated-scope variants passed. These fixtures establish expected bounded behaviors, **not population precision/recall** or universal false-positive rates. No beta rule automatically fails a gate. Legacy one-line duplicate alerts were intentionally replaced by substantial block requirements and documented as a noise reduction.

## Native duplication

Parser tokens remove comments/formatting, normalize local binding names and preserve operators and hashed literal values. Native matching verifies windows then extends matching blocks and groups occurrences; source inspectors show side-by-side spans. Different operators/literals do not imply equivalent clones. Default minimum is 50 tokens and six physical source lines. Density uses the union of duplicated production lines divided by selected production physical lines; New Code uses duplicated changed production lines divided by changed production physical lines. Empty denominators are unavailable, not zero.

Work is bounded by 100,000 windows, 20,000 candidate pairs, five million window/comparison token operations, 31 candidates per window and 200 groups. Exceeding a budget yields PARTIAL, not a fabricated complete result. Repeated matched ranges avoid redundant extension work. Detection covers function-body blocks, not whole-program semantic clones or complete cross-language duplication. Nested lexical bodies remain syntactic spans, so inspect context before extracting an abstraction.

## Identity, baseline and review

Fingerprint model `quality-symbol-v2` hashes rule + path + qualified symbol + structural symptom anchor, without line offsets. Observation/body context additionally controls whether a human review carries. Comments/blank-line movement keeps identity/review for unchanged semantics; changed symptom/body context resets review. Path/symbol renames create new identities. Repeated identical anchors in a symbol use occurrence order and can shift when identical earlier occurrences are inserted.

Explicit caller BASE takes precedence over configured BASE. First analysis is INITIAL; a compatible BASE produces NEW/EXISTING and absent observations become RESOLVED. Reintroduction in explicit BASE ancestry becomes REOPENED. Worsened existing numeric observations on changed source can be New Code while retaining identity. Analyzer/parser/rule/scope changes require a comparable baseline and do not turn unmatched older identities into claimed fixes. Ancestry is bounded to 200 same-tenant/repository snapshots; unrelated branches are not used to resolve issues.

OPEN/IN_REVIEW/CONFIRMED/FALSE_POSITIVE/ACCEPTED/RESOLVED human decisions remain distinct from machine deltas. Review writes require repository authorization, CSRF/origin, expected versions and a reason. Risk acceptance and exceptions require privileged roles and expiry. An accepted label alone cannot permanently exempt an expired exception: the gate returns to evaluating its finding after expiry. A review event does not rewrite the stored analysis observation.

## Coverage and explainable gates

Coverage imports support LCOV, Cobertura/coverage.py XML and JaCoCo XML as inert reports. The browser fixture imports actual LCOV counters and displays 75% reported line coverage. Format tests exercise mapped lines/branches and changed-line percentages. Missing reports remain NOT_AVAILABLE with null percentages; malformed inputs, entity declarations, ambiguous/traversal paths, conflicting counters and wrong producer revisions are rejected. Partial reports remain partial.

Limits: one MB per report, 100,000 counters, 150,000 XML nodes, depth 50. A recognized JaCoCo external declaration is removed without resolving it. Producer path prefix/source-root mappings are explicit; exact repository-relative source candidates and line ranges must match. Reports append content hash, declared producer/revision, source snapshot, mapping and actor provenance. These declarations do not independently prove test execution, authenticity or report freshness. A local content digest is labeled separately from a provider Git commit.

Quality gates are separate from security gates and feed the existing unified advisory engineering/PR result. Scope is NEW_CODE or OVERALL. Conditions show measured value, threshold, reason, remediation and linked findings. Default stable high/critical new findings and stable new reliability findings must be zero; changed-function complexity budget is 20. Beta normalized duplication above the configured three-percent density requires review; beta observations cannot automatically FAIL. Coverage is enforced only when its condition is configured. Missing/comparability BASE, required invalid/unavailable coverage and partial analysis yield REVIEW_REQUIRED. No first-party source makes quality conditions explicitly not applicable.

Current review/active exceptions/latest imported coverage feed effective quality and PR gates. Original snapshot/profile/gate evidence remains captured and preserved. Existing security/claim gates are composed by the worse applicable result. CLI exits PASS/WARNING=0, FAIL=2, REVIEW_REQUIRED=3, invalid input=4; each outcome has a regression fixture. Live GitHub/other SCM publishing was not verified.

## Evidence, owners, impact and history

Findings use the authoritative Record/review/source model. QualityOccurrence indexes support tenant/repository/snapshot/rule/severity/dimension/language/delta reads; QualityAnalysis is a captured projection with foreign-key ownership and uniqueness. Migration tests prove fresh head, rollback/re-upgrade and unchanged 0005 snapshot/profile rows. Runtime migration head is 0006.

Quality findings connect by DETECTED_IN to source, AFFECTS_FUNCTION to structural function nodes, OWNED_BY to CODEOWNERS/repository ownership, and DERIVED_FROM to quality policies. Shared evidence links related claims; graph traversal exposes affected findings/policies in PR impact. A dedicated test proves source/function/owner/policy relationships, PR FAIL, impact propagation and exception expiry. Owners are assignments, not inferred authors. Supported CODEOWNERS matching is bounded last-match glob handling, not full provider semantics.

Hotspot ranking is explicit: maximum cyclomatic + 3×active quality findings + 5×high/critical findings + min(duplicate lines,100)/10 + 2×observed snapshot changes. Factors and ownership are inspectable. Git authors and Git change frequency are null. Trends show captured branch-scoped counts, available coverage and duplication over 7/30/90-day windows, with model/profile annotations and a 200-snapshot bound. This is observed ProjectTrace history, not reconstructed Git history.

## Real supplied ZIP

The exact attached `smart-waste-management-system-main.zip` was statically analyzed; archive SHA-256 is `293fca0b7f1cf9b42b6726073b3468ae05ba432fe310daa81b93e0f7fd969919`. Its content was not executed or edited. Three already-owned smart-waste repository records receive additive 1.5 snapshots, retaining their configured severities and prior history.

The input contains 47 UTF-8 files: 19 production source, one test and 27 non-source files. Analysis reports 245 functions and 22 maintainability findings: seven cyclomatic, seven length, five cognitive, two parameter-count and one nesting observation. No native reliability rule triggered in the bounded scope. One file, `smart-waste-management-system-main/frontend/src/main.tsx`, has partial grammar coverage. Maximum observed cyclomatic is 32; metrics from that file are syntax observations from a partial parse. There are zero duplicate groups under the configured bounds. Coverage is NOT_AVAILABLE. Zero native SAST findings here is not a security-clean certification.

Current persisted imports show zero new and zero resolved quality observations for the unchanged source/model transition. Reanalyzing the same ZIP is not an authored code improvement. Legacy fingerprint changes are not claimed as fixed bugs. `ProjectTrace-1.5.0-smart-waste-analysis.json` records counts, diagnostic path and measured functions; the SARIF artifact is validated against the official schema and includes no source execution or coverage invention.

## Fresh validation

- Backend: **171 passed**, zero failures/errors/skips, 129.181 seconds. Ruff and Python compileall passed.
- Frontend: **22 passed**. TypeScript and final production build passed; 38 public routes prerendered with local noindex settings.
- Chromium: **10 passed**, zero failed/skipped/flaky; 125.78 seconds. Includes real signup/fresh ZIP import, return login, native/cloud profiles, quality review/baseline/source/duplication/coverage, graph/claims/security/drift and public/privacy/Guide workflows.
- Layout: screenshots and document overflow checks at 1440/1280/1024/768/390/360 pixels; selected Code Quality and public/Guide axe WCAG 2 A/AA/2.1 AA checks pass, including a dark 360-pixel quality view. This is selected browser validation, not a full accessibility certificate. Source/table regions support keyboard scrolling.
- Public production preview: all 38 exact HTML identities/headings work with JavaScript disabled and hydrate without eager graph/private workspace downloads. Existing light/dark/system and reduced-motion behavior remain.
- SARIF 2.1 validates with JSON Schema Draft 4 + format checker against the unmodified official OASIS schema; SHA-256 `c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e`. Live host ingestion is unverified. CSV formula prefixes are neutralized; JSON exports preserve scoped findings.
- Locked pip/npm audit artifacts report zero known vulnerabilities at the recorded run; future vulnerability status is not certified. No runtime SonarQube/Wiz integration was added.

Development failures were resolved before final proof: scoped finding kind prevented review UI access; accessible baseline label and saved-profile feedback were corrected; wide table regions became keyboard focusable; old import assertions were adapted to the dedicated view/versioned title. Windows pytest temporary-directory access failed on one attempt; an owned isolated temporary root fixed the environment. One browser run overlapped a direct local repository refresh and encountered SQLite's single-writer lock; final runs are serialized with that refresh and all ten pass. This does not prove sustained concurrent SQLite capacity. Starlette's testclient emitted one deprecation warning; it is recorded, not a test failure.

## Measured local performance

Windows/Python 3.14.3; installed parser signature `d939d5f473a80956a75abee914f8420842c8d60005528ce78c40cd6749db144b`. Sequential analyzer samples were measured after test workloads finished. Twelve cold and twenty cached samples per size use nearest-rank percentiles; with these sample sizes p99 equals observed maximum, not production tail proof. Fixtures are distinct small Python functions, not representative mixed-language monorepos.

| Files | Cold p50 ms | Cold p95 ms | Cold p99 ms | Cached p50 ms | Cached p95 ms | Cached p99 ms | Reused files |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10 | 3.43 | 10.31 | 10.31 | 0.61 | 1.22 | 1.4 | 10 |
| 100 | 35.32 | 39.61 | 39.61 | 7.82 | 10.03 | 11.2 | 100 |
| 1000 | 958.01 | 1358.15 | 1358.15 | 260.3 | 325.93 | 347.7 | 1000 |

At 1,000 files the observation cache serializes to 2,054,900 bytes. Total benchmark-process peak working set is 108,232,704 bytes, including accumulated classifier/corpus/results; isolated grammar-helper RSS is excluded. The benchmark measures classifier-only components at 10k/50k, while whole-source intake rejects both sizes. Those component results are not full-repository scale proof. A final file-metric lookup map avoids an avoidable per-file scan of every signal; cached parsing still performs bounded scope/quality/duplication projection work.

Reproduce with `python -m scripts.benchmark_quality --output quality-benchmark.json --real-zip repository.zip`. No imported dependency installation or program execution occurs. Mixed-language/tail/saturation/large unique repositories and fresh enterprise capacity are unverified.

## Preservation evidence

| Table | Before | After | Missing original IDs |
|---|---:|---:|---:|
| organizations | 40 | 61 | 0 |
| users | 40 | 61 | 0 |
| repositories | 34 | 52 | 0 |
| records | 18786 | 34850 | 0 |
| audit_events | 1318 | 2004 | 0 |

All 40 original credential hashes and all 99 original stored snapshot payloads are unchanged. SQLite quick check is ok, foreign-key errors zero. New rows are additive analyses and disposable browser fixtures. Other mutable review/audit/profile rows were not claimed byte-for-byte equal. Original private backup/ID files remain outside the source archive and deliverables. Historical public performance and real-runtime measurements retain their original versions.

## Product-owner proof questions

| Question from section 152 | Verified release answer and proof |
|---|---|
| Parse supported source structurally? | Yes within partial maturity: AST/grammar fixtures, explicit parser versions/states and real TSX diagnostic. |
| Calculate explainable complexity? | Yes: recorded contributions/formulas, parameter/span/nesting and contributor/source inspectors. |
| Identify maintainability problems? | Yes: threshold and normalized-duplicate fixtures; 22 observations in supplied ZIP. |
| Identify reliability problems? | Yes for modeled Python structural/exception and grammar exception checks; twelve-rule positive/negative corpus. |
| Detect duplication meaningfully? | Yes for substantial function blocks: renamed binding positives, operator/literal negatives, bounded groups and comparison UI. |
| Import real coverage? | Yes: LCOV/XML fixtures and browser 75% LCOV counters, revision/path/error tests. |
| Distinguish New Code? | Yes: explicit BASE, introduced and worsened-existing findings on changed lines; browser new-file result. |
| Use a baseline? | Yes: caller/configured BASE and same-scope ancestry/comparability tests. |
| Configure organization profiles? | Yes: audited organization defaults and repository overrides in NativeProfile; version/conflict/RBAC tests. |
| Configure gates? | Yes: NEW_CODE/OVERALL conditions/thresholds captured in profiles; API/CLI outputs and source-linked results. |
| Survive harmless movement? | Yes: fingerprint/review unchanged after 20 blank lines; changed body/rename boundary tests. |
| Review/resolve findings? | Yes: common inspector, reasons, optimistic version, machine removal/reopen and accepted-risk expiry tests. |
| Exclude generated/vendor correctly? | Yes in documented classifier/glob scope: twelve generated cases, vendor/scope and generated parse-error tests. |
| Show analysis coverage? | Yes: inventory/maturity/parser states, unsupported overrides/encoding, diagnostic and budget PARTIAL results. |
| PR quality results? | Yes locally: PR snapshot stores quality result and UI reads effective composed gate; dedicated PR test. Live publishing unverified. |
| Show improvement/regression history? | Yes for observed snapshots: removal/reintroduction/worsening and captured trend windows. No Git-history claim. |
| Identify maintenance hotspots? | Yes: explicit factors, observed changes and owner columns. No invented author/frequency signal. |
| Explain important findings? | Yes: versioned rule, measurement/threshold, range, symbol, remediation, contributors and source evidence. |
| Connect owners? | Yes: supported CODEOWNERS/fallback provenance and OWNED_BY fixture. |
| Connect Evidence Graph? | Yes: shared Record/source/function/owner/policy relationships and graph integrity suite. |
| Affect policies? | Yes: quality-derived policy results and combined gate/expiry tests. |
| Contribute Impact analysis? | Yes: affected findings/policies and PR graph traversal fixture. |
| Senior developer can trust the result? | Qualified: reproducible, source-linked, versioned syntax/report observations with explicit unknowns. Full semantics, production precision, enterprise scale and live integrations are not certified. |

## Operating instructions and remaining scope

Open `http://127.0.0.1:5181/quality` and use the existing account. Select repository/HEAD. Use Findings to inspect or review, Rules & Profiles to choose an accepted BASE, Repositories to upload a subsequent ZIP, and Coverage to import the producer report for that exact HEAD. Existing stored credentials remain valid. The local API is port 8011 and UI port 5181; these are local services, not a public deployment. For fresh source imports use Repositories → Import ZIP, not the synthetic demo.

The release does not claim full CFG/dataflow/type/framework support, full declaration/unused-symbol/call resolution, proprietary cognitive equivalence, arbitrary-language support, Git author history, report-producer authenticity, live SCM check/SARIF publication, sustained multiwriter SQLite or enterprise PostgreSQL load, 10k/50k whole-analysis capacity, complete accessibility certification or completed industry readiness. Owned rules/metrics remain static evidence; senior review is still needed. The permanent constitution and audit map retain these limits as further work, not hidden success.

Reference principles, without runtime dependency or copied proprietary algorithms: [Qodana baselines](https://www.jetbrains.com/help/qodana/baseline.html), [Codacy gates](https://docs.codacy.com/repositories-configure/adjusting-quality-gates/), [DeepSource issue workflow](https://docs.deepsource.com/docs/platform/dashboard/repository/issues), [PMD duplication](https://docs.pmd-code.org/latest/pmd_userdocs_cpd.html), [coverage.py XML](https://coverage.readthedocs.io/en/latest/commands/cmd_xml.html), [JaCoCo report format](https://github.com/jacoco/jacoco/blob/master/org.jacoco.report/src/org/jacoco/report/xml/report.dtd), [GitHub SARIF](https://docs.github.com/en/enterprise-cloud%40latest/code-security/reference/code-scanning/sarif-files/sarif-support), and [OASIS SARIF schema](https://github.com/oasis-tcs/sarif-spec/blob/main/sarif-2.1/schema/sarif-schema-2.1.0.json).
