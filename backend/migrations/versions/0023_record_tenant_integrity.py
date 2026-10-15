"""Enforce Record repository tenancy on direct SQL without rebuilding SQLite records."""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    invalid = bind.execute(sa.text("SELECT r.id FROM records r LEFT JOIN repositories p ON p.id=r.repository_id "
        "WHERE r.repository_id IS NOT NULL AND (p.id IS NULL OR r.organization_id<>p.organization_id) LIMIT 1")).first()
    if invalid:
        raise RuntimeError("Existing cross-tenant Record relationships require operator review; no data was rewritten.")
    op.create_index("uq_repositories_tenant_scope", "repositories", ["id", "organization_id"], unique=True)
    if bind.dialect.name == "postgresql":
        op.create_foreign_key("fk_records_repository_scope", "records", "repositories",
                              ["repository_id", "organization_id"], ["id", "organization_id"])
    elif bind.dialect.name == "sqlite":
        # ALTER TABLE cannot add a SQLite FK. Triggers enforce both sides without
        # copying/dropping records or losing existing expression indexes.
        for action, suffix in [("INSERT", "insert"), ("UPDATE OF repository_id, organization_id", "update")]:
            op.execute(sa.text(f"CREATE TRIGGER records_tenant_{suffix} BEFORE {action} ON records "
                "WHEN NEW.repository_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM repositories "
                "WHERE id=NEW.repository_id AND organization_id=NEW.organization_id) "
                "BEGIN SELECT RAISE(ABORT,'Cross-tenant Record repository scope rejected'); END"))
        op.execute(sa.text("CREATE TRIGGER repositories_tenant_update BEFORE UPDATE OF organization_id ON repositories "
            "WHEN NEW.organization_id<>OLD.organization_id AND EXISTS (SELECT 1 FROM records "
            "WHERE repository_id=OLD.id AND organization_id<>NEW.organization_id) "
            "BEGIN SELECT RAISE(ABORT,'Repository tenant reassignment would orphan Record scope'); END"))
    else:
        raise RuntimeError("Record tenant integrity requires a supported database adapter.")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_records_repository_scope", "records", type_="foreignkey")
    else:
        for name in ["records_tenant_insert", "records_tenant_update", "repositories_tenant_update"]:
            op.execute(sa.text("DROP TRIGGER " + name))
    op.drop_index("uq_repositories_tenant_scope", table_name="repositories")
