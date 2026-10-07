"""Add structural finding lineage without rewriting legacy records."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "finding_identities",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("introduced_snapshot_id", sa.String(80), sa.ForeignKey("records.id"), nullable=False),
        sa.Column("rule", sa.String(100), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
    )
    op.create_table(
        "finding_occurrences",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("identity_id", sa.String(80), sa.ForeignKey("finding_identities.id"), nullable=False),
        sa.Column("snapshot_id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
    )
    for table, columns in {
        "finding_identities": ("organization_id", "repository_id"),
        "finding_occurrences": ("organization_id", "repository_id", "identity_id", "snapshot_id", "finding_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_finding_history_scope",
        "finding_occurrences",
        ["organization_id", "repository_id", "identity_id", "created_at"],
    )


def downgrade():
    op.drop_table("finding_occurrences")
    op.drop_table("finding_identities")
