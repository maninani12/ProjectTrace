"""Encrypted expiring worker inputs, additive to existing records.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analysis_inputs",
        sa.Column("job_id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.String(50), nullable=False),
    )
    op.create_index("ix_analysis_inputs_organization_id", "analysis_inputs", ["organization_id"])
    op.create_index("ix_analysis_inputs_repository_id", "analysis_inputs", ["repository_id"])


def downgrade():
    op.drop_table("analysis_inputs")
