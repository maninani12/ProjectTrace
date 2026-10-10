# Administrative role and permission matrix

Generated from the implemented central permission catalog. Repository source grants and effective feature policies are additional requirements. Organization selection changes the membership being evaluated, never the primary identity. Unknown roles fail closed.

| Organization role | Exact permission keys |
| --- | --- |
| ORG_OWNER | `activity.read`, `admin.roles.manage`, `analyses.cancel`, `analyses.read`, `analyses.retry`, `audit.export`, `audit.read`, `engineering.exceptions.manage`, `engineering.write`, `features.manage`, `organization.ownership.accept`, `organization.ownership.transfer`, `organization.settings.manage`, `quotas.manage`, `repositories.access.grant`, `repositories.manage`, `repositories.read`, `security.investigate`, `security.policy.manage`, `sessions.revoke`, `teams.create`, `teams.manage`, `teams.read`, `usage.read`, `users.invite`, `users.reactivate`, `users.read`, `users.remove`, `users.roles.manage`, `users.suspend` |
| ADMIN | `activity.read`, `analyses.cancel`, `analyses.read`, `analyses.retry`, `audit.export`, `audit.read`, `engineering.exceptions.manage`, `engineering.write`, `features.manage`, `organization.ownership.accept`, `organization.settings.manage`, `repositories.access.grant`, `repositories.manage`, `repositories.read`, `security.investigate`, `security.policy.manage`, `sessions.revoke`, `teams.create`, `teams.manage`, `teams.read`, `usage.read`, `users.invite`, `users.reactivate`, `users.read`, `users.remove`, `users.roles.manage`, `users.suspend` |
| ORG_ADMIN | `activity.read`, `analyses.cancel`, `analyses.read`, `analyses.retry`, `audit.export`, `audit.read`, `engineering.exceptions.manage`, `engineering.write`, `features.manage`, `organization.ownership.accept`, `organization.settings.manage`, `repositories.access.grant`, `repositories.manage`, `repositories.read`, `security.investigate`, `security.policy.manage`, `sessions.revoke`, `teams.create`, `teams.manage`, `teams.read`, `usage.read`, `users.invite`, `users.reactivate`, `users.read`, `users.remove`, `users.roles.manage`, `users.suspend` |
| ENGINEER | `engineering.write`, `organization.ownership.accept` |
| STANDARD_USER | `engineering.write`, `organization.ownership.accept` |
| REVIEWER | `engineering.write`, `organization.ownership.accept` |
| SECURITY_REVIEWER | `engineering.exceptions.manage`, `engineering.write`, `organization.ownership.accept`, `security.policy.manage` |
| VIEWER | `organization.ownership.accept` |
| TEAM_ADMIN | `organization.ownership.accept`, `teams.read` |
| AUDITOR | `activity.read`, `analyses.read`, `audit.read`, `organization.ownership.accept`, `repositories.read`, `teams.read`, `usage.read` |
| SECURITY_ADMIN | `activity.read`, `analyses.read`, `audit.read`, `engineering.exceptions.manage`, `engineering.write`, `organization.ownership.accept`, `repositories.read`, `security.investigate`, `security.policy.manage`, `sessions.revoke`, `usage.read`, `users.reactivate`, `users.read`, `users.suspend` |

All known roles have `organization.ownership.accept`, which is self-service consent only for an unexpired transfer addressed to that member. It does not grant administration access. Legacy `ORG_ADMIN` is accepted for compatibility; new elevated role assignment is guarded. `STANDARD_USER`, `ENGINEER` and `REVIEWER` preserve existing engineering write behavior on explicitly authorized repositories.

An active team ADMIN assignment delegates `teams.manage`, `teams.read`, `features.manage`, `repositories.access.grant`, `usage.read`, `activity.read` and `analyses.read` only when the endpoint supplies and validates that team. It cannot cancel/retry organization jobs, view unrelated member actions, or change an organization/platform policy. The organization TEAM_ADMIN role alone does not appoint a person to any team.

| Platform role | Exact permission keys |
| --- | --- |
| PLATFORM_SUPER_ADMIN | `platform.accounts`, `platform.audit`, `platform.health`, `platform.operators`, `platform.organizations`, `platform.safety` |
| PLATFORM_SUPPORT_ADMIN | `platform.health`, `platform.organizations` |
| PLATFORM_AUDITOR | `platform.audit`, `platform.health` |

Platform bindings are independent of organization roles and confer metadata/control access only. A suspended own organization can still reach permitted platform metadata; global account restrictions remain authoritative. Source/evidence always requires explicit tenant membership and repository authorization.

| Permission | Meaning |
| --- | --- |
| `engineering.write` | Modify authorized engineering records; repository grants still apply. |
| `engineering.exceptions.manage` | Approve permitted risk exceptions on explicitly authorized repository records. |
| `security.policy.manage` | Manage permitted tenant trust controls without changing deployment safety caps. |
| `users.read` | Read the scoped organization member directory. |
| `users.invite` | Invite non-owner members into the current organization. |
| `users.suspend` | Restrict eligible organization memberships, without global account deletion. |
| `users.reactivate` | Reactivate eligible suspended memberships. |
| `users.remove` | Remove eligible organization memberships while retaining authored history. |
| `users.roles.manage` | Assign permitted non-owner organizational roles to another member. |
| `sessions.revoke` | Revoke sessions in the authorized organization, without exposing tokens. |
| `teams.read` | Read authorized teams and their membership metadata. |
| `teams.create` | Create teams in the current organization. |
| `teams.manage` | Manage authorized team membership and repository inheritance. |
| `repositories.read` | Read organization repository operational metadata; source grants are separate. |
| `repositories.manage` | Archive or pause future work without deleting repository history. |
| `repositories.access.grant` | Manage explicit scoped repository access and denials. |
| `analyses.read` | Read scoped job metadata; no encrypted inputs or raw source. |
| `analyses.cancel` | Request fenced cancellation of eligible scoped jobs. |
| `analyses.retry` | Retry eligible jobs through the existing bounded recovery workflow. |
| `features.manage` | Preview and manage eligible scoped feature policies. |
| `usage.read` | Read measured scoped usage and provenance. |
| `quotas.manage` | Reduce eligible scoped quotas within technical safety caps. |
| `activity.read` | Read bounded scoped application activity metadata. |
| `audit.read` | Read scoped governance audit metadata. |
| `audit.export` | Export a bounded, scoped, sanitized audit page after fresh authentication. |
| `security.investigate` | Read scoped access/security metadata without private source elevation. |
| `organization.settings.manage` | Manage ordinary current-organization settings. |
| `organization.ownership.transfer` | Request a consented ownership transfer with owner safeguards. |
| `organization.ownership.accept` | Consent only to an unexpired transfer addressed to this authenticated member; endpoint validates requester authority and membership versions. |
| `admin.roles.manage` | Assign eligible elevated organization roles after fresh authentication. |
