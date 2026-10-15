"""Fenced private output batches, encrypted stage receipts and atomic promotion.

Each stage is a replay boundary. A crash inside a stage replays that stage using
deterministic row identities; a completed stage restores its authenticated state.
No staging transaction changes public visibility.
"""
import hashlib
import json
import uuid
import weakref
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.db import AnalysisInput, Record, Repository, SourceInventoryFile, User, now
from backend.generation_models import (
    AnalysisGeneration,
    GenerationAudit,
    GenerationChunk,
    GenerationReceipt,
    GenerationRecord,
    PublishedGeneration,
)

SCHEMA = "projecttrace-generation-v1"
CHUNK_BYTES = 256_000
BATCH_ROWS = 250
STAGES = ("SNAPSHOT", "EVIDENCE", "CLAIMS", "FINDINGS", "DEPENDENCIES", "CORRELATION",
          "HISTORY", "ARTIFACT_GRAPH", "CONFIGURATION_GRAPH", "FUNCTION_GRAPH",
          "OWNERSHIP_GRAPH", "POLICY", "IMPACT", "FINAL_OUTPUT")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    # Context contains JSON values or explicit references, never Python objects
    # supplied by repository source. No pickle or executable deserialization.
    if isinstance(value, Record):
        return {"$record": value.id}
    from backend.publication_state import FindingRecords
    if isinstance(value, FindingRecords):
        return {"$finding_records": value.snapshots()}
    if isinstance(value, (set, tuple)):
        return {"$set" if isinstance(value, set) else "$tuple": list(value)}
    raise TypeError("Unsupported generation context type: " + type(value).__name__)


class Generation:
    def __init__(self, db, job_id, organization_id, repository_id, signature, checkpoint, *, branch="main", inventory_id, content_key):
        self.db, self.checkpoint = db, checkpoint
        self.pending, self.pending_audits = [], []
        self.pending_rows = {}
        self.finding_updates = {}
        self.stage, self.ordinal, self.reused = "SNAPSHOT", 0, 0
        self.replay_stage = False
        self.published = False
        self.owned_objects = weakref.WeakSet()
        self.batches, self.maximum_batch_rows = 0, 0
        self.user_id = db.get(Record, job_id).data.get("user_id")
        self.checkpoint()
        # Even tokenless synchronous retries serialize generation admission on
        # the durable job. Queue-backed attempts additionally hold their fence.
        db.scalar(select(Record).where(Record.id == job_id).with_for_update())
        db.scalar(select(Repository).where(Repository.id == repository_id).with_for_update())
        identity = str(uuid.uuid5(uuid.NAMESPACE_URL, SCHEMA + ":" + job_id + ":" + signature))
        self.generation_id = identity
        self.row = db.get(AnalysisGeneration, identity)
        if self.row is None:
            retained = db.get(AnalysisInput, job_id)
            pointer = db.get(PublishedGeneration, (organization_id, repository_id, branch))
            self.row = AnalysisGeneration(id=identity, job_id=job_id, organization_id=organization_id,
                repository_id=repository_id, signature=signature, content_key=content_key,
                state="STAGING", branch=branch, inventory_id=inventory_id,
                expected_pointer_revision=pointer.revision if pointer else 0,
                expires_at=min(retained.expires_at if retained else "9999",
                               (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()))
            db.add(self.row)
            db.flush()
        if (self.row.organization_id, self.row.repository_id, self.row.job_id, self.row.signature) != (
                organization_id, repository_id, job_id, signature):
            raise ValueError("Generation scope or source signature is invalid.")
        if self.row.state not in {"STAGING", "VALIDATED"}:
            raise ValueError("Generation is not available for staging.")
        if self.row.expires_at <= now() or self.row.branch != branch or self.row.inventory_id != inventory_id or self.row.content_key != content_key:
            raise ValueError("Generation retention or branch identity is invalid.")
        db.commit()
        self.snapshot_id = self.row.snapshot_id
        db.info["analysis_generation"] = self

    def fence(self):
        self.checkpoint()
        from backend.governance import authorize_job
        actor = self.db.get(User, self.user_id, populate_existing=True)
        job = self.db.get(Record, self.row.job_id)
        if not actor:
            raise ValueError("Generation actor is unavailable.")
        repo = self.db.get(Repository, self.row.repository_id)
        authorize_job(self.db, actor, repo, source=job.data.get("source", "INVENTORY"))

    def enter(self, stage):
        if stage not in STAGES:
            raise ValueError("Unknown generation stage.")
        self.stage, self.ordinal = stage, 0
        self.replay_stage = self.db.scalar(select(GenerationRecord.record_id).where(
            GenerationRecord.generation_id == self.row.id, GenerationRecord.stage == stage).limit(1)) is not None

    def identity(self, kind, data):
        self.ordinal += 1
        name = self.stage + ":" + str(self.ordinal)
        if kind in {"edge", "graph_node"}:
            # Shared graph declarations and relationships have one row even if
            # multiple independent producers discover them.
            name = kind + ":" + digest(json.dumps(data, sort_keys=True).encode())
        return str(uuid.uuid5(uuid.UUID(self.row.id), name))

    def register(self, record):
        self.owned_objects.add(record)
        if record.kind == "snapshot":
            self.snapshot_id = record.id
        self.pending.append((record.id, self.stage, self.ordinal))
        self.pending_rows[record.id] = record

    def batch(self):
        if not (self.pending or self.pending_audits or self.finding_updates or self.db.new or self.db.dirty):
            return
        self.fence()
        for row in list(self.db.new) + list(self.db.dirty):
            if self.snapshot_id and (getattr(row, "snapshot_id", None) == self.snapshot_id or
                                     getattr(row, "introduced_snapshot_id", None) == self.snapshot_id):
                self.owned_objects.add(row)
        self.db.flush()  # Establish parent Records before composite ownership FKs.
        if self.pending:
            self.db.execute(GenerationRecord.__table__.insert(), [dict(record_id=identity, generation_id=self.row.id,
                organization_id=self.row.organization_id, repository_id=self.row.repository_id,
                stage=stage, ordinal=ordinal) for identity, stage, ordinal in self.pending])
        if self.pending_audits:
            self.db.execute(GenerationAudit.__table__.insert(), [dict(event_id=event_id, activity_id=activity_id,
                generation_id=self.row.id, organization_id=self.row.organization_id,
                repository_id=self.row.repository_id) for event_id, activity_id in self.pending_audits])
        if self.finding_updates:
            from sqlalchemy import exists, update
            from sqlalchemy.orm.attributes import set_committed_value
            for identity, data in self.finding_updates.items():
                owned = exists(select(GenerationRecord.record_id).where(GenerationRecord.record_id == Record.id,
                    GenerationRecord.generation_id == self.row.id))
                changed = self.db.execute(update(Record.__table__).where(Record.id == identity, Record.kind == "finding",
                    Record.organization_id == self.row.organization_id, Record.repository_id == self.row.repository_id,
                    owned).values(data=data, version=Record.version + 1).returning(Record.version)).scalar_one()
                cached = self.db.identity_map.get((Record, (identity,), None))
                if cached is not None:
                    set_committed_value(cached, "data", data)
                    set_committed_value(cached, "version", changed)
        self.db.flush()
        self.fence()  # The accepted fence remains locked through this commit.
        self.db.commit()
        performance = getattr(self.checkpoint, "performance", None)
        if performance:
            performance.count("generation_staging_batches")
            performance.count("generation_inserted_records", len(self.pending))
            with performance.lock:
                performance.counters["generation_maximum_batch_records"] = max(
                    performance.counters["generation_maximum_batch_records"], len(self.pending))
        self.batches += 1
        self.maximum_batch_rows = max(self.maximum_batch_rows, len(self.pending))
        self.pending.clear()
        self.pending_rows.clear()
        self.pending_audits.clear()
        self.finding_updates.clear()

    def dependencies(self, stage):
        previous = STAGES[:STAGES.index(stage)]
        receipts = []
        for name in previous:
            row = self.db.get(GenerationReceipt, (self.row.id, name))
            if row is None:
                raise ValueError("Generation dependency is incomplete: " + name)
            receipts.append([name, row.digest])
        return digest(json.dumps(receipts).encode())

    def _chunk(self, stage, ordinal, raw):
        from backend.queue import cipher
        envelope = json.dumps({"identity": [SCHEMA, self.row.id, self.row.organization_id,
            self.row.repository_id, self.row.signature, stage, ordinal], "data": raw}).encode()
        row = self.db.get(GenerationChunk, (self.row.id, stage, ordinal))
        if row is None:
            row = GenerationChunk(generation_id=self.row.id, stage=stage, ordinal=ordinal,
                organization_id=self.row.organization_id, repository_id=self.row.repository_id)
            self.db.add(row)
        row.ciphertext, row.digest = cipher().encrypt(envelope).decode(), digest(envelope)
        self.batch()

    def save(self, stage, state):
        if self.db.get(GenerationReceipt, (self.row.id, stage)):
            raise ValueError("Completed generation receipt is immutable.")
        dependency_digest = self.dependencies(stage)
        self.batch()
        if stage == "SNAPSHOT":
            self.row.snapshot_id = state["snapshot"].id
            self.batch()
        combined, buffer, count = hashlib.sha256(), "", 0
        size = 0
        for part in json.JSONEncoder(default=encoded, ensure_ascii=True, separators=(",", ":")).iterencode(state):
            # Slice single long strings too; do not let one encoder part exceed
            # the encrypted chunk bound. Total context memory is qualified apart.
            for offset in range(0, len(part), CHUNK_BYTES):
                size += len(part[offset:offset + CHUNK_BYTES])
                if size > 64_000_000:
                    raise ValueError("Generation stage context exceeds its bounded byte budget.")
                buffer += part[offset:offset + CHUNK_BYTES]
                while len(buffer) >= CHUNK_BYTES:
                    raw, buffer = buffer[:CHUNK_BYTES], buffer[CHUNK_BYTES:]
                    combined.update(raw.encode())
                    self._chunk(stage, count, raw)
                    count += 1
        if buffer or count == 0:
            combined.update(buffer.encode())
            self._chunk(stage, count, buffer)
            count += 1
        records = self.db.scalar(select(func.count()).select_from(GenerationRecord).where(
            GenerationRecord.generation_id == self.row.id, GenerationRecord.stage == stage))
        self.db.add(GenerationReceipt(generation_id=self.row.id, stage=stage,
            organization_id=self.row.organization_id, repository_id=self.row.repository_id,
            dependency_digest=dependency_digest, digest=combined.hexdigest(), chunk_count=count,
            record_count=records))
        self.batch()

    def read_chunks(self, receipt):
        from backend.queue import cipher
        combined = hashlib.sha256()
        for ordinal in range(receipt.chunk_count):
            row = self.db.get(GenerationChunk, (self.row.id, receipt.stage, ordinal))
            if row is None or (row.organization_id, row.repository_id) != (
                    self.row.organization_id, self.row.repository_id):
                raise ValueError("Generation receipt chunk is unavailable in scope.")
            raw = cipher().decrypt(row.ciphertext.encode())
            if digest(raw) != row.digest:
                raise ValueError("Generation chunk digest is invalid.")
            envelope = json.loads(raw)
            if envelope.get("identity") != [SCHEMA, self.row.id, self.row.organization_id,
                    self.row.repository_id, self.row.signature, receipt.stage, ordinal]:
                raise ValueError("Generation chunk identity is invalid.")
            value = envelope["data"]
            if len(value) > CHUNK_BYTES:
                raise ValueError("Generation chunk exceeds its byte budget.")
            combined.update(value.encode())
            yield value
        if combined.hexdigest() != receipt.digest:
            raise ValueError("Generation receipt digest is invalid.")

    def load(self, stage):
        self.enter(stage)
        receipt = self.db.get(GenerationReceipt, (self.row.id, stage))
        if receipt is None:
            return None
        if receipt.dependency_digest != self.dependencies(stage):
            raise ValueError("Generation dependency digest is invalid.")

        def decode(value):
            if set(value) == {"$finding_records"}:
                from backend.publication_state import FindingRecords
                return FindingRecords(self.db, value["$finding_records"])
            if set(value) == {"$record"}:
                record = self.db.get(Record, value["$record"])
                if record is None or (record.organization_id, record.repository_id) != (
                        self.row.organization_id, self.row.repository_id):
                    raise ValueError("Generation context record is unavailable in scope.")
                owner = self.db.get(GenerationRecord, record.id)
                if owner and owner.generation_id == self.row.id:
                    self.owned_objects.add(record)
                return record
            if set(value) == {"$set"}:
                return set(value["$set"])
            if set(value) == {"$tuple"}:
                return tuple(value["$tuple"])
            return value
        self.reused += 1
        return json.loads("".join(self.read_chunks(receipt)), object_hook=decode)

    def validate(self, snapshot):
        """Validate with bounded row reads before the short promotion transaction."""
        self.batch()
        for stage in STAGES:
            receipt = self.db.get(GenerationReceipt, (self.row.id, stage))
            if receipt is None or receipt.dependency_digest != self.dependencies(stage):
                raise ValueError("Generation is missing a valid required receipt: " + stage)
            if (receipt.organization_id, receipt.repository_id) != (self.row.organization_id, self.row.repository_id) or not 1 <= receipt.chunk_count <= 250:
                raise ValueError("Generation receipt scope or chunk count is invalid.")
            actual = self.db.scalar(select(func.count()).select_from(GenerationRecord).where(
                GenerationRecord.generation_id == self.row.id, GenerationRecord.stage == stage))
            if actual != receipt.record_count:
                raise ValueError("Generation receipt record count is invalid.")
            for _ in self.read_chunks(receipt):
                pass
            self.fence()
            self.db.commit()
        previous_stage, previous_ordinal, count, snapshots, validation = "", 0, 0, [], hashlib.sha256()
        from backend.repository_store import BlobStore
        store = BlobStore()
        captured = {}
        for kind, field in (("claim", "claims"), ("finding", "findings"), ("dependency", "dependencies"),
                            ("drift", "drifts"), ("risk_path", "risk_paths"), ("cloud", "cloud_assets")):
            items = snapshot.data.get(field, [])
            captured[kind] = {item["id"]: item for item in items}
            if len(captured[kind]) != len(items):
                raise ValueError("Generation snapshot contains duplicate captured identities.")
        node_kinds = {"claim", "finding", "graph_node", "dependency", "evidence"}
        while True:
            from sqlalchemy import or_
            rows = self.db.execute(select(Record.id, Record.kind, Record.data, GenerationRecord.stage, GenerationRecord.ordinal).join(
                GenerationRecord, GenerationRecord.record_id == Record.id).where(
                GenerationRecord.generation_id == self.row.id, or_(GenerationRecord.stage > previous_stage,
                    (GenerationRecord.stage == previous_stage) & (GenerationRecord.ordinal > previous_ordinal)))
                .order_by(GenerationRecord.stage, GenerationRecord.ordinal).limit(BATCH_ROWS)).all()
            if not rows:
                break
            references, required_types = set(), {}

            def reference(identity, kinds):
                references.add(identity)
                required_types[identity] = required_types.get(identity, node_kinds) & kinds

            for row in rows:
                validation.update(json.dumps([row.id, row.kind, row.data], sort_keys=True, separators=(",", ":")).encode())
                count += 1
                data = row.data
                captured_kind = "cloud" if row.kind == "graph_node" and row.id in captured["cloud"] else row.kind
                if captured_kind in captured:
                    expected = captured[captured_kind].pop(row.id, None)
                    if expected is None:
                        raise ValueError("Generation output is absent from its captured snapshot.")
                    expected = {key: value for key, value in expected.items() if key != "id"}
                    actual = {key: data.get(key) for key in expected}
                    if json.dumps(expected, sort_keys=True) != json.dumps(actual, sort_keys=True):
                        raise ValueError("Generation output and captured snapshot are inconsistent.")
                scope = data.get("scope", {})
                if scope.get("snapshot_id", snapshot.id) != snapshot.id or scope.get("organization_id", self.row.organization_id) != self.row.organization_id:
                    raise ValueError("Generation output snapshot scope is invalid.")
                if row.kind == "edge":
                    if data.get("snapshot_id") != snapshot.id:
                        raise ValueError("Generation graph edge snapshot is invalid.")
                    reference(data["source"], node_kinds)
                    reference(data["target"], node_kinds)
                if row.kind == "snapshot":
                    snapshots.append(row.id)
                if row.kind == "evidence":
                    source = self.db.get(SourceInventoryFile, (self.row.inventory_id, data["path"]))
                    if source is None or source.digest != data["hash"]:
                        raise ValueError("Generation evidence does not match its immutable source inventory.")
                    store.read(self.row.organization_id, data["source_blob_digest"])
                if row.kind == "claim" and not set(data.get("supporting_ids", []) + data.get("contradicting_ids", [])) <= set(data.get("evidence_ids", [])):
                    raise ValueError("Generation claim association is invalid.")
                if row.kind == "finding" and data.get("claim_id"):
                    reference(data["claim_id"], {"claim"})
                for identity in data.get("evidence_ids", []):
                    reference(identity, {"evidence"})
                if row.kind == "risk_path":
                    for identity in data.get("node_ids", []):
                        reference(identity, node_kinds)
            references = sorted(references)
            for offset in range(0, len(references), BATCH_ROWS):
                selected = references[offset:offset + BATCH_ROWS]
                found = dict(self.db.execute(select(GenerationRecord.record_id, Record.kind).select_from(GenerationRecord)
                    .join(Record, Record.id == GenerationRecord.record_id).where(
                        GenerationRecord.generation_id == self.row.id, GenerationRecord.record_id.in_(selected))).all())
                if set(selected) != set(found) or any(found[identity] not in required_types[identity] for identity in selected):
                    raise ValueError("Generation has an unresolved graph/evidence reference.")
            previous_stage, previous_ordinal = rows[-1].stage, rows[-1].ordinal
            self.fence()
            self.db.commit()
        if snapshots != [snapshot.id] or snapshot.data.get("job_id") != self.row.job_id or snapshot.data.get("branch") != self.row.branch:
            raise ValueError("Generation must contain exactly its own job snapshot.")
        if any(captured.values()):
            raise ValueError("Generation snapshot references missing captured output.")
        self.row.snapshot_id, self.row.state = snapshot.id, "VALIDATED"
        self.row.validation_digest, self.row.validation_records = validation.hexdigest(), count
        self.batch()

    def promote(self, snapshot):
        self.fence()
        from analyzers.engine import PARSER_SIGNATURE, VERSION
        from backend.db import NativeProfile
        from backend.quality_profiles import effective
        # Profile rows may have changed since global computation or a restored
        # stage receipt. Refresh their identity-map state before comparing the
        # captured profile/version lineage; an old decision cannot publish as
        # the current configuration after an administrator changes it.
        lineage = snapshot.data.get("native_profile", {}).get("profile_lineage", [])
        if len(lineage) > 3:
            raise ValueError("Generation profile lineage is invalid.")
        if lineage:
            list(self.db.scalars(select(NativeProfile).where(NativeProfile.organization_id == self.row.organization_id,
                 NativeProfile.id.in_([item["id"] for item in lineage])).execution_options(populate_existing=True)))
        profile, _ = effective(self.db, self.row.organization_id, self.row.repository_id)
        if (snapshot.data.get("analyzer_version"), snapshot.data.get("parser_signature")) != (VERSION, PARSER_SIGNATURE) or snapshot.data.get("native_profile") != profile:
            raise ValueError("Generation analyzer or configuration changed before publication; a fresh analysis is required.")
        current = self.db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.id == self.row.id)
                                 .with_for_update().execution_options(populate_existing=True))
        if current.state != "VALIDATED" or current.snapshot_id != snapshot.id or not current.validation_digest:
            raise ValueError("Only a validated generation can be published.")
        key = (self.row.organization_id, self.row.repository_id, snapshot.data["branch"])
        self.db.scalar(select(Repository).where(Repository.id == self.row.repository_id).with_for_update())
        pointer = self.db.get(PublishedGeneration, key, with_for_update=True)
        if (pointer.revision if pointer else 0) != self.row.expected_pointer_revision:
            from backend.scheduling import JobCancelled
            raise JobCancelled("A newer generation was published before this generation could be promoted.")
        if pointer is None:
            pointer = PublishedGeneration(organization_id=key[0], repository_id=key[1], branch=key[2],
                                          generation_id=self.row.id)
            self.db.add(pointer)
        else:
            pointer.generation_id, pointer.revision = self.row.id, pointer.revision + 1
        current.state, current.published_at = "PUBLISHED", now()
        # The caller commits pointer, visibility, terminal job and cleanup together.


def clear(db):
    context = db.info.pop("analysis_generation", None)
    if context and not context.published:
        # Session.get can otherwise return a cached private object without
        # issuing the default visibility query after the worker context ends.
        # ORM refreshes of expired cached instances do not apply loader criteria.
        # Weak ownership tracking detaches only live private objects without
        # retaining repository-wide ORM state or querying an interrupted DB.
        from sqlalchemy import inspect
        for row in list(context.owned_objects):
            if inspect(row).session is db:
                db.expunge(row)


def purge_expired_chunks(db, *, limit=250):
    """Retain every snapshot/graph/receipt; expire only private context chunks.

    An active worker owns its input retention window. Maintenance never removes
    its recovery context. Expired unfinished generations remain hidden forever.
    """
    from sqlalchemy import exists

    from backend.db import QueueEntry
    active = exists(select(QueueEntry.job_id).where(QueueEntry.job_id == AnalysisGeneration.job_id,
                    QueueEntry.state == "RUNNING", QueueEntry.lease_expires_at > now()))
    eligible = select(AnalysisGeneration.id).where(AnalysisGeneration.expires_at <= now(), ~active)
    count = 0
    for chunk in db.scalars(select(GenerationChunk).where(GenerationChunk.generation_id.in_(eligible))
                           .order_by(GenerationChunk.generation_id, GenerationChunk.stage, GenerationChunk.ordinal)
                           .limit(limit)):
        db.delete(chunk)
        count += 1
    for row in db.scalars(select(AnalysisGeneration).where(AnalysisGeneration.id.in_(eligible),
                         AnalysisGeneration.state.in_(["STAGING", "VALIDATED"])).limit(limit)):
        row.state = "ABANDONED"
    return count
