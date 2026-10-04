"""Add scoped lookup index; preserve all existing application data."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_records_scoped_current", "records", ["organization_id", "repository_id", "kind", "created_at"])


def downgrade():
    op.drop_index("ix_records_scoped_current", table_name="records")
