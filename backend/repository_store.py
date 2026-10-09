"""Lazy source access backed by tenant-scoped encrypted, immutable content blobs."""

import hashlib
import json
import os
import re
import time
import zipfile
import zlib
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy import text as sql_text

from analyzers.engine import MAX_FILE_BYTES, SKIP_PARTS, TEXT_SUFFIXES, is_iac_source, safe_path
from backend.db import Record, SourceBlob, SourceInventory, SourceInventoryFile
from backend.domain import uid
from backend.intake_errors import IntakeError
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

    def view(self, *, native_only=False, paths=None, cache_sources=False):
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
        if cache_sources:
            result._source_cache = OrderedDict()
            result._source_cache_bytes = 0
            result._source_reads = result._source_hits = 0
        else:
            for key in ("_source_cache", "_source_cache_bytes", "_source_reads", "_source_hits"):
                result.__dict__.pop(key, None)
        return result

    @staticmethod
    def native_path(path):
        p = PurePosixPath(path)
        return not any(part in SKIP_PARTS for part in p.parts) and (
            p.suffix.lower() in TEXT_SUFFIXES
            or p.name in {"Dockerfile", "CODEOWNERS", "Makefile", ".env"}
            or p.name.startswith("Dockerfile")
        )

    def __len__(self):
        return len(self.paths)

    def __iter__(self):
        return iter(self.paths)

    def __getitem__(self, path):
        entry = self.entries.get(path)
        if not entry or not entry.get("text_retained") or path not in self:
            raise KeyError(path)
        cache = getattr(self, "_source_cache", None)
        if cache is not None and path in cache:
            self._source_hits += 1
            cache.move_to_end(path)
            return cache[path]
        source = self.store.read(self.organization_id, entry["hash"]).decode("utf-8")
        if cache is not None:
            self._source_reads += 1
            size = entry["bytes"]
            while cache and self._source_cache_bytes + size > 2_000_000:
                previous, _ = cache.popitem(last=False)
                self._source_cache_bytes -= self.entries[previous]["bytes"]
            cache[path] = source
            self._source_cache_bytes += size
        return source

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


def capture(db, organization_id, repository, items, *, source="OWNED_STREAM", quota=None, checkpoint=None):
    """Capture inert bytes; optional fenced checkpoints bound provider write transactions.

    Checkpointed captures commit incomplete inventory batches. Only CAPTURED
    inventories may be analyzed; callers must validate their authorization/lease
    in the callback before each commit. Default capture remains atomic.
    """
    started, policy = time.perf_counter(), quota or limits()
    if checkpoint and db.get_bind().dialect.name == "sqlite":
        db.commit()
        db.execute(sql_text("BEGIN IMMEDIATE"))
    inventory = SourceInventory(
        id=uid(),
        organization_id=organization_id,
        repository_id=repository.id,
        data={"state": "CAPTURING", "source": source},
    )
    db.add(inventory)
    db.flush()

    def commit_batch():
        checkpoint()
        db.commit()

    if checkpoint:
        commit_batch()

    def begin_batch():
        # End provider-fencing reads before acquiring the next bounded writer.
        # This avoids upgrading a stale WAL snapshot after another commit.
        db.commit()
        if db.get_bind().dialect.name == "sqlite":
            db.execute(sql_text("BEGIN IMMEDIATE"))

    def buffered_items():
        # Pull provider bytes before opening the next write transaction. Without
        # this buffer, a flush/lease renewal holds SQLite's writer during HTTP.
        batch, size = [], 0
        for path, value in items:
            if isinstance(value, bytes) and len(value) > policy["file_bytes"]:
                value = {"bytes": len(value), "state": "SKIPPED_SIZE_LIMIT"}
            raw_size = len(value) if isinstance(value, bytes) else 0
            if batch and size + raw_size > policy["partition_bytes"]:
                begin_batch()
                yield from batch
                commit_batch()
                batch, size = [], 0
            batch.append((path, value))
            size += raw_size
            if len(batch) >= policy["partition_files"] or size >= policy["partition_bytes"]:
                begin_batch()
                yield from batch
                commit_batch()
                batch, size = [], 0
        if batch:
            begin_batch()
            yield from batch
            commit_batch()

    store, seen, total, reused, count = BlobStore(), set(), 0, 0, 0
    roots, configured = {}, {}
    for path, value in buffered_items() if checkpoint else items:
        canonical = str(safe_path(path))
        if canonical in seen:
            raise IntakeError("DUPLICATE_PATH", "Repository inventory contains duplicate paths.")
        seen.add(canonical)
        count += 1
        if count > policy["files"]:
            raise IntakeError("REPOSITORY_FILE_COUNT", "Repository exceeds its configured file inventory quota.",
                              budget="REPOSITORY_MAX_FILES", actual=count, maximum=policy["files"])
        data = value if isinstance(value, dict) else {"bytes": len(value)}
        if not isinstance(data.get("bytes"), int) or data["bytes"] < 0:
            raise ValueError("Inventory entry has an invalid byte count.")
        total += data["bytes"]
        if total > policy["bytes"]:
            raise IntakeError("REPOSITORY_UNCOMPRESSED_BYTES", "Repository exceeds its configured uncompressed byte quota.",
                              budget="REPOSITORY_MAX_BYTES", actual=total, maximum=policy["bytes"])
        digest, text = None, None
        if isinstance(value, bytes) and len(value) <= policy["file_bytes"]:
            # Blob lookups must not implicitly flush the preceding inventory
            # row. The explicit 100-row flush retains all tenant/FK checks.
            with db.no_autoflush:
                digest, reused_blob = store.put(db, organization_id, value)
            reused += reused_blob
            from analyzers.code_quality.classification import binary_input

            if binary_input(canonical, value):
                data = {**data, "state": "BINARY"}
            else:
                try:
                    text = value.decode("utf-8")
                except UnicodeDecodeError:
                    pass
        if text is not None:
            from analyzers.analysis_coverage import infrastructure_format
            from analyzers.code_quality.classification import source_language

            data = {
                "infrastructure_format": infrastructure_format(canonical, text),
                "source_language": source_language(canonical, text),
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
    def inventory_rows():
        if not checkpoint:
            yield from db.scalars(select(SourceInventoryFile).where(SourceInventoryFile.inventory_id == inventory.id))
            return
        last = None
        while True:
            query = select(SourceInventoryFile).where(SourceInventoryFile.inventory_id == inventory.id)
            if last is not None:
                query = query.where(SourceInventoryFile.path > last)
            rows = list(db.scalars(query.order_by(SourceInventoryFile.path).limit(policy["partition_files"])))
            if not rows:
                break
            yield from rows
            last = rows[-1].path
            commit_batch()

    for row in inventory_rows():
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


def archive_items(stream, quota=None, *, validate_only=False):
    import stat

    policy = quota or limits()
    # Check the bounded end-directory metadata before ZipFile allocates its
    # central-directory objects. ZIP64 metadata is handled by the stdlib reader.
    end = zipfile._EndRecData(stream)
    if end is None:
        raise IntakeError("ARCHIVE_INVALID", "Archive has no valid ZIP end directory.")
    metadata_bytes = end[zipfile._ECD_SIZE]
    if metadata_bytes > 64_000_000:
        raise IntakeError("ARCHIVE_METADATA_BYTES", "Archive directory exceeds its metadata budget.",
                          budget="ARCHIVE_METADATA_BYTES", actual=metadata_bytes, maximum=64_000_000)
    declared_count = end[zipfile._ECD_ENTRIES_TOTAL]
    if declared_count > policy["files"]:
        raise IntakeError("ARCHIVE_ENTRY_COUNT", "Archive directory exceeds the inventory quota.",
                          budget="REPOSITORY_MAX_FILES", actual=declared_count, maximum=policy["files"])
    if end[zipfile._ECD_DISK_NUMBER] or end[zipfile._ECD_DISK_START]:
        raise IntakeError("ARCHIVE_MULTIDISK", "Multi-volume ZIP archives are unsupported.")
    with zipfile.ZipFile(stream) as archive:
        entries = archive.infolist()
        if len(entries) > policy["files"]:
            raise IntakeError("ARCHIVE_ENTRY_COUNT", "Archive directory exceeds the inventory quota.",
                              budget="REPOSITORY_MAX_FILES", actual=len(entries), maximum=policy["files"])
        total, seen = 0, set()
        # Validate the entire directory before decompressing any eligible entry.
        for entry in entries:
            try:
                safe_path(entry.orig_filename)
                path = str(safe_path(entry.filename))
            except ValueError:
                raise IntakeError("ARCHIVE_UNSAFE_PATH", "Archive contains an invalid path or path traversal.") from None
            if path in seen:
                raise IntakeError("DUPLICATE_PATH", "Archive contains duplicate canonical paths.")
            seen.add(path)
            if entry.flag_bits & 1:
                raise IntakeError("ARCHIVE_ENCRYPTED_ENTRY", "Encrypted ZIP entries cannot be inspected safely.",
                                  remediation="Export an unencrypted source-only ZIP and retry.")
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if mode not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
                raise IntakeError("ARCHIVE_SPECIAL_ENTRY", "Archive contains an unsupported device or special entry.")
            if entry.is_dir():
                continue
            total += entry.file_size
            if total > policy["bytes"]:
                raise IntakeError("REPOSITORY_UNCOMPRESSED_BYTES", "Archive exceeds its uncompressed byte quota.",
                                  budget="REPOSITORY_MAX_BYTES", actual=total, maximum=policy["bytes"],
                                  remediation="Import a bounded source component without generated/build output.")
            if entry.file_size > max(entry.compress_size, 1) * 200:
                raise IntakeError("ARCHIVE_COMPRESSION_RATIO", "Archive entry exceeds the compression ratio policy.",
                                  budget="ARCHIVE_MAX_COMPRESSION_RATIO", actual=round(entry.file_size / max(entry.compress_size, 1), 2),
                                  maximum=200)
        if validate_only:
            return
        for entry in entries:
            if entry.is_dir():
                continue
            path = str(safe_path(entry.filename))
            if stat.S_ISLNK(entry.external_attr >> 16):
                # Retain only the name/type/declared size. Never read a target,
                # extract anything, resolve a link or follow a filesystem path.
                yield path, {"bytes": entry.file_size, "state": "UNSUPPORTED", "source_kind": "SYMLINK"}
                continue
            if entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                yield path, {"bytes": entry.file_size, "state": "UNSUPPORTED", "source_kind": "ZIP_COMPRESSION_METHOD"}
                continue
            if entry.file_size > policy["file_bytes"]:
                yield path, {"bytes": entry.file_size, "state": "SKIPPED_SIZE_LIMIT"}
            else:
                try:
                    with archive.open(entry) as source:
                        raw = source.read(policy["file_bytes"] + 1)
                except (zipfile.BadZipFile, EOFError, RuntimeError, OSError, zlib.error) as error:
                    raise IntakeError("ARCHIVE_ENTRY_CORRUPT", "Archive entry failed its ZIP integrity check.") from error
                if len(raw) != entry.file_size or len(raw) > policy["file_bytes"]:
                    raise IntakeError("ARCHIVE_ENTRY_SIZE", "Archive entry size is inconsistent with its directory.")
                yield path, raw
