# ProjectTrace enterprise hardening validation

## Executive summary

This is the existing ProjectTrace 1.6.0 codebase with an additive enterprise hardening candidate in the working tree. It preserves the Claim Ledger, authoritative Evidence Graph, existing native quality/security/cloud capabilities and public product experience. No SonarQube, Wiz or external AI dependency was introduced. This is not production enterprise acceptance.

Subsequent Phase 2 closure verification is documented in [docs/PHASE_2_CLOSURE.md](docs/PHASE_2_CLOSURE.md). It covers complete intake inventory, unsupported/unknown source, parser failures, exclusions, truthful coverage/gates, historical/granted access and captured UI authority. Earlier broad candidate reports, benchmarks and archives below retain their original code/test scope; they are not fresh verification of these later changes. Current analyzer maturity remains PARTIAL and external production acceptance remains incomplete.

## Release version, commit and environment

Analyzer/package version remains **1.6.0**; this delivery is a hardening candidate, not an invented published version. Base commit: `663770fffd4b1f5f532b6bd7b59949eb1183a3ee`; changes are uncommitted. Tests ran on Windows 11, Python 3.14.3, local SQLite, synchronous native analysis and Chromium. Controlled PR load used four threads and an owned crashed subprocess. No live PostgreSQL/Redis/Celery cluster, Docker/Kubernetes runtime, IdP, GHES or S3 service was available. Only owned ProjectTrace code/helpers were executed; customer source remained inert.

The original specification and baseline remain in `docs/ENTERPRISE_HARDENING_SPECIFICATION.txt` and `docs/ENTERPRISE_HARDENING_BASELINE.md`. Previous 1.6.0 proof is archived as `docs/validation-enterprise-trust-1.6.0-before-hardening.md`; it is historical, not current capability status. Fresh aggregate verification belongs in `benchmarks/enterprise-hardening-verification.json`.

## The 21 buyer questions

SUPPORTED applies only to the behavior stated. PARTIAL identifies delivered behavior with missing implementation or external verification. UNMEASURED means the population or service measurement does not exist. Paths below are repository-relative; test names refer to files under `tests/`, browser tests under `frontend/e2e/`, and reports under `benchmarks/`.

### 1. How accurate is it?

**UNMEASURED.** Small purposive synthetic/framework/public-negative slices; representative production precision and recall unknown.

Implementation: `analyzers/capabilities.py; backend/accuracy.py`. Tests: `test_accuracy_hardening.py`. Benchmark evidence: accuracy-hardening-v2.json: 76 cases / 38 groups, no labeled mismatches.

### 2. How many false positives?

**UNMEASURED.** Voluntary feedback is biased; no universal false-positive percentage and no default precision qualification.

Implementation: `backend/accuracy.py; native_rules.py`. Tests: `test_accuracy_hardening.py; test_enterprise_trust.py`. Benchmark evidence: Per-group FP/FN and Wilson intervals in accuracy-hardening-v2.json.

### 3. What languages are truly supported?

**PARTIAL.** Python, JS/TS/JSX/TSX and Java have bounded syntax/static semantics, not complete compiler, type or framework modeling. See LANGUAGE_SUPPORT_MATRIX.md.

Implementation: `analyzers/languages.py; analysis_coverage.py`. Tests: `test_analyzers.py; test_code_quality.py; test_analysis_coverage.py`. Benchmark evidence: Accuracy groups and mixed-language scale report when complete.

### 4. What happens when your parser fails?

**PARTIAL.** Failure/skip/unsupported states remain visible; failed artifacts are not reused and unknown findings are not declared resolved. Complete helper filesystem/network sandbox remains unverified.

Implementation: `partitioned_analysis.py; analysis_coverage.py; process_limits.py`. Tests: `test_analysis_coverage.py; test_repository_store.py; test_security_hardening.py`. Benchmark evidence: Large-repository reports record coverage and terminal job state.

### 5. Do you execute our code?

**SUPPORTED.** Static parsing only. No customer install, build, tests, Terraform/provider execution, Helm rendering or project scripts.

Implementation: `repository_store.py; analyzers/engine.py; infrastructure.py`. Tests: `test_streaming_import.py; test_infrastructure_deep.py`. Benchmark evidence: All owned benchmark reports record customer_code_executed=false.

### 6. Does our source leave your infrastructure?

**PARTIAL.** External source/AI egress disabled; opt-in OSV sends package coordinates and SCM checks send policy states. Operator-configured private object storage receives ciphertext. OS network controls and real endpoint policy need deployment validation.

Implementation: `backend/trust.py; advisories.py; object_store.py; secure_http.py`. Tests: `test_enterprise_trust.py; test_ghes.py; test_private_operations.py`. Benchmark evidence: Controlled egress assertions; no deployed network-enforcement measurement.

### 7. Does an LLM receive source?

**SUPPORTED.** External AI remains disabled; no external/customer-managed AI feature is advertised as available.

Implementation: `Tenant AI policy and native analyzers`. Tests: `test_enterprise_trust.py; test_api.py`. Benchmark evidence: Benchmark external_llm_used=false.

### 8. How do you isolate tenants?

**PARTIAL.** Application authorization, compound new-storage scope and ORM guards are tested. Full PostgreSQL RLS and compound tenant keys across legacy tables remain deferred; direct SQL bypasses application guards.

Implementation: `security.py; db.py; repository_store.py; scheduling.py`. Tests: `test_api.py; test_ghes.py; test_repository_store.py; test_fair_scheduling.py`. Benchmark evidence: pr-load-100.json: two tenants, 40 completed snapshots each, scope verified.

### 9. How do you handle secrets?

**PARTIAL.** Redaction and encrypted retained source/input; operator secret-file injection. Managed KMS enforcement, Windows ACLs, audit key-history automation and production rotation require operator proof.

Implementation: `settings.py; queue.py; object_store.py; local_backup.py`. Tests: `test_private_operations.py; test_enterprise_trust.py`. Benchmark evidence: Owned encrypted backup/restore and key-rotation drill; source ZIP excludes keys.

### 10. Can I deploy it privately?

**PARTIAL.** Kubernetes base is closed until operator overlay supplies real verified images, TLS, secrets, PG/Redis/S3 and egress. No cluster, container scan/signature or production restore proof.

Implementation: `infrastructure/kubernetes/production.yaml; Compose/Docker; settings.py`. Tests: `test_private_operations.py; test_migrations.py`. Benchmark evidence: Local SQLite upgrade/restore and production frontend build only.

### 11. Can I use GitHub Enterprise?

**PARTIAL.** Per-connection App/install/host/CA/secret references, pinned TLS sockets, revocation and streaming ingestion implemented. No live GHES/private CA/vendor-version acceptance.

Implementation: `scm_connections.py; scm_webhook.py; integrations/github/connector.py; secure_http.py`. Tests: `test_ghes.py; test_scm_streaming.py; test_github.py`. Benchmark evidence: Controlled signed-event PR load and bounded tree/blob fixtures.

### 12. Can I use OIDC?

**PARTIAL.** One deployment issuer; explicit subjects or verified-email mapped-group provisioning. No email auto-link or group ORG_OWNER grant. No live Entra/Okta/Google, directory sync or IdP-wide logout.

Implementation: `oidc.py; oidc_lifecycle.py; OIDCAdministration.tsx`. Tests: `test_oidc_lifecycle.py; test_enterprise_trust.py; test_security_hardening.py`. Benchmark evidence: Controlled code/PKCE/JWT/group lifecycle only.

### 13. How do you handle a 3-million-line monorepo?

**PARTIAL.** Encrypted streaming inventories, 100-file/2MB partitions, incremental cache, declared components and paged graph implemented. Synthetic local timing does not qualify customer monorepos or distributed workers.

Implementation: `repository_store.py; partitioned_analysis.py; graph_api.py; migrations 0011/0013`. Tests: `test_repository_store.py; test_graph_pages.py; test_streaming_import.py`. Benchmark evidence: See LARGE_REPOSITORY_BENCHMARK.md and raw 10k/50k/3M/mixed reports; only terminal successful reports count.

### 14. What happens when 100 PRs arrive together?

**PARTIAL.** 115 controlled TestClient requests then four-thread drain; not continuous network arrival during huge analysis or real Redis/Celery/PostgreSQL staging. In-flight HTTP cannot be recalled after a last-head check.

Implementation: `scheduling.py; scm_webhook.py; workers/github.py; migrations 0012`. Tests: `test_fair_scheduling.py; test_queue.py; test_ghes.py`. Benchmark evidence: pr-load-100.json: 100 jobs, 80 completed, 20 superseded, no failure, one real subprocess crash recovered.

### 15. What evidence made this claim CONTRADICTED?

**SUPPORTED.** Deterministic source-backed evidence, ranges, reason and snapshot provenance. Static contradiction is bounded to recognized claims; no runtime correctness assertion.

Implementation: `analyzers/verifiers.py; domain.py; Evidence Graph and inspector`. Tests: `test_analyzers.py; test_api.py; real-import/workflow browser tests`. Benchmark evidence: Labeled claim cases; real ZIP static smoke.

### 16. Why should I trust this result?

**PARTIAL.** Inspect captured source authority, language maturity, exclusions, parser errors and profile versions. Missing runtime or accuracy proof remains explicit; partial is not clean.

Implementation: `analysis_coverage.py; trust_api.py; EnterpriseTrust.tsx`. Tests: `test_trust_controls.py; test_analysis_coverage.py; enterprise-trust browser test`. Benchmark evidence: Coverage, analyzer signature, gate and stages captured in benchmark snapshots.

### 17. Can your finding survive a line-number change?

**PARTIAL.** AST/native/IaC concept identity separates occurrences. Unique complete-file rename proof only; ambiguous copies, semantic context/rule/severity changes reopen review. Legacy snapshots are not rewritten.

Implementation: `finding_identity.py; finding_history.py; migration 0008`. Tests: `test_finding_identity.py; test_code_quality.py`. Benchmark evidence: Controlled line insert/rename/ambiguity/context cases, not a production continuity rate.

### 18. Can I configure the Quality Gate?

**SUPPORTED.** Recommended/org/team/repo inheritance, versioned thresholds and declarative conditions. Unmeasured rule precision stays advisory unless explicitly overridden by an administrator; imported coverage is provenance-bound.

Implementation: `quality_profiles.py; quality_domain.py; NativeProfiles/CodeQuality UI`. Tests: `test_quality_profiles.py; test_native_platform.py; code-quality browser test`. Benchmark evidence: Scale reports retain captured gate; synthetic accuracy does not enable default blocking.

### 19. Can I suppress something with an expiring exception?

**SUPPORTED.** Authorized reason/version/time-bounded exception with administration history. Suppression never deletes machine evidence. Notification delivery is deferred.

Implementation: `trust_api.py; TrustExceptions.tsx; review/exception Records`. Tests: `test_trust_controls.py; test_enterprise_trust.py`. Benchmark evidence: Controlled expiry/extend/revoke and scope checks; no notification-delivery benchmark.

### 20. Where is the audit record?

**PARTIAL.** Tenant hash-linked events plus optional external HMAC checkpoints. Legacy events remain unlinked; automatic WORM checkpoint retention and non-repudiation certification are not implemented.

Implementation: `trust.py; trust_api.py; Audit Trail and checkpoint verification API`. Tests: `test_security_hardening.py; test_enterprise_trust.py`. Benchmark evidence: 12 concurrent appends preserve chain; retained checkpoint detects privileged whole-chain rewrite.

### 21. What happens if a language isn't supported?

**SUPPORTED.** Inventory and unsupported state remain visible, with partial coverage/review implications. No semantic claim or zero-findings assurance is manufactured.

Implementation: `analysis_coverage.py; analyzers/capabilities.py; Trust & Coverage`. Tests: `test_analysis_coverage.py; test_code_quality.py`. Benchmark evidence: Captured unsupported/skipped inventory counts in scale and ZIP reports.

## Stable Finding, Quality Gate and Coverage validation

Structural identities and occurrence/history projections are additive. Explicit BASE lineage permits fixed/reopened decisions only with supported observations. Review and exception continuity is invalidated by relevant context/rule/severity/classification changes. Quality profiles inherit by scope and preserve immutable versions. Measured coverage, not absent findings, determines coverage conclusions. Trust & Coverage shows historical captured inventory, unknown LOC, parser failures, generated/vendor/oversize/binary exclusions, infrastructure diagnostics and gate/profile metadata. See `QUALITY_PROFILE_AND_GATE_GUIDE.md`, `LANGUAGE_SUPPORT_MATRIX.md` and the identity/profile/coverage tests.

## Accuracy results

`accuracy-hardening-v2.json` records 76 labeled cases and 38 groups across eleven domains, including owned synthetic/framework cases and pinned public negative-only examples. No FP/FN occurred on those specific labels after the measured fixes. Public negative-only cases cannot estimate precision or recall. The design-partner tier is unavailable. No universal accuracy score, zero-false-positive claim or default rule qualification follows. See `docs/ANALYZER_ACCURACY.md`.

## OIDC and GitHub Enterprise validation

Controlled protocol, lifecycle, network-policy, revocation and streaming tests passed in the full backend regression. These validate implementation behavior against owned fixtures. Vendor-specific live sign-in, private CA deployment, token expiry behavior against a real server and sustained ingestion remain unmeasured. See `docs/OIDC_AND_GHES_CONFIGURATION.md` and `docs/SECURITY_AND_DATA_EGRESS.md`.

## Large repository benchmark

See `docs/LARGE_REPOSITORY_BENCHMARK.md` for terminal results and preserved failures. The current 10,000-file Python run analyzed 100,000 LOC; its eight-file HEAD reused 9,992 observations. Windows suspend time is separated from active system time. Owned benchmark active-clock budgets are explicitly labeled; production wall timeouts are unchanged. No real customer monorepo or distributed scale claim follows. The 50,000-file / 500,000-line initial recovery and eight-file HEAD both persisted under the 1.5 GiB memory guard. The initial timing retains its historical code hashes; the recovered HEAD uses final code and a fully hash-validated retained capture, with eight owned changed-file artifacts evicted to measure 49,992 unchanged hits/eight misses. Recovery intake is reference reuse, not capture throughput. Cold completion throughput remains unmeasured; earlier interrupted and memory-failed reports are retained. Authorized read APIs have ten local samples per endpoint against the persisted isolated fixture.

## 100 PR load benchmark

`pr-load-100.json` records 100 primary events across two tenants/four repositories, 10 delivery replays, five additional delivery IDs for the same current SHA, 100 jobs, 20 superseded cancellations and 80 completed inventory-backed snapshots. The final adapter uses production streaming capture and records 80 tenant-encrypted inventories with current implementation hashes. An actual owned subprocess exited with code 73; after controlled lease expiry one job recovered. Webhook p95 was 75.997 ms and queue wait p95 45,843.272 ms on this local adapter. This is controlled burst-and-drain behavior on a shared host and separate database, not broker/staging or a mixed large-job queue qualification. See `docs/PR_LOAD_BENCHMARK.md`.

## Infrastructure coverage and Engineering Changes

Terraform, CloudFormation, Kubernetes, Compose and Dockerfile have bounded native static parsing, resource/context rules and visible unresolved constructs. Local Terraform declaration links do not expand or fetch modules; templates/providers/IaC are never executed. Runtime reachability and complete IAM evaluation remain unobserved. See `docs/INFRASTRUCTURE_SUPPORT_MATRIX.md` and `test_infrastructure_deep.py`.

Engineering Changes compares explicit BASE/HEAD source-backed records, claims, findings, dependency/resource changes, owners and gates through the shared graph. Links and queries are bounded and tenant/repository scoped. Content changes and re-evaluation are distinguished. `test_engineering_changes.py` and frontend controls tests cover the implementation; the public Guide includes the topic.

## Private deployment validation and security testing

Local encrypted recovery, tamper detection, analysis-key rotation, fake S3 ciphertext/SSE headers, managed secret loading, production configuration rejection, additive migration preservation, tenant authorization, signed webhook validation, pinned provider transport, audit checkpoint verification and concurrent audit appends have controlled tests. API readiness checks migration head/Redis in production; worker health remains separate. Kubernetes manifests are operator templates and have not run on a cluster. Package audits/SBOMs concern owned application dependencies, not image vulnerability/signature qualification. See `docs/PRIVATE_DEPLOYMENT_GUIDE.md` and `docs/UPGRADE_ENTERPRISE_HARDENING.md`.

## Known limitations and deferred items

Representative accuracy/design-partner evaluation; live IdP/GHES; verified PostgreSQL/Redis/Celery/S3/TLS staging; whole-schema RLS/compound tenant constraints; complete parser filesystem/network sandbox; signed/pinned/scanned container promotion; automatic WORM checkpoint retention; automatic source snapshot retention/GC; production backup/key-rotation drills; availability/RPO/RTO and realistic sustained concurrency remain unfinished or unmeasured. Histories are preserved rather than silently garbage-collected. Application checks cannot retract an outbound HTTP request already in flight.

## Release recommendation

Use this as a locally verified hardening candidate for controlled evaluation. Preserve the private backup and matching keys, apply the additive migrations and verify scoped workflows. Production promotion requires the external staging and representative measurements above; do not market this delivery as enterprise-certified or fully production-qualified.
