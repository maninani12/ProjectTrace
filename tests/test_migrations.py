import os
import sqlite3
import subprocess
import sys


def test_migrations_upgrade_rollback_and_constraints(tmp_path):
    database = tmp_path / "migrations.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database).replace("\\", "/")}
    for revision in ["head", "base", "head"]:
        command = "downgrade" if revision == "base" else "upgrade"
        subprocess.run([sys.executable, "-m", "alembic", command, revision], env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003"
        assert "ix_records_scoped_current" in {r[1] for r in db.execute("PRAGMA index_list(records)")}
        assert "uq_provider_repository" in {r[1] for r in db.execute("PRAGMA index_list(repositories)")}
