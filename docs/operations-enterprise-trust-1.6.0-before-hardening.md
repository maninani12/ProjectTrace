# Enterprise trust operations — 1.6.0

This release implements trust foundations. It is not enterprise-ready certification. Read ENTERPRISE_TRUST_VALIDATION.md for the exact supported/partial/unmeasured/deferred boundaries.

## Tenant source and metadata egress

Every tenant defaults to NO_EXTERNAL_SOURCE_EGRESS, AI DISABLED, package-coordinate advisories disabled and GitHub check metadata disabled. Organization administrators use Settings → Data & AI Egress. The server validates strict types, optimistic policy versions and administrator roles; every change is audited. Source-sharing and customer-managed/external AI modes are not implemented and are rejected rather than advertised.

OSV admission and the worker recheck tenant authorization before transferring ecosystem/package/version. Revoking authorization blocks later work. Locally cached sample advisories require no outbound transfer. GitHub fetching is authorized inbound ingestion. Optional check publishing rechecks the tenant policy and emits system policy names/result states only: free-text reasons may quote source-backed claims and are deliberately omitted. Blocked check publication does not discard a successful analysis. Deployment network controls must separately constrain outbound traffic; application policy is not an OS network sandbox.

## OIDC operator configuration

OIDC is disabled until the operator provides OIDC_ISSUER, OIDC_AUTHORIZATION_URL, OIDC_TOKEN_URL, OIDC_JWKS_URL, OIDC_CLIENT_ID, OIDC_REDIRECT_URI, OIDC_FRONTEND_URL and OIDC_ALLOWED_HOSTS. Optional OIDC_CLIENT_SECRET stays in the operator environment; it is never returned through an API. Use a managed secret injection mechanism for production. The frontend origin must be an explicit CORS origin. The exact callback path is /api/auth/oidc/callback. Production requires HTTPS callback/frontend URLs; only local development permits HTTP callbacks. Authorization/token/JWKS/issuer endpoints always require HTTPS and an approved host. Internal endpoint addresses require explicit OIDC_PRIVATE_HOSTS authorization and valid TLS trust. Redirect following and inherited HTTP proxy configuration are disabled. Deployment DNS/network allowlisting must also prevent rebinding; that complete network proof is unverified.

Approve an existing member and their repository grants first. Run `python -m scripts.oidc_membership --email <approved-member-email> --subject <issuer-subject>` from the protected operator host, or use the administrator-only /api/auth/oidc/membership endpoint with the existing user ID and CSRF session. This neither creates a user nor changes their role. Disable a binding with `--disable` or enabled=false. Existing sessions are revoked; authentication also rechecks the enabled membership on every request. No email-domain, group-claim or automatic administrator provisioning is performed. One issuer is supported per deployment. Local accounts remain available: production break-glass accounts still require operator-managed access/monitoring and are not a completed automated lifecycle.

The browser sign-in link appears only when configuration validates. Authorization Code uses S256 PKCE, encrypted five-minute verifier retention, nonce, single-use state and a separate HttpOnly browser-binding cookie. RS256/ES256 ID tokens require matching configured issuer/audience/signing key, nonce, subject and fresh time claims; multiple audiences require the correct authorized party. JWT-provided key URLs are ignored. Successful login rotates the local opaque session. Local logout/revocation exists; provider logout, federation provisioning and live Entra/Okta/Google acceptance are deferred.

Protocol reference: [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html). This reference defines protocol validation; it is not evidence of live interoperability.

## Audit verification and checkpoints

New calls through the central audit writer hash canonical event fields, tenant scope, sequence and previous digest in the same transaction. PostgreSQL organization row locks serialize appends; SQLite remains a local single-writer adapter. /api/trust/audit-integrity is organization-administrator-only and returns integrity metadata, not other repositories' source or event bodies. Existing unlinked history is counted as legacy and is not silently rebranded immutable.

Configure AUDIT_CHECKPOINT_KEY with at least 32 operator-managed characters and AUDIT_CHECKPOINT_KEY_ID for an HMAC-SHA256 checkpoint. Keep the key outside the database. Download and retain checkpoints in separately controlled storage; verify the HMAC over the exact returned payload. Keyed checkpoints are optional and visibly unavailable when no key is configured. Whole-chain replacement by a DB administrator can evade an unanchored chain. WORM archival, key rotation/re-signing and automatic external checkpoint retention are deferred; no non-repudiation certification is claimed.

## Parser isolation and static infrastructure

IaC parsing uses an owned `-I -B` Python helper, an empty temporary working directory and a stripped environment. Wall timeout 15s, source 512KB, result 8MB; YAML tokens/nesting/aliases and Helm checks remain enforced. POSIX helper limits are CPU 10s, address space 384MB, no output files and 32 open descriptors. On Windows those POSIX resource controls are not enforced. JS/TS/Java grammar helpers retain their previous process/node bounds. Python AST remains in the analysis process. Full non-root/read-only/no-network/process-count/job-object/seccomp isolation for all parsers is incomplete; do not claim imported text is fully OS sandboxed. Imported project commands, builds, IaC providers/templates and tests are never executed.

Native resources carry format, resource identity, range, static authority and an explicit unobserved-runtime state. Dockerfile stages, final users, image references and COPY stage links are parsed without execution. Heredocs remain PARTIAL. Terraform expressions/count/for_each are symbolic, module expansion/fetching is disabled. CloudFormation intrinsics are retained, transforms/nested stacks unresolved. Kubernetes/Compose declarations are checked structurally; Secret/ConfigMap values are not retained in resource metadata. Complete provider semantics, local-module expansion, Helm rendering, runtime reachability and image CVE scanning are deferred.

Reference: [Dockerfile instruction and stage semantics](https://docs.docker.com/reference/dockerfile/). Static checks are ProjectTrace-owned rules; these documents are not test evidence.

## Gates, reviews and exceptions

Unknown representative rule precision prevents default rule-based blocking. Native critical findings and exceeded quality reliability/high/complexity thresholds require review. Explicitly configured imported coverage and parsed-file coverage can fail based on measured evidence. Parsed-file denominator is included first-party source/test/example plus unsupported source/encoding; vendor/generated/binary/configuration files are excluded. No clean-repository conclusion follows from partial coverage.

FALSE_POSITIVE feedback records actor/reason/time/repository/rule/version/language/framework. Rule health counts latest versioned judgments per occurrence within repository grants. Voluntary dismissal fraction is not population precision/recall. A dismissal does not disable a global rule. Stable native-statement fingerprints exclude line offsets; safe review carry additionally requires unchanged normalized full-file security context, severity, confidence, classification and rule version. Ambiguous repeats, renames and semantic/formatting changes can reopen findings; this is not a complete AST structural identity system for every finding family.

CREATE_EXCEPTION / ACCEPT_RISK obey the tenant maximum (1–90 days). Privileged reviewers can POST /api/trust/exceptions/{id} with expected_version, action EXTEND/REVOKE, reason and days. Changes retain administration history and hash-linked audit events; revoke expires the suppression immediately. Expiry/exception administration does not rewrite the machine observation. Notification delivery and a dedicated exception administration UI are deferred.

## Production and scale boundaries

Existing self-hosted Compose/non-root Docker assets remain, but pinned OCI digests, image signing/provenance, production SBOM scan promotion, a complete Helm/K8s/operator installation, managed KMS deletion/rotation, source object storage and a current staging restore drill are not delivered enterprise proof. GHES connection-specific app/installation/webhook/CA/host configuration is still unimplemented; the current GitHub connector retains its deployment-wide github.com credentials. Do not configure arbitrary enterprise URLs into unrelated settings.

Application organization/repository grants and new ORM write guards are enforced and tested. Tenant scope reassignment is rejected. PostgreSQL RLS and complete compound tenant foreign keys across the original schema remain deferred; direct SQL is not covered by ORM guards.

Current source intake remains 1,000 entries / 10MB total / 512KB per file. The generated three-million-line admission benchmark proves rejection, not successful analysis. The 100-request benchmark proves sequential local durable receipt and replay handling, not simultaneous PR analysis/fairness/latency. A streaming content-addressed/sharded storage model, tenant-fair scheduler, supersession, staged PostgreSQL/Redis workers and representative load tests are required before claiming either target.
