"""Bounded graph node-class pages, including their stable ID ordering."""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    data = sa.column("data", sa.JSON())
    op.create_index("ix_records_graph_class", "records", ["organization_id", "repository_id", "kind",
                    data["scope"]["snapshot_id"].as_string(), data["class"].as_string(), "id"])


def downgrade():
    op.drop_index("ix_records_graph_class", table_name="records")
