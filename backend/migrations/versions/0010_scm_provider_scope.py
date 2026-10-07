"""Retain provider identity while accommodating scoped enterprise host URLs."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("repositories") as batch:
        batch.alter_column("provider_id", existing_type=sa.String(100), type_=sa.String(600), existing_nullable=True)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM repositories WHERE LENGTH(provider_id) > 100")).scalar():
        raise RuntimeError("Enterprise provider identities exceed the old column limit; preserve or migrate them before downgrade.")
    with op.batch_alter_table("repositories") as batch:
        batch.alter_column("provider_id", existing_type=sa.String(600), type_=sa.String(100), existing_nullable=True)
