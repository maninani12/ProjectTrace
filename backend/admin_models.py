"""Additive governance models; existing identity, grants and evidence stay authoritative."""
from sqlalchemy import JSON, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base, now


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (Index("ix_membership_directory", "organization_id", "state", "user_id"),
        CheckConstraint("state IN ('ACTIVE','SUSPENDED','REMOVED')", name="ck_membership_state"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(50), nullable=True, default=now)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class SessionContext(Base):
    __tablename__ = "session_contexts"
    digest: Mapped[str] = mapped_column(ForeignKey("sessions.digest", ondelete="CASCADE"), primary_key=True)
    public_id: Mapped[str] = mapped_column(String(80), unique=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reauthenticated_at: Mapped[float | None] = mapped_column(nullable=True)
    assurance: Mapped[str] = mapped_column(String(20), default="LEGACY")


class PlatformOperator(Base):
    __tablename__ = "platform_operators"
    __table_args__ = (CheckConstraint("role IN ('PLATFORM_SUPER_ADMIN','PLATFORM_SUPPORT_ADMIN','PLATFORM_AUDITOR')", name="ck_platform_role"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class OrganizationControl(Base):
    __tablename__ = "organization_controls"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    notice: Mapped[str | None] = mapped_column(String(300), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class AccountControl(Base):
    __tablename__ = "platform_account_controls"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    expires_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("organization_id", "id"), UniqueConstraint("organization_id", "name"),
                      ForeignKeyConstraint(["organization_id", "owner_id"], ["organization_memberships.organization_id", "organization_memberships.user_id"]),
                      Index("ix_team_directory", "organization_id", "archived", "name", "id"))
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "team_id"], ["teams.organization_id", "teams.id"]),
        ForeignKeyConstraint(["organization_id", "user_id"], ["organization_memberships.organization_id", "organization_memberships.user_id"]),
        CheckConstraint("role IN ('MEMBER','ADMIN')", name="ck_team_role"),
        Index("ix_team_member_user", "organization_id", "user_id", "team_id"),
    )
    team_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20), default="MEMBER")
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class TeamRepository(Base):
    __tablename__ = "team_repositories"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "team_id"], ["teams.organization_id", "teams.id"]),
        Index("ix_team_repository_scope", "organization_id", "repository_id", "team_id"),
    )
    team_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))


class RepositoryControl(Base):
    __tablename__ = "repository_controls"
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    archived: Mapped[bool] = mapped_column(default=False)
    analysis_paused: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class RepositoryDenial(Base):
    __tablename__ = "repository_access_denials"
    __table_args__ = (ForeignKeyConstraint(["organization_id", "user_id"],
        ["organization_memberships.organization_id", "organization_memberships.user_id"]),)
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)


class FeaturePolicy(Base):
    __tablename__ = "feature_policies"
    __table_args__ = (
        UniqueConstraint("scope_key", "feature"), Index("ix_feature_policy_scope", "organization_id", "scope_type", "target_id"),
        CheckConstraint("decision IN ('ALLOW','DENY','INHERIT')", name="ck_feature_decision"),
        CheckConstraint("scope_type IN ('PLATFORM','ORGANIZATION','TEAM','USER','ROLE')", name="ck_feature_scope"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    scope_key: Mapped[str] = mapped_column(String(250))
    scope_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(80))
    feature: Mapped[str] = mapped_column(String(60))
    decision: Mapped[str] = mapped_column(String(20))
    mandatory: Mapped[bool] = mapped_column(default=False)
    allow_user_exceptions: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str] = mapped_column(String(500))
    changed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[str] = mapped_column(String(50), default=now)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class PolicyRevision(Base):
    __tablename__ = "feature_policy_revisions"
    __table_args__ = (UniqueConstraint("policy_id", "version"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("feature_policies.id"), index=True)
    version: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class GovernanceRevision(Base):
    __tablename__ = "governance_revisions"
    scope_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    revision: Mapped[int] = mapped_column(default=0)


class Invitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (Index("ix_invitation_directory", "organization_id", "state", "created_at", "id"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    expires_at: Mapped[str] = mapped_column(String(50))
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class AdministrativeCommand(Base):
    __tablename__ = "administrative_commands"
    __table_args__ = (UniqueConstraint("organization_id", "actor_id", "idempotency_key"),
                      Index("ix_admin_command_retention", "created_at", "id"))
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class Approval(Base):
    __tablename__ = "administrative_approvals"
    __table_args__ = (Index("ix_admin_approval_scope", "organization_id", "state", "created_at"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    data: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    expires_at: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class QuotaPolicy(Base):
    __tablename__ = "administrative_quotas"
    __table_args__ = (UniqueConstraint("scope_key", "metric"), Index("ix_admin_quota_scope", "organization_id", "scope_type", "target_id"))
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    scope_key: Mapped[str] = mapped_column(String(250))
    scope_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(80))
    metric: Mapped[str] = mapped_column(String(40))
    limit: Mapped[int]
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class ActivityEvent(Base):
    __tablename__ = "application_activity"
    __table_args__ = (
        Index("ix_activity_timeline", "organization_id", "created_at", "id"),
        Index("ix_activity_actor", "organization_id", "actor_id", "created_at", "id"),
        Index("ix_activity_action", "organization_id", "action", "created_at", "id"),
        Index("ix_activity_outcome", "organization_id", "outcome", "created_at", "id"),
        Index("ix_activity_repository", "organization_id", "repository_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(30))
    outcome: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class JobAttribution(Base):
    __tablename__ = "job_attribution"
    __table_args__ = (Index("ix_job_attribution_actor", "organization_id", "user_id", "created_at", "job_id"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("records.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class JobTeamAttribution(Base):
    """Prospective submission-time membership, never inferred from current teams."""
    __tablename__ = "job_team_attribution"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "team_id"], ["teams.organization_id", "teams.id"]),
        Index("ix_job_team_usage", "organization_id", "team_id", "created_at", "job_id"),
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("records.id"), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class Notification(Base):
    __tablename__ = "administrative_notifications"
    __table_args__ = (Index("ix_admin_notifications", "organization_id", "user_id", "read_at", "created_at"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    read_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PolicyPreview(Base):
    __tablename__ = "administrative_policy_previews"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_digest: Mapped[str] = mapped_column(String(64))
    decision_version: Mapped[str] = mapped_column(String(100))
    affected_count: Mapped[int]
    expires_at: Mapped[str] = mapped_column(String(50))
