"""Explicit initial schema; no production create_all dependency."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
    )
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("system", sa.String(200), nullable=False),
        sa.Column("component", sa.String(200), nullable=False),
        sa.Column("owner", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_id", sa.String(100)),
    )
    op.create_table(
        "repository_grants",
        sa.Column("user_id", sa.String(80), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), primary_key=True),
    )
    op.create_table(
        "sessions",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(80), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("csrf", sa.String(100), nullable=False),
        sa.Column("expires", sa.Float, nullable=False),
    )
    op.create_table(
        "records",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), index=True),
        sa.Column("kind", sa.String(40), nullable=False, index=True),
        sa.Column("natural_key", sa.String(250), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.UniqueConstraint("organization_id", "kind", "natural_key"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), index=True),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("received_at", sa.String(50), nullable=False),
    )


def downgrade():
    for table in [
        "webhook_deliveries",
        "audit_events",
        "records",
        "sessions",
        "repository_grants",
        "repositories",
        "users",
        "organizations",
    ]:
        op.drop_table(table)
