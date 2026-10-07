"""Add disabled-user controls and bind OIDC attempts to organization/configuration."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("users", sa.Column("local_login_allowed", sa.Boolean(), server_default=sa.true(), nullable=False))
    with op.batch_alter_table("oidc_attempts") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(80), nullable=True))
        batch.add_column(sa.Column("configuration_hash", sa.String(64), nullable=True))
        batch.create_foreign_key("fk_oidc_attempt_organization", "organizations", ["organization_id"], ["id"])


def downgrade():
    # Do not permit disabled/OIDC-only accounts to become valid local passwords during downgrade.
    connection = op.get_bind()
    unsafe = connection.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE enabled = false OR local_login_allowed = false")
    ).scalar()
    if unsafe:
        raise RuntimeError(
            "Restore or remove disabled/OIDC-only accounts explicitly before downgrading account controls."
        )
    with op.batch_alter_table("oidc_attempts") as batch:
        batch.drop_constraint("fk_oidc_attempt_organization", type_="foreignkey")
        batch.drop_column("configuration_hash")
        batch.drop_column("organization_id")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("local_login_allowed")
        batch.drop_column("enabled")
