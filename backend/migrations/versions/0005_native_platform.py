"""Additive native profiles, typed inventory and PostgreSQL claim search.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "native_profiles",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=True),
        sa.Column("scope_key", sa.String(80), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("organization_id", "scope_key"),
    )
    op.create_table(
        "cloud_assets",
        sa.Column("id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("snapshot_id", sa.String(80), sa.ForeignKey("records.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(500), nullable=False),
        sa.Column("asset_kind", sa.String(120), nullable=False),
        sa.Column("exposure", sa.String(60), nullable=False),
        sa.Column("encryption", sa.String(60), nullable=False),
        sa.Column("observed_at", sa.String(50), nullable=False),
    )
    for table, fields in [
        ("native_profiles", ["organization_id", "repository_id"]),
        ("cloud_assets", ["organization_id", "repository_id", "snapshot_id"]),
    ]:
        for field in fields:
            op.create_index(f"ix_{table}_{field}", table, [field])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_records_claim_search ON records USING gin (to_tsvector('english', coalesce(data->>'text', '') || ' ' || coalesce(data->>'category', ''))) WHERE kind = 'claim'"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_records_claim_search")
    op.drop_table("cloud_assets")
    op.drop_table("native_profiles")
