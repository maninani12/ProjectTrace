"""Operator local recovery drill; writes only fresh destinations and never includes encryption keys."""

import argparse
import json
from pathlib import Path

from backend.local_backup import backup_local, restore_local

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--database", type=Path, default=Path("data/projecttrace.db"))
    parser.add_argument("--blobs", type=Path, default=Path("data/source-blobs"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--key-file", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.action == "backup":
        result = backup_local(arguments.database, arguments.blobs, arguments.bundle, arguments.key_file)
        print(json.dumps({key: value for key, value in result.items() if key != "files"}))
    else:
        if not arguments.destination:
            parser.error("Restore requires a fresh --destination.")
        print(json.dumps(restore_local(arguments.bundle, arguments.destination, arguments.key_file)))
