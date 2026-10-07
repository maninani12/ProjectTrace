"""Indexed queue claims, fenced leases and latest PR heads; legacy jobs remain intact."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "queue_cursor",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("last_tenant", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "queue_entries",
        sa.Column("job_id", sa.String(80), sa.ForeignKey("records.id"), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("lease_expires_at", sa.String(50), nullable=True),
        sa.Column("worker_token", sa.String(80), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("pr_key", sa.String(200), nullable=True),
        sa.Column("head_sha", sa.String(40), nullable=True),
    )
    op.create_index("ix_queue_ready", "queue_entries", ["state", "created_at", "organization_id", "repository_id"])
    op.create_index(
        "ix_queue_running_scope", "queue_entries", ["organization_id", "repository_id", "state", "lease_expires_at"]
    )
    op.create_index("ix_queue_pr", "queue_entries", ["organization_id", "repository_id", "pr_key", "state"])
    op.create_table(
        "queue_pr_heads",
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), primary_key=True),
        sa.Column("pr_key", sa.String(200), primary_key=True),
        sa.Column("job_id", sa.String(80), sa.ForeignKey("records.id"), nullable=False),
        sa.Column("head_sha", sa.String(40), nullable=False),
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM queue_entries WHERE state IN ('QUEUED','RUNNING')")).scalar():
        raise RuntimeError("Drain or cancel active queue entries before downgrading 0012.")
    op.drop_table("queue_pr_heads")
    op.drop_table("queue_entries")
    op.drop_table("queue_cursor")
