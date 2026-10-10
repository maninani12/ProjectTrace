import os
import sqlite3
import subprocess
import sys

import pytest


def test_migrations_upgrade_rollback_and_constraints(tmp_path):
    database = tmp_path / "migrations.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database).replace("\\", "/")}
    for revision in ["head", "base", "head"]:
        command = "downgrade" if revision == "base" else "upgrade"
        subprocess.run([sys.executable, "-m", "alembic", command, revision], env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0020"
        assert "ix_activity_outcome" in {r[1] for r in db.execute("PRAGMA index_list(application_activity)")}
        assert "ix_records_graph_class" in {r[1] for r in db.execute("PRAGMA index_list(records)")}
        assert db.execute("SELECT count(*) FROM snapshot_views").fetchone()[0] == 0
        assert "ix_parser_artifact_lookup" in {r[1] for r in db.execute("PRAGMA index_list(parser_artifacts)")}
        assert "ix_records_scoped_current" in {r[1] for r in db.execute("PRAGMA index_list(records)")}
        assert "uq_provider_repository" in {r[1] for r in db.execute("PRAGMA index_list(repositories)")}


def test_quality_upgrade_preserves_previous_snapshot_profile_and_rollback(tmp_path):
    database = tmp_path / "previous-release.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database).replace("\\", "/")}

    def migrate(command, revision):
        subprocess.run([sys.executable, "-m", "alembic", command, revision], env=env, check=True, capture_output=True)

    migrate("upgrade", "0005")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO organizations VALUES ('preserved', 'Existing organization')")
        db.execute(
            "INSERT INTO repositories VALUES ('repo', 'preserved', 'Existing repository', 'System', 'Component', 'Owner', 'LOCAL', NULL)"
        )
        db.execute(
            "INSERT INTO records VALUES ('snapshot', 'preserved', 'repo', 'snapshot', 'existing', '{\"branch\":\"main\",\"findings\":[]}', '2026-10-01', 1)"
        )
        db.execute("INSERT INTO native_profiles VALUES ('profile', 'preserved', 'repo', 'repo', '{\"rules\":{}}', 3)")
        original = db.execute("SELECT * FROM records").fetchall()
    migrate("upgrade", "head")
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys=ON")
        assert db.execute("SELECT * FROM records").fetchall() == original
        assert db.execute("SELECT version FROM native_profiles").fetchone() == (3,)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO quality_analyses VALUES ('missing', 'preserved', 'repo', 'main', '1.5.0', 'hash', '{}')"
            )
    migrate("downgrade", "0005")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM records").fetchall() == original
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='quality_analyses'").fetchall()
    migrate("upgrade", "head")
