# Security boundaries

This release has automated checks for tenant isolation, repository ACLs, CSRF, role checks, archive traversal, symlinks, oversized data, secret masking, webhook signatures/replay, fake citation rejection and repository nonexecution. These checks do not establish complete security coverage.

- Every tenant resource is selected through organization scope; repository grants are checked on detail reads, search/investigation, graph data, reviews and exports. Owner roles do not bypass source grants.
- Local credentials use Argon2id. Sessions are opaque random values; only their SHA-256 digests are stored. Cookies are HttpOnly, SameSite=Strict, Secure in production, expire after eight hours, rotate at login and invalidate at logout.
- POSTs require an exact allowlisted Origin. Authenticated browser mutations also require the session CSRF value. Signed GitHub webhook requests use HMAC instead of browser CSRF.
- Input is bounded before JSON/ZIP parsing. ZIP paths, symlinks, duplicate paths, compression ratio, file count and file sizes are checked. No archive extraction writes are performed. Nested archives and binaries are skipped.
- Detected secrets are redacted from persisted source and finding output. Detection is heuristic: unsupported secret formats can still be missed. Do not import highly sensitive code until broader secret detection and retention controls are validated.
- Critical low-confidence secret patterns recommend human review rather than automatic merge blocking. Accepting risk/creating exceptions requires privileged roles and expiry.
- Audit has no edit/delete API. It is append-oriented at the application layer; a database administrator can alter it. Cryptographic tamper evidence and archival controls are not implemented.
- Local mode uses separate in-process admission policies. Production uses Redis atomic counters and fails closed if Redis is unavailable. Redis transport and multi-replica behavior have not been executed on this host. Queue admission bounds active jobs per tenant/repository; PostgreSQL locks tenant admission. Weighted fairness, process isolation, provider token lifecycle, OIDC and incident controls remain incomplete.
- Queued raw source is encrypted with a shared Fernet key outside source control in a scoped `analysis_inputs` table. It expires after 72 hours, is deleted on completion/cancellation, and has hourly expiry cleanup when Celery beat runs. Encryption at rest does not remove the worker's need to decrypt source. Operators must run the scheduler and manage/rotate keys; external object storage and broader retention controls remain deferred.

Production mode disables demo login/API docs and requires explicit origins and a non-SQLite URL. These guards are necessary but do not mean production release gates have passed. Compose is a loopback-bound demo configuration and must not be exposed publicly.

Report issues privately through your project's chosen security process. No external reporting address is configured by this scaffold.
