"""Cover version-checked snapshot reads without traversing large JSON payloads."""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_records_snapshot_identity", "records", ["organization_id", "repository_id", "created_at", "id", "version"],
                    sqlite_where=sa.column("kind") == "snapshot", postgresql_where=sa.column("kind") == "snapshot")


def downgrade():
    op.drop_index("ix_records_snapshot_identity", table_name="records")
