"""Scoped quality projections; existing source, graph and reviews are preserved."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quality_analyses",
        sa.Column("snapshot_id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("branch", sa.String(200), nullable=False),
        sa.Column("analyzer_version", sa.String(40), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_table(
        "quality_occurrences",
        sa.Column("finding_id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("snapshot_id", sa.String(80), sa.ForeignKey("records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        *[
            sa.Column(k, sa.String(n), nullable=False)
            for k, n in [
                ("fingerprint", 64),
                ("rule", 50),
                ("path", 240),
                ("symbol", 500),
                ("language", 40),
                ("dimension", 40),
                ("severity", 20),
                ("delta", 30),
            ]
        ],
        sa.UniqueConstraint("snapshot_id", "fingerprint"),
    )
    for table, fields in [
        ("quality_analyses", ["organization_id", "repository_id", "branch"]),
        (
            "quality_occurrences",
            [
                "snapshot_id",
                "organization_id",
                "repository_id",
                "fingerprint",
                "rule",
                "path",
                "language",
                "dimension",
                "severity",
                "delta",
            ],
        ),
    ]:
        for field in fields:
            op.create_index(f"ix_{table}_{field}", table, [field])
    op.create_index(
        "ix_quality_scoped_rule", "quality_occurrences", ["organization_id", "repository_id", "snapshot_id", "rule"]
    )


def downgrade():
    op.drop_table("quality_occurrences")
    op.drop_table("quality_analyses")
