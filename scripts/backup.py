"""Consistent local SQLite backup; deployed PostgreSQL uses pg_dump."""

import argparse
import sqlite3
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit("Destination already exists; backups are never overwritten.")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect("data/projecttrace.db") as source, sqlite3.connect(args.destination) as target:
        source.backup(target)
        assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("Local backup written and SQLite integrity checked. Store it securely; it contains redacted repository data.")
