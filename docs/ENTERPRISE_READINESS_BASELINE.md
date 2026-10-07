# Enterprise readiness baseline

Inspected 6 October 2026 before enterprise source changes. Current API/UI/native 1.5.0; Alembic head 0006. Git base ae98c4a57472249f15ba191947d054673e1de74c with preserved uncommitted 1.4/1.5 work. Last completed release proof: 171 backend, 22 frontend and ten Chromium workflows; 38 public routes; selected audits and static real-ZIP analysis. Those are prior baseline results, not enterprise production proof.

The permanent industry constitution and Code Quality prompt remain in force. This buyer-readiness program adds controls; it does not replace the Evidence Graph/Claim Ledger. No SonarQube/Wiz dependency or imported execution is permitted.

## Twenty-one questions

| Exact buyer question | Starting status | Inspected evidence / missing scope |
|---|---|---|
| 1. HOW ACCURATE IS IT? | UNMEASURED | Twelve manually labeled quality positive/negative/generated fixtures; native synthetic benchmark. No representative population accuracy. |
| 2. HOW MANY FALSE POSITIVES? | PARTIAL | FALSE_POSITIVE reviews and reasons exist; no rule-health aggregates or valid dismissal-rate denominators. |
| 3. WHAT LANGUAGES ARE TRULY SUPPORTED? | PARTIAL | Python AST and JS/JSX/TS/TSX/Java Tree-sitter; quality maturity PARTIAL. No unified capability registry. |
| 4. WHAT HAPPENS WHEN YOUR PARSER FAILS? | PARTIAL | JS/TS/Java helper strips credentials, 30s wall/16MB result/40k nodes. Python/HCL/YAML in parent; no enforced OS sandbox. |
| 5. DO YOU EXECUTE OUR CODE? | IMPLEMENTED | Inert ZIP/text parsers; tests reject execution/traversal/hooks. No imported build or test commands. |
| 6. DOES OUR SOURCE LEAVE YOUR INFRASTRUCTURE? | PARTIAL | No external AI; OSV sends package coordinates. No configurable tenant egress policy. |
| 7. DOES AN LLM RECEIVE SOURCE? | IMPLEMENTED | LLM provider disabled; authorized evidence/citation validation helpers. Optional external transport absent. |
| 8. HOW DO YOU ISOLATE TENANTS? | PARTIAL | Organization/repository scope, grants, IDOR tests, encrypted inputs. No RLS or tenant compound FK defense for all entities. |
| 9. HOW DO YOU HANDLE SECRETS? | PARTIAL | Provider-shaped, assignments, keys, URL masking and encrypted queue input. No managed key lifecycle or complete DLP. |
| 10. CAN I DEPLOY IT PRIVATELY? | PARTIAL | Self-hosting files and older non-root Linux runtime evidence exist; no current OCI signing, K8s staging restore or production validation. |
| 11. CAN I USE GITHUB ENTERPRISE? | UNIMPLEMENTED | connector.py hardcodes api.github.com; app/key/installation/webhook secret deployment-wide. |
| 12. CAN I USE OIDC? | UNIMPLEMENTED | Local Argon2 sessions/CSRF only; no Authorization Code/PKCE/issuer/nonce/subject mapping. |
| 13. HOW DO YOU HANDLE A 3-MILLION-LINE MONOREPO? | UNIMPLEMENTED | Fixed 1,000 entries/10MB/512KB and dictionary intake. No 3M-line sharded model/benchmark. |
| 14. WHAT HAPPENS WHEN 100 PRs ARRIVE TOGETHER? | UNMEASURED | Durable delivery IDs/Celery leases/recovery/admission quotas; no fair 100-PR measured workload. |
| 15. WHAT EVIDENCE MADE THIS CLAIM CONTRADICTED? | IMPLEMENTED | Claim statement/status/scope/verifier/evidence/reason/history via Record, verifiers and inspector; graph tests. |
| 16. WHY SHOULD I TRUST THIS RESULT? | PARTIAL | Rules/versions/confidence/authority/source scope available; no consistent enterprise trust envelope. |
| 17. CAN A FINDING SURVIVE A LINE-NUMBER CHANGE? | PARTIAL | quality-symbol-v2 excludes offsets with context-safe review carry; non-quality native finding identity still uses line. |
| 18. CAN I CONFIGURE THE QUALITY GATE? | PARTIAL | Versioned organization/repository profiles and BASE/NEW_CODE/OVERALL quality gate. Precision unknown can still fail locally; no minimum coverage condition/team profiles. |
| 19. CAN I SUPPRESS IT WITH AN EXPIRING EXCEPTION? | IMPLEMENTED | Privileged risk acceptance/expiring exception restores effective gates; expiry test. Notification/revoke/extend administration incomplete. |
| 20. WHERE IS THE AUDIT RECORD? | PARTIAL | Append-oriented audit has actor/reason/time; no hash chain/signed checkpoint/immutable archival. |
| 21. WHAT HAPPENS IF A LANGUAGE IS UNSUPPORTED? | PARTIAL | Quality source inventory shows unsupported/encoding/generated/vendor/parse gaps; GitHub fetcher still drops unknown suffixes and invalid encoding. |

## Inspected architecture and infrastructure

Source: analyzers/engine.py, quality.py, languages.py, infrastructure.py, native_rules.py, code_quality/*; backend/db.py, security.py, domain.py, main.py, native.py, quality_api.py, jobs.py, queue.py, llm_gateway.py; workers/tasks.py/github.py; integrations/github/connector.py; migrations 0001–0006, test corpus, benchmark_quality.py and existing deployment/operations documentation. Quality has twelve rules; generic registry adds native SAST/secrets/IaC/dependencies. Settings reuse NativeProfile. Queued inputs use Fernet with 72h expiry and required production key; Redis/Celery uses late ack, prefork bounds, worker leases and capped recovery. PostgreSQL is production; SQLite is local single-writer adapter.

Infrastructure currently uses bounded SafeLoader YAML and HCL2, retaining symbolic CloudFormation intrinsics. Terraform resources/public ACL/ingress/wildcard policy, limited CloudFormation resource/ACL/policy/encryption, Kubernetes workloads/service accounts/privilege/limits, Compose privilege/root/namespace/mount and Dockerfile line-level USER checks work. Dockerfile instruction/stage parsing, richer networking/storage/RBAC/symbolic diagnostics, unified format coverage/resources UI and complete format benchmarks are missing. Declared assets remain STATIC and runtime unobserved.

Existing GitHub uses a validated repo/SHA transport and neutral checks but fixed github.com endpoints and global credential configuration; no current GHES or OIDC verification. Ask Engineering is deterministic retrieval over scoped evidence; external AI is disabled. No source egress to a model is implemented. Logs avoid raw source; source redaction occurs before persisted evidence/cache. Audit is an ordinary mutable DB table.

## Required release boundaries

Implement and test each new control against actual behavior. Do not claim enterprise-ready, private-deployment maturity, live OIDC/GHES, 3M-line scale, 100-PR fairness, OS sandbox or representative precision from local tests. External staging/provider/KMS/OCI-signing validation requires configured infrastructure and remains separately identified. The final ENTERPRISE_TRUST_VALIDATION.md must state supported/partial/unsupported/unmeasured, exact source/tests/benchmarks/limits and next action for all questions.
