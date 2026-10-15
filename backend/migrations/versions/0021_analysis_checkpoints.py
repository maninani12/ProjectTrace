"""Retain completed global computation privately across publication retries."""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uq_records_checkpoint_scope", "records", ["id", "organization_id", "repository_id"], unique=True)
    op.create_table(
        "analysis_checkpoints",
        sa.Column("job_id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(50), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["job_id", "organization_id", "repository_id"],
                                ["records.id", "records.organization_id", "records.repository_id"],
                                ondelete="CASCADE", name="fk_checkpoint_job_scope"),
    )
    op.create_index("ix_analysis_checkpoints_organization_id", "analysis_checkpoints", ["organization_id"])
    op.create_index("ix_analysis_checkpoints_repository_id", "analysis_checkpoints", ["repository_id"])
    op.create_index("ix_analysis_checkpoints_expires_at", "analysis_checkpoints", ["expires_at"])


def downgrade():
    op.drop_table("analysis_checkpoints")
    op.drop_index("uq_records_checkpoint_scope", table_name="records")
