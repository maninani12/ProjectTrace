"""Consistent local SQLite + immutable encrypted-blob recovery bundles; keys stay separate."""

import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bounded_ciphertext(path):
    with Path(path).open("rb") as stream:
        value = stream.read(700001)
    if len(value) > 700000:
        raise ValueError("Recovery blob exceeds its bounded ciphertext size.")
    return value


def blob_relative(org, digest):
    import re

    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Backup contains an invalid blob identity.")
    return Path("blobs") / hashlib.sha256(org.encode()).hexdigest() / digest[:2] / (digest + ".enc")


def backup_local(database, blob_root, destination, key_file):
    destination, blob_root = Path(destination).resolve(), Path(blob_root).resolve()
    if destination.exists():
        raise ValueError("Backup destinations must be fresh; existing backups are never overwritten.")
    encryption = Fernet(Path(key_file).read_bytes().strip())
    destination.mkdir(parents=True, mode=0o700)
    target = destination / "database.db"
    with (
        sqlite3.connect("file:" + Path(database).resolve().as_posix() + "?mode=ro", uri=True) as source,
        sqlite3.connect(target) as backed,
    ):
        source.backup(backed)
        if backed.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup database integrity failed.")
        blobs = (
            backed.execute("SELECT organization_id,digest FROM source_blobs").fetchall()
            if backed.execute("SELECT name FROM sqlite_master WHERE name='source_blobs'").fetchone()
            else []
        )
    files = {"database.db": file_digest(target)}
    for org, digest in blobs:
        relative = blob_relative(org, digest)
        original = blob_root / Path(*relative.parts[1:])
        encrypted = bounded_ciphertext(original)
        if len(encrypted) > 700000 or hashlib.sha256(encryption.decrypt(encrypted)).hexdigest() != digest:
            raise ValueError("Backup blob integrity or decrypt validation failed.")
        copied = destination / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes(encrypted)
        files[relative.as_posix()] = hashlib.sha256(encrypted).hexdigest()
    manifest = {
        "schema": "projecttrace-local-recovery-v1",
        "state": "VERIFIED_LOCAL_BACKUP",
        "encrypted_blobs": len(blobs),
        "key_included": False,
        "files": files,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def restore_local(bundle, destination, key_file):
    bundle, destination = Path(bundle).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("Restore destinations must be fresh; existing data is never overwritten.")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "projecttrace-local-recovery-v1":
        raise ValueError("Unknown recovery bundle schema.")
    # Validate the complete bundle before creating any restored files.
    for name, digest in manifest["files"].items():
        if name != "database.db" and not re.fullmatch(r"blobs/[0-9a-f]{64}/[0-9a-f]{2}/[0-9a-f]{64}\.enc", name):
            raise ValueError("Recovery manifest contains an invalid relative destination.")
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle) or path.is_symlink() or file_digest(path) != digest:
            raise ValueError("Recovery manifest integrity or path validation failed.")
    encryption = Fernet(Path(key_file).read_bytes().strip())
    with sqlite3.connect("file:" + (bundle / "database.db").as_posix() + "?mode=ro", uri=True) as db:
        if (
            db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or db.execute("PRAGMA foreign_key_check").fetchone()
        ):
            raise ValueError("Restored database constraints failed.")
        blobs = (
            db.execute("SELECT organization_id,digest FROM source_blobs").fetchall()
            if db.execute("SELECT name FROM sqlite_master WHERE name='source_blobs'").fetchone()
            else []
        )
        for org, digest in blobs:
            raw = encryption.decrypt(bounded_ciphertext(bundle / blob_relative(org, digest)))
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("Restored encrypted blob failed integrity validation.")
        if set(manifest["files"]) != {"database.db", *(blob_relative(org, digest).as_posix() for org, digest in blobs)}:
            raise ValueError("Recovery manifest does not exactly match the database blob references.")
    destination.mkdir(parents=True, mode=0o700)
    for name in manifest["files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle / name, target)
    return {"state": "VERIFIED_LOCAL_RESTORE", "encrypted_blobs": len(blobs), "key_included": False}
