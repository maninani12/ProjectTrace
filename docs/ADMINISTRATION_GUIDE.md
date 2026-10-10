# ProjectTrace Administration & Control Center

This guide describes implemented controls. Read the [validation report](../ADMINISTRATION_CONTROL_CENTER_VALIDATION.md) for measured acceptance and remaining release gates. Administration does not establish full-product production readiness. The [exact permission matrix](ADMINISTRATION_PERMISSIONS.md) lists the server-enforced role permissions.

## Open the control center

Sign in with your existing account, select the intended organization in the workspace selector, then open **Administration**. The server derives sections and permitted actions from the selected membership, current restrictions, and any separately assigned platform operator role. Existing organization owners receive organization administration after the additive migration. Startup never creates a platform administrator, resets passwords, or seeds an existing database.

Ordinary engineers can use authorized engineering workflows and their own notifications. They cannot open the organization user directory or global controls. A member with an active team ADMIN assignment can open Team Operations and manage only that team. Assigning the organization TEAM_ADMIN role alone does not grant authority over every team.

## Members and invitations

Users supports server pagination, search, recorded restriction state, member detail, permitted role changes, temporary or permanent suspension, reactivation, removal, and organization-scoped session revocation. Directory timestamps distinguish membership creation from unknown legacy account creation. Usage and last-login fields show only recorded measurements; historical telemetry is incomplete. Public session identifiers identify sessions without exposing cookie digests.

Invitation links are manually delivered by the administrator. The token is returned once, stored only as a digest, carried in the browser URL fragment, then removed from browser history. Replaying an administrative command does not disclose it again. Invitations expire after seven days; resend invalidates the old token. Acceptance is single use and rechecks the issuing administrator's current authority. Existing accounts must authenticate as the invited identity; acceptance never changes an existing password. OIDC-only users must sign in through their provider. Local password acceptance for a new account requires at least 16 characters. No email delivery is configured or claimed.

Suspension/removal preserves authored evidence, review and audit history. It revokes affected organization sessions; other valid memberships remain available after sign-in. Expired temporary suspension is resolved on the server. Global account suspension is a separate platform control. Unknown roles and invalid grant expirations fail closed. Self-promotion, changing your own membership through privileged lifecycle commands, direct owner-role assignment, and removal of the last eligible owner are rejected.

Ownership transfer requires an active target member, current membership versions, a reason, and a designated target's fresh consent within 24 hours. The previous owner becomes ADMIN. Source access remains governed by explicit repository grants.

## Teams and repositories

Create, rename, archive or restore teams; assign members and delegated administrators; transfer team ownership; and inspect their permitted operational scope. Member selection is paginated and searchable. Delegated administrators see a minimal candidate directory, not organization-wide email/session details. A team owner must transfer ownership before being removed.

Repository administration lists metadata separately from source access. Pause blocks future work; archive preserves repository and snapshot history. Explicit user grants and active-team inheritance allow source access only within the selected tenant. A user-specific denial overrides both. Clearing a denial does not create a direct grant; it restores whatever permitted grant or inheritance remains. Archiving a team removes its inherited access while retaining history. Platform roles and organization ownership do not automatically grant repository source access.

Team usage/job attribution is prospective, captured at submission. Moving a person between teams does not rewrite historical attribution. Team activity includes team-targeted events and attributed jobs, not unrelated actions by current team members.

## Feature access and quotas

The catalog controls eight implemented capabilities: ZIP import, public GitHub import, private SCM connections, analysis submissions, Ask Engineering, cloud inventory/views, exports, and engineering API access. It does not advertise unimplemented per-analyzer switches. Disabling submission never silently converts an incomplete analysis into success.

Policies are scoped to platform, organization, team, role or user. Preview the proposed access, inspect its bounded affected-population count/sample, provide a reason, and confirm against the recorded version. A preview is bound to the actor, request body, governing revisions and expiration; stale previews must be regenerated. History restoration creates a new policy revision rather than rewriting history.

Precedence:

1. Active platform DENY and mandatory organization DENY remain authoritative.
2. Ordinary organization restrictions permit a user ALLOW only when user exceptions are explicitly enabled.
3. Conflicting team/role defaults deny unless an eligible explicit user exception applies.
4. Unknown features, roles and malformed allowance expirations deny.

User ALLOW exceptions must expire. Ordinary expiring policies are limited to 90 days. Platform emergency DENY is mandatory and does not expire automatically. Releasing it requires a distinct, freshly authenticated current super administrator's approval within 30 minutes. Local password reauthentication confirms a recent password check, not MFA. OIDC sensitive operations require fresh supported provider sign-in.

The server enforces access at request authentication, repository authorization, admission, dispatch and worker start. Active work may finish its previously authorized declared scope; use explicit fenced cancellation to stop it. This avoids silently changing analyzer coverage halfway through a run. The browser polls access approximately every ten seconds and clears protected cached results when access changes. Session revocation returns to sign-in. Server enforcement does not wait for browser polling.

Owners can reduce pending/daily analysis quotas for organization, team or user scopes. Admission serializes competing submissions. Retries remain subject to existing finite recovery rules. Deployment safety caps remain authoritative: the 900-second analysis budget, bounded parser helpers, upload limits, request deadlines and database resource protections are unchanged. Configurable CPU, memory, bytes-per-job or SLA controls are unavailable where there is no measured/enforced implementation.

## Operations, analytics and privacy

Dashboard, usage, jobs, security, activity and audit are independent bounded metadata queries. They do not download a workspace evidence graph. Choose day/week/month/90 days or an explicit range of at most 90 days. Null CPU/memory/live-worker heartbeat fields mean unavailable, not zero. Recorded analysis duration is wall time, not CPU consumption. Queue wait is reported only when recorded. Source storage is measured at organization scope; team/user storage is not fabricated from shared blobs.

Activity filters include actor, repository, action, category, outcome, target, correlation and time. Inspect opens a sanitized event detail. Exports are scoped pages of at most 100 records, require export authority/entitlement and fresh authentication, and append an audit event. A bounded page is not a complete compliance archive. Audit events retain the existing tenant hash chain; hash chaining is tamper evidence, not external immutable storage.

Required governance mutations, their command receipts, audit and activity mirrors commit atomically. Audit failure rolls back the mutation. Routine failed-login/access-denial telemetry uses a bounded asynchronous queue and may drop under backpressure, write failure or process crash; health exposes process counters. Unknown-account events are not falsely assigned to a customer tenant. No passwords, invitation/session tokens, imported source, request bodies, questions/chat, IP addresses or device/user-agent surveillance are collected in these telemetry payloads. Redaction and payload bounds also apply to returned metadata. Reasons are operator-provided; do not place secrets in them.

Notifications are durable in-app notices with per-user read state and pagination, including membership restrictions and policy changes. There is no email/SMS delivery guarantee. Security Center reports recorded denial/restriction events, not behavioral anomaly detection or automated incident containment.

## Platform operations

Platform roles are separately bound existing accounts: SUPER_ADMIN for safety/accounts/operators/metadata, SUPPORT_ADMIN for health and organization metadata, AUDITOR for health and platform audit. None implies customer source access. Organization/global restrictions are independent from membership roles. Operator changes and emergency feature releases require a distinct current super administrator; the last unrestricted super administrator is protected. There is no public bootstrap endpoint or implicit support bypass.

Initial offline bootstrap is `python -m scripts.bootstrap_platform`, using the existing configured database. It requires TWO distinct existing local organization owners to enter their own credentials and the exact confirmation phrase interactively. It operates only while there are no platform operator records and writes the required audit events. It never resets credentials or grants repository access. Do not run it unattended or collect another person's password. This local bootstrap has not been performed on the customer's database.

## Retention, recovery and deployment

Migration 0019 adds governance tables, indexed activity and legacy membership/session backfills; it does not rebuild source tables. Migration 0020 adds an outcome index so security counts can read the tenant's relevant index range without scanning activity payloads. Back up the database plus encrypted blobs and separately retain required keys before migrating. Verify copy migration, preservation and constraints first. Downgrade of governance is rejected once actual governance/history/restrictions exist because dropping them would lose controls. Restore a verified complete recovery bundle under the documented deployment recovery procedure; do not reset the database to fix a UI problem.

The optional offline `python -m scripts.retain_activity --organization-id ID --owner-email EMAIL` previews routine activity older than 90 days. The owner authenticates interactively. `--apply --reason` additionally requires an exact confirmation phrase and deletes one bounded batch (default 500, maximum 1000). The minimum retention window is 30 days. Required audit history and audit-derived activity mirrors are never removed by this tool. No automatic customer retention purge has been executed. Contractual/legal retention and external immutable archives require deployment-specific qualification.

Managed local start/stop uses `scripts.dev_runtime` or the existing PowerShell wrappers. Stop verifies project process identities and drains active work; start migrates and checks API/UI readiness without reseeding. Inspect sanitized job details, retained inventory, parser diagnostics and stages when work fails. Use the existing bounded retry/cancellation workflow rather than increasing timeouts. A timed-out administrative mutation may have committed: retry with the same command ID and unchanged payload to obtain its durable receipt.

Known limits include SQLite's single publication writer, application/ORM tenant enforcement without full database RLS, no complete imported-code helper sandbox, no production IdP/GHES/provider/browser matrix qualification, no sustained multi-host/broker throughput claim, incomplete legacy telemetry and unchanged large-repository cold/memory/coverage release gates. Read the previous reliability reports for the actual OpenMetadata and ZIP outcomes; administration does not supersede them.
