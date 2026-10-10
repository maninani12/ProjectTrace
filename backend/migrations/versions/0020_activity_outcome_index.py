"""Cover bounded tenant outcome counts without reading activity payloads."""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_activity_outcome", "application_activity", ["organization_id", "outcome", "created_at", "id"], unique=False)


def downgrade():
    op.drop_index("ix_activity_outcome", table_name="application_activity")
