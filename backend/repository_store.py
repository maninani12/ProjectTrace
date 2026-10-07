"""Lazy source access backed by tenant-scoped encrypted, immutable content blobs."""

import hashlib
import json
import os
import re
import time
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from cryptography.fernet import InvalidToken
from sqlalchemy import select

from analyzers.engine import MAX_FILE_BYTES, SKIP_PARTS, TEXT_SUFFIXES, is_iac_source, safe_path
from backend.db import Record, SourceBlob, SourceInventory, SourceInventoryFile
from backend.domain import uid
from backend.queue import cipher


def limits():
    def bounded(name, default, low, high):
        value = int(os.getenv(name, str(default)))
        if not low <= value <= high:
            raise ValueError("Enterprise source quota configuration is outside supported bounds.")
        return value

    return {
        "files": bounded("REPOSITORY_MAX_FILES", 100000, 1000, 200000),
        "bytes": bounded("REPOSITORY_MAX_BYTES", 2_000_000_000, 10_000_000, 4_000_000_000),
        "archive_bytes": bounded("REPOSITORY_MAX_ARCHIVE_BYTES", 512_000_000, 10_000_000, 1_000_000_000),
        "file_bytes": MAX_FILE_BYTES,
        "partition_files": 100,
        "partition_bytes": 2_000_000,
    }


class BlobStore:
    def __init__(self):
        self.root = Path(os.getenv("SOURCE_BLOB_DIR", "data/source-blobs")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.encryption = cipher()
        mode = os.getenv("SOURCE_BLOB_BACKEND", "local")
        if mode not in {"local", "s3"}:
            raise ValueError("Source blob backend must be local or s3.")
        self.remote = None
        if mode == "s3":
            from backend.object_store import EncryptedObjectStore

            self.remote = EncryptedObjectStore()

    def path(self, organization_id, digest):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Blob digest is invalid.")
        tenant = hashlib.sha256(organization_id.encode()).hexdigest()
        return self.root / tenant / digest[:2] / (digest + ".enc")

    def put(self, db, organization_id, raw):
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Source blob exceeds its bounded storage budget.")
        digest = hashlib.sha256(raw).hexdigest()
        target = self.path(organization_id, digest)
        row = db.get(SourceBlob, (organization_id, digest))
        if row and (self.remote or target.is_file()):
            self.read(organization_id, digest)
            return digest, True
        if self.remote:
            self.remote.put(organization_id, digest, self.encryption.encrypt(raw))
        else:
            self._write_local(target, raw)
        if not row:
            if db.get_bind().dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            elif db.get_bind().dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                raise ValueError("Content storage requires a supported SQL adapter.")
            db.execute(
                insert(SourceBlob)
                .values(organization_id=organization_id, digest=digest, bytes=len(raw))
                .on_conflict_do_nothing(index_elements=["organization_id", "digest"])
            )
        return digest, False

    def _write_local(self, target, raw):
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace avoids readers observing partially written ciphertext.
        temporary = target.parent / (uid() + ".pending")
        try:
            temporary.write_bytes(self.encryption.encrypt(raw))
            temporary.chmod(0o600)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, organization_id, digest):
        try:
            if self.remote:
                encrypted = self.remote.read(organization_id, digest)
            else:
                with self.path(organization_id, digest).open("rb") as stream:
                    encrypted = stream.read(700_001)
            if len(encrypted) > 700_000:
                raise ValueError("Source ciphertext exceeds its bounded storage budget.")
            raw = self.encryption.decrypt(encrypted)
        except (OSError, InvalidToken):
            raise ValueError("Encrypted source is unavailable or failed its integrity check.") from None
        if len(raw) > MAX_FILE_BYTES or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Immutable blob integrity check failed.")
        return raw


class RepositoryFiles(Mapping):
    """Only backend-authorized inventories construct this non-JSON source input."""

    def __init__(self, db, organization_id, repository_id, inventory_id, *, native_only=False):
        inventory = db.get(SourceInventory, inventory_id)
        if not inventory or (inventory.organization_id, inventory.repository_id) != (organization_id, repository_id):
            raise ValueError("Source inventory is outside the authorized repository scope.")
        self.organization_id, self.repository_id, self.inventory_id = organization_id, repository_id, inventory_id
        self.native_only = native_only
        self.store = BlobStore()
        entries = db.execute(
            select(
                SourceInventoryFile.path,
                SourceInventoryFile.digest,
                SourceInventoryFile.component,
                SourceInventoryFile.data,
            ).where(
                SourceInventoryFile.inventory_id == inventory_id,
                SourceInventoryFile.organization_id == organization_id,
                SourceInventoryFile.repository_id == repository_id,
            )
        ).all()
        self.entries = {row.path: {**row.data, "hash": row.digest, "component": row.component} for row in entries}
        self.intake = [{"path": p, **data} for p, data in self.entries.items() if not data.get("text_retained")]
        self.paths = [
            p
            for p, data in self.entries.items()
            if data.get("text_retained") and (not native_only or self.native_path(p))
        ]
        if inventory.data.get("state") != "CAPTURED":
            raise ValueError("Source inventory capture is incomplete.")
        self.path_set = set(self.paths)
        self.data = inventory.data

    def view(self, *, native_only=False, paths=None):
        result = object.__new__(type(self))
        result.__dict__ = self.__dict__.copy()
        result.native_only = native_only
        allowed = None if paths is None else set(paths)
        result.paths = [
            p
            for p in (self.entries if allowed is None else sorted(allowed))
            if p in self.entries and self.entries[p].get("text_retained") and (not native_only or self.native_path(p))
        ]
        result.path_set = set(result.paths)
        return result

    @staticmethod
    def native_path(path):
        p = PurePosixPath(path)
        return not any(part in SKIP_PARTS for part in p.parts) and (
            p.suffix.lower() in TEXT_SUFFIXES or p.name in {"Dockerfile", "CODEOWNERS", "Makefile", ".env"}
        )

    def __len__(self):
        return len(self.paths)

    def __iter__(self):
        return iter(self.paths)

    def __getitem__(self, path):
        entry = self.entries.get(path)
        if not entry or not entry.get("text_retained") or path not in self:
            raise KeyError(path)
        return self.store.read(self.organization_id, entry["hash"]).decode("utf-8")

    def __contains__(self, path):
        return path in self.path_set

    def metadata_for(self, path):
        return self.entries.get(path)

    def hash_for(self, path):
        return self.entries[path]["hash"]

    def component_for(self, path):
        return self.entries[path]["component"]


def component_boundaries(value, *, basis="PROJECTTRACE_CONFIGURATION"):
    if not isinstance(value, dict) or set(value) != {"version", "components"} or value["version"] != 1:
        raise ValueError("Component configuration must declare version 1 and components.")
    items = value["components"]
    if not isinstance(items, list) or len(items) > 500:
        raise ValueError("Component configuration exceeds its bounded declaration budget.")
    roots = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"root", "name"}:
            raise ValueError("A component declaration requires only root and name.")
        root = "." if item["root"] == "." else str(safe_path(item["root"]))
        name = item["name"]
        if root in roots or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9@/_. -]{1,150}", name):
            raise ValueError("Component boundaries contain a duplicate or invalid name.")
        roots[root] = {"name": name, "root": root, "basis": basis}
    return roots


def capture(db, organization_id, repository, items, *, source="OWNED_STREAM", quota=None):
    """Items yield one (path, raw bytes or skipped metadata) at a time; never run them."""
    started, policy = time.perf_counter(), quota or limits()
    inventory = SourceInventory(
        id=uid(),
        organization_id=organization_id,
        repository_id=repository.id,
        data={"state": "CAPTURING", "source": source},
    )
    db.add(inventory)
    db.flush()
    store, seen, total, reused, count = BlobStore(), set(), 0, 0, 0
    roots, configured = {}, {}
    for path, value in items:
        canonical = str(safe_path(path))
        if canonical in seen:
            raise ValueError("Repository inventory contains duplicate paths.")
        seen.add(canonical)
        count += 1
        if count > policy["files"]:
            raise ValueError("Repository exceeds its configured file inventory quota.")
        data = value if isinstance(value, dict) else {"bytes": len(value)}
        if not isinstance(data.get("bytes"), int) or data["bytes"] < 0:
            raise ValueError("Inventory entry has an invalid byte count.")
        total += data["bytes"]
        if total > policy["bytes"]:
            raise ValueError("Repository exceeds its configured uncompressed byte quota.")
        digest, text = None, None
        if isinstance(value, bytes) and len(value) <= policy["file_bytes"]:
            # Blob lookups must not implicitly flush the preceding inventory
            # row. The explicit 100-row flush retains all tenant/FK checks.
            with db.no_autoflush:
                digest, reused_blob = store.put(db, organization_id, value)
            reused += reused_blob
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError:
                pass
        if text is not None:
            from analyzers.analysis_coverage import infrastructure_format

            data = {
                "infrastructure_format": infrastructure_format(canonical, text),
                "iac_candidate": is_iac_source(canonical, text),
                "bytes": len(value),
                "physical_lines": len(text.splitlines()),
                "text_retained": True,
                "generated_header": bool(
                    re.search(
                        r"(?im)^\s*(?:#|//|/\*|\*)\s*(?:@generated|generated (?:by|file|code)|auto-generated|do not edit)",
                        text[:2000],
                    )
                ),
            }
            if canonical == ".projecttrace/components.json":
                configured = component_boundaries(json.loads(text))
                for info in configured.values():
                    info["path"] = canonical
            if PurePosixPath(canonical).name == "package.json":
                try:
                    name = json.loads(text).get("name")
                    if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9@/_.-]{1,150}", name):
                        roots[str(PurePosixPath(canonical).parent)] = {
                            "name": name,
                            "root": str(PurePosixPath(canonical).parent),
                            "basis": "PACKAGE_MANIFEST",
                            "path": canonical,
                        }
                except (ValueError, AttributeError):
                    pass
        else:
            data = {
                **data,
                "physical_lines": None,
                "text_retained": False,
                **({"state": "SKIPPED_SIZE_LIMIT"} if data["bytes"] > policy["file_bytes"] else {}),
            }
        db.add(
            SourceInventoryFile(
                inventory_id=inventory.id,
                path=canonical,
                organization_id=organization_id,
                repository_id=repository.id,
                digest=digest,
                component=repository.component,
                data=data,
            )
        )
        if count % 100 == 0:
            db.flush()
    if not count:
        raise ValueError("Repository inventory is empty.")
    db.flush()
    correction = db.scalar(
        select(Record).where(
            Record.organization_id == organization_id,
            Record.repository_id == repository.id,
            Record.kind == "component_assignment",
        )
    )
    roots.update(configured)
    if correction:
        overrides = component_boundaries(correction.data["configuration"], basis="HUMAN_ASSIGNMENT")
        for info in overrides.values():
            info.update(path=correction.id, assignment_version=correction.version)
        roots.update(overrides)
    # A declared manifest/configuration or explicit correction establishes a boundary.
    for row in db.scalars(select(SourceInventoryFile).where(SourceInventoryFile.inventory_id == inventory.id)):
        matching = [(root, info) for root, info in roots.items() if root == "." or row.path.startswith(root + "/")]
        if matching:
            root, info = max(matching, key=lambda pair: len(pair[0]))
            row.component = info["name"]
            row.data = {
                **row.data,
                "component_basis": info["basis"],
                "component_evidence": info["path"],
                "component_root": root,
            }
    inventory.data = {
        "state": "CAPTURED",
        "source": source,
        "files": count,
        "bytes": total,
        "content_blobs_reused": reused,
        "components": list(roots.values()),
        "quotas": policy,
        "inventory_ms": round(1000 * (time.perf_counter() - started), 2),
        "limitations": ["Manifest boundaries are static; runtime and dynamic workspace membership are unobserved."],
    }
    db.flush()
    return inventory


def archive_items(stream, quota=None):
    import stat

    policy = quota or limits()
    with zipfile.ZipFile(stream) as archive:
        entries = archive.infolist()
        if len(entries) > policy["files"]:
            raise ValueError("Archive directory exceeds the inventory quota.")
        for entry in entries:
            safe_path(entry.orig_filename)
            path = str(safe_path(entry.filename))
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Archive symbolic links are forbidden.")
            if entry.is_dir():
                continue
            if entry.file_size > max(entry.compress_size, 1) * 200:
                raise ValueError("Archive entry exceeds the compression ratio policy.")
            if entry.file_size > policy["file_bytes"]:
                yield path, {"bytes": entry.file_size, "state": "SKIPPED_SIZE_LIMIT"}
            else:
                with archive.open(entry) as source:
                    raw = source.read(policy["file_bytes"] + 1)
                if len(raw) != entry.file_size or len(raw) > policy["file_bytes"]:
                    raise ValueError("Archive entry size is inconsistent.")
                yield path, raw
