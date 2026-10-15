"""Scoped learning journeys, objectives, encrypted assessments and reviews."""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    # Additive learning data; captured source and previous records are preserved.
    op.create_table('learning_journeys',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('source_repository_id', sa.String(length=80), nullable=True),
    sa.Column('snapshot_id', sa.String(length=80), nullable=False),
    sa.Column('team_id', sa.String(length=80), nullable=True),
    sa.Column('participant_id', sa.String(length=80), nullable=False),
    sa.Column('mentor_id', sa.String(length=80), nullable=False),
    sa.Column('manager_id', sa.String(length=80), nullable=False),
    sa.Column('request_key', sa.String(length=80), nullable=False),
    sa.Column('mode', sa.String(length=30), nullable=False),
    sa.Column('role', sa.String(length=30), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.String(length=50), nullable=False),
    sa.Column('expires_at', sa.String(length=50), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint("(mode='NEW_HIRE' AND source_repository_id IS NULL) OR (mode='INTERNAL_TRANSFER' AND source_repository_id IS NOT NULL AND source_repository_id<>repository_id)", name='ck_learning_source_mode'),
    sa.CheckConstraint("mode IN ('NEW_HIRE','INTERNAL_TRANSFER')", name='ck_learning_mode'),
    sa.CheckConstraint("state IN ('ACTIVE','COMPLETED','REFRESH_REQUIRED')", name='ck_learning_state'),
    sa.CheckConstraint('participant_id<>mentor_id AND participant_id<>manager_id AND mentor_id<>manager_id', name='ck_learning_independent_review'),
    sa.ForeignKeyConstraint(['organization_id', 'manager_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id'], ),
    sa.ForeignKeyConstraint(['organization_id', 'mentor_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id'], ),
    sa.ForeignKeyConstraint(['organization_id', 'participant_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id'], ),
    sa.ForeignKeyConstraint(['organization_id', 'team_id'], ['teams.organization_id', 'teams.id'], ),
    sa.ForeignKeyConstraint(['repository_id', 'organization_id'], ['repositories.id', 'repositories.organization_id'], ),
    sa.ForeignKeyConstraint(['snapshot_id', 'organization_id', 'repository_id'], ['records.id', 'records.organization_id', 'records.repository_id'], ),
    sa.ForeignKeyConstraint(['source_repository_id', 'organization_id'], ['repositories.id', 'repositories.organization_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organization_id', 'repository_id'),
    sa.UniqueConstraint('organization_id', 'participant_id', 'request_key')
    )
    op.create_index('ix_learning_participants', 'learning_journeys', ['organization_id', 'participant_id', 'created_at'], unique=False)
    op.create_table('learning_objectives',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('journey_id', sa.String(length=80), nullable=False),
    sa.Column('snapshot_id', sa.String(length=80), nullable=False),
    sa.Column('record_id', sa.String(length=80), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint("state IN ('ASSIGNED','SUBMITTED','APPROVED','CHANGES_REQUESTED')", name='ck_learning_objective_state'),
    sa.ForeignKeyConstraint(['journey_id', 'organization_id', 'repository_id'], ['learning_journeys.id', 'learning_journeys.organization_id', 'learning_journeys.repository_id'], ),
    sa.ForeignKeyConstraint(['record_id', 'organization_id', 'repository_id'], ['records.id', 'records.organization_id', 'records.repository_id'], ),
    sa.ForeignKeyConstraint(['snapshot_id', 'organization_id', 'repository_id'], ['records.id', 'records.organization_id', 'records.repository_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organization_id', 'repository_id'),
    sa.UniqueConstraint('journey_id', 'revision', 'record_id')
    )
    op.create_index('ix_learning_objective_revision', 'learning_objectives', ['journey_id', 'revision', 'state'], unique=False)
    op.create_table('learning_assessments',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('objective_id', sa.String(length=80), nullable=False),
    sa.Column('participant_id', sa.String(length=80), nullable=False),
    sa.Column('ciphertext', sa.Text(), nullable=False),
    sa.Column('evidence_ids', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['objective_id', 'organization_id', 'repository_id'], ['learning_objectives.id', 'learning_objectives.organization_id', 'learning_objectives.repository_id'], ),
    sa.ForeignKeyConstraint(['organization_id', 'participant_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_learning_assessment_objective', 'learning_assessments', ['objective_id', 'created_at', 'id'], unique=False)
    op.create_table('learning_reviews',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('journey_id', sa.String(length=80), nullable=False),
    sa.Column('objective_id', sa.String(length=80), nullable=True),
    sa.Column('reviewer_id', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('decision', sa.String(length=30), nullable=False),
    sa.Column('ciphertext', sa.Text(), nullable=False),
    sa.Column('created_at', sa.String(length=50), nullable=False),
    sa.CheckConstraint("kind IN ('MENTOR','MANAGER')", name='ck_learning_review_kind'),
    sa.ForeignKeyConstraint(['journey_id', 'organization_id', 'repository_id'], ['learning_journeys.id', 'learning_journeys.organization_id', 'learning_journeys.repository_id'], ),
    sa.ForeignKeyConstraint(['objective_id', 'organization_id', 'repository_id'], ['learning_objectives.id', 'learning_objectives.organization_id', 'learning_objectives.repository_id'], ),
    sa.ForeignKeyConstraint(['organization_id', 'reviewer_id'], ['organization_memberships.organization_id', 'organization_memberships.user_id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM learning_journeys")).scalar():
        raise RuntimeError("Populated learning history must be preserved; use an operator-reviewed migration.")
    op.drop_table('learning_reviews')
    op.drop_table('learning_assessments')
    op.drop_table('learning_objectives')
    op.drop_table('learning_journeys')
