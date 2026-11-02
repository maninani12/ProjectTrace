"""Owned complete context, admission, bounded decoding and recovery contracts."""
import hashlib
import json
import os
import zlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from analyzers.observation_store import EncryptedRows
from backend.db import Record
from backend.domain import add
from backend.generation_context import PAGE_BYTES, Reader
from backend.generation_models import GenerationChunk, GenerationContextPart, GenerationReceipt, PublishedGeneration
from backend.generations import Generation, encoded, purge_expired_chunks
from backend.queue import cipher
from tests.test_repository_store import captured, storage  # noqa: F401


def context(storage):  # noqa: F811
    db, user, repo = storage
    files = captured(storage, {"owned.py": "pass\n"})
    job = add(db, user.organization_id, repo.id, "job", {"source": "INVENTORY", "user_id": user.id})
    db.commit()
    generation = Generation(db, job.id, user.organization_id, repo.id, "a" * 64, lambda: None,
        inventory_id=files.inventory_id, content_key="b" * 64)
    snapshot = add(db, user.organization_id, repo.id, "snapshot", {"branch": "main"}, "owned-snapshot")
    return generation, {"snapshot": snapshot}


def fingerprint(value):
    combined = hashlib.sha256()
    # Sets have no order contract; compare their complete members canonically.
    def canonical(item):
        return {"$set": sorted(item)} if isinstance(item, set) else encoded(item)
    for part in json.JSONEncoder(default=canonical, sort_keys=True).iterencode(value):
        combined.update(part.encode())
    return combined.hexdigest()


def test_complete_large_context_shared_rows_fresh_session_and_mutation(storage, monkeypatch):  # noqa: F811
    import backend.generation_context as codec
    # Lower the test envelope; production remains unchanged at 64,000,000.
    monkeypatch.setattr(codec, "MAX_BYTES", 1_000_000)
    generation, state = context(storage)
    db = generation.db
    rows = EncryptedRows(("owned",))
    for number in range(180):
        rows.append({"path": "owned.py", "number": number, "text": "complete output " * 1000})
    state.update({"metrics": rows, "quality": {"metrics": rows}, "literal": {"$record": "ordinary JSON"},
                  "references": [(state["snapshot"], str(n)) for n in range(10)], "ids": {"a", "b"}})
    original = fingerprint(state)
    generation.save("SNAPSHOT", state)
    receipt = db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT"))
    assert receipt.format_version == 2 and receipt.chunk_count == 1
    size = db.scalar(select(func.sum(func.length(GenerationContextPart.ciphertext))))
    assert size < 1_000_000
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0
    identity = generation.row.id
    args = (generation.row.job_id, generation.row.organization_id, generation.row.repository_id, generation.row.signature)
    inventory, content_key = generation.row.inventory_id, generation.row.content_key
    db.info.pop("analysis_generation", None)
    db.expunge_all()
    with sessionmaker(db.get_bind(), expire_on_commit=False)() as fresh:
        replay = Generation(fresh, *args, lambda: None, inventory_id=inventory, content_key=content_key)
        assert replay.row.id == identity
        restored = replay.load("SNAPSHOT")
        assert fingerprint(restored) == original
        assert restored["metrics"] is restored["quality"]["metrics"]
        assert restored["references"][0][0].id == restored["snapshot"].id
        assert restored["literal"] == {"$record": "ordinary JSON"}
        metrics = restored["metrics"]
        metrics._replace(0, {**metrics[0], "new_code": True})
        assert next(metrics.for_path("owned.py"))["new_code"]
        receipt = fresh.get(GenerationReceipt, (identity, "SNAPSHOT"))
        Reader(replay, receipt, validate_only=True).load()
        metrics.close()
    rows.close()


def test_legacy_receipt_still_restores_records_sets_and_complete_json(storage):  # noqa: F811
    generation, state = context(storage)
    state.update({"values": list(range(40)), "ids": {"old"}})
    expected = fingerprint(state)
    generation._save_legacy("SNAPSHOT", state)
    assert generation.db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")).format_version == 1
    assert fingerprint(generation.load("SNAPSHOT")) == expected


@pytest.mark.parametrize("damage", ["missing", "bitflip", "scope", "digest", "bomb", "swapped", "extra", "expiry"])
def test_corrupt_pages_fail_closed_without_publication(storage, damage):  # noqa: F811
    generation, state = context(storage)
    state["rows"] = [{"path": "owned.py", "text": "row data " * 5000} for _ in range(30)]
    generation.save("SNAPSHOT", state)
    db = generation.db
    parts = list(db.scalars(select(GenerationContextPart).where(GenerationContextPart.collection == 0)
                           .order_by(GenerationContextPart.ordinal)))
    assert len(parts) > 1
    part = parts[0]
    if damage == "missing":
        db.delete(part)
    elif damage == "bitflip":
        part.ciphertext = part.ciphertext[:-8] + "aaaaaaaa"
    elif damage == "digest":
        part.digest = "0" * 64
    elif damage in {"scope", "bomb"}:
        packed = cipher().decrypt(part.ciphertext.encode())
        header, _, compressed = packed.partition(b"\n")
        if damage == "scope":
            fields = json.loads(header)
            fields[2] = "another-tenant"
            header = json.dumps(fields).encode()
        else:
            compressed = zlib.compress(b"x" * (PAGE_BYTES + 1))
        packed = header + b"\n" + compressed
        part.ciphertext, part.digest = cipher().encrypt(packed).decode(), hashlib.sha256(packed).hexdigest()
    elif damage == "swapped":
        part.ciphertext, parts[1].ciphertext = parts[1].ciphertext, part.ciphertext
        part.digest, parts[1].digest = parts[1].digest, part.digest
    elif damage == "extra":
        db.add(GenerationContextPart(generation_id=part.generation_id, stage=part.stage, attempt=part.attempt,
            collection=99, ordinal=0, organization_id=part.organization_id, repository_id=part.repository_id,
            ciphertext=part.ciphertext, digest=part.digest, expires_at=part.expires_at))
    else:
        part.expires_at = "2000-01-01"
    db.commit()
    with pytest.raises(Exception):
        generation.load("SNAPSHOT")
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0


def test_incompressible_budget_rejects_receipt_and_cleans_only_staging(storage, monkeypatch):  # noqa: F811
    import backend.generation_context as codec
    monkeypatch.setattr(codec, "MAX_BYTES", 300_000)
    generation, state = context(storage)
    state["values"] = [os.urandom(10000).hex() for _ in range(40)]
    with pytest.raises(ValueError, match="bounded byte budget"):
        generation.save("SNAPSHOT", state)
    assert generation.db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")) is None
    assert generation.db.scalar(select(func.count()).select_from(GenerationContextPart)) == 0


def test_cancel_write_and_replay_then_retry_complete(storage):  # noqa: F811
    generation, state = context(storage)
    state["values"] = ["complete " * 6000 for _ in range(20)]
    db = generation.db
    check = generation.checkpoint
    def cancel_write():
        if db.scalar(select(func.count()).select_from(GenerationContextPart)):
            raise RuntimeError("owned cancellation")
    check.read_check = cancel_write
    with pytest.raises(RuntimeError, match="owned cancellation"):
        generation.save("SNAPSHOT", state)
    assert db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")) is None
    assert db.scalar(select(func.count()).select_from(GenerationContextPart)) == 0
    check.read_check = lambda: None
    generation.save("SNAPSHOT", state)
    expected = fingerprint(state)
    check.read_check = lambda: (_ for _ in ()).throw(RuntimeError("owned cancellation"))
    with pytest.raises(RuntimeError, match="owned cancellation"):
        generation.load("SNAPSHOT")
    check.read_check = lambda: None
    restored = generation.load("SNAPSHOT")
    assert fingerprint(restored) == expected
    restored["values"].close()


def test_lost_commit_ack_preserves_admitted_receipt_and_retry(storage, monkeypatch):  # noqa: F811
    generation, state = context(storage)
    state["values"] = list(range(20))
    expected = fingerprint(state)
    db = generation.db
    commit = db.commit
    interrupted = False
    def lose_ack():
        nonlocal interrupted
        admitted = db.scalar(select(func.count()).select_from(GenerationReceipt)) > 0
        commit()
        if admitted and not interrupted:
            interrupted = True
            raise RuntimeError("lost acknowledgement")
    monkeypatch.setattr(db, "commit", lose_ack)
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        generation.save("SNAPSHOT", state)
    assert db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")) is not None
    assert fingerprint(generation.load("SNAPSHOT")) == expected
    with pytest.raises(ValueError, match="immutable"):
        generation.save("SNAPSHOT", state)


def test_interleaved_tokenless_writer_cannot_admit_reaped_pages(storage, monkeypatch):  # noqa: F811
    from backend.generation_context import Writer
    generation, state = context(storage)
    state["values"] = ["original complete " * 5000 for _ in range(12)]
    page, started = Writer.page, False
    def interleave(writer, collection, raw):
        nonlocal started
        page(writer, collection, raw)
        if not started and collection >= 0:
            started = True
            generation.save("SNAPSHOT", {"snapshot": state["snapshot"], "winner": True})
    monkeypatch.setattr(Writer, "page", interleave)
    with pytest.raises(ValueError, match="immutable|inventory"):
        generation.save("SNAPSHOT", state)
    assert generation.load("SNAPSHOT")["winner"] is True


def test_foreign_record_scope_rejected_and_expiry_reclamation_is_batched(storage):  # noqa: F811
    generation, state = context(storage)
    state["foreign"] = Record(id="another", organization_id="another", repository_id="another", kind="snapshot", data={})
    with pytest.raises(ValueError, match="scope"):
        generation.save("SNAPSHOT", state)
    del state["foreign"]
    state["values"] = ["complete " * 6000 for _ in range(20)]
    generation.save("SNAPSHOT", state)
    db = generation.db
    count = db.scalar(select(func.count()).select_from(GenerationContextPart))
    generation.row.expires_at = "2000-01-01"
    db.commit()
    assert purge_expired_chunks(db, limit=2) == 2
    db.commit()
    assert db.scalar(select(func.count()).select_from(GenerationContextPart)) == count - 1
    assert db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")) is not None
    assert db.scalar(select(func.count()).select_from(GenerationChunk)) == 0


def test_dictionary_iteration_order_survives_replay(storage):  # noqa: F811
    generation, state = context(storage)
    state["evidence"] = {"z-last-alphabetically": 1, "a-first-alphabetically": 2}
    state["rows"] = [{"z": i, "a": i} for i in range(12)]
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")
    assert list(restored) == list(state)
    assert list(restored["evidence"]) == list(state["evidence"])
    assert list(restored["rows"][0]) == list(state["rows"][0])


def test_mutable_finding_rows_keep_live_identity_nested_updates_and_bounded_cache(storage):  # noqa: F811
    import gc
    generation, state = context(storage)
    state["findings"] = [{"path": "owned.py", "delta": "NEW", "nested": {"lines": [1, 2]}} for _ in range(350)]
    generation.save("SNAPSHOT", state)
    rows = generation.load("SNAPSHOT")["findings"]
    first, again = rows[0], rows[0]
    assert first is again
    first["delta"] = "EXISTING"
    first["nested"]["lines"].append(3)
    assert again["nested"]["lines"] == [1, 2, 3]
    first.update(owner="owned")
    first.setdefault("labels", []).extend(["a", "b"])
    labels = first["labels"]
    first["labels"] += ["c"]
    assert first["labels"] is labels
    labels.remove("c")
    first["labels"].pop()
    del first["owner"]
    expected = json.loads(json.dumps(first))
    # A retained nested view deliberately keeps its row alive too.
    assert len(rows.live) == 1
    del first, again, labels
    for row in rows:
        assert row["path"] == "owned.py"
    del row
    gc.collect()
    assert len(rows.live) == 0
    assert rows[0] == expected
    assert next(rows.for_path("owned.py"))["delta"] == "EXISTING"
    rows.close()


def test_cancellation_during_payload_replay_closes_owner_and_keeps_receipt(storage, monkeypatch):  # noqa: F811
    import backend.generation_context as codec
    generation, state = context(storage)
    state["rows"] = [{"path": "owned.py", "value": "complete " * 700} for _ in range(300)]
    generation.save("SNAPSHOT", state)
    seen, replay = [], codec.Replay
    def observe(scope):
        owner = replay(scope)
        seen.append(owner)
        return owner
    monkeypatch.setattr(codec, "Replay", observe)
    def cancel():
        if seen and len(seen[0].rows) > 0:
            raise RuntimeError("owned replay cancellation")
    generation.checkpoint.read_check = cancel
    with pytest.raises(RuntimeError, match="owned replay cancellation"):
        generation.load("SNAPSHOT")
    assert seen[0].rows.closed
    assert generation.db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")) is not None
