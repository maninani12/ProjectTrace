# Administration & Control Center: architecture audit and implementation plan

Status (2026-10-10): qualified local administration scope **ADMIN_FEATURE_READY_FOR_DEMO**; whole-product/pilot gate **BLOCKED**. See the [final validation](../ADMINISTRATION_CONTROL_CENTER_VALIDATION.md) for executed gates, original 0020 rollout and limitations. The audit below records the historical pre-implementation baseline, not the current schema or an unlimited acceptance claim.
Baseline checkout: `07ae2b2` (`resolved errors`), clean at inspection. Migration head: `0018`.

## Existing architecture

- FastAPI routers authenticate through `backend/security.py`. Passwords use Argon2; cookie sessions last eight hours and mutations validate CSRF. OIDC subjects are explicitly bound and provider revocation is checked on requests.
- `User.organization_id` and `User.role` currently describe one primary tenant. There is no general multi-organization membership model or session-selected tenant. User emails are unique. OIDC subjects are identity bindings, not a replacement for team or organization memberships.
- `Grant` is the existing user/repository access model. Owners have no implicit source access. Existing scoped Records, graph queries, inventory and encrypted blobs depend on those grants. Preserve this property.
- Authorization is currently a combination of `EDIT_ROLES`, repository grants and individual administrator checks. Roles include ORG_OWNER, ADMIN, ENGINEER, VIEWER, REVIEWER and SECURITY_REVIEWER; none is a platform super administrator.
- QueueEntry, QueueCursor and PRHead provide bounded admission, fenced claims, recovery and cancellation. Jobs carry `user_id`, tenant/repository IDs and request IDs. Workers currently assume a user's primary organization; multi-membership requires an explicitly resolved job context.
- `Audit`/`AuditHead`/`AuditLink` provide transactional, tenant-scoped hash chaining through `backend/trust.append_audit`. This is tamper evidence, not immutable external storage. Privileged changes must commit with their audit event or roll back.
- Repository catalogue, finding/claim summaries and Infrastructure reads were recently corrected. Administration must use its own bounded indexed reads, never load a full workspace graph to populate a dashboard.
- React uses cookie/CSRF APIs, React Query and existing workspace navigation/styles. Read deadlines remain 15 seconds. Identity failures distinguish 401 from retryable failures. The native repository-analysis budget remains 900 seconds.
- Existing migrations and tests cover SQLite and disposable PostgreSQL schemas. Migration head assertions must advance with an additive revision. No production table reset or source-history rewrite is appropriate.

## Gaps and decisions

Add organization memberships alongside the existing primary organization, not duplicate users. Backfill existing primary memberships and preserve existing role/credential/source records. Resolve request tenant from an authorized session context; switching never edits the user's primary tenant. Organization suspension affects one membership; global suspension is a separate platform operation. Keep compatibility with existing isolated fixtures without opening membership fallback for an explicitly removed/suspended membership.

Add relational team/membership/repository inheritance, explicit platform operator bindings, versioned feature policies, restrictions, invitation digests, administrative command receipts and bounded application activity. Platform operators have operational metadata permissions; they receive no tenant membership or repository grant automatically. Exceptional source support is unavailable until a separate explicit, time-limited customer authorization is implemented and qualified.

Centralize role permissions, delegated resource checks, effective entitlements and repository authorization. Default deny unknown roles/features. Platform hard denies and organization mandatory restrictions outrank user exceptions. Conflicting team defaults deny; an explicit authorized user exception may override only ordinary defaults. Expiration is evaluated server-side on every decision. No broad privilege cache is introduced.

Do not turn off an analyzer silently. Analysis-submission/ingestion entitlements are checked at submission, dispatch and execution. Existing publications survive restrictions. Ordinary member suspension prevents new requests and queued execution. Already-running work may finish its previously authorized declared scope; explicit fenced cancellation is the separate control for active work. SQLite's existing long atomic publication transaction can delay competing control writes; do not promise instantaneous cancellation during that transaction. Any analyzer-specific rollout must preserve an honest declared scope; unsupported controls remain unavailable in the catalog.

Administrative mutations require CSRF, a granular permission, bounded input, expected versions where applicable, an idempotency key and a reason. Protect the last active owner; no self-promotion, team-admin escape or public platform bootstrap. Sensitive platform changes require fresh supported reauthentication and separate trusted operator bootstrap/approval where needed. Destructive erasure is a distinct retention-aware process, not ordinary suspension/removal.

Use existing audit chaining for privileged actions and structured safe activity metadata for analytics. Do not log passwords, invitation tokens, session digests, raw imported source, question text, device activity or arbitrary request bodies. Read aggregates in SQL with bounded date ranges. Metrics absent from durable measurements remain unavailable, never fabricated zero usage. Notifications start as durable in-app records; no email/provider delivery is claimed without configuration and tests.

## Ordered execution and acceptance plan

1. **Preserve/baseline:** verified online SQLite + encrypted blob recovery bundle, private count/hash/credential manifest, current service/job ownership and migration identity; run current auth/API/OIDC/queue/migration baseline in isolated databases. Do not interrupt active customer jobs to migrate.
2. **Identity/authorization:** additive migration, membership context and switching, role/permission catalog, platform bootstrap, centralized repository/team authorization and negative tests. Test migration/backfill/downgrade on a copy before applying locally.
3. **Lifecycle:** searchable paginated users/teams, digest-only invitations and acceptance, membership roles/suspension/reactivation/removal, scoped session revocation, team administration and repository inheritance. Preserve primary identities and historical data.
4. **Entitlements/governance:** versioned policies and explainable previews, temporary restrictions/exceptions, platform denies, API/worker enforcement, reduced quotas within hard technical caps, repository pause/archive metadata and fenced job control. Test concurrency and audit rollback.
5. **Activity/operations:** real SQL counts/trends, bounded activity/audit/security explorers, job metadata, usage provenance, in-app notifications and health. Tenant metadata/source confidentiality remains enforced.
6. **Integrated UX:** administration routes/nav with server-derived permissions, paginated tables/details, confirmations, access matrix/preview, errors/retry/loading/empty states, responsive and keyboard workflows. Never treat hidden buttons as authorization.
7. **Qualification:** full regression, disposable PostgreSQL, two-tenant role/permission matrix, expiration/revocation/worker checks, activity-volume and concurrent-update benchmarks, actual browser lifecycle/feature/team workflows, clean restart and preservation verification.
8. **Documentation/report:** role meanings and enforcement points, precedence, collection/retention, bootstrap/recovery, administrator guide, actual timings/results, changed files, migration proof and unsupported capabilities. Final verdict is ADMIN_FEATURE_READY_FOR_DEMO, CONTROLLED_PILOT_CANDIDATE or BLOCKED, based on measured gates. Existing whole-product release blockers are retained.

Private recovery and acceptance receipts are stored outside the product tree under the current task's `work/admin-control-center` directory. Credentials and backup contents must not be printed or linked as public artifacts. No commit/push is authorized.
