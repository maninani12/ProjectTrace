# ProjectTrace native platform 1.3.3

ProjectTrace owns finding rules, quality metrics, profiles, claims, graph correlation, risk paths and gates. Python AST, Tree-sitter grammars, HCL2 and safe YAML supply parsing primitives. External security finding servers are unnecessary for native analysis. OSV optionally supplies exact-version advisory data; unqueried declarations remain NOT_CHECKED/UNKNOWN_VERSION.

## Code intelligence and application security

Python AST extracts functions and implementation evidence. Maintained Tree-sitter grammars cover JavaScript/JSX, TypeScript/TSX and Java functions/methods/constructors, class spans, control branches, empty catches and a small set of parsed security patterns. Syntax failures and parser budgets produce PARTIAL diagnostics; unsupported syntax never implies a clean scan.

Each function stores source location, language, cyclomatic complexity, source-span length, syntax nesting, an explicitly approximate cognitive metric and a normalized body fingerprint. Python complexity is 1 + if/loops/exception handlers/ternary contributions + boolean operands minus one + match alternatives minus one. JS/TS/Java complexity is 1 + recognized if/loop/catch/switch-case/ternary contributions + short-circuit operators. Nested definitions are excluded from outer metrics. Thresholds: complexity >10, function length >80, nesting >4, class span >200. Duplicate detection requires matching normalized bodies of at least 30 syntax nodes/tokens; it does not detect arbitrary near duplicates. No arbitrary maintainability/debt score is assigned. Cognitive approximation is not a standardized or complete cognitive-complexity implementation.

Python static flow tracks modeled request/input sources, assignments, expressions, bounded local helper calls (depth three), contextual HTML sanitization and SQL parameter separation into modeled SQL/shell/deserialization/HTML/path/HTTP sinks. Evidence includes actual file/line steps. CONFIRMED_STATIC_FINDING means a modeled static source-to-sink path, not runtime exploitability. Unknown transformations and unproven patterns remain SECURITY_HOTSPOT. Complete control-flow/path feasibility, cross-file calls, framework models and equivalent JS/TS/Java taint analysis remain partial/deferred.

`GET /api/native/rules` returns 31 versioned rule records with actual language coverage, title, severity, explanation, remediation, CWE where applicable, references and concrete examples. Ten SAST, eight quality (including parser errors), nine IaC, one secret, one license and two AWS inventory rules describe implemented scope. Rule count does not establish maturity, precision or recall.

## Profiles, deltas and gate

Settings exposes authenticated native profiles: rule enable/disable, severity, observed SPDX approved/restricted identifiers and ALL_FINDINGS/NEW_FINDINGS gate scope. Only organization owners/admins write profiles; repository authorization, optimistic versions and audit apply. Analyzed snapshots retain their exact profile. Organization defaults apply when a repository has no override; a repository profile is an explicit replacement profile rather than a field-by-field inheritance merge.

Analysis caches keep unfiltered native observations; profile application occurs afterward. Profile changes enter analysis identity, so cached observations cannot poison another profile. New analysis is required after editing settings. Changed line ranges and stable rule/path/source signatures distinguish NEW, EXISTING and ANALYZER_BASELINE findings. New-code scope intersects changed line ranges. New-findings gates exclude unchanged legacy and analyzer-only baseline issues while still reviewing claim contradictions. PASS/WARNING/REVIEW_REQUIRED/FAIL include reasons, finding/claim IDs and active exception handling. Enforcement in a live provider PR has not been verified.

## Infrastructure and evidence

HCL2 parses Terraform declarations and literal jsonencode IAM objects without running Terraform. Safe YAML/JSON handles supported CloudFormation resources and Kubernetes workloads including CronJob; Compose and Dockerfile have bounded configuration checks. Rules cover explicit public ACLs/Internet ingress/wildcard IAM, public access block disables, privileged/root containers, host namespaces/mounts, escalation/capabilities and missing Kubernetes resource limits. YAML aliases, excessive syntax/depth and unrendered Helm templates explicitly reduce coverage. Terraform plan/provider evaluation and complete policy semantics are unsupported.

Declared assets become scoped CLOUD_RESOURCE/CLOUD_IDENTITY/CONTAINER_WORKLOAD/EXPOSURE nodes and typed CloudAsset projections. DECLARED_IN/AFFECTS/EXPOSES and unambiguous declared relationships link actual records. Static risk paths traverse existing exposure/resource/finding IDs and retain owner, provenance, remedy and runtime UNOBSERVED. Similar names are insufficient for a deployment link.

The narrow explicit claim “Production storage is private.” is contradicted only by an explicitly public supported production-bound declaration. An unrelated development bucket, absence of a public declaration or unknown deployment cannot prove production privacy. More general cloud claims, effective permissions, identity escalation and runtime claims need additional evidence models.

PostgreSQL Ask uses authorized current claims with full-text ranking, status evidence and bounded stored graph neighborhoods. SQLite retains deterministic token matching. Vector retrieval is NOT_CONFIGURED; embeddings and a complete semantic search platform are deferred.

## Preserved working functionality

Claim verification, documentation/implementation origins, stable identities, STALE history, rule-only analysis provenance, reverse graph impact including deleted files, source viewer, dependency inventory/SBOM, human review, expiring exceptions, audit, local authentication/session/CSRF, repository grants, signed GitHub intake, ZIP limits, queues and canonical routes remain in the same product. Source imports never execute application code or install imported dependencies.

Native Tree-sitter grammars run as one bounded isolated helper process per uncached language batch. Only ProjectTrace-owned Python executes; source is JSON data in memory, and credential environment variables/user Python paths are excluded. The helper has a 30-second timeout and bounded input/results; failures mark PARSING/QUALITY/SAST PARTIAL. Source locations use UTF-8 byte offsets. This process boundary does not establish a complete OS filesystem/network sandbox.
