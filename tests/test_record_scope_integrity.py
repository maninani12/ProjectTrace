import pytest
from sqlalchemy.exc import IntegrityError

from backend.db import Record
from tests.test_repository_store import storage  # noqa: F401


def test_record_database_rejects_cross_tenant_repository(storage):  # noqa: F811
 db,_,repo=storage
 with pytest.raises(IntegrityError):
  db.execute(Record.__table__.insert().values(id='cross-tenant',organization_id='other',repository_id=repo.id,
      kind='claim',natural_key='cross-tenant',data={}))


def test_sqlite_migration_preserves_records_and_expression_indexes(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    database = tmp_path / "scope-migration.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database).replace("\\", "/")}

    def migrate(revision):
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], env=env, check=True, capture_output=True)

    migrate("0022")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO organizations VALUES ('a','A'),('b','B')")
        db.execute("INSERT INTO repositories VALUES ('r','a','Repo','System','Component','Owner','LOCAL',NULL)")
        db.execute("INSERT INTO records VALUES ('preserved','a','r','claim','preserved','{}','2026-10-15',1)")
        before = db.execute("SELECT * FROM records").fetchall()
        indexes = db.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name='records' ORDER BY name").fetchall()
    migrate("head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM records").fetchall() == before
        assert db.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name='records' ORDER BY name").fetchall() == indexes
        with pytest.raises(sqlite3.IntegrityError, match="Cross-tenant Record"):
            db.execute("INSERT INTO records VALUES ('bad','b','r','claim','bad','{}','2026-10-15',1)")
        with pytest.raises(sqlite3.IntegrityError, match="Cross-tenant Record"):
            db.execute("UPDATE records SET organization_id='b' WHERE id='preserved'")
        with pytest.raises(sqlite3.IntegrityError, match="Repository tenant reassignment"):
            db.execute("UPDATE repositories SET organization_id='b' WHERE id='r'")
        assert db.execute("SELECT * FROM records").fetchall() == before


def test_migration_rejects_invalid_legacy_scope_without_rewriting_data(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    database = tmp_path / "invalid-scope.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database).replace("\\", "/")}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "0022"], env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO organizations VALUES ('a','A'),('b','B')")
        db.execute("INSERT INTO repositories VALUES ('r','a','Repo','System','Component','Owner','LOCAL',NULL)")
        db.execute("INSERT INTO records VALUES ('bad','b','r','claim','bad','{}','2026-10-15',1)")
        before = db.execute("SELECT * FROM records").fetchall()
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, capture_output=True)
    assert result.returncode != 0
    assert b"operator review" in result.stderr
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM records").fetchall() == before
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0022"
