"""Central scoped authorization. Platform operations never imply tenant source grants."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select

from backend.admin_models import (
    AccountControl,
    FeaturePolicy,
    GovernanceRevision,
    OrganizationControl,
    OrganizationMembership,
    PlatformOperator,
    RepositoryControl,
    RepositoryDenial,
    Team,
    TeamMembership,
    TeamRepository,
)
from backend.db import Grant, Repository

PERMISSIONS = {
    "engineering.write": "Modify authorized engineering records; repository grants still apply.",
    "engineering.exceptions.manage": "Approve permitted risk exceptions on explicitly authorized repository records.",
    "security.policy.manage": "Manage permitted tenant trust controls without changing deployment safety caps.",
    "users.read": "Read the scoped organization member directory.",
    "users.invite": "Invite non-owner members into the current organization.",
    "users.suspend": "Restrict eligible organization memberships, without global account deletion.",
    "users.reactivate": "Reactivate eligible suspended memberships.",
    "users.remove": "Remove eligible organization memberships while retaining authored history.",
    "users.roles.manage": "Assign permitted non-owner organizational roles to another member.",
    "sessions.revoke": "Revoke sessions in the authorized organization, without exposing tokens.",
    "teams.read": "Read authorized teams and their membership metadata.",
    "teams.create": "Create teams in the current organization.",
    "teams.manage": "Manage authorized team membership and repository inheritance.",
    "repositories.read": "Read organization repository operational metadata; source grants are separate.",
    "repositories.manage": "Archive or pause future work without deleting repository history.",
    "repositories.access.grant": "Manage explicit scoped repository access and denials.",
    "analyses.read": "Read scoped job metadata; no encrypted inputs or raw source.",
    "analyses.cancel": "Request fenced cancellation of eligible scoped jobs.",
    "analyses.retry": "Retry eligible jobs through the existing bounded recovery workflow.",
    "features.manage": "Preview and manage eligible scoped feature policies.",
    "usage.read": "Read measured scoped usage and provenance.",
    "quotas.manage": "Reduce eligible scoped quotas within technical safety caps.",
    "activity.read": "Read bounded scoped application activity metadata.",
    "audit.read": "Read scoped governance audit metadata.",
    "audit.export": "Export a bounded, scoped, sanitized audit page after fresh authentication.",
    "security.investigate": "Read scoped access/security metadata without private source elevation.",
    "organization.settings.manage": "Manage ordinary current-organization settings.",
    "organization.ownership.transfer": "Request a consented ownership transfer with owner safeguards.",
    "organization.ownership.accept": "Consent only to an unexpired transfer addressed to this authenticated member; endpoint validates requester authority and membership versions.",
    "admin.roles.manage": "Assign eligible elevated organization roles after fresh authentication.",
}
OWNER = frozenset(PERMISSIONS)
ADMIN = OWNER - {"organization.ownership.transfer", "admin.roles.manage", "quotas.manage"}
ROLE_PERMISSIONS = {
    "ORG_OWNER": OWNER, "ADMIN": ADMIN, "ORG_ADMIN": ADMIN,
    "ENGINEER": {"engineering.write"}, "STANDARD_USER": {"engineering.write"},
    "REVIEWER": {"engineering.write"}, "SECURITY_REVIEWER": {"engineering.write","engineering.exceptions.manage","security.policy.manage"},
    "VIEWER": set(), "TEAM_ADMIN": {"teams.read"},
    "AUDITOR": {"audit.read", "activity.read", "usage.read", "teams.read", "repositories.read", "analyses.read"},
    "SECURITY_ADMIN": {"engineering.write", "engineering.exceptions.manage", "security.policy.manage", "users.read", "users.suspend", "users.reactivate", "sessions.revoke",
        "activity.read", "audit.read", "security.investigate", "repositories.read", "analyses.read", "usage.read"},
}
PLATFORM_PERMISSIONS = {
    "PLATFORM_SUPER_ADMIN": {"platform.health", "platform.organizations", "platform.safety", "platform.operators", "platform.audit", "platform.accounts"},
    "PLATFORM_SUPPORT_ADMIN": {"platform.health", "platform.organizations"},
    "PLATFORM_AUDITOR": {"platform.health", "platform.audit"},
}
for _role,_permissions in list(ROLE_PERMISSIONS.items()):
    ROLE_PERMISSIONS[_role]=frozenset(_permissions)|{"organization.ownership.accept"}
SELF_SERVICE_PERMISSIONS={"engineering.write","organization.ownership.accept"}
FEATURES = {
    "zip_import": ("ZIP import", "Submit new ZIP imports and source archives."),
    "public_github": ("Public GitHub import", "Fetch authorized public repositories without executing them."),
    "private_scm": ("Private SCM connections", "Configure and use existing private SCM integrations."),
    "analyses": ("Analysis submissions", "Submit, retry and begin new static analysis work."),
    "ask_engineering": ("Ask Engineering", "Run source-evidence investigations in authorized snapshots."),
    "cloud": ("Cloud inventory", "Read cloud views and request configured read-only inventory."),
    "exports": ("Exports", "Download authorized source-evidence and governance exports."),
    "api_access": ("Application API access", "Use engineering APIs; identity, notices and administration remain reachable."),
}
CATALOG_VERSION = "projecttrace-governance-v1"


def timestamp():
    return datetime.now(timezone.utc)


def future(value):
    if value is None:
        return True
    try:
        moment = datetime.fromisoformat(value)
        return moment.tzinfo is not None and moment > timestamp()
    except (TypeError, ValueError):
        return False


def expired(value):
    if value is None:
        return False
    try:
        moment = datetime.fromisoformat(value)
        return moment.tzinfo is not None and moment <= timestamp()
    except (TypeError, ValueError):
        return False


def policy_active(row):
    # Corrupt/ambiguous expirations cannot lift a restriction or grant access.
    return not expired(row.expires_at) if row.decision == "DENY" else future(row.expires_at)


@dataclass
class Principal:
    identity: object
    organization_id: str
    role: str
    enabled: bool
    membership_version: int = 0
    platform_role: str | None = None

    def __getattr__(self, name):
        return getattr(self.identity, name)


def resolve_principal(db, user, organization_id=None, *, platform_only=False):
    organization_id = organization_id or user.organization_id
    if isinstance(user, Principal):
        user = user.identity
    account = db.get(AccountControl,user.id,populate_existing=True)
    globally_enabled = bool(user.enabled and (not account or account.state=="ACTIVE" or account.state=="SUSPENDED" and expired(account.expires_at)))
    member = db.get(OrganizationMembership, (organization_id, user.id), populate_existing=True)
    # Existing test/legacy primary identities remain compatible. An explicit
    # removed/suspended row NEVER falls back to User.role.
    active = bool(globally_enabled and (member is not None or organization_id == user.organization_id))
    role = member.role if member else user.role if organization_id == user.organization_id else "UNKNOWN"
    active = active and role in ROLE_PERMISSIONS
    if member:
        active = active and (member.state == "ACTIVE" or member.state == "SUSPENDED" and expired(member.expires_at))
    control = db.get(OrganizationControl, organization_id)
    if control and control.state != "ACTIVE":
        active = False
    operator = db.get(PlatformOperator, user.id)
    platform_role = operator.role if operator and operator.enabled and globally_enabled else None
    if platform_only and platform_role:
        active = globally_enabled
    return Principal(user, organization_id, role, active, member.version if member else 0, platform_role)


def team_ids(db, user, *, administered=False):
    query = select(TeamMembership.team_id).join(Team, Team.id == TeamMembership.team_id).where(
        TeamMembership.organization_id == user.organization_id, TeamMembership.user_id == user.id, Team.archived.is_(False))
    if administered:
        query = query.where(TeamMembership.role == "ADMIN")
    return list(db.scalars(query))


def permitted(db, user, permission, *, team_id=None):
    if not user.enabled:
        return False
    if permission.startswith("platform."):
        return permission in PLATFORM_PERMISSIONS.get(getattr(user, "platform_role", None), set())
    if permission in ROLE_PERMISSIONS.get(user.role, set()):
        return True
    if team_id and permission in {"teams.manage", "teams.read", "features.manage", "repositories.access.grant", "usage.read", "activity.read", "analyses.read"}:
        return team_id in team_ids(db, user, administered=True)
    if permission == "teams.read":
        return bool(team_ids(db, user, administered=True))
    return False


def require_permission(db, user, permission, *, team_id=None):
    if permission not in PERMISSIONS and not permission.startswith("platform."):
        raise HTTPException(403, "Unknown administrative permission.")
    if not permitted(db, user, permission, team_id=team_id):
        raise HTTPException(403, "This action is not permitted in your administrative scope.")


def repository_condition(user):
    direct = exists(select(Grant.user_id).where(Grant.user_id == user.id, Grant.repository_id == Repository.id))
    inherited = exists(select(TeamRepository.repository_id).join(TeamMembership,
        and_(TeamMembership.team_id == TeamRepository.team_id, TeamMembership.organization_id == TeamRepository.organization_id))
        .join(Team, Team.id == TeamRepository.team_id).where(TeamRepository.repository_id == Repository.id,
            TeamRepository.organization_id == user.organization_id, TeamMembership.user_id == user.id, Team.archived.is_(False)))
    denied = exists(select(RepositoryDenial.user_id).where(RepositoryDenial.user_id == user.id,
        RepositoryDenial.organization_id == user.organization_id, RepositoryDenial.repository_id == Repository.id))
    return and_(Repository.organization_id == user.organization_id, or_(direct, inherited), ~denied)


def policy_scope(organization_id, scope_type, target_id):
    return "PLATFORM" if scope_type == "PLATFORM" else f"{organization_id}:{scope_type}:{target_id}"


def decision_version(db, user, rows=()):
    revisions = list(db.execute(select(GovernanceRevision.scope_key, GovernanceRevision.revision).where(
        GovernanceRevision.scope_key.in_(["PLATFORM", user.organization_id]))))
    value = [CATALOG_VERSION, user.organization_id, user.id, user.role, getattr(user, "membership_version", 0),
        sorted((r.scope_key, r.revision) for r in revisions), sorted((r.id, r.version, future(r.expires_at)) for r in rows)]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:24]


def feature_access(db, user, feature, *, proposed=None):
    if feature not in FEATURES:
        return {"feature": feature, "allowed": False, "reason": "UNKNOWN_FEATURE", "decision_version": CATALOG_VERSION}
    scopes = ["PLATFORM", policy_scope(user.organization_id, "ORGANIZATION", user.organization_id),
        policy_scope(user.organization_id, "USER", user.id), policy_scope(user.organization_id, "ROLE", user.role)]
    scopes.extend(policy_scope(user.organization_id, "TEAM", team_id) for team_id in team_ids(db, user))
    rows = list(db.scalars(select(FeaturePolicy).where(FeaturePolicy.feature == feature, FeaturePolicy.scope_key.in_(scopes))))
    if proposed is not None and proposed.feature == feature and proposed.scope_key in scopes:
        rows = [row for row in rows if row.scope_key != proposed.scope_key] + [proposed]
    active = [row for row in rows if row.decision != "INHERIT" and policy_active(row)]
    denies = [row for row in active if row.decision == "DENY"]
    hard = [row for row in denies if row.scope_type == "PLATFORM" or row.scope_type == "ORGANIZATION" and row.mandatory]
    specific = [row for row in active if row.scope_type == "USER"]
    # User ALLOW overrides ordinary team/role defaults only with an explicit,
    # expiring exception authorized by the organization policy.
    organization = next((row for row in active if row.scope_type == "ORGANIZATION"), None)
    exception = bool(organization and organization.allow_user_exceptions and specific and specific[0].expires_at)
    if not user.enabled:
        selected, allowed, reason = None, False, "MEMBERSHIP_UNAVAILABLE"
    elif hard:
        selected = sorted(hard, key=lambda row: (row.scope_type != "PLATFORM", row.id))[0]
        allowed, reason = False, "MANDATORY_RESTRICTION"
    elif specific and (specific[0].decision == "DENY" or not denies or exception):
        selected = specific[0]
        allowed, reason = selected.decision == "ALLOW", "EXPLICIT_USER_POLICY"
    elif denies:
        selected = sorted(denies, key=lambda row: (row.scope_type != "ORGANIZATION", row.id))[0]
        allowed, reason = False, "INHERITED_DENY"
    else:
        selected = sorted(active, key=lambda row: row.id)[0] if active else None
        allowed, reason = True, "INHERITED_ALLOW" if selected else "EXISTING_IMPLEMENTED_CAPABILITY"
    return {"feature": feature, "allowed": allowed, "reason": reason, "source_policy": selected.id if selected else None,
        "scope": selected.scope_type if selected else "DEFAULT", "mandatory": bool(selected and selected.mandatory),
        "priority": 1000 if selected and selected.scope_type == "PLATFORM" else 900 if selected and selected.mandatory else 700 if selected else 0,
        "expires_at": selected.expires_at if selected else None, "decision_version": decision_version(db, user, rows),
        "organization_id": user.organization_id, "user_id": user.id,
        "policies": [{"id": row.id, "scope": row.scope_type, "target_id": row.target_id, "decision": row.decision,
            "mandatory": row.mandatory, "expires_at": row.expires_at, "active": policy_active(row), "version": row.version} for row in rows]}


def require_feature(db, user, feature):
    decision = feature_access(db, user, feature)
    if not decision["allowed"]:
        raise HTTPException(403, {"code": "FEATURE_RESTRICTED", "message": "This feature is unavailable by access policy. Contact your organization administrator.",
            "feature": feature, "decision_version": decision["decision_version"], "expires_at": decision.get("expires_at")})
    return decision


def request_feature(path, method, params):
    if path == "/api/ask":
        return "ask_engineering"
    if path.startswith(("/api/archive/",)) and method == "POST" or path.endswith("/source-archive"):
        return "zip_import"
    if path.startswith("/api/github/public/"):
        return "public_github"
    if path.startswith(("/api/scm/", "/api/github/connections")) or path == "/api/connections/github":
        return "private_scm"
    if path.startswith("/api/cloud/") or path.startswith("/api/trust/cloud") or params.get("view") in {"Cloud", "Cloud Assets", "Cloud Identities", "Exposure", "Risk Paths"}:
        return "cloud"
    if path.startswith("/api/export") or path.endswith(("/sarif", "/sbom", "/export")):
        return "exports"
    if method == "POST" and (path.endswith("/analyze") or path.endswith("/retry") or path == "/api/import"):
        return "analyses"
    return None


def enforce_request(db, user, request):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith(("/api/auth/", "/api/admin/", "/api/notifications")):
        require_feature(db, user, "api_access")
        feature = request_feature(path, request.method, request.query_params)
        if feature:
            require_feature(db, user, feature)
        if feature in {"zip_import", "public_github"}:
            require_feature(db, user, "analyses")


def authorize_job(db, user, repo, source=None):
    """Recheck every dispatch/start; already-running work retains its declared scope.

    Ordinary policy changes prevent new work. Explicit fenced cancellation is
    the separate control for active jobs; no completed publication is erased.
    """
    principal = resolve_principal(db, user, repo.organization_id)
    if not principal.enabled:
        raise HTTPException(403, "Job submitter's organization access is unavailable.")
    require_feature(db, principal, "api_access")
    require_feature(db, principal, "analyses")
    if source in {"PUBLIC_GITHUB", "GITHUB"}:
        require_feature(db, principal, "public_github" if source == "PUBLIC_GITHUB" else "private_scm")
    if source in {"ZIP", "INVENTORY"}:
        require_feature(db, principal, "zip_import")
    control = db.get(RepositoryControl, repo.id)
    if control and (control.archived or control.analysis_paused):
        raise HTTPException(403, "New analysis is paused for this repository.")
    from backend.security import require_repo
    require_repo(db, principal, repo.id)
    return principal


def job_principal(db, job):
    """Resolve the durable submitting/integration identity in the job tenant."""
    from backend.db import Record, User
    repo=db.get(Repository,job.repository_id)
    if not repo or repo.organization_id!=job.organization_id:
        raise HTTPException(403,"Job repository scope is invalid.")
    actor_id=job.data.get("user_id")
    if not actor_id and job.data.get("source")=="GITHUB":
        key="github:"+job.data["connection_id"] if job.data.get("connection_id") else "github"
        integration=db.scalar(select(Record).where(Record.organization_id==job.organization_id,Record.kind=="integration",Record.natural_key==key))
        actor_id=integration.data.get("owner_id") if integration else None
    actor=db.get(User,actor_id) if actor_id else None
    if actor is None:
        raise HTTPException(403,"A currently authorized job identity is required.")
    return authorize_job(db,actor,repo,job.data.get("source"))
