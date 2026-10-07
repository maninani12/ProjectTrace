"""Additive tenant policy, audit integrity and explicit OIDC membership."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    # Freeze this revision's schema; later ORM changes must not alter old upgrades.
    op.create_table(
        "tenant_policies",
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "audit_heads",
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
    )
    op.create_table(
        "audit_links",
        sa.Column("event_id", sa.String(80), sa.ForeignKey("audit_events.id"), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("previous_digest", sa.String(64), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.UniqueConstraint("organization_id", "sequence"),
    )
    op.create_index("ix_audit_links_organization_id", "audit_links", ["organization_id"])
    op.create_table(
        "oidc_subjects",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(250), nullable=False),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.String(80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("issuer", "subject"),
    )
    op.create_index("ix_oidc_subjects_organization_id", "oidc_subjects", ["organization_id"])
    op.create_table(
        "oidc_attempts",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("expires", sa.Float(), nullable=False),
    )
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("oidc_subject_id", sa.String(80), nullable=True))
        batch.create_foreign_key("fk_sessions_oidc_subject_id", "oidc_subjects", ["oidc_subject_id"], ["id"])


def downgrade():
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("fk_sessions_oidc_subject_id", type_="foreignkey")
        batch.drop_column("oidc_subject_id")
    for table in ("oidc_attempts", "oidc_subjects", "audit_links", "audit_heads", "tenant_policies"):
        op.drop_table(table)
