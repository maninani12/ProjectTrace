"""A provider repository cannot be attached to conflicting tenant scopes."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uq_provider_repository", "repositories", ["provider", "provider_id"], unique=True)


def downgrade():
    op.drop_index("uq_provider_repository", table_name="repositories")
