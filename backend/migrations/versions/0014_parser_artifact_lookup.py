"""Match tenant-private cache lookup predicates without scanning a tenant's cache."""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_parser_artifact_lookup", "parser_artifacts", ["organization_id", "id"])


def downgrade():
    op.drop_index("ix_parser_artifact_lookup", table_name="parser_artifacts")
