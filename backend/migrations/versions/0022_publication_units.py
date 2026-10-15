"""Private bounded publication preparation units."""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("publication_units",
        sa.Column("job_id", sa.String(80), primary_key=True),
        sa.Column("unit_key", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("dependency_key", sa.String(64), nullable=True),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["job_id", "organization_id", "repository_id"],
            ["records.id", "records.organization_id", "records.repository_id"],
            ondelete="CASCADE", name="fk_publication_unit_job_scope"))
    op.create_index("ix_publication_units_expiry", "publication_units", ["expires_at"])


def downgrade():
    op.drop_table("publication_units")
