"""Small covering indexes for complete authorized claim/finding aggregates."""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

def upgrade():
    records = sa.Table("records", sa.MetaData(), sa.Column("organization_id", sa.String),
                       sa.Column("repository_id", sa.String), sa.Column("kind", sa.String), sa.Column("data", sa.JSON))
    for kind, fields in (("claim", ("status",)), ("finding", ("severity", "review_status"))):
        sa.Index("ix_records_" + kind + "_summary", records.c.organization_id, records.c.repository_id,
                 records.c.data["scope"]["snapshot_id"].as_string(), *(records.c.data[field].as_string() for field in fields),
                 sqlite_where=records.c.kind == kind, postgresql_where=records.c.kind == kind).create(op.get_bind())

def downgrade():
    op.drop_index("ix_records_finding_summary", table_name="records")
    op.drop_index("ix_records_claim_summary", table_name="records")
