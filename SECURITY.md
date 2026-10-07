# Security boundaries

This release has automated checks for tenant isolation, repository ACLs, CSRF, role checks, archive traversal, symlinks, oversized data, secret masking, webhook signatures/replay, fake citation rejection and repository nonexecution. These checks do not establish complete security coverage.

- Every tenant resource is selected through organization scope; repository grants are checked on detail reads, search/investigation, graph data, reviews and exports. Owner roles do not bypass source grants.
- Local credentials use Argon2id. Sessions are opaque random values; only their SHA-256 digests are stored. Cookies are HttpOnly, SameSite=Strict, Secure in production, expire after eight hours, rotate at login and invalidate at logout.
- POSTs require an exact allowlisted Origin. Authenticated browser mutations also require the session CSRF value. Signed GitHub webhook requests use HMAC instead of browser CSRF.
- Input is bounded before JSON/ZIP parsing. ZIP paths, symlinks, duplicate paths, compression ratio, file count and file sizes are checked. No archive extraction writes are performed. Nested archives and binaries are skipped.
- Detected secrets are redacted from persisted source and finding output. Detection is heuristic: unsupported secret formats can still be missed. Do not import highly sensitive code until broader secret detection and retention controls are validated.
- Critical low-confidence secret patterns recommend human review rather than automatic merge blocking. Accepting risk/creating exceptions requires privileged roles and expiry.
- Audit has no edit/delete API. It is append-oriented at the application layer; a database administrator can alter it. Cryptographic tamper evidence and archival controls are not implemented.
- Local mode uses separate in-process admission policies. Production uses Redis atomic counters and fails closed if Redis is unavailable. Real Redis transport, two competing workers, production admission, broker outage/retry, cancellation and non-root Linux prefork were exercised in a disposable VM. This does not establish multi-replica production capacity or fairness. Queue admission bounds active jobs per tenant/repository; PostgreSQL locks tenant admission. Weighted fairness, process isolation, provider token lifecycle, OIDC and incident controls remain incomplete.
- Queued raw source is encrypted with a shared Fernet key outside source control in a scoped `analysis_inputs` table. It expires after 72 hours, is deleted on completion/cancellation, and has hourly expiry cleanup when Celery beat runs. Encryption at rest does not remove the worker's need to decrypt source. Operators must run the scheduler and manage/rotate keys; external object storage and broader retention controls remain deferred.

Production mode disables demo login/API docs and requires explicit origins and a non-SQLite URL. These guards are necessary but do not mean production release gates have passed. Compose is a loopback-bound demo configuration and must not be exposed publicly.

## Public site boundary

Public pages use labeled synthetic excerpts and never fetch private workspace/source records. `/api/auth/options` returns only authenticated/local-registration/demo-availability booleans, with the existing no-store and admission middleware. Invalid/expired sessions reveal no account identity. Post-login destinations are restricted to known internal workspace paths. Registration and demo remain disabled in production. Public HTML contains no stored tenant data; hosting must apply HTTPS, operator security headers, correct static-route resolution and a separate API proxy.

The privacy page explains that persistent redacted source/history and backups are operator managed. Expiring encrypted queued input is separate from persistent source retention. No self-service source deletion, external AI submission, live cloud certification or enterprise identity promise is made. No real public domain was configured; the default build blocks indexing.

Report issues privately through your project's chosen security process. No external reporting address is configured by this scaffold.

## Native platform boundaries

Native rule/profile writes and direct cloud inventory require current authorization, CSRF and privileged roles. Profile conflicts return 409; writes append audit. AWS account matching and an explicit read-operation allowlist prevent cross-account inventory and write authority. Host credential references never enter output records. The live adapter has fixture verification and a tested missing-credential gate; no real cloud account was connected.

HCL2/Tree-sitter/safe YAML parse source as data. YAML alias/depth/node budgets and ZIP limits constrain work; workers have time/recycling/memory limits. The non-root prefork worker read ProjectTrace source from a read-only directory. A complete operating-system parser sandbox, language-specific worst-case resource proof and container-image scan remain release gates. Static flow findings do not establish runtime exploitability.

Native Tree-sitter grammars run as one bounded isolated helper process per uncached language batch. Only ProjectTrace-owned Python executes; source is JSON data in memory, and credential environment variables/user Python paths are excluded. The helper has a 30-second timeout and bounded input/results; failures mark PARSING/QUALITY/SAST PARTIAL. Source locations use UTF-8 byte offsets. This process boundary does not establish a complete OS filesystem/network sandbox.


## Code Intelligence boundary

Quality API reads enforce organization plus explicit repository grants, including selected historical snapshots, exports and source windows. Profile writes require administrators, CSRF/origin, current versions and audit. Human machine statuses are distinct; accepted-risk and exceptions retain privileged role/expiry requirements. Rule/scope profiles are bounded JSON data and cannot execute repository hooks.

Coverage is limited to 1 MB / 100,000 counters / 150,000 XML nodes / depth 50. Entity declarations and external document definitions are rejected. A recognized inert JaCoCo declaration is stripped without resolving it. Paths match exact repository-relative candidates after explicitly configured producer-prefix/root mapping; traversal, ambiguous matches and wrong declared revisions are refused. Producer revision matching does not independently prove execution or authenticity. CSV exports neutralize spreadsheet formula prefixes. SARIF is locally schema-validated; live SCM publishing remains unverified.


## Enterprise trust foundations (1.6.0)

New egress/OIDC/ORM guards/hash-linked audit/exception controls are described in [enterprise operations](docs/ENTERPRISE_TRUST_OPERATIONS.md). The [21-question validation](ENTERPRISE_TRUST_VALIDATION.md) distinguishes application controls from incomplete OS/network sandboxing, direct-SQL/RLS defense, secret lifecycle, production deployment and representative rule qualification. Existing deployment assets are not enterprise certification.
