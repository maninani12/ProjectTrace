"""Versioned, authenticated generation context with bounded encrypted replay.

Only a complete receipt admits an attempt. Collection payloads are never joined
on replay. JSON data and application references have separate typed descriptors.
The existing stage byte quota applies to all retained encoded payloads together.
"""
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
import weakref
import zlib

from sqlalchemy import delete, func, select

from analyzers.observation_store import EncryptedRows
from backend.checkpoint_pages import MAX_CIPHER_PAGE, PAGE_BYTES, ROW_BYTES, Replay, ReplayRows, encode
from backend.context_maps import ContextMap, Entries, admit_key, entry_key, index
from backend.db import Record, now
from backend.generation_models import GenerationChunk, GenerationContextPart, GenerationReceipt, GenerationRecord

SCHEMA = "projecttrace-generation-context-v2"
MAX_BYTES = 64_000_000
ROW_LIMIT = ROW_BYTES - 8192


def plain_row(value, check, depth=0):
    """Route nested large maps/references out of atomic JSON rows, no copies."""
    check()
    if depth > 60:
        raise ValueError("Generation context descriptor budget exceeded.")
    if isinstance(value, ContextMap):
        raise NeedsReference()
    if isinstance(value, dict):
        if len(value) > 128:
            raise NeedsReference()
        for child in value.values():
            plain_row(child, check, depth + 1)
    elif isinstance(value, (list, tuple)):
        if isinstance(value, EncryptedRows) or len(value) > 128:
            raise NeedsReference()
        for child in value:
            plain_row(child, check, depth + 1)


def where(generation, attempt=None):
    row = generation.row
    clauses = [GenerationContextPart.generation_id == row.id, GenerationContextPart.stage == generation.stage,
               GenerationContextPart.organization_id == row.organization_id,
               GenerationContextPart.repository_id == row.repository_id]
    return clauses + ([GenerationContextPart.attempt == attempt] if attempt else [])


def identity(generation, attempt, dependencies):
    row = generation.row
    return [SCHEMA, row.id, row.organization_id, row.repository_id, row.signature,
            generation.stage, attempt, dependencies]


class NeedsReference(TypeError):
    pass


def unsupported(value):
    raise NeedsReference()


class Writer:
    def __init__(self, generation, dependencies):
        self.g = generation
        self.attempt = str(uuid.uuid4())
        self.context = identity(generation, self.attempt, dependencies)
        self.memo, self.inventory, self.active, self.maps = {}, {}, set(), {}
        self.nodes, self.steps, self.checked = 0, 0, time.perf_counter()
        self.check = getattr(generation.checkpoint, "read_check", generation.checkpoint)

    def tick(self):
        self.steps += 1
        if self.steps >= 256 or time.perf_counter() - self.checked >= 1:
            self.check()
            self.steps, self.checked = 0, time.perf_counter()

    def lock(self):
        db = self.g.db
        if db.get_bind().dialect.name == "sqlite":
            db.commit()
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        self.g.fence()
        db.scalar(select(Record.id).where(Record.id == self.g.row.job_id).with_for_update())
        if db.get(GenerationReceipt, (self.g.row.id, self.g.stage), populate_existing=True):
            raise ValueError("Completed generation receipt is immutable.")

    def budget(self, extra=0):
        db = self.g.db
        parts = db.scalar(select(func.coalesce(func.sum(func.length(GenerationContextPart.ciphertext)), 0)).where(*where(self.g)))
        chunks = db.scalar(select(func.coalesce(func.sum(func.length(GenerationChunk.ciphertext)), 0)).where(
            GenerationChunk.generation_id == self.g.row.id, GenerationChunk.stage == self.g.stage))
        if parts + chunks + extra > MAX_BYTES:
            raise ValueError("Generation stage context exceeds its bounded byte budget.")

    def page(self, collection, raw):
        from backend.queue import cipher
        self.check()
        number = self.inventory.get(collection, 0)
        packed = json.dumps([*self.context, collection, number], separators=(",", ":")).encode() + b"\n" + zlib.compress(raw, 1)
        encrypted = cipher().encrypt(packed).decode()
        self.lock()
        self.budget(len(encrypted))
        self.g.db.add(GenerationContextPart(generation_id=self.g.row.id, stage=self.g.stage,
            attempt=self.attempt, collection=collection, ordinal=number,
            organization_id=self.g.row.organization_id, repository_id=self.g.row.repository_id,
            ciphertext=encrypted, digest=hashlib.sha256(packed).hexdigest(), expires_at=self.g.row.expires_at))
        self.g.db.commit()
        self.inventory[collection] = number + 1

    def rows(self, values, depth=0, *, kind=None):
        key = id(values)
        if key in self.active:
            raise ValueError("Generation context contains a cycle.")
        if key in self.memo:
            return self.memo[key][1]
        if len(self.memo) >= PAGE_BYTES:
            raise ValueError("Generation context descriptor budget exceeded.")
        kind = kind or ("mutable" if getattr(values, "mutable", not isinstance(values, EncryptedRows)) else "snapshots")
        descriptor = ["rows", len(self.memo), 0, 0, 0, "", kind]
        self.memo[key] = (values, descriptor)
        self.active.add(key)
        buffer, combined = bytearray(), hashlib.sha256()
        for value in values:
            try:
                plain_row(value, self.tick, depth + 1)
                raw = b"J" + encode(value, ROW_LIMIT, self.tick, default=unsupported, sort_keys=False) + b"\n"
            except NeedsReference:
                raw = b"E" + encode(self.node(value, depth + 1), ROW_LIMIT, self.tick) + b"\n"
            descriptor[2] += 1
            descriptor[4] += len(raw)
            combined.update(raw)
            for offset in range(0, len(raw), PAGE_BYTES):
                buffer.extend(raw[offset:offset + PAGE_BYTES])
                if len(buffer) >= PAGE_BYTES:
                    self.page(descriptor[1], bytes(buffer[:PAGE_BYTES]))
                    del buffer[:PAGE_BYTES]
        if buffer:
            self.page(descriptor[1], bytes(buffer))
        if hasattr(values, "__len__") and len(values) != descriptor[2]:
            raise ValueError("Generation collection changed during serialization.")
        descriptor[3], descriptor[5] = self.inventory.get(descriptor[1], 0), combined.hexdigest()
        self.active.remove(key)
        return descriptor

    def mapping(self, value, depth):
        key = id(value)
        if key in self.active:
            raise ValueError("Generation context contains a cycle.")
        if key in self.maps:
            return self.maps[key][1]
        descriptor = ["map", None]
        self.maps[key] = (value, descriptor)
        self.active.add(key)
        descriptor[1] = self.rows(Entries(value), depth + 1, kind="mapping")
        self.active.remove(key)
        return descriptor

    def node(self, value, depth=0):
        from backend.publication_state import FindingRecords
        self.tick()
        self.nodes += 1
        if depth > 60 or self.nodes > PAGE_BYTES:
            raise ValueError("Generation context descriptor budget exceeded.")
        if isinstance(value, Record):
            # Visibility is checked again on recovery, including cached objects.
            if (value.organization_id, value.repository_id) != (self.g.row.organization_id, self.g.row.repository_id):
                raise ValueError("Generation context record is unavailable in scope.")
            return ["record", value.id]
        if isinstance(value, FindingRecords):
            return ["findings", self.rows(value.snapshots(), depth + 1)]
        if isinstance(value, set):
            return ["set", self.rows(value, depth + 1)]
        if isinstance(value, (list, tuple)):
            if len(value) <= 8:
                return ["inline", [self.node(child, depth + 1) for child in value]]
            return self.rows(value, depth)
        if isinstance(value, dict):
            if isinstance(value, ContextMap) or len(value) > 8:
                return self.mapping(value, depth)
            if any(type(key) is not str for key in value):
                raise ValueError("Generation context keys must be strings.")
            # Stage replay must preserve producer iteration order: graph row
            # ordinals are deterministic identities during partial-stage retry.
            return ["object", [[key, self.node(child, depth + 1)] for key, child in value.items()]]
        if value is None or type(value) in {str, int, float, bool}:
            return ["scalar", value]
        raise TypeError("Unsupported generation context type: " + type(value).__name__)

    def save(self, state):
        from backend.generations import SCHEMA as LEGACY_SCHEMA
        from backend.queue import cipher
        db = self.g.db
        try:
            self.lock()
            db.execute(delete(GenerationContextPart).where(*where(self.g)))
            db.execute(delete(GenerationChunk).where(GenerationChunk.generation_id == self.g.row.id,
                                                     GenerationChunk.stage == self.g.stage))
            db.commit()  # Only unreachable, unreceipted state is reclaimed.
            root = self.node(state)
            manifest = encode({"context": self.context, "expires_at": self.g.row.expires_at, "root": root}, ROW_LIMIT, self.tick)
            for offset in range(0, len(manifest), PAGE_BYTES):
                self.page(-1, manifest[offset:offset + PAGE_BYTES])
            pointer = encode({"context": self.context, "expires_at": self.g.row.expires_at,
                "manifest_pages": self.inventory[-1], "manifest_bytes": len(manifest),
                "manifest_digest": hashlib.sha256(manifest).hexdigest(), "pages": sum(self.inventory.values())}, PAGE_BYTES, self.tick).decode()
            envelope = json.dumps({"identity": [LEGACY_SCHEMA, self.g.row.id, self.g.row.organization_id,
                self.g.row.repository_id, self.g.row.signature, self.g.stage, 0], "data": pointer}).encode()
            encrypted = cipher().encrypt(envelope).decode()
            self.lock()
            self.budget(len(encrypted))
            actual = db.execute(select(GenerationContextPart.collection, func.count(), func.min(GenerationContextPart.ordinal),
                func.max(GenerationContextPart.ordinal)).where(*where(self.g, self.attempt)).group_by(GenerationContextPart.collection)).all()
            if {c: n for c, n, _, _ in actual} != self.inventory or any((low, high) != (0, n - 1) for _, n, low, high in actual):
                raise ValueError("Generation staged page inventory changed before admission.")
            if self.g.dependencies(self.g.stage) != self.context[-1]:
                raise ValueError("Generation dependencies changed before admission.")
            records = db.scalar(select(func.count()).select_from(GenerationRecord).where(
                GenerationRecord.generation_id == self.g.row.id, GenerationRecord.stage == self.g.stage))
            db.add(GenerationChunk(generation_id=self.g.row.id, stage=self.g.stage, ordinal=0,
                organization_id=self.g.row.organization_id, repository_id=self.g.row.repository_id,
                ciphertext=encrypted, digest=hashlib.sha256(envelope).hexdigest()))
            db.add(GenerationReceipt(generation_id=self.g.row.id, stage=self.g.stage,
                organization_id=self.g.row.organization_id, repository_id=self.g.row.repository_id,
                dependency_digest=self.context[-1], digest=hashlib.sha256(pointer.encode()).hexdigest(),
                chunk_count=1, record_count=records, format_version=2))
            self.g.batch()  # Root and immutable receipt are admitted together.
        except BaseException:
            db.rollback()
            # Rollback expires ORM attributes, including the active context
            # used by the visibility hook. Refresh only this ledger row with
            # that hook's context temporarily removed; never refresh Records
            # without their private-generation visibility predicate.
            active = db.info.pop("analysis_generation", None)
            try:
                db.refresh(self.g.row)
                receipt = db.get(GenerationReceipt, (self.g.row.id, self.g.stage), populate_existing=True)
                # A lost commit acknowledgement must preserve admitted pages.
                if receipt is None:
                    db.execute(delete(GenerationContextPart).where(*where(self.g, self.attempt)))
                    db.commit()
            except Exception:
                db.rollback()
            finally:
                if active is not None:
                    db.info["analysis_generation"] = active
            raise


class ContextRows(ReplayRows):
    def __init__(self, reader, collection, mutable):
        super().__init__(reader.owner, collection)
        self.reader = reader
        self.mutable = mutable
        # Only callers holding a row keep its live mutable identity. The owner
        # never strongly retains every row read during a collection traversal.
        self.live = weakref.WeakValueDictionary()

    def _json_iter(self):
        # Authenticate freshly even if a caller retains a live mutable row.
        # Avoid creating new write-through cycles solely for serialization.
        for position in range(len(self)):
            frame = ReplayRows.__getitem__(self, position)
            self._open()
            value = self.live.get(position)
            if value is None:
                value = frame[1] if frame[0] == "J" else self.reader.restore(frame[1])
            del frame
            try:
                yield value
            finally:
                del value

    def __getitem__(self, position):
        if isinstance(position, slice):
            return [self[index] for index in range(*position.indices(len(self)))]
        self._open()
        if position < 0:
            position += len(self)
        if position in self.live:
            return self.live[position]
        frame = super().__getitem__(position)
        value = frame[1] if frame[0] == "J" else self.reader.restore(frame[1])
        if self.mutable and isinstance(value, (dict, list)) and not isinstance(value, (ContextMap, EncryptedRows)):
            from backend.context_json import tracked
            root = []
            def changed():
                if self.live.get(position) is root[0]:
                    self._store(position, root[0])
            root.append(tracked(value, changed))
            self.live[position] = root[0]
            return root[0]
        return value

    def append_frame(self, frame):
        super().append(frame)
        value = frame[1] if frame[0] == "J" else None
        self.owner.rows.connection.execute("UPDATE positions SET path=? WHERE collection=? AND position=?",
            (self.owner.tag(value), self.collection, self._count - 1))

    def append(self, value):
        self.append_frame(self.reader.mutable_frame(value))

    def __setitem__(self, position, value):
        if not self.mutable or not isinstance(position, int):
            raise TypeError("Only mutable context rows support integer replacement.")
        self._replace(position, value)

    def _replace(self, position, value):
        if position < 0:
            position += len(self)
        if not 0 <= position < len(self):
            raise IndexError(position)
        self.live.pop(position, None)
        self._store(position, value)

    def _store(self, position, value):
        super()._replace(position, self.reader.mutable_frame(value))
        self.owner.rows.connection.execute("UPDATE positions SET path=? WHERE collection=? AND position=?",
            (self.owner.tag(value), self.collection, position))


class Reader:
    def __init__(self, generation, receipt, *, validate_only=False):
        self.g, self.receipt = generation, receipt
        self.check = getattr(generation.checkpoint, "read_check", generation.checkpoint)
        self.owner = None if validate_only else Replay((generation.row.organization_id, generation.row.repository_id, generation.row.id, receipt.stage))
        self.memo, self.inventory, self.resources, self.nodes = {}, {}, [], 0
        self.maps, self.key_connection = {}, None
        self.finding_values, self.registered = {}, False
        self.map_secret = self.owner.secret if self.owner else secrets.token_bytes(32)
        self.steps, self.checked = 0, time.perf_counter()

    def tick(self):
        self.steps += 1
        if self.steps >= 256 or time.perf_counter() - self.checked >= 1:
            self.check()
            self.steps, self.checked = 0, time.perf_counter()

    def map_index(self):
        if self.key_connection is None:
            if self.owner:
                self.key_connection = self.owner.rows.connection
            else:
                # Validation needs only HMAC uniqueness, never payload replay.
                self.key_connection = sqlite3.connect("")
                self.key_connection.execute("PRAGMA journal_mode=OFF")
                self.key_connection.execute("PRAGMA cache_size=-1024")
                self.key_connection.execute("PRAGMA mmap_size=0")
            index(self.key_connection)
        return self.key_connection

    def mutable_frame(self, value, depth=0):
        try:
            plain_row(value, self.tick, depth)
            encode(value, ROW_LIMIT, self.tick, default=unsupported, sort_keys=False)
            return ["J", value]
        except NeedsReference:
            nodes = [0]
            descriptor = self.mutable_node(value, nodes, depth)
            encode(descriptor, ROW_LIMIT, self.tick)
            return ["E", descriptor]

    def mutable_node(self, value, nodes, depth=0):
        from backend.publication_state import FindingRecords
        self.tick()
        nodes[0] += 1
        if depth > 60 or nodes[0] > PAGE_BYTES:
            raise ValueError("Generation context descriptor budget exceeded.")
        if isinstance(value, ContextMap) and value.reader is self:
            return ["map", value.descriptor]
        if isinstance(value, ContextRows) and value.reader is self:
            return self.memo[value.collection][0]
        if isinstance(value, Record):
            self.record(value.id)
            return ["record", value.id]
        if isinstance(value, FindingRecords):
            rows = self.new_rows(value.snapshots(), depth + 1, contract="snapshots")
            return ["findings", self.memo[rows.collection][0]]
        if isinstance(value, dict):
            if len(value) > 8:
                return ["map", self.new_map(value, depth).descriptor]
            if any(type(key) is not str for key in value):
                raise ValueError("Generation context keys must be strings.")
            return ["object", [[key, self.mutable_node(child, nodes, depth + 1)] for key, child in value.items()]]
        if isinstance(value, (list, tuple, set)):
            if len(value) > 8:
                rows = self.new_rows(value, depth)
                result = self.memo[rows.collection][0]
            else:
                result = ["inline", [self.mutable_node(child, nodes, depth + 1) for child in value]]
            return ["set", result] if isinstance(value, set) else result
        if value is None or type(value) in {str, int, float, bool}:
            return ["scalar", value]
        raise TypeError("Unsupported generation context mutation type: " + type(value).__name__)

    def new_rows(self, value, depth, *, contract="mutable"):
        if len(self.memo) >= PAGE_BYTES:
            raise ValueError("Generation context descriptor budget exceeded.")
        collection = max(self.memo, default=-1) + 1
        descriptor = ["rows", collection, 0, 0, 0, "", contract]
        rows = ContextRows(self, collection, contract == "mutable")
        self.memo[collection] = (descriptor, rows)
        for child in value:
            self.tick()
            rows.append_frame(self.mutable_frame(child, depth + 1))
        descriptor[2] = len(rows)
        return rows

    def new_map(self, value, depth):
        rows = self.new_rows((), depth, contract="mapping")
        descriptor = self.memo[rows.collection][0]
        self.map_index()
        result = ContextMap(self, descriptor)
        self.maps[rows.collection] = result
        for key, child in value.items():
            self.tick()
            if type(key) is not str:
                raise ValueError("Generation context keys must be strings.")
            position = len(rows)
            rows.append_frame(self.mutable_frame([key, child], depth + 1))
            admit_key(self.map_index(), self.map_secret, rows.collection, position, key)
            result.count += 1
        descriptor[2] = len(rows)
        return result

    def page(self, collection, number):
        from backend.queue import cipher
        self.check()
        db = self.g.db
        conditions = [*where(self.g, self.context[6]), GenerationContextPart.collection == collection,
                      GenerationContextPart.ordinal == number, GenerationContextPart.expires_at == self.g.row.expires_at,
                      GenerationContextPart.expires_at > now()]
        info = db.execute(select(func.length(GenerationContextPart.ciphertext), GenerationContextPart.digest).where(*conditions)).first()
        if info is None or not 0 < info[0] <= MAX_CIPHER_PAGE:
            raise ValueError("Generation context page is missing or exceeds its byte budget.")
        encrypted = db.scalar(select(GenerationContextPart.ciphertext).where(*conditions))
        packed = cipher().decrypt(encrypted.encode())
        if hashlib.sha256(packed).hexdigest() != info[1]:
            raise ValueError("Generation context page digest is invalid.")
        header, sep, compressed = packed.partition(b"\n")
        if not sep or json.loads(header) != [*self.context, collection, number]:
            raise ValueError("Generation context page identity is invalid.")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, PAGE_BYTES + 1)
        if len(raw) > PAGE_BYTES or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise ValueError("Generation context page compression bound or encoding is invalid.")
        return raw

    def record(self, identity, *, materialize=False):
        from backend.generation_visibility import visible_record
        if type(identity) is not str:
            raise ValueError("Generation context record identity is invalid.")
        query = select(Record if materialize else Record.id).where(Record.id == identity,
            Record.organization_id == self.g.row.organization_id, Record.repository_id == self.g.row.repository_id,
            visible_record(Record.id, self.g.row.id)).execution_options(populate_existing=True)
        record = self.g.db.scalar(query)
        if record is None:
            raise ValueError("Generation context record is unavailable in scope.")
        if materialize:
            self.g.owned_objects.add(record)
        return record

    def validate_node(self, node, depth=0):
        self.nodes += 1
        if depth > 60 or self.nodes > PAGE_BYTES or not isinstance(node, list) or not node:
            raise ValueError("Generation context descriptor budget or type is invalid.")
        tag = node[0]
        if len(node) == 2 and tag == "scalar":
            if node[1] is not None and type(node[1]) not in {str, int, float, bool}:
                raise ValueError("Generation scalar descriptor is invalid.")
        elif len(node) == 2 and tag == "record":
            self.record(node[1])
        elif len(node) == 2 and tag in {"set", "findings"}:
            self.validate_node(node[1], depth + 1)
        elif len(node) == 2 and tag == "map":
            child = node[1]
            if not isinstance(child, list) or len(child) != 7 or child[0] != "rows" or child[-1] != "mapping":
                raise ValueError("Generation map descriptor is invalid.")
            self.validate_node(child, depth + 1)
        elif len(node) == 2 and tag == "inline":
            if not isinstance(node[1], list) or len(node[1]) > 8:
                raise ValueError("Generation inline sequence is invalid.")
            for child in node[1]:
                self.validate_node(child, depth + 1)
        elif len(node) == 2 and tag == "object":
            keys = set()
            for key, child in node[1]:
                if type(key) is not str or key in keys:
                    raise ValueError("Generation object key is invalid or repeated.")
                keys.add(key)
                self.validate_node(child, depth + 1)
        elif tag == "rows" and len(node) == 7:
            self.collection(node, depth)
        else:
            raise ValueError("Generation context descriptor is invalid.")

    def collection(self, descriptor, depth=0):
        _, collection, count, pages, length, digest, contract = descriptor
        if contract not in {"mutable", "snapshots", "mapping"}:
            raise ValueError("Generation collection row contract is invalid.")
        if any(type(n) is not int or n < 0 for n in (collection, count, pages, length)) or pages > self.pointer["pages"]:
            raise ValueError("Generation collection counts are invalid.")
        if collection in self.memo:
            previous, rows = self.memo[collection]
            if previous != descriptor or rows is False:
                raise ValueError("Generation collection reference changed or is cyclic.")
            return
        if len(self.memo) >= PAGE_BYTES:
            raise ValueError("Generation context descriptor budget exceeded.")
        self.memo[collection] = (descriptor, False)
        if contract == "mapping":
            self.map_index()  # Empty maps still need an ordered mutable index.
        rows = ContextRows(self, collection, contract == "mutable") if self.owner else None
        combined, buffer, size, received = hashlib.sha256(), bytearray(), 0, 0
        for number in range(pages):
            raw = self.page(collection, number)
            combined.update(raw)
            size += len(raw)
            buffer.extend(raw)
            while (end := buffer.find(b"\n")) >= 0:
                if not 1 <= end <= ROW_LIMIT + 1 or buffer[0] not in (ord("J"), ord("E")):
                    raise ValueError("Generation context row frame is invalid or oversized.")
                kind, value = chr(buffer[0]), json.loads(buffer[1:end])
                if kind == "E":
                    self.validate_node(value, depth + 1)
                if contract == "mapping":
                    key = entry_key([kind, value])
                    admit_key(self.map_index(), self.map_secret, collection, received, key)
                if rows is not None:
                    rows.append_frame([kind, value])
                received += 1
                if received % 256 == 0:
                    self.check()
                del buffer[:end + 1]
            if len(buffer) > ROW_LIMIT + 1:
                raise ValueError("Generation replay row exceeds its byte budget.")
        if buffer or received != count or size != length or combined.hexdigest() != digest:
            raise ValueError("Generation collection is incomplete or its digest is invalid.")
        self.inventory[collection] = pages
        self.memo[collection] = (descriptor, rows)

    def restore(self, node):
        tag, value = node[:2]
        if tag == "scalar":
            return value
        if tag == "record":
            return self.record(value, materialize=True)
        if tag == "object":
            return {key: self.restore(child) for key, child in value}
        if tag == "inline":
            return [self.restore(child) for child in value]
        if tag == "rows":
            return self.memo[value][1]
        if tag == "map":
            collection = value[1]
            if collection not in self.maps:
                self.maps[collection] = ContextMap(self, value)
            return self.maps[collection]
        if tag == "set":
            return set(self.restore(value))
        if tag == "findings":
            from backend.publication_state import FindingRecords
            collection = value[1]
            if collection not in self.finding_values:
                result = FindingRecords(self.g.db, self.restore(value))
                self.finding_values[collection] = result
                self.resources.append(result.data)
                own = getattr(self.g.checkpoint, "close_on_failure", None)
                if self.registered and own:
                    own(result.data)
            return self.finding_values[collection]
        raise ValueError("Generation context descriptor is invalid.")

    def load(self):
        try:
            if self.receipt.chunk_count != 1:
                raise ValueError("Generation context pointer chunk count is invalid.")
            self.pointer = json.loads("".join(self.g.read_chunks(self.receipt)))
            if set(self.pointer) != {"context", "expires_at", "manifest_pages", "manifest_bytes", "manifest_digest", "pages"}:
                raise ValueError("Generation context pointer schema is invalid.")
            self.context = self.pointer["context"]
            if (not isinstance(self.context, list) or len(self.context) != 8 or
                    self.context != identity(self.g, self.context[6], self.receipt.dependency_digest) or
                    type(self.context[6]) is not str or str(uuid.UUID(self.context[6])) != self.context[6] or
                    self.pointer["expires_at"] != self.g.row.expires_at or self.g.row.expires_at <= now()):
                raise ValueError("Generation context identity or retention is invalid.")
            if (any(type(self.pointer[n]) is not int or self.pointer[n] < 0 for n in ("manifest_pages", "manifest_bytes", "pages"))
                    or not 1 <= self.pointer["manifest_bytes"] <= ROW_LIMIT
                    or self.pointer["manifest_pages"] != (self.pointer["manifest_bytes"] + PAGE_BYTES - 1) // PAGE_BYTES
                    or not self.pointer["manifest_pages"] <= self.pointer["pages"] <= MAX_BYTES // 100):
                raise ValueError("Generation manifest counts are invalid.")
            Writer(self.g, self.receipt.dependency_digest).budget()
            raw = bytearray()
            for number in range(self.pointer["manifest_pages"]):
                raw.extend(self.page(-1, number))
                if len(raw) > ROW_LIMIT:
                    raise ValueError("Generation manifest exceeds its byte budget.")
            if len(raw) != self.pointer["manifest_bytes"] or hashlib.sha256(raw).hexdigest() != self.pointer["manifest_digest"]:
                raise ValueError("Generation manifest digest is invalid.")
            manifest = json.loads(raw)
            if set(manifest) != {"context", "expires_at", "root"} or manifest["context"] != self.context or manifest["expires_at"] != self.g.row.expires_at:
                raise ValueError("Generation manifest identity is invalid.")
            self.validate_node(manifest["root"])
            self.inventory[-1] = self.pointer["manifest_pages"]
            actual = self.g.db.execute(select(GenerationContextPart.collection, func.count(), func.min(GenerationContextPart.ordinal),
                func.max(GenerationContextPart.ordinal)).where(*where(self.g, self.context[6])).group_by(GenerationContextPart.collection)).all()
            if ({c: n for c, n, _, _ in actual} != {c: n for c, n in self.inventory.items() if n}
                    or any((low, high) != (0, n - 1) for _, n, low, high in actual)
                    or sum(self.inventory.values()) != self.pointer["pages"]):
                raise ValueError("Generation context page inventory is invalid.")
            self.check()
            if self.owner is None:
                return None
            result = self.restore(manifest["root"])
            own = getattr(self.g.checkpoint, "close_on_failure", None)
            if own:
                own(self.owner)
                for resource in self.resources:
                    own(resource)
            self.registered = True
            return result
        except BaseException:
            if self.owner:
                self.owner.close()
            for resource in self.resources:
                resource.close()
            raise
        finally:
            if self.owner is None and self.key_connection is not None:
                self.key_connection.close()
