# ProjectTrace enterprise trust validation — 1.6.0

Validated locally on Windows with Python 3.14.3, SQLite, synchronous analysis and Chromium. This is a trust-foundations release, not completion of the enterprise program. The permanent product vision and Claim Ledger / Evidence Graph remain. Section 41 of the execution specification permits explicit deferral; every unfinished capability below remains NOT DONE.

The pre-implementation audit is [ENTERPRISE_READINESS_BASELINE.md](ENTERPRISE_READINESS_BASELINE.md). Operator instructions are [ENTERPRISE_TRUST_OPERATIONS.md](operations-enterprise-trust-1.6.0-before-hardening.md). Exact requested scope is [ENTERPRISE_TRUST_SPECIFICATION.txt](ENTERPRISE_TRUST_SPECIFICATION.txt). Final verification totals and measurement context are in [enterprise-verification-1.6.0.json](../benchmarks/enterprise-verification-1.6.0.json). Tests named below are executable checks against owned fixtures; imported customer projects were never built, installed, tested or executed.

STATUS describes the delivered behavior for the question's full requested scope. SUPPORTED is bounded to the behavior stated, PARTIAL identifies missing implementation or verification, UNSUPPORTED means the target is not delivered, and UNMEASURED means the required measurement does not exist. No production acceptance follows from local tests.

| Question | Status |
| --- | --- |
| 1. Accuracy | UNMEASURED |
| 2. False positives | UNMEASURED |
| 3. Language support | PARTIAL |
| 4. Parser failure | PARTIAL |
| 5. Imported code execution | SUPPORTED |
| 6. Source egress | PARTIAL |
| 7. Source to an LLM | SUPPORTED |
| 8. Tenant isolation | PARTIAL |
| 9. Secrets | PARTIAL |
| 10. Private deployment | PARTIAL |
| 11. GitHub Enterprise | UNSUPPORTED |
| 12. OIDC | PARTIAL |
| 13. Three-million-line monorepo | UNSUPPORTED |
| 14. One hundred simultaneous PRs | UNMEASURED |
| 15. Contradiction evidence | SUPPORTED |
| 16. Trust metadata | PARTIAL |
| 17. Stable finding identity | PARTIAL |
| 18. Configurable quality gates | PARTIAL |
| 19. Expiring exceptions | PARTIAL |
| 20. Audit integrity | PARTIAL |
| 21. Unsupported languages | PARTIAL |

## 1. HOW ACCURATE IS IT?

**STATUS: UNMEASURED.** Representative deployment accuracy is unknown.

**IMPLEMENTATION EVIDENCE:** `scripts/benchmark_enterprise.py` defines a versioned, manually labeled synthetic corpus with source hashes and per-rule/version/language/framework TP/TN/FP/FN, precision, recall and F1. `analyzers/native_rules.py`, `analyzers/capabilities.py` and native finding metadata explicitly retain UNMEASURED precision and false blocking eligibility. `backend/domain.py` requires explicit blocking eligibility before a critical rule can block by default. Quality thresholds with unqualified rule precision require review; explicitly measured coverage policies remain separately enforceable.

**TEST EVIDENCE:** `test_capabilities_do_not_claim_full_support_or_measured_precision`, `test_unmeasured_native_rule_never_blocks_by_default`, and the positive/negative quality fixtures in `test_code_quality.py`.

**BENCHMARK EVIDENCE:** [enterprise-labeled-accuracy-1.6.0.json](../benchmarks/enterprise-labeled-accuracy-1.6.0.json): 22 cases, 11 selected rule/language/framework groups, two cases per group. Each group has one TP and one TN, zero FP/FN on those exact cases, and population SYNTHETIC_ONLY_UNQUALIFIED. This is not a universal accuracy score. The previous quality corpus remains separately available in `benchmarks/code-quality-1.5.0-measurements.json`.

**LIMITATIONS:** No representative repository population, independent labeling agreement, calibration intervals, production recall, or qualified rule-promotion process. Uncovered rules and frameworks have no accuracy measurement.

**NEXT ACTION:** Deferred: collect a licensed representative corpus, independently label it, measure each rule/version/language/framework separately, and implement qualification and regression thresholds before promoting default blocking.

## 2. HOW MANY FALSE POSITIVES?

**STATUS: UNMEASURED.** Population false-positive rate is unknown.

**IMPLEMENTATION EVIDENCE:** `backend/main.py` records FALSE_POSITIVE judgments with rule/version/language/framework, actor, reason and scope. `backend/trust_api.py` exposes latest judgments per occurrence only within authorized repositories. Dismissal fraction is labeled feedback, not precision; a dismissal does not globally disable a rule. Later review actions supersede earlier judgments.

**TEST EVIDENCE:** `test_false_positive_feedback_has_context_and_is_not_population_precision` verifies a dismissal, versioned context, scoped feedback and continued UNMEASURED status.

**BENCHMARK EVIDENCE:** The 22 synthetic cases above contain zero observed false positives for their selected labels. There is no measured false-positive rate across real repositories or unreviewed findings.

**LIMITATIONS:** Voluntary review is biased. The projection limits its window to the latest 20,000 review events. Legacy reviews lack the new metadata. No false-positive confidence interval or cross-tenant population statistic exists.

**NEXT ACTION:** Deferred: representative negative cases, adjudicated reviews, rule calibration and promotion/regression workflows. Preserve tenant privacy when aggregating any feedback.

## 3. WHAT LANGUAGES ARE TRULY SUPPORTED?

**STATUS: PARTIAL.** Selected native syntax and rules are implemented; no language is declared semantically complete.

**IMPLEMENTATION EVIDENCE:** `/api/trust/capabilities` reports Python, JavaScript, JSX, TypeScript, TSX and Java plus Terraform, CloudFormation, Kubernetes, Compose and Dockerfile. It reports parser/grammar versions, PARTIAL maturity, selected quality/security scope, limited flow, runtime unobserved and UNMEASURED precision. Python uses CPython AST; JS/TS/Java use Tree-sitter grammars; infrastructure uses owned bounded HCL/YAML/JSON/instruction processing. Trust & Coverage renders this registry. File inventory remains visible for unsupported source.

**TEST EVIDENCE:** `test_native_languages_have_versioned_parser_metrics`, `test_native_large_tsx_locations_and_parser_lifecycle`, `test_quality_scope_cache_thresholds_and_parser_honesty`, and the capability test. JSON infrastructure intake and coverage are checked by `test_json_infrastructure_intake_and_coverage_agree` for all four relevant formats.

**BENCHMARK EVIDENCE:** Selected synthetic IaC/Python rule groups and previous quality measurements only; these do not measure whole-language or framework coverage.

**LIMITATIONS:** No complete type/CFG/framework/cross-file taint model. Unsupported languages such as Go are inventory gaps. Structured declarations and syntax parsing are not complete security coverage. Coverage import accepts producer reports; ProjectTrace does not run project tests.

**NEXT ACTION:** Deferred: publish rule-level representative coverage by framework and extend supported semantic models without declaring syntax support equivalent to completeness.

## 4. WHAT HAPPENS WHEN YOUR PARSER FAILS?

**STATUS: PARTIAL.** Failures and budgets produce visible partial/failed coverage, but full OS isolation is incomplete.

**IMPLEMENTATION EVIDENCE:** `analyzers/infrastructure.py` runs owned IaC parsing in an isolated Python interpreter with an empty temporary cwd and stripped environment, a 15-second wall timeout, 512KB source bound and 8MB result check. `iac_worker.py` applies POSIX CPU/address-space/file/descriptors limits. YAML aliases, excessive nesting/tokens and unrendered Helm are refused. Existing grammar helpers remain bounded. Engine diagnostics do not turn parser failure into a clean scan.

**TEST EVIDENCE:** `test_iac_process_failure_does_not_mark_unaffected_python_clean`, `test_native_parser_process_failure_is_partial_not_clean`, `test_kubernetes_structure_and_alias_budgets`, and unsupported-encoding tests.

**BENCHMARK EVIDENCE:** No adversarial OS resource or parser escape qualification benchmark. Synthetic fixtures measure behavior, not a complete sandbox.

**LIMITATIONS:** Python AST still runs in the parent analysis process. Windows does not enforce the POSIX helper limits. Full non-root/read-only/no-network/process-count isolation, Windows job objects, and independent memory/output enforcement for every parser are deferred. The post-capture output bound is not an OS output quota.

**NEXT ACTION:** Deferred: isolate every parser with enforced CPU/memory/process/output/network/filesystem quotas, then run crash, exhaustion and escape tests on supported deployment platforms.

## 5. DO YOU EXECUTE OUR CODE?

**STATUS: SUPPORTED.** Imported projects are treated as inert data.

**IMPLEMENTATION EVIDENCE:** `analyzers/engine.py` validates archive paths, entries and byte budgets. Owned parser helpers consume text; they do not invoke commands embedded in that text. Docker RUN/CMD, Terraform providers/modules, CloudFormation transforms, Compose commands, Helm templates, hooks, project builds and imported test runners are not executed. Customer ZIP analysis was performed only through ProjectTrace's static analyzer.

**TEST EVIDENCE:** `test_source_is_never_executed`, `test_multistage_docker_final_user_and_inert_commands`, archive traversal/symlink/size tests, and `test_quality_cli_exit_codes_and_reports_are_based_on_inert_zip_data`. The inert-command fixture verifies no marker file appears.

**BENCHMARK EVIDENCE:** All benchmark inputs are owned synthetic text consumed statically. No imported project is executed to produce accuracy or scale results.

**LIMITATIONS:** Owned parser processes do execute ProjectTrace code; this guarantee does not claim complete OS sandboxing or absence of vulnerabilities in parser dependencies.

**NEXT ACTION:** Retain the non-execution contract and extend adversarial regression coverage whenever intake or parsing changes.

## 6. DOES OUR SOURCE LEAVE YOUR INFRASTRUCTURE?

**STATUS: PARTIAL.** Application source transfers are disabled; deployment-wide egress containment is unverified.

**IMPLEMENTATION EVIDENCE:** New tenant policies default to NO_EXTERNAL_SOURCE_EGRESS, AI DISABLED, package advisories disabled and GitHub check metadata disabled. Strict administrator-only, versioned policy changes are audited. Advisory admission and workers recheck tenant authorization. Authorized OSV requests contain ecosystem/name/version. Optional GitHub checks contain system policy names/result states, omitting source excerpts and free-text reasons. GitHub source retrieval is authorized inbound ingestion. There is no source-sharing mode.

**TEST EVIDENCE:** Default-deny/admin/version tests, existing advisory worker tests and `test_check_metadata_omits_source_backed_reasons`. The enterprise browser test changes a tenant policy and verifies its audit chain.

**BENCHMARK EVIDENCE:** No deployment packet-capture or enforced-egress penetration test was run. Local benchmarks use no external project-code execution or source-export provider.

**LIMITATIONS:** Application settings are not firewall/network policy. Provider traffic, operator access, backups, database storage and logging still need deployment controls. Comprehensive DLP, enforced destination isolation and production traffic proof are deferred.

**NEXT ACTION:** Deferred: verify outbound network policy and data-flow captures on the private staging deployment, including logs and backup destinations.

## 7. DOES AN LLM RECEIVE SOURCE?

**STATUS: SUPPORTED.** No external LLM call is implemented in this release.

**IMPLEMENTATION EVIDENCE:** Tenant AI mode accepts DISABLED only. `backend/llm_gateway.py` defines an interface, bounded redacted context and citation validation but no enabled network provider. `/api/ask` uses authorized stored evidence and deterministic answers. Setting an unused LLM environment variable does not enable source transfer.

**TEST EVIDENCE:** `test_ask_is_grounded`, `test_fake_citation_rejected`, `test_context_redacts_and_bounds_source`, `test_prompt_injection_is_data_only`, and strict tenant-policy validation.

**BENCHMARK EVIDENCE:** Static benchmark outputs are produced without an LLM. No LLM accuracy metric is claimed.

**LIMITATIONS:** Customer-managed AI, external AI consent, provider contracts/retention and AI audit trails are not implemented. The gateway interface is not an enabled provider feature.

**NEXT ACTION:** Keep DISABLED enforced. Any AI feature needs a separately implemented and verified tenant egress contract before enabling it.

## 8. HOW DO YOU ISOLATE TENANTS?

**STATUS: PARTIAL.** Application authorization and ORM write guards are verified locally; database defense in depth is incomplete.

**IMPLEMENTATION EVIDENCE:** `backend/security.py` applies organization/session/repository grants. Trust projections filter authorized repositories and snapshots. `backend/db.py` rejects cross-organization repository grants, scoped record/projection references, OIDC membership mismatch and organization reassignment during ORM flush. Workspace query caches are per authenticated workspace and cleared on sign-out.

**TEST EVIDENCE:** `test_cross_tenant_idor`, `test_private_repository_acl_applies_to_every_surface`, `test_cross_tenant_orm_references_are_rejected`, `test_trust_projections_require_repository_and_snapshot_scope`, `test_graph_snapshot_query_and_impact_never_cross_tenant_or_repository`, and browser context isolation.

**BENCHMARK EVIDENCE:** No PostgreSQL RLS acceptance test or tenant contention/load benchmark. Local tests use SQLite and isolated synthetic tenants.

**LIMITATIONS:** Direct SQL bypasses ORM guards. Complete compound tenant foreign keys and PostgreSQL RLS across the original schema are not delivered. Cache/queue/object-store/resource-quota separation lacks enterprise deployment proof.

**NEXT ACTION:** Deferred: compound tenant constraints, activated RLS, privileged-worker boundaries and cross-tenant adversarial tests on PostgreSQL/Redis/private storage.

## 9. HOW DO YOU HANDLE SECRETS?

**STATUS: PARTIAL.** Known patterns are masked and retained worker input is encrypted; comprehensive secret lifecycle controls are absent.

**IMPLEMENTATION EVIDENCE:** `analyzers/engine.py` masks credential-shaped assignments, private keys, database URL passwords and supported token formats before evidence persistence. Resource metadata is recursively masked, including keys and nested relations. Kubernetes Secret/ConfigMap values are not retained as resource metadata. Queued source and OIDC PKCE verifiers use the existing Fernet input cipher. OIDC callback access logs mask authorization-code/state query strings. Credentials stay in operator configuration and are not validated by using them against providers during secret scanning.

**TEST EVIDENCE:** `test_import_redacts_secrets`, `test_secret_masking_and_private_key`, `test_native_metadata_masks_credentials_before_caching`, `test_secret_values_are_not_resource_metadata_and_rbac_is_structural`, encrypted queue tests and `test_oidc_callback_access_log_masks_authorization_code_and_state`.

**BENCHMARK EVIDENCE:** Pattern fixtures only. No comprehensive secret-recall, entropy/DLP, KMS or rotation benchmark.

**LIMITATIONS:** Unknown secret formats can remain in source evidence. SQLite source evidence is not comprehensively encrypted at rest by ProjectTrace. Backups/operator storage and provider credentials need protected deployment storage. Key rotation, tenant deletion across backups, KMS lifecycle and complete log/archive DLP are deferred.

**NEXT ACTION:** Deferred: managed key integration, rotation/deletion drills, broader secret corpus and storage/log/export/backups validation. Never use detected customer credentials to test their validity.

## 10. CAN I DEPLOY IT PRIVATELY?

**STATUS: PARTIAL.** Self-hosting assets exist; enterprise private-deployment acceptance is not established.

**IMPLEMENTATION EVIDENCE:** `compose.yaml`, `infrastructure/Dockerfile`, `infrastructure/frontend.Dockerfile`, Nginx and `docs/deployment.md` retain the local/self-hosted deployment path. The backend image uses a non-root user. Existing migrations, backup tools and environment configuration remain. No new external service dependency or SonarQube/Wiz dependency was introduced.

**TEST EVIDENCE:** SQLite migration upgrade/rollback/preservation tests and existing backup tests. This run verified the Windows API/Vite setup. It did not build/start the production Compose images or a Kubernetes deployment.

**BENCHMARK EVIDENCE:** Local SQLite measurements only. No enterprise private staging availability/restore/deployment benchmark.

**LIMITATIONS:** Existing Compose uses demo configuration; it is not a completed enterprise installer. Pinned image digests, signed provenance, current image SBOM/vulnerability promotion, TLS/network-policy acceptance, complete Helm/operator installation, external object storage, managed keys and a current production restore drill remain deferred.

**NEXT ACTION:** Deferred: harden and stage a real private deployment, sign/pin/scan artifacts and verify backup restoration and documented operator workflows.

## 11. CAN I USE GITHUB ENTERPRISE?

**STATUS: UNSUPPORTED.** GHES support is not implemented.

**IMPLEMENTATION EVIDENCE:** `integrations/github/connector.py` still uses deployment-wide GitHub App credentials and fixed github.com/api.github.com endpoints. No GHES base URL, per-connection app/installation/webhook credentials, custom CA or approved enterprise-host transport is present.

**TEST EVIDENCE:** Current connector tests reject arbitrary URL fetching and validate GitHub metadata/intake behavior. They do not establish GHES support. No live enterprise-host test was run.

**BENCHMARK EVIDENCE:** None for GHES.

**LIMITATIONS:** This gap is missing implementation, not merely missing user credentials. Publishing ordinary github.com check summaries requires tenant authorization but does not add enterprise transport.

**NEXT ACTION:** Deferred: implement connection-scoped GHES configuration/credentials, host/redirect/DNS restrictions, TLS/CA validation, webhook routing and live enterprise installation acceptance.

## 12. CAN I USE OIDC?

**STATUS: PARTIAL.** A generic single-issuer authorization-code flow is implemented and mock-tested; live provider acceptance is unverified.

**IMPLEMENTATION EVIDENCE:** `backend/oidc.py` uses S256 PKCE, nonce, single-use hashed state, encrypted five-minute verifier retention and a separate HttpOnly browser-binding cookie. It validates configured issuer/audience/time claims, signing algorithm/kid/JWKS and authorized party. Endpoints require HTTPS, allowlisted hosts, validated DNS addresses, bounded requests and no redirects. Only existing explicitly approved issuer/subject memberships can log in. Session rotation and membership revocation are enforced. `scripts/oidc_membership.py` provisions bindings without creating users or elevating roles. The browser shows the sign-in option only after configuration validates.

**TEST EVIDENCE:** `test_oidc_code_pkce_nonce_explicit_membership_and_state_replay`, parameterized invalid-claim tests, `test_oidc_approved_endpoints_reject_ssrf`, and callback log masking. The RSA-signed mock flow tests exchange, replay rejection, rotation and revocation.

**BENCHMARK EVIDENCE:** No Entra/Okta/Google or internal-provider live login benchmark. This local deployment is visibly unconfigured for OIDC.

**LIMITATIONS:** One issuer per deployment; no JIT/group role mapping, provider logout, complete multi-provider lifecycle or automated break-glass lifecycle. Deployment DNS/network controls and private CA workflows lack live acceptance. Mock tests are not interoperability certification.

**NEXT ACTION:** Deferred: stage actual approved providers, verify all redirect/TLS/membership/logout/revocation paths and implement the remaining identity lifecycle controls.

## 13. HOW DO YOU HANDLE A 3-MILLION-LINE MONOREPO?

**STATUS: UNSUPPORTED.** The target cannot be accepted by current source intake.

**IMPLEMENTATION EVIDENCE:** `analyzers/engine.py` retains 1,000 archive-entry, 10MB total and 512KB per-file bounds. Analysis retains bounded in-memory source/cache/projections. It has no streaming content-addressed/sharded model for this target.

**TEST EVIDENCE:** Source/archive budget tests reject excessive intake safely. No successful three-million-line import or incremental reanalysis test exists.

**BENCHMARK EVIDENCE:** [enterprise-large-admission-1.6.0.json](../benchmarks/enterprise-large-admission-1.6.0.json): generated 3,000,000 lines / 18,000,000 bytes, REJECTED_BY_BOUNDED_INTAKE, 76.013ms, 36,000,722 Python traced peak bytes. This memory value is not process RSS. Analysis throughput is null because no analysis happened.

**LIMITATIONS:** Increasing the constants alone would not deliver the required architecture, memory bounds or latency. Rejection is intake protection, not large-monorepo support.

**NEXT ACTION:** Deferred: streaming intake, content-addressed storage, incremental shards, bounded retrieval/projections and successful real large-repository throughput/RSS/latency measurements.

## 14. WHAT HAPPENS WHEN 100 PRs ARRIVE TOGETHER?

**STATUS: UNMEASURED.** Simultaneous end-to-end analysis and fairness are unverified.

**IMPLEMENTATION EVIDENCE:** Existing signed webhook validation, durable delivery/job records, replay handling, encrypted input, retry/cancel and Celery worker paths remain. There is no verified tenant-fair admission/concurrency/supersession system satisfying the requested burst target.

**TEST EVIDENCE:** `test_webhook_signature_replay_and_unconfigured`, encrypted-queue, retry/cancel and worker-failure tests establish local lifecycle behavior. They do not establish 100 concurrent PR capacity.

**BENCHMARK EVIDENCE:** [enterprise-receipts-1.6.0.json](../benchmarks/enterprise-receipts-1.6.0.json): 100 SEQUENTIAL signed HTTP receipts, concurrency 1, isolated SQLite; 100 accepted/durable deliveries/jobs, replay DUPLICATE. Receipt p50 13.694ms, p95 23.880ms, p99 26.614ms, 64.505 receipts/s. Queue wait and analysis throughput are null; tenant fairness is UNMEASURED.

**LIMITATIONS:** No Redis worker burst, successful concurrent PR analysis, live provider, tenant fairness, supersession or end-to-end SLA measurement. Sequential durable receipt is not concurrency proof.

**NEXT ACTION:** Deferred: implement global/tenant quotas, fair scheduling and supersession, then run concurrent mixed-tenant PostgreSQL/Redis/provider staging tests with receipt, queue, analysis and fairness measurements.

## 15. WHAT EVIDENCE MADE THIS CLAIM CONTRADICTED?

**STATUS: SUPPORTED.** Recognized claims expose captured, scoped evidence and deterministic explanations.

**IMPLEMENTATION EVIDENCE:** `analyzers/verifiers.py` retains support/contradiction signals and explanations. `backend/domain.py` persists evidence IDs, snapshot scope, claim lineage and graph relationships. The Claim Ledger inspector displays evidence locations, versions and source. Authorized lazy loading also retrieves infrastructure evidence from the existing `/api/record/{id}` endpoint when the workspace summary omits source. Missing evidence alone does not create a contradiction.

**TEST EVIDENCE:** `test_storage_claim_contradiction_uses_structured_hcl_evidence`, `test_jwt_session_transition_is_evidence_backed`, `test_missing_evidence_is_not_contradiction`, graph impact tests, real-import browser review and enterprise infrastructure source inspection.

**BENCHMARK EVIDENCE:** Functional contradiction fixtures; no representative claim-extraction/verifier accuracy benchmark.

**LIMITATIONS:** Only recognized statements and supported static evidence are verified. A declared public bucket is not proof of effective runtime public access. Unbound environments and missing/runtime evidence remain unknown. Unsupported natural-language claims are not comprehensively extracted.

**NEXT ACTION:** Extend independently labeled claim/verifier examples and environment binding while preserving explanations, scope and runtime uncertainty.

## 16. WHY SHOULD I TRUST THIS RESULT?

**STATUS: PARTIAL.** Important result families carry trust metadata, but a complete trust envelope is not yet universal.

**IMPLEMENTATION EVIDENCE:** `backend/domain.py:add` adds schema/version, authority, method, scope, confidence, rule/analyzer version, precision, runtime observation and limitations to new claim/finding/snapshot/risk-path/graph-node records. Finding inspectors retain source/rule/snapshot provenance. Infrastructure and Trust & Coverage expose static authority, diagnostics and unqualified precision. Analyzer model changes are labeled as baselines rather than source drift.

**TEST EVIDENCE:** Scoped graph/risk-path tests, model-upgrade tests, actual infrastructure/evidence browser inspection and registry honesty tests.

**BENCHMARK EVIDENCE:** Per-case source hashes and versioned synthetic measurements. The user's waste-management refresh preserves the 47-file inventory and 22 quality findings, with source_changed=false and analysis_model_changed=true from 1.5.0 to 1.6.0.

**LIMITATIONS:** Some fields default to UNSPECIFIED or generic static limitations; historical records do not acquire the new envelope. Every result family, interpretation, confidence calibration and stale lineage is not fully covered. Runtime authority and representative precision remain unmeasured.

**NEXT ACTION:** Deferred: complete and enforce typed trust envelopes across every result family, add freshness/lineage invariants and calibration checks, and expose missing fields visibly.

## 17. CAN A FINDING SURVIVE A LINE-NUMBER CHANGE?

**STATUS: PARTIAL.** Line/comment movement is stable for tested findings; universal structural identity is unfinished.

**IMPLEMENTATION EVIDENCE:** Native `native-statement-v1` fingerprints exclude line numbers and include rule/path/resource identity/normalized statement/explanation/occurrence. Full-file normalized security-context hashes, rule version, severity, confidence and classification guard human review carry. The existing quality `quality-symbol-v2` model preserves symbol/observation identity and conservative reopen/rename behavior. Identity is separate from the displayed location.

**TEST EVIDENCE:** `test_native_identity_survives_lines_but_security_context_changes`, `test_history_movement_reviews_resolution_reopen_and_rename`, `test_equivalent_declaration_and_review_continuity_are_versioned_safely`, and `test_finding_exception_follows_only_unchanged_evidence`.

**BENCHMARK EVIDENCE:** Regression fixtures only; no cross-language real-history lineage benchmark.

**LIMITATIONS:** Native identity uses normalized statements, not a complete AST neighborhood for every family. Semantic/formatting changes, file/symbol renames, multiline instruction changes and ambiguous repeated findings can reopen. Unrelated executable edits change the conservative whole-file carry guard. All requested movement/formatting/rename guarantees are not delivered.

**NEXT ACTION:** Deferred: versioned language/resource structural anchors, tested ambiguity/rename reconciliation and safe context-aware review carry across representative real histories.

## 18. CAN I CONFIGURE THE QUALITY GATE?

**STATUS: PARTIAL.** Versioned profiles and measured coverage conditions exist; the complete requested gate program is not delivered.

**IMPLEMENTATION EVIDENCE:** Native and quality profiles remain administrator-authorized, versioned and audited, with organization/repository scope, rule toggles/severity, thresholds and new-code settings. `analyzers/code_quality/core.py` adds optional minimum parsed-file coverage; its denominator includes first-party source/test/example and unsupported source, excluding vendor/generated/binary/configuration. Profile UI exposes it. Unqualified reliability/complexity rule thresholds require review; explicit producer-report coverage and parsed-file coverage can fail on measured values.

**TEST EVIDENCE:** `test_authorized_profiles_pagination_reports_gate_and_sarif`, `test_native_profiles_are_authorized_versioned_and_audited`, `test_quality_profile_write_requires_admin_and_report_write_requires_csrf`, `test_explicit_analysis_coverage_gate_counts_unsupported_source` (50% against 100% fails), and quality browser profile/coverage flow.

**BENCHMARK EVIDENCE:** Profile/gate behavior fixtures and earlier quality measurements. No organization-scale gate-calibration benchmark.

**LIMITATIONS:** No complete qualified rule-promotion registry or every enterprise condition family. A PASS remains scoped; unsupported code and missing coverage must be inspected separately. Imported report provenance is declared by its producer and is not proof that ProjectTrace ran tests.

**NEXT ACTION:** Deferred: complete the condition/qualification schema and per-scope administration, then validate rule promotion and gate decisions against representative labeled data.

## 19. CAN I SUPPRESS IT WITH AN EXPIRING EXCEPTION?

**STATUS: PARTIAL.** The exception lifecycle API and existing creation UI are implemented; dedicated administration/notifications are incomplete.

**IMPLEMENTATION EVIDENCE:** CREATE_EXCEPTION/ACCEPT_RISK require privileged review, a reason and tenant-bounded duration (maximum 1–90 days). Stable identity/context controls carry. `/api/trust/exceptions/{id}` supports optimistic-version EXTEND/REVOKE, retains administration history and appends audit links. Revoke expires the suppression immediately. Observations remain stored and unchanged. Expiry is reevaluated by the gate.

**TEST EVIDENCE:** `test_exception_extension_and_revocation_are_audited_and_versioned`, `test_expired_exceptions_do_not_bypass_gate`, `test_exception_identity_expiry_and_changed_evidence_fail_closed`, and quality accepted-risk/owner tests.

**BENCHMARK EVIDENCE:** Deterministic lifecycle tests only; no delivery or large exception-administration measurement.

**LIMITATIONS:** No dedicated extension/revocation administration UI or expiry-notification delivery. Retention and operator review procedures need private-deployment validation.

**NEXT ACTION:** Deferred: add scoped administration views, expiry notifications and operator reconciliation without deleting findings or rewriting machine observations.

## 20. WHERE IS THE AUDIT RECORD?

**STATUS: PARTIAL.** New events are hash linked; immutable retention and external anchoring are absent.

**IMPLEMENTATION EVIDENCE:** `backend/trust.py` writes canonical SHA256 links over event fields, organization, sequence and previous digest with AuditHead in the same transaction. PostgreSQL row locking serializes appends; SQLite uses local single-writer semantics. The administrator-only integrity endpoint streams verification and reports legacy unlinked history separately. Optional operator-held HMAC checkpoints identify a key and can be downloaded. Audit Trail remains available with existing repository authorization.

**TEST EVIDENCE:** `test_audit_chain_detects_mutation_and_checkpoint_authenticates_head`, administrator restriction tests, policy/exception lifecycle tests and browser VERIFIED integrity. Historical data survives additive migration; old audit rows are preserved and honestly labeled legacy.

**BENCHMARK EVIDENCE:** No production retention, checkpoint-rotation, PostgreSQL concurrency or WORM archive measurement.

**LIMITATIONS:** An unanchored chain can be wholly rewritten by a DB administrator. HMAC is not non-repudiation. This local deployment has no checkpoint key configured; unavailable signing/immutable archival is visible. Legacy history is not silently rehashed as immutable. External automatic anchoring, WORM, rotation and complete audit-schema/tenant enforcement are deferred.

**NEXT ACTION:** Deferred: separate append/archive administration, retained external checkpoints, rotation/restore validation and production tamper/deletion/concurrency acceptance.

## 21. WHAT HAPPENS IF A LANGUAGE IS UNSUPPORTED?

**STATUS: PARTIAL.** Intake/inventory and parsed-file coverage expose supported gaps; universal semantic coverage accounting is incomplete.

**IMPLEMENTATION EVIDENCE:** Source inventory and intake diagnostics retain unsupported language/encoding and binary distinctions. The GitHub fetcher now retains bounded UTF-8 unknown-language files and records encoding/binary intake instead of silently skipping all unfamiliar suffixes. Capability registry explicitly declares unsupported analysis a gap. Parser/quality partial state and optional parsed-file gate prevent interpreting unsupported source as fully covered. JSON infrastructure admission and supported-file counting use the same predicate.

**TEST EVIDENCE:** `test_provider_intake_keeps_unknown_language_and_encoding_diagnostics`, `test_zip_encoding_diagnostics_prevent_false_complete_and_preserve_binary_inventory`, `test_explicit_analysis_coverage_gate_counts_unsupported_source`, and JSON infrastructure coverage tests.

**BENCHMARK EVIDENCE:** Owned unsupported-source fixtures; no representative mixed-language coverage completeness benchmark.

**LIMITATIONS:** Supported syntax can still lack framework/security semantics. Not every engine denominator is a universal whole-repository semantic coverage measurement. A scoped PASS or zero findings cannot establish safety of unsupported files. Archive/provider admission limits remain.

**NEXT ACTION:** Deferred: unify file/rule/framework coverage accounting for every engine and qualify mixed-language repository behavior under bounded intake.

## Native infrastructure acceptance boundaries

The Infrastructure module has Overview, Findings, Resources, Terraform, CloudFormation, Kubernetes, Compose, Dockerfile, Rules & Profiles and Coverage views. Server filtering applies before pagination. Inventory includes source configuration declarations from authorized captured snapshots and excludes auxiliary image-reference nodes and live AWS observations from the static configuration count. Resource/finding inspectors load authorized linked source evidence and retain record kind/version for review.

| Format | Implemented and verified scope | NOT DONE / deferred |
| --- | --- | --- |
| Terraform HCL / JSON | Resource and selected declaration inventory; symbolic expressions/references; selected IAM/storage/network/database/encryption observations | Provider execution, complete provider semantics, local/remote module expansion, effective IAM/reachability |
| CloudFormation YAML / JSON | Resource inventory; retained intrinsics/references; selected literal public-storage/database/encryption observations | Transform/macro/nested-stack execution, complete condition/effective policy semantics |
| Kubernetes YAML / JSON | Selected controllers, service/ingress/identity/RBAC/network/config declarations; selected privilege/image/read-only/seccomp/TLS/RBAC observations; Secret/ConfigMap metadata excludes values | Helm rendering, admission-default resolution, full selector/network/RBAC evaluation, complete schema coverage |
| Compose YAML / JSON | Services, image/dependency references, selected privileged/root/host-mount/capability/read-only observations | Build execution, interpolation resolution, merged multi-file effective deployment semantics |
| Dockerfile | Native instructions/continuations, multistage inheritance, effective final USER location, COPY stage links, selected remote/secret/image observations | Build/RUN execution, heredoc completion, image contents/CVEs, complete ARG expansion and effective build semantics |

The 22-case accuracy corpus checks selected positive/negative rules in these native areas. Additional regression tests verify JSON admission, metadata masking, Docker stage behavior, aliases and failed-process handling. All rules retain unqualified precision and static runtime uncertainty. Deep infrastructure completeness is PARTIAL for every format.

## Preservation and release acceptance

Migration `0007` is additive. Comparison against a consistent private pre-change database checked all common columns of 13 preexisting tables before migration verification and again after final browser tests/refreshes: zero missing/changed original rows and zero foreign-key violations. All 61 original credential hashes and 139 original snapshot payloads are unchanged; SQLite quick_check is ok. Synthetic fixtures and fresh analyses add rows. No private database/keys are included in the release.

The actual `smart-waste-management-system-main.zip` was refreshed in its three existing authorized repositories without executing its contents. Each refresh retains 47 files and 22 quality findings, is PARTIAL, preserves its historical snapshot and marks the 1.5.0→1.6.0 analyzer baseline separately from source drift. No test coverage report was invented.

The clean source ZIP has exactly one `ProjectTrace/` root. The release manifest records file hashes, the base commit and the fact that source changes are uncommitted. Data, credentials, private backups, virtual environments, dependencies, build output and browser traces are excluded. Passing local regression checks does not change any deferred status in this document.
