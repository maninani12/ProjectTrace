"""Authenticated compressed collection pages; no joined global-result buffer.

The quota covers all retained encrypted pages plus the active manifest, including
staging attempts. A row is independently bounded by the existing spill row cap.
Replay authenticates every page before returning attempt-private lazy snapshots.
"""
import hashlib
import hmac
import json
import secrets
import time
import uuid
import zlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from analyzers.observation_store import EncryptedRows, MetricRows
from backend.db import AnalysisCheckpoint, AnalysisCheckpointPart, AnalysisInput, Record, now

SCHEMA = "projecttrace-analysis-checkpoint-v2"
PAGE_BYTES = 256_000
ROW_BYTES = 32_000_000
MAX_CIPHER_PAGE = PAGE_BYTES * 2 + 4096


class BudgetExceeded(ValueError):
    def __init__(self, message, *, site, limit, measured, exact, **components):
        super().__init__(message)
        self.diagnostic = {
            "site": site,
            "measurement": "ENCRYPTED_AGGREGATE_BYTES" if exact else "RAW_UTF8_PREFIX_BYTES",
            "site_limit_bytes": limit,
            "measured_bytes": measured,
            "measurement_exact": exact,
            **components,
        }


def encode(value, maximum, check, *, default=None, sort_keys=True, site="ROW_ENCODING"):
    raw = bytearray()
    for index, part in enumerate(json.JSONEncoder(default=default, ensure_ascii=True, sort_keys=sort_keys, separators=(",", ":")).iterencode(value)):
        if index % 256 == 0:
            check()
        attempted = len(raw) + len(part)  # ensure_ascii makes these UTF-8 byte lengths.
        if attempted > maximum:
            raise BudgetExceeded("Checkpoint row or manifest exceeds its byte budget.",
                                 site=site, limit=maximum, measured=attempted, exact=False)
        raw.extend(part.encode("ascii"))
    return bytes(raw)


def identity(job, signature, attempt):
    return [SCHEMA, job.id, job.organization_id, job.repository_id, signature, attempt]


def parts_where(job, attempt=None):
    clauses = [AnalysisCheckpointPart.job_id == job.id,
               AnalysisCheckpointPart.organization_id == job.organization_id,
               AnalysisCheckpointPart.repository_id == job.repository_id]
    return clauses + ([AnalysisCheckpointPart.attempt == attempt] if attempt else [])


def discard(db, job):
    db.execute(delete(AnalysisCheckpointPart).where(*parts_where(job)))


def save(db, job, signature, result, maximum, fence, check, *, rejection=None):
    from backend.queue import cipher
    attempt = str(uuid.uuid4())
    context = identity(job, signature, attempt)
    retained = db.get(AnalysisInput, job.id)
    expires = min(retained.expires_at if retained else "9999",
                  (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat())
    ordinal, memo, encrypted_bytes = 0, {}, 0
    row_limit = min(ROW_BYTES, maximum) - 4096  # Replay's authenticated row/scope envelope.
    descriptor_nodes = 0
    checked_at, steps = time.perf_counter(), 0

    def tick():
        nonlocal checked_at, steps
        steps += 1
        current = time.perf_counter()
        if steps >= 256 or current - checked_at >= 1:
            check()
            checked_at, steps = current, 0

    def lock():
        # A short writer transaction ends on every page; cancellation writers
        # are never held behind a complete serialization traversal.
        if db.get_bind().dialect.name == "sqlite":
            db.commit()
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        fence()
        db.scalar(select(Record.id).where(Record.id == job.id).with_for_update())

    def retained_bytes():
        total = db.scalar(select(func.coalesce(func.sum(func.length(AnalysisCheckpointPart.ciphertext)), 0))
                          .where(*parts_where(job)))
        active = db.scalar(select(func.length(AnalysisCheckpoint.ciphertext)).where(AnalysisCheckpoint.job_id == job.id)) or 0
        return total, active

    def page(collection, number, raw):
        nonlocal ordinal, encrypted_bytes
        check()
        packed = json.dumps([*context, collection, number], separators=(",", ":")).encode() + b"\n" + zlib.compress(raw, 1)
        encrypted = cipher().encrypt(packed).decode()
        lock()
        total, active = retained_bytes()
        attempted = total + active + len(encrypted)
        if attempted > maximum:
            raise BudgetExceeded("Aggregate encrypted checkpoint budget exceeded.",
                                 site="PAGE_ADMISSION", limit=maximum, measured=attempted, exact=True,
                                 retained_page_bytes=total, active_manifest_bytes=active,
                                 proposed_ciphertext_bytes=len(encrypted), component_raw_bytes=len(raw))
        db.add(AnalysisCheckpointPart(job_id=job.id, attempt=attempt, ordinal=ordinal,
            organization_id=job.organization_id, repository_id=job.repository_id,
            ciphertext=encrypted, digest=hashlib.sha256(packed).hexdigest(), expires_at=expires))
        db.commit()
        ordinal += 1
        encrypted_bytes += len(encrypted)

    def collection(values, kind):
        key = id(values)
        if key in memo:
            return memo[key][1]
        descriptor = ["rows", len(memo), kind, 0, ordinal, 0, 0, ""]
        memo[key] = (values, descriptor)  # Keep owners alive; no object-ID reuse.
        buffer, combined = bytearray(), hashlib.sha256()
        for value in values:
            raw = encode(value, row_limit, tick) + b"\n"
            descriptor[3] += 1
            descriptor[6] += len(raw)
            combined.update(raw)
            for offset in range(0, len(raw), PAGE_BYTES):
                buffer.extend(raw[offset:offset + PAGE_BYTES])
                if len(buffer) >= PAGE_BYTES:
                    page(descriptor[1], descriptor[5], bytes(buffer[:PAGE_BYTES]))
                    descriptor[5] += 1
                    del buffer[:PAGE_BYTES]
        if buffer:
            page(descriptor[1], descriptor[5], bytes(buffer))
            descriptor[5] += 1
        if hasattr(values, "__len__") and descriptor[3] != len(values):
            raise ValueError("Checkpoint collection changed during serialization.")
        descriptor[7] = combined.hexdigest()
        return descriptor

    def tree(value, depth=0, files=False):
        nonlocal descriptor_nodes
        tick()
        descriptor_nodes += 1
        if depth > 60 or descriptor_nodes > PAGE_BYTES:
            raise ValueError("Checkpoint descriptor structure budget exceeded.")
        if files or isinstance(value, (list, tuple)):
            return collection(value, "metrics" if isinstance(value, MetricRows) else "rows")
        if isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise ValueError("Checkpoint object keys must be strings.")
            return ["object", [[key, tree(child, depth + 1)] for key, child in sorted(value.items())]]
        return ["scalar", value]

    try:
        # No partially written attempt is a valid checkpoint. It is safe to
        # reclaim unreachable attempts only under the current fenced claim.
        lock()
        active = db.get(AnalysisCheckpoint, job.id, populate_existing=True)
        active_attempt = None
        if active:
            if (active.organization_id, active.repository_id) != (job.organization_id, job.repository_id):
                raise ValueError("Existing checkpoint owner is invalid.")
            previous_raw = cipher().decrypt(active.ciphertext.encode())
            if hashlib.sha256(previous_raw).hexdigest() != active.result_digest:
                raise ValueError("Existing checkpoint digest is invalid.")
            previous = json.loads(previous_raw)
            if previous.get("schema") == SCHEMA:
                if previous.get("identity", [])[:5] != identity(job, active.signature, "")[:5]:
                    raise ValueError("Existing checkpoint scope is invalid.")
                active_attempt = previous["identity"][-1]
            elif (previous.get("schema"), previous.get("job_id"), previous.get("organization_id"),
                  previous.get("repository_id"), previous.get("signature")) != (
                    "projecttrace-analysis-checkpoint-v1", job.id, job.organization_id, job.repository_id, active.signature):
                raise ValueError("Existing legacy checkpoint scope is invalid.")
        statement = delete(AnalysisCheckpointPart).where(*parts_where(job))
        if active_attempt:
            statement = statement.where(AnalysisCheckpointPart.attempt != active_attempt)
        db.execute(statement)
        db.commit()
        # files is an iterable inventory view, never repository source text.
        root = ["object", [[key, tree(value, files=key == "files")] for key, value in sorted(result.items())]]
        manifest = {"schema": SCHEMA, "identity": context, "root": root, "pages": ordinal, "expires_at": expires}
        raw = encode(manifest, row_limit, tick, site="MANIFEST_ENCODING")
        encrypted = cipher().encrypt(raw).decode()
        lock()
        total, active_size = retained_bytes()
        attempted = total + max(active_size, len(encrypted))
        if attempted > maximum:
            raise BudgetExceeded("Aggregate encrypted checkpoint budget exceeded.",
                                 site="MANIFEST_ADMISSION", limit=maximum, measured=attempted, exact=True,
                                 retained_page_bytes=total, active_manifest_bytes=active_size,
                                 proposed_ciphertext_bytes=len(encrypted), component_raw_bytes=len(raw))
        inventory = db.execute(select(func.count(), func.min(AnalysisCheckpointPart.ordinal),
            func.max(AnalysisCheckpointPart.ordinal)).where(*parts_where(job, attempt))).one()
        if inventory[0] != ordinal or ordinal and (inventory[1], inventory[2]) != (0, ordinal - 1):
            raise ValueError("Checkpoint staged page inventory changed before admission.")
        active = db.get(AnalysisCheckpoint, job.id, populate_existing=True)
        if active is None:
            active = AnalysisCheckpoint(job_id=job.id, organization_id=job.organization_id, repository_id=job.repository_id)
            db.add(active)
        active.signature, active.expires_at, active.format_version = signature, expires, 2
        active.ciphertext, active.result_digest = encrypted, hashlib.sha256(raw).hexdigest()
        db.execute(delete(AnalysisCheckpointPart).where(*parts_where(job), AnalysisCheckpointPart.attempt != attempt))
        db.commit()  # Only this atomic manifest replacement admits the pages.
        performance = getattr(fence, "performance", None)
        if performance:
            for name, value in {
                "checkpoint_pages_saved": ordinal,
                "checkpoint_collections_saved": len(memo),
                "checkpoint_encrypted_payload_bytes": encrypted_bytes + len(encrypted),
                "checkpoint_unique_row_json_bytes": sum(descriptor[6] for _, descriptor in memo.values()),
                "checkpoint_manifest_json_bytes": len(raw),
            }.items():
                performance.count(name, value)
        return True
    except BaseException as error:
        db.rollback()
        try:
            # A commit acknowledgement can be lost after admission. Preserve
            # authenticated committed pages and propagate the original error;
            # a fresh attempt can still recover this complete receipt.
            active_ciphertext = db.scalar(select(AnalysisCheckpoint.ciphertext).where(AnalysisCheckpoint.job_id == job.id))
            active_context = json.loads(cipher().decrypt(active_ciphertext.encode())).get("identity") if active_ciphertext else None
            if active_context != context:
                db.execute(delete(AnalysisCheckpointPart).where(*parts_where(job, attempt)))
                db.commit()
                cleanup = "ATTEMPT_REMOVED"
            else:
                cleanup = "ACTIVE_ATTEMPT_PRESERVED"
        except Exception:
            db.rollback()  # Preserve the original failure; expiry reclaims orphans.
            cleanup = "CLEANUP_FAILED"
        if isinstance(error, BudgetExceeded):
            if rejection is not None:
                rejection.update(schema="projecttrace-checkpoint-rejection-v1",
                                 storage_schema=SCHEMA, stage="GLOBAL_CHECKPOINT",
                                 configured_limit_bytes=maximum, staged_page_count=ordinal,
                                 logical_v1_bytes=None, logical_v1_size_reason="V1_ENVELOPE_NOT_SERIALIZED",
                                 cleanup=cleanup, **error.diagnostic)
            return False
        raise


class Replay:
    """One private encrypted SQLite owner/cache for every replayed collection."""
    def __init__(self, scope):
        self.rows = EncryptedRows(scope)
        self.secret = secrets.token_bytes(32)
        self.rows.connection.execute("CREATE TABLE positions (collection INTEGER, position INTEGER, ordinal INTEGER, path BLOB, PRIMARY KEY(collection,position))")
        self.rows.connection.execute("CREATE INDEX replay_path ON positions(collection,path,position)")

    def tag(self, value):
        path = value.get("path") if isinstance(value, dict) else None
        return hmac.digest(self.secret, path.encode(), "sha256") if isinstance(path, str) else None

    def close(self):
        self.rows.close()


class ReplayRows(MetricRows):
    """Existing encrypted-row snapshot contract, with one shared store/cache."""
    def __init__(self, owner, collection, count=0):
        self.owner, self.collection, self._count = owner, collection, count
        self.scope, self.maximum_bytes, self.row_bytes = owner.rows.scope, owner.rows.maximum_bytes, owner.rows.row_bytes
        self.label = "CHECKPOINT_REPLAY"

    def _open(self):
        self.owner.rows._open()

    @property
    def closed(self):
        return self.owner.rows.closed

    def close(self):
        self.owner.close()

    def append(self, value):
        ordinal = len(self.owner.rows)
        self.owner.rows.append({"collection": self.collection, "position": self._count, "value": value})
        self.owner.rows.connection.execute("INSERT INTO positions VALUES (?,?,?,?)",
            (self.collection, self._count, ordinal, self.owner.tag(value)))
        self._count += 1

    def __getitem__(self, position):
        self._open()
        if isinstance(position, slice):
            return [self[index] for index in range(*position.indices(self._count))]
        if position < 0:
            position += self._count
        if not 0 <= position < self._count:
            raise IndexError(position)
        ordinal = self.owner.rows.connection.execute("SELECT ordinal FROM positions WHERE collection=? AND position=?",
            (self.collection, position)).fetchone()[0]
        row = self.owner.rows[ordinal]
        if row.get("collection") != self.collection or row.get("position") != position:
            raise ValueError("Replay position does not match its encrypted row.")
        return row["value"]

    def _replace(self, position, value):
        ordinal = self.owner.rows.connection.execute("SELECT ordinal FROM positions WHERE collection=? AND position=?",
            (self.collection, position)).fetchone()[0]
        self.owner.rows._replace(ordinal, {"collection": self.collection, "position": position, "value": value})
        self.owner.rows.connection.execute("UPDATE positions SET path=? WHERE collection=? AND position=?",
            (self.owner.tag(value), self.collection, position))

    def for_path(self, path):
        self._open()
        tag = hmac.digest(self.owner.secret, path.encode(), "sha256")
        cursor = self.owner.rows.connection.execute("SELECT position FROM positions WHERE collection=? AND path=? ORDER BY position",
            (self.collection, tag))
        try:
            for position, in cursor:
                row = self[position]
                if row.get("path") != path:
                    raise ValueError("Replay path index does not match its encrypted row.")
                yield row
        finally:
            cursor.close()


def load(db, job, signature, manifest, maximum, check, own, expected_digest):
    from backend.queue import cipher
    if set(manifest) != {"schema", "identity", "root", "pages", "expires_at"}:
        raise ValueError("Checkpoint manifest schema is invalid.")
    context = manifest.get("identity")
    if (not isinstance(context, list) or len(context) != 6 or context[:5] != identity(job, signature, "")[:5]
            or type(manifest.get("pages")) is not int or not 0 <= manifest["pages"] <= maximum // 100):
        raise ValueError("Checkpoint manifest identity or page count is invalid.")
    attempt = context[-1]
    if type(attempt) is not str or str(uuid.UUID(attempt)) != attempt:
        raise ValueError("Checkpoint attempt identity is invalid.")
    total = db.scalar(select(func.coalesce(func.sum(func.length(AnalysisCheckpointPart.ciphertext)), 0))
                      .where(*parts_where(job)))
    root_size = db.scalar(select(func.length(AnalysisCheckpoint.ciphertext)).where(AnalysisCheckpoint.job_id == job.id)) or 0
    if total + root_size > maximum:
        raise ValueError("Aggregate encrypted checkpoint exceeds its byte budget.")
    owner, memo, expected_ordinal, descriptor_nodes = Replay(tuple(context)), {}, 0, 0

    def restore(node, depth=0):
        nonlocal expected_ordinal, descriptor_nodes
        check()
        descriptor_nodes += 1
        if depth > 60 or descriptor_nodes > PAGE_BYTES or not isinstance(node, list) or not node:
            raise ValueError("Checkpoint descriptor is invalid.")
        if node[0] == "scalar" and len(node) == 2:
            if not (node[1] is None or type(node[1]) in {str, int, float, bool}):
                raise ValueError("Checkpoint scalar descriptor is invalid.")
            return node[1]
        if node[0] == "object" and len(node) == 2:
            result = {}
            for key, child in node[1]:
                if type(key) is not str or key in result:
                    raise ValueError("Checkpoint object key is invalid or repeated.")
                result[key] = restore(child, depth + 1)
            return result
        if len(node) != 8 or node[0] != "rows" or node[2] not in {"metrics", "rows"}:
            raise ValueError("Checkpoint collection descriptor is invalid.")
        _, collection, kind, count, first, pages, length, digest = node
        if any(type(value) is not int or value < 0 for value in (collection, count, first, pages, length)):
            raise ValueError("Checkpoint collection counts are invalid.")
        if collection in memo:
            previous, rows = memo[collection]
            if node != previous:
                raise ValueError("Checkpoint collection reference changed.")
            return rows
        if collection != len(memo) or first != expected_ordinal or pages > manifest["pages"] - first:
            raise ValueError("Checkpoint collection order or counts are invalid.")
        rows, buffer, combined, decoded = ReplayRows(owner, collection), bytearray(), hashlib.sha256(), 0
        for number in range(pages):
            check()
            key = (job.id, attempt, first + number)
            info = db.execute(select(func.length(AnalysisCheckpointPart.ciphertext), AnalysisCheckpointPart.digest)
                .where(*parts_where(job, attempt), AnalysisCheckpointPart.ordinal == first + number,
                       AnalysisCheckpointPart.expires_at > now())).first()
            if info is None or not 0 < info[0] <= MAX_CIPHER_PAGE:
                raise ValueError("Checkpoint page is missing or exceeds its byte budget.")
            encrypted = db.scalar(select(AnalysisCheckpointPart.ciphertext).where(*parts_where(job, attempt),
                AnalysisCheckpointPart.ordinal == key[2]))
            packed = cipher().decrypt(encrypted.encode())
            if hashlib.sha256(packed).hexdigest() != info[1]:
                raise ValueError("Checkpoint page digest is invalid.")
            header, separator, compressed = packed.partition(b"\n")
            if not separator or json.loads(header) != [*context, collection, number]:
                raise ValueError("Checkpoint page identity is invalid.")
            decoder = zlib.decompressobj()
            raw = decoder.decompress(compressed, PAGE_BYTES + 1)
            if len(raw) > PAGE_BYTES or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                raise ValueError("Checkpoint page compression bound or encoding is invalid.")
            combined.update(raw)
            decoded += len(raw)
            buffer.extend(raw)
            while (end := buffer.find(b"\n")) >= 0:
                if end > min(ROW_BYTES, maximum):
                    raise ValueError("Checkpoint replay row exceeds its byte budget.")
                rows.append(json.loads(buffer[:end]))
                del buffer[:end + 1]
                if len(rows) % 256 == 0:
                    check()
            if len(buffer) > min(ROW_BYTES, maximum):
                raise ValueError("Checkpoint replay row exceeds its byte budget.")
        expected_ordinal += pages
        if buffer or len(rows) != count or decoded != length or combined.hexdigest() != digest:
            raise ValueError("Checkpoint collection is incomplete or its digest is invalid.")
        memo[collection] = (node, rows)
        return rows

    try:
        result = restore(manifest["root"])
        actual = db.scalar(select(func.count()).select_from(AnalysisCheckpointPart).where(*parts_where(job, attempt)))
        if expected_ordinal != manifest["pages"] or actual != expected_ordinal:
            raise ValueError("Checkpoint page inventory is incomplete or has extra pages.")
        if db.scalar(select(AnalysisCheckpoint.result_digest).where(AnalysisCheckpoint.job_id == job.id)) != expected_digest:
            raise ValueError("Analysis checkpoint changed during recovery.")
        check()
        if own:
            own(owner)
        return result
    except BaseException:
        owner.close()
        raise
