"""Tenant-scoped encrypted content references and reusable parser artifacts."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_blobs",
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("bytes", sa.Integer(), nullable=False),
    )
    op.create_table(
        "source_inventories",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.UniqueConstraint("id", "organization_id", "repository_id"),
    )
    for field in ("organization_id", "repository_id"):
        op.create_index("ix_source_inventories_" + field, "source_inventories", [field])
    op.create_table(
        "source_inventory_files",
        sa.Column("inventory_id", sa.String(80), primary_key=True),
        sa.Column("path", sa.String(240), primary_key=True),
        sa.Column("organization_id", sa.String(80), nullable=False),
        sa.Column("repository_id", sa.String(80), nullable=False),
        sa.Column("digest", sa.String(64), nullable=True),
        sa.Column("component", sa.String(200), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["inventory_id", "organization_id", "repository_id"],
            ["source_inventories.id", "source_inventories.organization_id", "source_inventories.repository_id"],
        ),
        sa.ForeignKeyConstraint(["organization_id", "digest"], ["source_blobs.organization_id", "source_blobs.digest"]),
    )
    op.create_index(
        "ix_source_files_scoped_component",
        "source_inventory_files",
        ["organization_id", "repository_id", "inventory_id", "component"],
    )
    op.create_table(
        "snapshot_inventories",
        sa.Column("snapshot_id", sa.String(80), sa.ForeignKey("records.id"), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("inventory_id", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(
            ["inventory_id", "organization_id", "repository_id"],
            ["source_inventories.id", "source_inventories.organization_id", "source_inventories.repository_id"],
        ),
    )
    op.create_table(
        "parser_artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(80), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("language", sa.String(80), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
    )
    op.create_index(
        "ix_parser_artifact_scope", "parser_artifacts", ["organization_id", "content_hash", "parser_version"]
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM snapshot_inventories")).scalar():
        raise RuntimeError(
            "Snapshots retain encrypted content references; export or restore their original release before downgrading content storage."
        )
    for table in (
        "parser_artifacts",
        "snapshot_inventories",
        "source_inventory_files",
        "source_inventories",
        "source_blobs",
    ):
        op.drop_table(table)
