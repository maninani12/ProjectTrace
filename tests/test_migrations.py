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
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0026"
        assert "ix_checkpoint_parts_expiry" in {r[1] for r in db.execute("PRAGMA index_list(analysis_checkpoint_parts)")}
        assert db.execute("PRAGMA foreign_key_list(analysis_checkpoint_parts)").fetchall()
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


@pytest.mark.parametrize("retained", ["manifest", "staging_pages", "generation_manifest", "generation_pages"])
def test_checkpoint_upgrade_preserves_legacy_and_refuses_unsafe_downgrade(tmp_path, retained):
    database = tmp_path / "checkpoint-upgrade.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database).replace("\\", "/")}
    def migrate(command, revision, *, check=True):
        return subprocess.run([sys.executable, "-m", "alembic", command, revision], env=env,
                              check=check, capture_output=True, text=True)
    migrate("upgrade", "0025")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO organizations VALUES ('owned','Owned')")
        db.execute("INSERT INTO repositories(id,organization_id,name,system,component,owner,provider) VALUES ('repo','owned','Owned','Owned','Owned','Owned','LOCAL')")
        db.execute("INSERT INTO records(id,organization_id,repository_id,kind,natural_key,data,created_at,version) VALUES ('job','owned','repo','job','owned-job','{}','2026-01-01',1)")
        db.execute("INSERT INTO analysis_checkpoints VALUES ('job','owned','repo',? ,? ,'2099-01-01','opaque-legacy-ciphertext','2026-01-01')", ("a"*64,"b"*64))
        db.execute("INSERT INTO analysis_generations(id,organization_id,repository_id,job_id,signature,content_key,inventory_id,branch,expected_pointer_revision,state,created_at,expires_at) VALUES ('generation','owned','repo','job','signature','content','inventory','main',0,'STAGING','2026-01-01','2099-01-01')")
        db.execute("INSERT INTO generation_receipts VALUES ('generation','SNAPSHOT','owned','repo','dependency','digest',1,0,'2026-01-01')")
        db.execute("INSERT INTO generation_chunks VALUES ('generation','SNAPSHOT',0,'owned','repo','opaque-legacy-generation','digest')")
        original = db.execute("SELECT * FROM analysis_checkpoints").fetchone()
        old_receipt = db.execute("SELECT * FROM generation_receipts").fetchone()
    migrate("upgrade", "head")
    with sqlite3.connect(database) as db:
        upgraded = db.execute("SELECT * FROM analysis_checkpoints").fetchone()
        assert upgraded[:-1] == original and upgraded[-1] == 1
        upgraded_receipt = db.execute("SELECT * FROM generation_receipts").fetchone()
        assert upgraded_receipt[:-1] == old_receipt and upgraded_receipt[-1] == 1
        assert db.execute("SELECT ciphertext FROM generation_chunks").fetchone() == ("opaque-legacy-generation",)
        if retained == "manifest":
            db.execute("UPDATE analysis_checkpoints SET format_version=2")
        elif retained == "staging_pages":
            db.execute("INSERT INTO analysis_checkpoint_parts VALUES ('job','owned-attempt',0,'owned','repo','opaque-page',?,'2099-01-01')", ("c"*64,))
        elif retained == "generation_manifest":
            db.execute("UPDATE generation_receipts SET format_version=2")
        else:
            db.execute("INSERT INTO generation_context_parts VALUES ('generation','SNAPSHOT','owned-attempt',0,0,'owned','repo','opaque-page',?,'2099-01-01')", ("d"*64,))
    blocked = migrate("downgrade", "0025", check=False)
    assert blocked.returncode != 0 and "Retained paged checkpoints" in blocked.stderr
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0026",)
        assert db.execute("SELECT ciphertext FROM analysis_checkpoints").fetchone() == ("opaque-legacy-ciphertext",)
        db.execute("DELETE FROM analysis_checkpoint_parts")
        db.execute("UPDATE analysis_checkpoints SET format_version=1")
        db.execute("DELETE FROM generation_context_parts")
        db.execute("UPDATE generation_receipts SET format_version=1")
    migrate("downgrade", "0025")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM analysis_checkpoints").fetchone() == original
        assert db.execute("SELECT * FROM generation_receipts").fetchone() == old_receipt
        assert db.execute("SELECT ciphertext FROM generation_chunks").fetchone() == ("opaque-legacy-generation",)

