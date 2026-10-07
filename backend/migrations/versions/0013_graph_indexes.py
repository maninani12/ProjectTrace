"""Index authorized snapshot graph pages and endpoint neighborhoods."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    data = sa.column("data", sa.JSON())
    op.create_index(
        "ix_records_graph_snapshot",
        "records",
        ["organization_id", "repository_id", "kind", data["scope"]["snapshot_id"].as_string()],
    )
    for endpoint in ("source", "target"):
        op.create_index(
            "ix_records_graph_" + endpoint,
            "records",
            ["organization_id", "repository_id", "kind", data["snapshot_id"].as_string(), data[endpoint].as_string()],
        )


def downgrade():
    for name in ("snapshot", "source", "target"):
        op.drop_index("ix_records_graph_" + name, table_name="records")
