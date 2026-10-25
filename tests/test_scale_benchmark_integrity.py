import sqlite3

import pytest

from scripts.benchmark_repository_scale import verify_database


def test_benchmark_requires_valid_persisted_database(tmp_path):
    path = tmp_path / "owned.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE owned(id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO owned VALUES (1)")
    assert verify_database(path) == {"sqlite_integrity": "ok", "foreign_key_violations": 0}
    # Damage only an owned disposable fixture; never a repository/application DB.
    path.write_bytes(b"not an sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        verify_database(path)


def test_benchmark_rejects_foreign_key_violations(tmp_path):
    path = tmp_path / "owned.db"
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE parent(id INTEGER PRIMARY KEY);"
                         "CREATE TABLE child(id INTEGER REFERENCES parent(id));"
                         "INSERT INTO child VALUES (123);")
    with pytest.raises(ValueError, match="integrity validation"):
        verify_database(path)
