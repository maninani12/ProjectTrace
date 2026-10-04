import sqlite3


def test_sqlite_consistent_backup_preserves_audit(tmp_path):
    source = tmp_path / "source.db"
    backup = tmp_path / "restored.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY, reason TEXT)")
        db.execute("INSERT INTO audit VALUES (1, ?)", ("Verified evidence review",))
    with sqlite3.connect(source) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
        assert dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert dst.execute("SELECT * FROM audit").fetchall() == src.execute("SELECT * FROM audit").fetchall()
