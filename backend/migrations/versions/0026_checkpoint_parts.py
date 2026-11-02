"""Add encrypted checkpoint pages without changing legacy receipt rows."""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analysis_checkpoints", sa.Column("format_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_table("analysis_checkpoint_parts",
        sa.Column("job_id", sa.String(80), primary_key=True),
        sa.Column("attempt", sa.String(36), primary_key=True),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["job_id", "organization_id", "repository_id"],
            ["records.id", "records.organization_id", "records.repository_id"],
            ondelete="CASCADE", name="fk_checkpoint_part_job_scope"))
    op.create_index("ix_checkpoint_parts_expiry", "analysis_checkpoint_parts", ["expires_at"])
    op.add_column("generation_receipts", sa.Column("format_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_table("generation_context_parts",
        sa.Column("generation_id", sa.String(80), primary_key=True),
        sa.Column("stage", sa.String(40), primary_key=True),
        sa.Column("attempt", sa.String(36), primary_key=True),
        sa.Column("collection", sa.Integer(), primary_key=True),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(80), nullable=False),
        sa.Column("repository_id", sa.String(80), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["generation_id", "organization_id", "repository_id"],
            ["analysis_generations.id", "analysis_generations.organization_id", "analysis_generations.repository_id"]))
    op.create_index("ix_generation_context_expiry", "generation_context_parts", ["expires_at"])


def downgrade():
    connection = op.get_bind()
    if (connection.execute(sa.text("SELECT count(*) FROM analysis_checkpoint_parts")).scalar()
            or connection.execute(sa.text("SELECT count(*) FROM analysis_checkpoints WHERE format_version=2")).scalar()
            or connection.execute(sa.text("SELECT count(*) FROM generation_context_parts")).scalar()
            or connection.execute(sa.text("SELECT count(*) FROM generation_receipts WHERE format_version=2")).scalar()):
        raise RuntimeError("Retained paged checkpoints must complete or expire before downgrade.")
    op.drop_table("analysis_checkpoint_parts")
    op.drop_column("analysis_checkpoints", "format_version")
    op.drop_table("generation_context_parts")
    op.drop_column("generation_receipts", "format_version")
