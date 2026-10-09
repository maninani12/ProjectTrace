"""Bounded published snapshot metadata without reading repository-sized caches."""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "snapshot_views",
        sa.Column("snapshot_id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    for field in ("organization_id", "repository_id"):
        op.create_index("ix_snapshot_views_" + field, "snapshot_views", [field])


def downgrade():
    op.drop_table("snapshot_views")
