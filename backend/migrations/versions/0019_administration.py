"""Add scoped administration without rewriting identities, evidence or audit history."""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_audit_tenant_timeline', 'audit_events', ['organization_id','created_at','id'], unique=False)
    op.create_table('platform_account_controls',
        sa.Column('user_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.String(length=50), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_table('governance_revisions',
        sa.Column('scope_key', sa.String(length=100), primary_key=True, nullable=False),
        sa.Column('revision', sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_table('administrative_quotas',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('scope_key', sa.String(length=250), primary_key=False, nullable=False),
        sa.Column('scope_type', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('target_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('metric', sa.String(length=40), primary_key=False, nullable=False),
        sa.Column('limit', sa.Integer(), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.UniqueConstraint('scope_key', 'metric'),
    )
    op.create_index('ix_admin_quota_scope', 'administrative_quotas', ['organization_id', 'scope_type', 'target_id'], unique=False)
    op.create_table('organization_controls',
        sa.Column('organization_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('state', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('notice', sa.String(length=300), primary_key=False, nullable=True),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
    )
    op.create_table('administrative_approvals',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('requested_by', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('approved_by', sa.String(length=80), primary_key=False, nullable=True),
        sa.Column('action', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('data', sa.JSON(), primary_key=False, nullable=False),
        sa.Column('state', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('expires_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id']),
    )
    op.create_index('ix_admin_approval_scope', 'administrative_approvals', ['organization_id', 'state', 'created_at'], unique=False)
    op.create_table('administrative_commands',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('actor_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('idempotency_key', sa.String(length=100), primary_key=False, nullable=False),
        sa.Column('request_digest', sa.String(length=64), primary_key=False, nullable=False),
        sa.Column('result', sa.JSON(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.UniqueConstraint('organization_id', 'actor_id', 'idempotency_key'),
    )
    op.create_index('ix_admin_command_retention', 'administrative_commands', ['created_at', 'id'], unique=False)
    op.create_table('administrative_notifications',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('user_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('message', sa.String(length=500), primary_key=False, nullable=False),
        sa.Column('severity', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('target_id', sa.String(length=100), primary_key=False, nullable=True),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('read_at', sa.String(length=50), primary_key=False, nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
    )
    op.create_index('ix_admin_notifications', 'administrative_notifications', ['organization_id', 'user_id', 'read_at', 'created_at'], unique=False)
    op.create_table('administrative_policy_previews',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('actor_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('request_digest', sa.String(length=64), primary_key=False, nullable=False),
        sa.Column('decision_version', sa.String(length=100), primary_key=False, nullable=False),
        sa.Column('affected_count', sa.Integer(), primary_key=False, nullable=False),
        sa.Column('expires_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
    )
    op.create_table('application_activity',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('actor_id', sa.String(length=80), primary_key=False, nullable=True),
        sa.Column('repository_id', sa.String(length=80), primary_key=False, nullable=True),
        sa.Column('action', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('category', sa.String(length=30), primary_key=False, nullable=False),
        sa.Column('outcome', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('target_id', sa.String(length=100), primary_key=False, nullable=True),
        sa.Column('correlation_id', sa.String(length=100), primary_key=False, nullable=True),
        sa.Column('data', sa.JSON(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
    )
    op.create_index('ix_activity_action', 'application_activity', ['organization_id', 'action', 'created_at', 'id'], unique=False)
    op.create_index('ix_activity_actor', 'application_activity', ['organization_id', 'actor_id', 'created_at', 'id'], unique=False)
    op.create_index('ix_activity_repository', 'application_activity', ['organization_id', 'repository_id', 'created_at', 'id'], unique=False)
    op.create_index('ix_activity_timeline', 'application_activity', ['organization_id', 'created_at', 'id'], unique=False)
    op.create_table('feature_policies',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=True),
        sa.Column('scope_key', sa.String(length=250), primary_key=False, nullable=False),
        sa.Column('scope_type', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('target_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('feature', sa.String(length=60), primary_key=False, nullable=False),
        sa.Column('decision', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('mandatory', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('allow_user_exceptions', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('expires_at', sa.String(length=50), primary_key=False, nullable=True),
        sa.Column('reason', sa.String(length=500), primary_key=False, nullable=False),
        sa.Column('changed_by', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('changed_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.CheckConstraint("decision IN ('ALLOW','DENY','INHERIT')", name='ck_feature_decision'),
        sa.CheckConstraint("scope_type IN ('PLATFORM','ORGANIZATION','TEAM','USER','ROLE')", name='ck_feature_scope'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id']),
        sa.UniqueConstraint('scope_key', 'feature'),
    )
    op.create_index('ix_feature_policy_scope', 'feature_policies', ['organization_id', 'scope_type', 'target_id'], unique=False)
    op.create_table('organization_invitations',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('email', sa.String(length=200), primary_key=False, nullable=False),
        sa.Column('role', sa.String(length=40), primary_key=False, nullable=False),
        sa.Column('token_digest', sa.String(length=64), primary_key=False, nullable=False),
        sa.Column('state', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('expires_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('invited_by', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id']),
        sa.UniqueConstraint('token_digest'),
    )
    op.create_index('ix_invitation_directory', 'organization_invitations', ['organization_id', 'state', 'created_at', 'id'], unique=False)
    op.create_table('organization_memberships',
        sa.Column('organization_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('role', sa.String(length=40), primary_key=False, nullable=False),
        sa.Column('state', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('display_name', sa.String(length=120), primary_key=False, nullable=True),
        sa.Column('expires_at', sa.String(length=50), primary_key=False, nullable=True),
        sa.Column('reason', sa.String(length=500), primary_key=False, nullable=True),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=True),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.CheckConstraint("state IN ('ACTIVE','SUSPENDED','REMOVED')", name='ck_membership_state'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
    )
    op.create_index('ix_membership_directory', 'organization_memberships', ['organization_id', 'state', 'user_id'], unique=False)
    op.create_table('platform_operators',
        sa.Column('user_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('role', sa.String(length=40), primary_key=False, nullable=False),
        sa.Column('enabled', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.CheckConstraint("role IN ('PLATFORM_SUPER_ADMIN','PLATFORM_SUPPORT_ADMIN','PLATFORM_AUDITOR')", name='ck_platform_role'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_table('repository_controls',
        sa.Column('repository_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('archived', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('analysis_paused', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
    )
    op.create_index('ix_repository_controls_organization_id', 'repository_controls', ['organization_id'], unique=False)
    op.create_table('feature_policy_revisions',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('policy_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.Column('data', sa.JSON(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['policy_id'], ['feature_policies.id']),
        sa.UniqueConstraint('policy_id', 'version'),
    )
    op.create_index('ix_feature_policy_revisions_policy_id', 'feature_policy_revisions', ['policy_id'], unique=False)
    op.create_table('job_attribution',
        sa.Column('job_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('user_id', sa.String(length=80), primary_key=False, nullable=True),
        sa.Column('team_ids', sa.JSON(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['job_id'], ['records.id']),
    )
    op.create_index('ix_job_attribution_actor', 'job_attribution', ['organization_id', 'user_id', 'created_at', 'job_id'], unique=False)
    op.create_table('repository_access_denials',
        sa.Column('user_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('repository_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id', 'user_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id']),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
    )
    op.create_index('ix_repository_access_denials_organization_id', 'repository_access_denials', ['organization_id'], unique=False)
    op.create_table('teams',
        sa.Column('id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('name', sa.String(length=120), primary_key=False, nullable=False),
        sa.Column('owner_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('archived', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.Column('version', sa.Integer(), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['organization_id', 'owner_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.UniqueConstraint('organization_id', 'id'),
        sa.UniqueConstraint('organization_id', 'name'),
    )
    op.create_index('ix_team_directory', 'teams', ['organization_id', 'archived', 'name', 'id'], unique=False)
    op.create_table('session_contexts',
        sa.Column('digest', sa.String(length=64), primary_key=True, nullable=False),
        sa.Column('public_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=True),
        sa.Column('reauthenticated_at', sa.Double(), primary_key=False, nullable=True),
        sa.Column('assurance', sa.String(length=20), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['digest'], ['sessions.digest'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.UniqueConstraint('public_id'),
    )
    op.create_index('ix_session_contexts_organization_id', 'session_contexts', ['organization_id'], unique=False)
    op.create_table('team_memberships',
        sa.Column('team_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('role', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('created_at', sa.String(length=50), primary_key=False, nullable=False),
        sa.CheckConstraint("role IN ('MEMBER','ADMIN')", name='ck_team_role'),
        sa.ForeignKeyConstraint(['organization_id', 'user_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id']),
        sa.ForeignKeyConstraint(['organization_id', 'team_id'], ['teams.organization_id', 'teams.id']),
    )
    op.create_index('ix_team_member_user', 'team_memberships', ['organization_id', 'user_id', 'team_id'], unique=False)
    op.create_table('team_repositories',
        sa.Column('team_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('repository_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), primary_key=False, nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
        sa.ForeignKeyConstraint(['organization_id', 'team_id'], ['teams.organization_id', 'teams.id']),
    )
    op.create_index('ix_team_repository_scope', 'team_repositories', ['organization_id', 'repository_id', 'team_id'], unique=False)
    op.create_table('job_team_attribution',
        sa.Column('job_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('team_id', sa.String(length=80), primary_key=True, nullable=False),
        sa.Column('organization_id', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['records.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['organization_id', 'team_id'], ['teams.organization_id', 'teams.id']),
    )
    op.create_index('ix_job_team_usage', 'job_team_attribution', ['organization_id', 'team_id', 'created_at', 'job_id'], unique=False)
    connection = op.get_bind()
    connection.execute(sa.text("INSERT INTO organization_memberships (organization_id,user_id,role,state,version) SELECT organization_id,id,role,'ACTIVE',1 FROM users"))
    sessions = connection.execute(sa.text("SELECT s.digest,u.organization_id FROM sessions s JOIN users u ON u.id=s.user_id")).fetchall()
    contexts = sa.table("session_contexts", sa.column("digest"),sa.column("public_id"),sa.column("organization_id"),sa.column("assurance"))
    if sessions:
        connection.execute(contexts.insert(), [{"digest":digest,"public_id":str(uuid.uuid4()),"organization_id":org,"assurance":"LEGACY"} for digest,org in sessions])
    connection.execute(sa.text("INSERT INTO governance_revisions (scope_key,revision) SELECT id,0 FROM organizations"))
    connection.execute(sa.text("INSERT INTO governance_revisions (scope_key,revision) VALUES ('PLATFORM',0)"))


def downgrade():
    connection = op.get_bind()
    unsafe = connection.execute(sa.text("SELECT COUNT(*) FROM organization_memberships m JOIN users u ON u.id=m.user_id WHERE m.organization_id<>u.organization_id OR m.role<>u.role OR m.state<>'ACTIVE' OR m.expires_at IS NOT NULL")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM session_contexts c JOIN sessions s ON s.digest=c.digest JOIN users u ON u.id=s.user_id WHERE c.organization_id<>u.organization_id")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM administrative_quotas")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM organization_controls")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM administrative_approvals")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM administrative_commands")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM administrative_notifications")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM administrative_policy_previews")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM application_activity")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM feature_policies")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM organization_invitations")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM platform_operators")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM platform_account_controls")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM repository_controls")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM feature_policy_revisions")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM job_attribution")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM job_team_attribution")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM repository_access_denials")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM teams")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM team_memberships")).scalar()
    unsafe += connection.execute(sa.text("SELECT COUNT(*) FROM team_repositories")).scalar()
    if unsafe:
        raise RuntimeError("Governance data or restrictions exist; retain the schema or use a reviewed recovery bundle. Downgrade must not silently discard controls/history.")
    op.drop_index('ix_audit_tenant_timeline',table_name='audit_events')
    op.drop_table('job_team_attribution')
    op.drop_table('team_repositories')
    op.drop_table('team_memberships')
    op.drop_table('session_contexts')
    op.drop_table('teams')
    op.drop_table('repository_access_denials')
    op.drop_table('job_attribution')
    op.drop_table('feature_policy_revisions')
    op.drop_table('repository_controls')
    op.drop_table('platform_operators')
    op.drop_table('platform_account_controls')
    op.drop_table('organization_memberships')
    op.drop_table('organization_invitations')
    op.drop_table('feature_policies')
    op.drop_table('application_activity')
    op.drop_table('administrative_policy_previews')
    op.drop_table('administrative_notifications')
    op.drop_table('administrative_commands')
    op.drop_table('administrative_approvals')
    op.drop_table('organization_controls')
    op.drop_table('administrative_quotas')
    op.drop_table('governance_revisions')
