# FINAL PRODUCT VALIDATION — ProjectTrace 1.4.0

Date: 6 October 2026 (Asia/Calcutta). Recorded UTC: 2026-10-06T13:13:24.882703+00:00.

ProjectTrace now has a public landing page, permanent 31-topic Guide and working transitions into its native engineering-integrity platform. The existing native engines remain independent of SonarQube and Wiz. The two supplied specifications are retained in `docs/PRODUCT_CONSTITUTION.txt` and `docs/PUBLIC_LANDING_SPECIFICATION.txt`; the constitution's phases and honest remaining scope are mapped in `docs/PRODUCT_ROADMAP.md`. This release does not claim the entire enterprise vision is complete.

## Exact source and release scope

Base Git commit: `ae98c4a57472249f15ba191947d054673e1de74c` (`fix: pin tinyexec to published version`). Version 1.4.0 is this commit plus uncommitted changes. No new commit, push or PR was created. API/UI/package release is **1.4.0**; native analyzer/rule registry version remains **1.3.3**, because native analysis was preserved. No database migration was added. The new ZIP has one `ProjectTrace/` root and a per-file SHA-256 manifest identifying the exact changed source.

Baseline this turn: clean existing checkout; 131 backend tests, 15 frontend tests and production build passed. The 1.3.3 report is retained as `docs/validation-native-1.3.3.md`. Historical source/benchmark/runtime deliverables remain historical; current tests and public measurements below are fresh. Imported user application code, its dependencies and build were not executed.

## Preservation

Original primary-key sets were compared with current tables after the browser workflows:

| Collection | Before | After | Missing original IDs |
|---|---:|---:|---:|
| organizations | 30 | 40 | 0 |
| users | 30 | 40 | 0 |
| repositories | 26 | 34 | 0 |
| records | 17422 | 18786 | 0 |
| audit_events | 1199 | 1315 | 0 |

SQLite quick check: **ok**. Foreign-key errors: **0**. New rows belong to additive isolated workflow-test tenants/imports and authorized demo review activity. Existing credentials, repositories and source history were retained. This checks row presence and integrity, not a cryptographic comparison of every mutable row. Browser workflows intentionally update review/gate history in test/demo scope. No credentials, raw source database or private preservation backup is in the delivery ZIP.

The two existing smart-waste imports still show **PARTIAL**, native analyzer 1.3.3, 40 files, 74 claims, 19 findings, 245 function metrics, 297 dependencies and three declared cloud assets each. Their earlier TSX grammar diagnostic remains explicit. Unsupported/unchecked dependency and runtime states were not converted into clean results. Earlier source snapshots remain available.

## Architecture

Public React routes → opaque auth-option flags; authorized workspace → existing FastAPI tenant/repository boundary → SQLAlchemy/Alembic PostgreSQL (SQLite local adapter). Workspace/query/graph code loads lazily. Public and workspace components share fonts, themes, badges and source excerpts. A build-time React renderer emits 38 public HTML pages with route metadata; matching client routes hydrate. Directory indexes plus `.html` aliases preserve clean-URL static serving before the SPA fallback.

Native Python AST, maintained JS/TS/TSX/Java grammar helpers, HCL2 and safe YAML produce ProjectTrace-owned evidence, quality/security findings, metrics and static inventory. Existing claims, findings, snapshots and edges remain the center of the Evidence Graph and Claim Ledger. Redis/Celery queues job IDs; encrypted retained source input is scoped and expiring. A bounded grammar process protects the parent, but a complete OS filesystem/network sandbox remains deferred. Static declaration, cloud control-plane and runtime authority remain distinct.

## New working public/product functionality

- Public `/` explains the problem, source-to-decision workflow, native coverage, claim verification/history, change impact, cloud declaration limits, human ownership and next action.
- Synthetic JWT → session history has interactive VERIFIED → STALE → CONTRADICTED stages. Source/finding inspectors use actual maintained demo excerpts and shared source/badge components. No private tenant data, fake scan, customer/logo/testimonial, pricing or fabricated performance counter appears.
- Analyze CTA leads to a real empty local workspace and immediately opens the ZIP import dialog; existing login, source upload and Northstar demo remain functional. Production registration/demo flags are respected; known internal return destinations prevent open redirects. Demo failure has a working retry action.
- Permanent `/guide` plus **31 topics**, simple/technical modes, search, 17-term glossary and interactive eight-stage product map. Every module includes meaning, why, inputs, outputs, example, connections, action and limits. Authenticated sidebar, command palette and major-page context links open the Guide.
- Five real public documents: security model, source/privacy, documentation, about and changelog. Cloud coverage, external AI, retained source, backups, deletion and private-source limits are described precisely.
- Mobile navigation, Escape/focus return, keyboard source scrolling, light/dark/system appearance, reduced motion and useful unknown-path/error screens. Existing canonical and legacy workspace routes remain supported.
- Build-time title/description/Open Graph/Twitter metadata and root software/FAQ structured data. Public domain is unconfigured, so actual local output deliberately uses noindex, disallow-all robots and an empty sitemap. An authorized `PROJECTTRACE_PUBLIC_ORIGIN` enables actual canonical/social URLs and the 38-page sitemap. Public deployment and social-platform rendering were not verified.

## Preserved native functionality

Authorized ZIP intake, snapshot jobs/status, atomic documentation/implementation claims, VERIFIED/INFERRED/UNVERIFIED/CONTRADICTED status and STALE history; source inspection, scoped graph retrieval, true snapshot drift/reverse-graph impact, grounded deterministic Ask, versioned profiles/new-findings gates, owner reviews/concurrency, expiring privileged exceptions, append-oriented audit and optional authorized transports all remain functional. Core connection UI has no competitor dependency.

The following unchanged language/rule/provider coverage is carried from native release 1.3.3 and protected by the current regression/browser suite:

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

| Provider | Status | Verification |
|---|---|---|
| AWS | Implemented bounded direct read-only STS/S3/EC2/IAM SDK adapter; credential/account/repository checks and native ACL/ingress hotspots | SDK fixtures and actual missing-credential browser/API gates pass. **No live authorized account was connected; live provider proof is UNVERIFIED.** |
| Azure | Static resource-kind/configuration observations where supported | Live inventory/CSPM/identity adapter DEFERRED |
| GCP | Static resource-kind observations where supported | Live inventory/CSPM/identity adapter DEFERRED |
| Kubernetes/Compose | Supported static workload/security declarations and actual source references | Cluster/workload runtime inventory and active scanning unsupported |

AWS caps: 50 buckets/100 groups/100 roles, 30-second deadline and bounded SDK timeouts/retries; truncation/failure is PARTIAL. Credentials remain protected tenant-scoped host references. Federation, managed rotation, full pagination, effective IAM permissions/escalation, account-wide access-block/policy semantics and code-to-deployment mappings remain deferred. See `docs/CLOUD_READ_ONLY.md` for exact allowlisted reads and credential setup.

Claim types retain supported framework/database/authentication/API/dependency/configuration facts and declared documentation claims. Inferred imports are not runtime verification. The native cloud addition models narrow affirmative storage-privacy claims with explicit production scope. Unsupported general security/compliance/runtime claims, ambiguous environments and missing evidence remain UNVERIFIED. Similar resource names do not create deployment edges. Static risk paths are configuration risks, not demonstrated runtime attacks.

## Fresh tests and security checks

| Check | Result in this release |
|---|---|
| Backend pytest | **132 passed**, 0 failures, 46.46 seconds; one upstream Starlette TestClient deprecation warning |
| Ruff / Python compileall | Passed |
| Frontend Vitest | **22 passed** in four files, 0 failures |
| TypeScript / Vite 8.3.3 / static build | Passed; **38 public route identities** rendered |
| Playwright Chromium | **9 passed**, 0 failures/flaky/skipped, 44.61 seconds in final run |
| All public HTML without JavaScript | 38/38 exact path/heading checks pass; local static-link audit has 0 missing routes/broken landing anchors |
| Public hydration/network | Interactive hero/Guide works; 0 captured console/page errors; no eager workspace/graph download |
| Axe WCAG A/AA / 2.1 AA | 0 violations on tested public light page, dark mobile page and Guide |
| Locked npm audit | 0 reported vulnerabilities at check time |
| Locked requirements pip-audit | 0 known vulnerabilities reported at check time |
| Database preservation/integrity | 0 missing original IDs; quick check ok; 0 foreign-key errors |

Security regression scope includes tenant/repository ACL/IDOR, CSRF/origin/RBAC, opaque sessions, ZIP traversal/symlink/budgets, source nonexecution, secret masking, webhook signatures/replay, review concurrency/audit, citation/grounding, native profile conflicts/cache scope, cloud read/account gates and parser failure classification. New public tests cover anonymous/private separation, boolean-only auth options, invalid cookies, disabled production registration/demo, return-path allowlists, real fresh import and useful errors. The production auth-options unit test isolates auth policy from the separately tested Redis admission mechanism; production fail-closed behavior is not disabled in application code.

Resolved this turn: muted text failed contrast (4.37:1); source scroll regions lacked keyboard access; long public source lines needed wrapping. Shared contrast/source fixes passed axe and visual checks. A final static-link review exposed Vite serving the SPA home page for extension-free document URLs; `.html` aliases now resolve them correctly, and the no-JavaScript regression asserts all 38 exact page identities/headings. Development-only harness issues (stopped dev server, ambiguous Guide navigation selector, old tour title and an npm command run from the wrong folder) were corrected. The initial Lighthouse launcher failed to spawn; the successful measured runs used a Playwright-owned Chromium CDP session. Final required checks have no unresolved failure.

## UI, accessibility and explanation review

Visual screenshots were reviewed at **1440, 1280, 1024, 768, 390 and 360** pixels, with no horizontal overflow in the browser checks. Desktop/source wrapping, mobile hero/navigation, dark public/Guide, native capability/change sections, FAQ/footer and existing authenticated flows were inspected. Focus/keyboard, Escape, dialogs, labeled forms, reduced motion and all Guide topic limits were exercised. Existing CEO/developer workflow, reviews/audit, real ZIP/second snapshot, native profiles/static cloud and unsupported Ask smoke tests passed.

The public narrative explains stale engineering knowledge in ordinary language; the Guide provides technical mechanisms and limits separately. Its examples join risk, evidence, ownership and action. This is a focused engineering/visual review and automated accessibility scan, not a representative nontechnical/CEO usability study, complete manual screen-reader audit or accessibility certification. Public source examples are synthetic. The existing demo still labels its older local-import history separately from the four maintained synthetic repositories.

## Public performance and bounded load

Lighthouse **13.5.0**, production preview on localhost, Playwright-owned headless Chromium. Mobile uses Lighthouse simulated mobile throttling (150 ms RTT, 1638.4 Kbps, CPU slowdown four); desktop uses the official desktop configuration. One lab run per configuration; both have no run warnings. The final build retains the exact measured public entry hashes; the later routing fix adds static aliases only.

| Lab run | Performance | Accessibility | Best practices | SEO | FCP | LCP | TBT | CLS |
|---|---:|---:|---:|---:|---|---|---|---|
| mobile | 98 | 100 | 100 | 63 | 2.0 s | 2.0 s | 0 ms | 0.002 |
| desktop | 100 | 100 | 100 | 63 | 0.5 s | 0.5 s | 0 ms | 0.002 |

SEO **63** is the actual result: the local page is intentionally blocked from indexing, with no invented public domain. Field INP and real-user Core Web Vitals are **UNMEASURED**. Local scores are not deployment/CDN or sustained-capacity proof. Unused JS (~39 KiB), CSS render-blocking and network/reflow diagnostics remain measured optimization opportunities.

Public initial JS total: **304,226 bytes raw / 94,836 bytes gzip potential**, including shared runtime. Main entry is 295.45 kB; workspace 160.76 kB and graph 180.04 kB are lazy. CSS is 60.89 kB / 11.96 kB gzip. Manifest traversal and actual browser network checks establish that graph/workspace are absent from initial public loading. Gzip size is compression potential, not a claim that preview or a public CDN compresses delivery.

Fresh read-only public API load: 40 localhost requests, four concurrent clients, Windows/SQLite, 0.374 seconds; nearest-rank percentiles, 20 samples per route:

| Route | Requests | Errors | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|
| `/health` | 20 | 0 | 26.221 | 95.798 | 100.671 |
| `/api/auth/options` | 20 | 0 | 31.381 | 97.108 | 101.494 |

These small-sample tails are illustrative. They exclude analysis, queue delay, provider calls and production concurrency; no scale claim is made.

## Native benchmark and service proof carried forward

No analyzer, queue, schema or worker behavior changed in 1.4.0. Earlier benchmark/runtime proof is preserved with its tested release and environment, not relabeled as a fresh 1.4 run:

- Native 1.3.3: **33/33 synthetic fixtures**, seven explicit false-positive traps, rule-presence TP=22/TN=20/FP=0/FN=0. General population/finding-instance precision and recall remain unmeasured. The prior 500-file static run measured median/p95 638.649/659.509 ms; cached 64.379/84.819 ms, excluding persistence/queue/provider time.
- Native 1.3.3 local SQLite API smoke: 40 requests/four clients, 0 errors; workspace p50/p95/p99 261.04/344.78/344.78 ms; Ask 160.45/348.43/348.43 ms. This includes client creation overhead and is not capacity evidence.
- Native 1.3.0: 13 actual PostgreSQL/Redis/Windows-worker checks. Native 1.3.3: seven non-root Linux prefork checks and four forced-crash/natural-lease recovery checks. Tested isolated Alpine 3.24 QEMU, PostgreSQL 18.6, Redis 8.8.0, Python 3.14.8, Celery 5.6.3. Actual upgrade/rollback/re-upgrade, full-text retrieval, duplicate delivery, broker retry, encrypted-input cancellation/expiry and natural lease recovery passed.
- Shipped Compose PostgreSQL 17/Redis 7 images remain **unbuilt/unscanned in this environment**. Production restore/key rotation, sustained queue fairness/load, public hosting and exact container-version deployment are unverified. The VM/service proof establishes its recorded environment only; it is not a currently running cloud deployment.

See the retained native report and native proof JSON for complete timings and limits.

## All 18 product-owner questions

Answers refer to the implemented release scope. Supported behavior is proved; broad security or runtime completeness is never implied.

| Question | Evidence-backed answer |
|---|---|
| Analyze source without SonarQube? | YES: current real-import browser workflow and existing user ZIP/native snapshot evidence. |
| Produce quality results natively? | YES: four-language syntax/AST metrics, duplication/profile/gate regressions and source locations; full semantic analysis remains partial. |
| Perform native SAST? | YES within modeled Python/static-rule scope, with trace/hotspot separation; complete multi-language taint is deferred. |
| Perform native dependency analysis? | YES: inventory, supported lockfiles, optional exact-version advisories and SBOM; unchecked/unknown states stay explicit. |
| Find secrets? | YES for implemented masked patterns and synthetic import fixtures; all secret formats are not covered. |
| Analyze IaC? | YES within supported HCL/YAML/JSON/Dockerfile declarations and native rule fixtures; runtime plans/images are not analyzed. |
| Generate evidence? | YES: source/artifact/observation records and source viewers in current browser workflows. |
| Build claims? | YES: native/documentation atomic claims in real imported snapshots and Claim Ledger regression tests. |
| Show contradictions? | YES: actual demo inspector and synthetic public JWT-to-session example agree with maintained source fixtures. |
| Show true historical drift? | YES: current second-snapshot import workflow and preserved snapshot histories; initial contradictions stay consistency findings. |
| Calculate impact? | YES: supported changed-file/reverse-graph impact with snapshot scope; missing deployment relationships are not fabricated. |
| Analyze a PR? | YES for snapshot/change and synthetic PR evidence with explainable gates; live GitHub installation/check publication remains unverified. |
| Explain a decision? | YES: source, rule/profile, scope, authority, status and gate reasons are inspectable; static results do not claim runtime exploitability. |
| Show ownership? | YES: owner fields, review assignment and current CEO/developer review workflow. |
| Keep an audit trail? | YES: current attributable reviews/profile/import events; audit is append-oriented, not cryptographically tamper-proof. |
| Explain itself to a common person through Guide? | YES in reviewed implementation: 31 simple modules, examples, glossary/product map and contextual help; representative user comprehension is not yet studied. |
| Explain itself to a CEO? | YES in reviewed implementation: problem/risk/ownership/action narrative plus working guided investigation; no real-user business study is claimed. |
| Can a senior developer trust the evidence? | Evidence is inspectable and bounded: exact source/snapshot/rule/authority/trace/coverage and unsupported states are visible. Independent correctness for all languages/runtime behavior is not claimed. |

## Known limits, next phases and deployment requirements

Full interprocedural/type/CFG SAST, broader ecosystems/resolution, population precision, full OS parser sandbox, live AWS proof, Azure/GCP inventory, effective IAM/escalation, deployed reachability and complete code-to-cloud relationships remain incomplete. OIDC/member lifecycle, managed source retention/self-service deletion, backups/restore/key rotation, cryptographic audit archival, semantic vector/AI synthesis, sustained fairness/capacity and monitoring/incident operations remain future constitution phases. Optional historical competitor adapters are compatibility contracts only.

For production: provision supported PostgreSQL, Redis and Linux Celery/beat; migrate safely, manage keys/credentials, restrict origins/RBAC, apply HTTPS/security headers, route public HTML before SPA fallback, proxy API, configure the actual public origin, validate images/restore/operations and verify each authorized provider. The demo installation is loopback only. No public deployment, cloud resource write, provider PR publication or external AI submission was performed.

## Reproduction and artifacts

Follow README for installation and localhost startup. Run backend pytest in a dedicated temp directory, Ruff/compileall, both lockfile audits, frontend tests/build, then Playwright with dev API/UI and a production preview. Set `PROJECTTRACE_STATIC_BASE_URL` to the preview origin so production checks are not skipped. `docs/PUBLIC_EXPERIENCE.md` describes routes, hosting and first import.

Current deliverables: `ProjectTrace-1.4.0-source.zip` and source manifest; this report; v14 browser JSON/screenshots, static-route/link proof, preservation JSON, public-build manifest, raw mobile/desktop Lighthouse plus performance summary, public API load and both dependency audits. Historical native benchmarks/runtime proofs and smart-waste reports remain available separately. Raw tenant source, databases, passwords, session material, backups, VM credentials, dependencies/builds and failure traces are excluded from the clean source archive.
