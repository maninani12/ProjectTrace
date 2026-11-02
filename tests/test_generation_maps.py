"""Indexed context map regressions; complete values and original key order."""
import hashlib
import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import JSON, Column, Integer, MetaData, Table, func, select
from sqlalchemy.orm import sessionmaker

from backend.context_maps import ContextMap
from backend.generation_context import Reader, Writer
from backend.generation_models import GenerationContextPart, GenerationReceipt, GenerationRecord
from backend.generations import Generation, encoded
from tests.test_generation_context import context
from tests.test_repository_store import storage  # noqa: F401


def test_ten_thousand_entry_dictionary_round_trip(storage, monkeypatch):  # noqa: F811
    generation, state = context(storage)
    values = {str(i): {f"owned_{j}": j for j in range(28)} for i in range(10000)}
    assert len(json.dumps({"claims_by_id": values}, separators=(",", ":")).encode()) == 3_808_908
    state["claims_by_id"] = values
    counters = []
    save = Writer.save
    def observed(writer, source):
        save(writer, source)
        counters.append((writer.nodes, len(writer.memo), len(writer.maps)))
    monkeypatch.setattr(Writer, "save", observed)
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")["claims_by_id"]
    assert len(restored) == len(values)
    assert list(restored) == list(values)
    assert isinstance(restored, ContextMap)
    assert dict.__len__(restored) == 1
    assert counters == [(3, 1, 1)]
    for key, value in values.items():
        assert restored[key] == value
    assert json.loads(json.dumps(restored)) == values
    assert restored == values and values == restored
    assert json.loads(json.dumps(restored, sort_keys=True)) == values
    receipt = generation.db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT"))
    Reader(generation, receipt, validate_only=True).load()


def streaming_hash(value):
    combined = hashlib.sha256()
    for part in json.JSONEncoder(default=encoded, separators=(",", ":")).iterencode(value):
        combined.update(part.encode())
    return combined.hexdigest()


def test_nested_maps_sequences_and_typed_references_round_trip(storage):  # noqa: F811
    generation, state = context(storage)
    shared = {f"key-{n}": {"literal": {"$record": "ordinary data"}, "order": n} for n in range(200)}
    typed = {f"z-{n}": {"reference": state["snapshot"], "label": str(n)} for n in reversed(range(30))}
    state["maps"] = {"shared": shared, "alias": shared, "typed": typed,
                     "nested": {"large_sequence": list(range(500))}}
    expected = streaming_hash(state)
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")
    assert streaming_hash(restored) == expected
    assert restored["maps"]["shared"] is restored["maps"]["alias"]
    for key, value in restored["maps"]["typed"].items():
        assert value["reference"].id == state["snapshot"].id
        assert value["label"] == typed[key]["label"]
    assert list(restored["maps"]["typed"]) == list(typed)
    assert list(restored["maps"]["nested"]["large_sequence"]) == list(range(500))


def test_map_mutations_keep_order_and_complete_values_through_another_receipt(storage):  # noqa: F811
    generation, state = context(storage)
    source = {f"z-{n}": {"number": n, "nested": {"lines": [1, 2]}} for n in reversed(range(180))}
    state["map"] = source
    generation.save("SNAPSHOT", state)
    value = generation.load("SNAPSHOT")["map"]
    first = value["z-179"]
    assert first is value["z-179"]
    first["number"] = -1
    first["nested"]["lines"].append(3)
    source["z-179"]["number"] = -1
    source["z-179"]["nested"]["lines"].append(3)
    value["z-178"] = {"replaced": True}
    source["z-178"] = {"replaced": True}
    value.pop("z-177")
    del source["z-177"]
    value["z-177"] = {"reinserted": True}
    source["z-177"] = {"reinserted": True}
    value.setdefault("new", {"lines": []})["lines"].extend([4, 5])
    source["new"] = {"lines": [4, 5]}
    value.update(extra={"complete": True})
    source.update(extra={"complete": True})
    assert value == source
    assert list(value) == list(source)
    assert list(reversed(value)) == list(reversed(source))
    assert json.loads(json.dumps(value)) == source
    # Mutable values containing application references remain typed, including
    # references inside a newly inserted large private map and sequence.
    value["typed"] = {"record": state["snapshot"], "detail": {"lines": [1]}}
    value["typed"]["detail"]["lines"].append(2)
    value["large"] = {str(i): {"record": state["snapshot"], "items": list(range(12))} for i in range(10)}
    value["large"]["0"]["items"].append(12)
    expected = streaming_hash(value)
    generation.enter("EVIDENCE")
    generation.save("EVIDENCE", {"map": value})
    replayed = generation.load("EVIDENCE")["map"]
    assert streaming_hash(replayed) == expected
    assert list(replayed) == list(value)
    assert replayed["typed"]["detail"]["lines"] == [1, 2]
    assert list(replayed["large"]["0"]["items"]) == list(range(13))
    assert replayed.popitem()[0] == "large"
    replayed.clear()
    assert len(replayed) == 0 and list(replayed) == [] and json.dumps(replayed) == "{}"
    replayed["after-clear"] = 1
    assert dict(replayed) == {"after-clear": 1}


def test_plain_sqlalchemy_json_serialization_keeps_every_key_value_and_order(storage):  # noqa: F811
    generation, state = context(storage)
    source = {f"key-{n}": {"unicode": "owned \u03bb", "numbers": [n, n + 1]} for n in reversed(range(300))}
    source["\ud800"] = {"surrogate": "\udfff"}
    state["map"] = source
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")["map"]
    table = Table("owned_context_map_json", MetaData(), Column("id", Integer, primary_key=True), Column("data", JSON))
    table.create(generation.db.get_bind())
    generation.db.execute(table.insert().values(id=1, data={"map": restored}))
    generation.db.commit()
    stored = generation.db.execute(select(table.c.data)).scalar_one()["map"]
    assert stored == source and list(stored) == list(source)


@pytest.mark.parametrize("seed", ["1", "999"])
def test_fresh_process_replays_complete_map_in_deterministic_order(storage, seed):  # noqa: F811
    generation, state = context(storage)
    source = {f"key-{n}": {"value": n, "reference": state["snapshot"]} for n in reversed(range(300))}
    state["map"] = source
    generation.save("SNAPSHOT", state)
    expected = streaming_hash(source)
    code = r'''
import hashlib,json,sys
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from backend.db import make_engine
from backend.generation_models import AnalysisGeneration
from backend.generations import Generation,encoded
with sessionmaker(make_engine(sys.argv[1]),expire_on_commit=False)() as db:
 row=db.scalar(select(AnalysisGeneration))
 generation=Generation(db,row.job_id,row.organization_id,row.repository_id,row.signature,lambda:None,
  inventory_id=row.inventory_id,content_key=row.content_key)
 value=generation.load('SNAPSHOT')['map'];h=hashlib.sha256()
 for part in json.JSONEncoder(default=encoded,separators=(',',':')).iterencode(value):h.update(part.encode())
 print(json.dumps({'sha256':h.hexdigest(),'count':len(value),'first':next(iter(value))}))
'''
    completed = subprocess.run([sys.executable, "-c", code, str(generation.db.get_bind().url)],
        env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {"sha256": expected, "count": 300, "first": "key-299"}


def test_indexed_map_partial_stage_replay_preserves_record_identities(storage):  # noqa: F811
    from backend.db import Record
    from backend.domain import add
    from backend.generations import clear
    generation, state = context(storage)
    source = {f"z-{i}": i for i in reversed(range(20))}
    state["ordered"] = source
    generation.save("SNAPSHOT", state)
    generation.enter("EVIDENCE")
    for key in list(source)[:4]:
        add(generation.db, generation.row.organization_id, generation.row.repository_id,
            "evidence", {"path": key}, key)
    generation.batch()
    db = generation.db
    before = list(db.execute(select(GenerationRecord.record_id, GenerationRecord.ordinal).where(
        GenerationRecord.generation_id == generation.row.id, GenerationRecord.stage == "EVIDENCE")
        .order_by(GenerationRecord.ordinal)))
    args = (generation.row.job_id, generation.row.organization_id, generation.row.repository_id, generation.row.signature)
    inventory, content = generation.row.inventory_id, generation.row.content_key
    clear(db)
    with sessionmaker(db.get_bind(), expire_on_commit=False)() as fresh:
        resumed = Generation(fresh, *args, lambda: None, inventory_id=inventory, content_key=content)
        ordered = resumed.load("SNAPSHOT")["ordered"]
        resumed.enter("EVIDENCE")
        for key in ordered:
            add(fresh, resumed.row.organization_id, resumed.row.repository_id, "evidence", {"path": key}, key)
        resumed.batch()
        after = list(fresh.execute(select(GenerationRecord.record_id, GenerationRecord.ordinal).where(
            GenerationRecord.generation_id == resumed.row.id, GenerationRecord.stage == "EVIDENCE")
            .order_by(GenerationRecord.ordinal)))
        assert after[:4] == before and len(after) == len(source)
        paths = [fresh.get(Record, identity).data["path"] for identity, _ in after]
        assert paths == list(source)


def test_maps_keep_descriptor_and_storage_guards_and_clean_failed_attempts(storage, monkeypatch):  # noqa: F811
    import backend.generation_context as codec
    generation, state = context(storage)
    nested = "leaf"
    for _ in range(61):
        nested = {"nested": nested}
    state["map"] = {str(i): nested for i in range(10)}
    with pytest.raises(ValueError, match="descriptor budget"):
        generation.save("SNAPSHOT", state)
    state["map"] = {str(i): os.urandom(10000).hex() for i in range(40)}
    monkeypatch.setattr(codec, "MAX_BYTES", 300_000)
    with pytest.raises(ValueError, match="bounded byte budget"):
        generation.save("SNAPSHOT", state)
    assert generation.db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")) is None
    assert generation.db.scalar(select(func.count()).select_from(GenerationContextPart)) == 0


def test_map_replay_index_substitution_and_omission_fail_closed(storage):  # noqa: F811
    generation, state = context(storage)
    state["map"] = {f"private-key-{i}": {"value": i} for i in range(20)}
    generation.save("SNAPSHOT", state)
    value = generation.load("SNAPSHOT")["map"]
    assert b"private-key-" not in value.connection.serialize()
    selected = value.connection.execute("SELECT tag,position FROM context_map_keys WHERE collection=? ORDER BY position LIMIT 2",
        (value.collection,)).fetchall()
    value.connection.execute("UPDATE context_map_keys SET position=9999 WHERE collection=? AND tag=?", (value.collection, selected[0][0]))
    value.connection.execute("UPDATE context_map_keys SET position=? WHERE collection=? AND tag=?", (selected[0][1], value.collection, selected[1][0]))
    value.connection.execute("UPDATE context_map_keys SET position=? WHERE collection=? AND tag=?", (selected[1][1], value.collection, selected[0][0]))
    with pytest.raises(ValueError, match="index does not match"):
        value["private-key-0"]
    value.connection.execute("DELETE FROM context_map_keys WHERE collection=?", (value.collection,))
    with pytest.raises(ValueError, match="incomplete"):
        json.dumps(value)


def test_writer_and_reader_keep_the_exact_descriptor_node_guard(storage):  # noqa: F811
    generation, state = context(storage)
    source, descriptor = 0, ["scalar", 0]
    for _ in range(6):
        source = [source] * 8
        descriptor = ["inline", [descriptor] * 8]
    state["metadata"] = source
    with pytest.raises(ValueError, match="descriptor budget"):
        generation.save("SNAPSHOT", state)
    # These are inline descriptors, not map entries. The 256,000-node guard
    # remains a real bound on both sides of the new collection representation.
    reader = Reader(generation, None, validate_only=True)
    with pytest.raises(ValueError, match="descriptor budget"):
        reader.validate_node(descriptor)
    assert generation.db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT")) is None


def test_duplicate_encrypted_map_entries_are_rejected_before_any_replay_is_returned(storage, monkeypatch):  # noqa: F811
    from backend.context_maps import Entries
    generation, state = context(storage)
    state["map"] = {str(i): i for i in range(20)}
    original = Entries.__iter__
    def duplicate(entries):
        for position, pair in enumerate(original(entries)):
            yield ["0", pair[1]] if position == 1 else pair
    monkeypatch.setattr(Entries, "__iter__", duplicate)
    generation.save("SNAPSHOT", state)
    with pytest.raises(ValueError, match="duplicate keys"):
        generation.load("SNAPSHOT")
    receipt = generation.db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT"))
    with pytest.raises(ValueError, match="duplicate keys"):
        Reader(generation, receipt, validate_only=True).load()


def test_map_cancellation_closes_replay_and_preserves_complete_durable_receipt(storage, monkeypatch):  # noqa: F811
    import backend.generation_context as codec
    generation, state = context(storage)
    state["map"] = {str(i): {"text": "owned complete " * 100} for i in range(800)}
    saved, replay = [], codec.Replay
    def observe(scope):
        owner = replay(scope)
        saved.append(owner)
        return owner
    monkeypatch.setattr(codec, "Replay", observe)
    generation.save("SNAPSHOT", state)
    def cancel():
        if saved and len(saved[0].rows) > 0:
            raise RuntimeError("owned map cancellation")
    generation.checkpoint.read_check = cancel
    with pytest.raises(RuntimeError, match="owned map cancellation"):
        generation.load("SNAPSHOT")
    assert saved[0].rows.closed
    generation.checkpoint.read_check = lambda: None
    restored = generation.load("SNAPSHOT")["map"]
    assert streaming_hash(restored) == streaming_hash(state["map"])


def test_map_row_mutation_failure_is_not_silently_persisted_or_suppressed(storage, monkeypatch):  # noqa: F811
    generation, state = context(storage)
    state["map"] = {str(i): i for i in range(20)}
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")["map"]
    connection_owner = restored.rows.owner.rows
    monkeypatch.setattr(connection_owner, "maximum_bytes", connection_owner.bytes + 20)
    from analyzers.observation_store import ObservationBudgetExceeded
    with pytest.raises(ObservationBudgetExceeded):
        restored["0"] = os.urandom(1000).hex()
    assert restored["0"] == 0
    assert list(restored) == list(state["map"])


def test_map_finding_working_state_remains_typed_and_registered_for_failure_cleanup(storage):  # noqa: F811
    from backend.domain import add
    from backend.publication_state import FindingRecords
    generation, state = context(storage)
    finding = add(generation.db, generation.row.organization_id, generation.row.repository_id,
        "finding", {"title": "owned finding"}, "owned-finding")
    working = FindingRecords(generation.db)
    working[finding.id] = finding
    state["map"] = {str(i): i for i in range(20)}
    state["map"]["working"] = working
    generation.save("SNAPSHOT", state)
    owners = []
    generation.checkpoint.close_on_failure = owners.append
    restored = generation.load("SNAPSHOT")["map"]
    resumed = restored["working"]
    assert resumed is restored["working"]
    assert resumed.data in owners
    resumed[finding.id].data = {"title": "updated owned finding"}
    generation.enter("EVIDENCE")
    generation.save("EVIDENCE", {"map": restored})
    assert generation.load("EVIDENCE")["map"]["working"][finding.id].data["title"] == "updated owned finding"


def test_large_v1_dictionary_replays_and_feeds_v2_without_rewriting_old_receipt(storage):  # noqa: F811
    from backend.generation_models import GenerationChunk
    generation, state = context(storage)
    source = {str(i): {f"owned_{j}": j for j in range(28)} for i in reversed(range(10000))}
    state["map"] = source
    generation._save_legacy("SNAPSHOT", state)
    db = generation.db
    old = db.get(GenerationReceipt, (generation.row.id, "SNAPSHOT"))
    digest = old.digest
    chunks = [(row.ordinal, row.ciphertext) for row in db.scalars(select(GenerationChunk).order_by(GenerationChunk.ordinal))]
    restored = generation.load("SNAPSHOT")["map"]
    assert type(restored) is dict and restored == source and list(restored) == list(source)
    generation.enter("EVIDENCE")
    generation.save("EVIDENCE", {"map": restored})
    replayed = generation.load("EVIDENCE")["map"]
    assert isinstance(replayed, ContextMap) and replayed == source and list(replayed) == list(source)
    assert old.format_version == 1 and old.digest == digest
    after = [(row.ordinal, row.ciphertext) for row in db.scalars(select(GenerationChunk).where(
        GenerationChunk.stage == "SNAPSHOT").order_by(GenerationChunk.ordinal))]
    assert after == chunks


def test_nested_paged_sequence_mutations_preserve_typed_references_and_scope(storage):  # noqa: F811
    from backend.db import Record
    generation, state = context(storage)
    state["map"] = {str(i): i for i in range(20)}
    state["map"]["rows"] = list(range(200))
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")["map"]
    rows = restored["rows"]
    rows.append(state["snapshot"])
    rows[0] = {"record": state["snapshot"], "data": {"value": 1}}
    rows[0]["data"]["value"] = 2
    with pytest.raises(ValueError, match="scope"):
        rows.append(Record(id="foreign-record", organization_id="other", repository_id="other", kind="snapshot", data={}))
    assert len(rows) == 201
    expected = streaming_hash(restored)
    generation.enter("EVIDENCE")
    generation.save("EVIDENCE", {"map": restored})
    replayed = generation.load("EVIDENCE")["map"]
    assert streaming_hash(replayed) == expected
    assert replayed["rows"][-1].id == state["snapshot"].id
    assert replayed["rows"][0]["data"]["value"] == 2


def test_map_missing_and_unhashable_lookups_match_dictionary_behavior(storage):  # noqa: F811
    generation, state = context(storage)
    state["map"] = {str(i): i for i in range(20)}
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")["map"]
    assert restored.get(1) is None and 1 not in restored
    with pytest.raises(TypeError):
        restored.get([])
    with pytest.raises(TypeError):
        [] in restored


def test_cleared_indexed_map_replays_as_empty_and_remains_mutable(storage):  # noqa: F811
    generation, state = context(storage)
    state["map"] = {str(i): i for i in range(20)}
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")["map"]
    restored.clear()
    generation.enter("EVIDENCE")
    generation.save("EVIDENCE", {"empty": restored})
    receipt = generation.db.get(GenerationReceipt, (generation.row.id, "EVIDENCE"))
    Reader(generation, receipt, validate_only=True).load()
    empty = generation.load("EVIDENCE")["empty"]
    assert len(empty) == 0 and json.dumps(empty) == "{}" and dict(empty) == {}
    empty["after-replay"] = {"complete": True}
    assert json.loads(json.dumps(empty)) == {"after-replay": {"complete": True}}


def test_collection_header_cap_matches_on_writer_and_reader(storage, monkeypatch):  # noqa: F811
    import backend.generation_context as codec
    generation, _ = context(storage)
    # Lower the existing cap to exercise its boundary without allocating
    # hundreds of thousands of headers; production remains 256,000.
    monkeypatch.setattr(codec, "PAGE_BYTES", 2)
    writer = Writer(generation, generation.dependencies("SNAPSHOT"))
    first, second = writer.rows([]), writer.rows([])
    with pytest.raises(ValueError, match="descriptor budget"):
        writer.rows([])
    reader = Reader(generation, GenerationReceipt(stage="SNAPSHOT"))
    reader.pointer = {"pages": 0}
    try:
        reader.collection(first)
        reader.collection(second)
        assert len(reader.memo) == 2
        third = ["rows", 2, 0, 0, 0, hashlib.sha256(b"").hexdigest(), "mutable"]
        with pytest.raises(ValueError, match="descriptor budget"):
            reader.collection(third)
        assert len(reader.memo) == 2
    finally:
        reader.owner.close()
