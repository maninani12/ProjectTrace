"""Private generation ownership, receipts and atomic publication pointer."""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    # Additive tables and indexes; legacy rows and columns are untouched.
    op.create_index('uq_audits_generation_scope', 'audit_events', ['id', 'organization_id', 'repository_id'], unique=True)
    op.create_index('uq_activity_generation_scope', 'application_activity', ['id', 'organization_id', 'repository_id'], unique=True)
    op.create_table('analysis_generations',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('job_id', sa.String(length=80), nullable=False),
    sa.Column('signature', sa.String(length=64), nullable=False),
    sa.Column('content_key', sa.String(length=64), nullable=False),
    sa.Column('inventory_id', sa.String(length=80), nullable=False),
    sa.Column('branch', sa.String(length=200), nullable=False),
    sa.Column('expected_pointer_revision', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('snapshot_id', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.String(length=50), nullable=False),
    sa.Column('expires_at', sa.String(length=50), nullable=False),
    sa.Column('published_at', sa.String(length=50), nullable=True),
    sa.Column('validation_digest', sa.String(length=64), nullable=True),
    sa.Column('validation_records', sa.Integer(), nullable=True),
    sa.CheckConstraint("state IN ('STAGING','VALIDATED','PUBLISHED','ABANDONED')", name='ck_generation_state'),
    sa.ForeignKeyConstraint(['inventory_id', 'organization_id', 'repository_id'], ['source_inventories.id', 'source_inventories.organization_id', 'source_inventories.repository_id'], ),
    sa.ForeignKeyConstraint(['job_id', 'organization_id', 'repository_id'], ['records.id', 'records.organization_id', 'records.repository_id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ),
    sa.ForeignKeyConstraint(['snapshot_id', 'organization_id', 'repository_id'], ['records.id', 'records.organization_id', 'records.repository_id'], ),
    sa.ForeignKeyConstraint(['snapshot_id'], ['records.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organization_id', 'repository_id'),
    sa.UniqueConstraint('job_id', 'signature')
    )
    op.create_index('ix_generations_recovery', 'analysis_generations', ['state', 'expires_at'], unique=False)
    op.create_table('generation_records',
    sa.Column('record_id', sa.String(length=80), nullable=False),
    sa.Column('generation_id', sa.String(length=80), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('stage', sa.String(length=40), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id', 'organization_id', 'repository_id'], ['analysis_generations.id', 'analysis_generations.organization_id', 'analysis_generations.repository_id'], ),
    sa.ForeignKeyConstraint(['record_id', 'organization_id', 'repository_id'], ['records.id', 'records.organization_id', 'records.repository_id'], ),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('generation_id', 'stage', 'ordinal')
    )
    op.create_index('ix_generation_records_stage', 'generation_records', ['generation_id', 'stage', 'ordinal'], unique=False)
    op.create_table('generation_receipts',
    sa.Column('generation_id', sa.String(length=80), nullable=False),
    sa.Column('stage', sa.String(length=40), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('dependency_digest', sa.String(length=64), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('record_count', sa.Integer(), nullable=False),
    sa.Column('completed_at', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['generation_id', 'organization_id', 'repository_id'], ['analysis_generations.id', 'analysis_generations.organization_id', 'analysis_generations.repository_id'], ),
    sa.PrimaryKeyConstraint('generation_id', 'stage')
    )
    op.create_table('generation_chunks',
    sa.Column('generation_id', sa.String(length=80), nullable=False),
    sa.Column('stage', sa.String(length=40), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('ciphertext', sa.Text(), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['generation_id', 'organization_id', 'repository_id'], ['analysis_generations.id', 'analysis_generations.organization_id', 'analysis_generations.repository_id'], ),
    sa.PrimaryKeyConstraint('generation_id', 'stage', 'ordinal')
    )
    op.create_table('generation_audits',
    sa.Column('event_id', sa.String(length=80), nullable=False),
    sa.Column('activity_id', sa.String(length=80), nullable=False),
    sa.Column('generation_id', sa.String(length=80), nullable=False),
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['activity_id', 'organization_id', 'repository_id'], ['application_activity.id', 'application_activity.organization_id', 'application_activity.repository_id'], ),
    sa.ForeignKeyConstraint(['activity_id'], ['application_activity.id'], ),
    sa.ForeignKeyConstraint(['event_id', 'organization_id', 'repository_id'], ['audit_events.id', 'audit_events.organization_id', 'audit_events.repository_id'], ),
    sa.ForeignKeyConstraint(['event_id'], ['audit_events.id'], ),
    sa.ForeignKeyConstraint(['generation_id', 'organization_id', 'repository_id'], ['analysis_generations.id', 'analysis_generations.organization_id', 'analysis_generations.repository_id'], ),
    sa.PrimaryKeyConstraint('event_id'),
    sa.UniqueConstraint('activity_id')
    )
    op.create_index(op.f('ix_generation_audits_generation_id'), 'generation_audits', ['generation_id'], unique=False)
    op.create_table('published_generations',
    sa.Column('organization_id', sa.String(length=80), nullable=False),
    sa.Column('repository_id', sa.String(length=80), nullable=False),
    sa.Column('branch', sa.String(length=200), nullable=False),
    sa.Column('generation_id', sa.String(length=80), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id', 'organization_id', 'repository_id'], ['analysis_generations.id', 'analysis_generations.organization_id', 'analysis_generations.repository_id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ),
    sa.PrimaryKeyConstraint('organization_id', 'repository_id', 'branch')
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM analysis_generations")).scalar():
        raise RuntimeError("Generation data must be preserved; populated generation downgrade requires operator migration.")
    op.drop_table('published_generations')
    op.drop_table('generation_audits')
    op.drop_table('generation_chunks')
    op.drop_table('generation_receipts')
    op.drop_table('generation_records')
    op.drop_table('analysis_generations')
    op.drop_index('uq_activity_generation_scope', table_name='application_activity')
    op.drop_index('uq_audits_generation_scope', table_name='audit_events')
