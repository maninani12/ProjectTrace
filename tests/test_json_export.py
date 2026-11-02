"""Complete JSON contracts, lazy crypto reads and bounded export ownership."""
import copy
import gc
import hashlib
import io
import json
import weakref

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import JSON, Column, Integer, MetaData, Table, select

from backend.generations import encoded
from backend.json_export import CHUNK_BYTES, dumps, iter_bytes, iter_text, write_json
from tests.generation_json_export_probe import profile
from tests.generation_map_iteration_probe import CountingCipher
from tests.test_generation_context import context
from tests.test_generation_map_iteration import counted_map, damage_row, observe_cursor
from tests.test_repository_store import storage  # noqa: F401


@pytest.mark.parametrize("value", [None, True, False, -123, -0.0, 1e-20,
    "escaped\n\t\"\\é\ud800", [], {}, (1, "two"),
    {None: "null", False: "bool", 1.2: ["é", {"z": 1, "a": 2}]}])
@pytest.mark.parametrize("options", [{}, {"separators": (",", ":")}, {"ensure_ascii": False}])
def test_exact_stdlib_text_semantics(value, options):
    expected = json.dumps(value, **options)
    assert "".join(iter_text(value, **options)) == expected
    assert dumps(value, **options) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_numbers_match_stdlib(value):
    assert "".join(iter_text({value: value})) == json.dumps({value: value})
    with pytest.raises(ValueError, match="not JSON compliant"):
        list(iter_text([value], allow_nan=False))


@pytest.mark.parametrize("cycle", ["list", "dict", "default"])
def test_circular_references_rejected(cycle):
    value = [] if cycle == "list" else {}
    if cycle == "list":
        value.append(value)
    else:
        value["self"] = value
    if cycle == "default":
        original = object()
        value = original
        def default(_):
            return original
    else:
        default = None
    with pytest.raises(ValueError, match="Circular"):
        dumps(value, default=default)


def test_unsupported_types_and_keys_still_rejected():
    for value in ([object()], {object(): "invalid"}):
        with pytest.raises(TypeError):
            dumps(value)
    with pytest.raises(TypeError, match="Unsupported generation context type: object"):
        dumps({object()}, default=encoded)


def test_generation_set_encoding_is_deterministic():
    value = {"ids": {"b", "a"}, "mixed": {1, "1", (2, "x")}}
    expected = '{"ids": {"$set": ["a", "b"]}, "mixed": {"$set": ["1", 1, [2, "x"]]}}'

    assert dumps(value, default=encoded) == expected
    assert dumps({"ids": set(reversed(["a", "b"]))}, default=encoded) == '{"ids": {"$set": ["a", "b"]}}'


@pytest.mark.parametrize("legacy", [False, True])
def test_typed_context_export_replay_mutations_and_snapshot_integrity(storage, legacy):  # noqa: F811
    generation, state = context(storage)
    snapshot_before = copy.deepcopy(state["snapshot"].data)
    state.update({"map": {str(i): {"record": state["snapshot"], "values": [i, "é"]} for i in range(20)},
                  "ids": {"a", "b"}, "tuple": (1, "x")})
    expected = "".join(json.JSONEncoder(default=encoded).iterencode(state))
    (generation._save_legacy if legacy else generation.save)("SNAPSHOT", state)
    value = generation.load("SNAPSHOT")
    assert "".join(iter_text(value, default=encoded)) == expected
    value["map"]["0"]["values"].append(99)
    actual = dumps(value, default=encoded)
    assert json.loads(actual)["map"]["0"]["values"] == [0, "é", 99]
    generation.enter("EVIDENCE")
    generation.save("EVIDENCE", value)
    assert dumps(generation.load("EVIDENCE"), default=encoded) == actual
    assert state["snapshot"].data == snapshot_before


def test_partial_writes_and_deterministic_export_import(storage):  # noqa: F811
    _, value, counter = counted_map(storage)
    expected = {f"key-{i}": {"value": i} for i in range(20)}
    class Partial(io.BytesIO):
        def write(self, raw):
            return super().write(raw[:7])
    sink = Partial()
    total = write_json(value, sink)
    raw = sink.getvalue()
    assert total == len(raw)
    assert json.loads(raw) == expected
    assert raw == json.dumps(expected).encode()
    assert counter.decryptions == 20 and counter.encryptions == 0
    assert hashlib.sha256(raw).digest() == hashlib.sha256(b"".join(iter_bytes(value))).digest()
    assert not value.rows.closed


@pytest.mark.parametrize("written", [0, None, True, -1, 1_000_000])
def test_invalid_sink_writes_fail(written):
    class Sink:
        def write(self, raw):
            return written
    with pytest.raises(OSError, match="valid byte count"):
        write_json({"value": 1}, Sink())


@pytest.mark.parametrize("failure", ["sink", "cancel", "corrupt", "hmac"])
def test_failure_closes_nested_cursors_even_with_retained_traceback(storage, failure):  # noqa: F811
    _, value, _ = counted_map(storage)
    probe = observe_cursor(value)
    value["key-0"] = {"pad": "x" * 150_000}
    if failure == "corrupt":
        damage_row(value, 3)
    if failure == "hmac":
        value.connection.execute("UPDATE context_map_keys SET tag=? WHERE collection=? AND position=3",
            (b"x" * 32, value.collection))
    class Sink:
        def write(self, raw):
            if failure == "sink":
                raise OSError("owned broken sink")
            return len(raw)
    def checkpoint():
        if failure == "cancel" and probe.created > 0:
            raise RuntimeError("owned cancelled")
    with pytest.raises((OSError, RuntimeError, InvalidToken, ValueError)) as retained:
        write_json({"outer": [value]}, Sink(), checkpoint=checkpoint)
    assert retained.value is not None
    assert probe.created == probe.closed == 1
    assert not value.rows.closed
    assert value["key-19"] == {"value": 19}


def test_abandoned_export_releases_iterators_but_not_caller_owner(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    value["key-0"] = {"pad": "x" * 150_000}
    probe = observe_cursor(value)
    stream = iter_bytes(value)
    assert 0 < len(next(stream)) <= CHUNK_BYTES
    assert probe.created == 1 and probe.closed == 0
    stream.close()
    assert probe.closed == 1 and not value.rows.closed
    gc.collect()
    assert len(value.live) == 0


def test_mid_read_owner_close_still_rejects_export(storage, monkeypatch):  # noqa: F811
    _, value, _ = counted_map(storage)
    original = value._frame
    def frame(position):
        result = original(position)
        value.rows.close()
        return result
    monkeypatch.setattr(value, "_frame", frame)
    with pytest.raises(ValueError, match="closed"):
        dumps(value)


def test_stream_releases_frames_and_keeps_one_decryption_per_entry(storage, monkeypatch):  # noqa: F811
    import backend.context_maps as maps
    _, value, counter = counted_map(storage)
    refs, live, original = [], [], value._frame
    original_tag, tags = maps.tag, []
    def tag(*args):
        tags.append(1)
        return original_tag(*args)
    monkeypatch.setattr(maps, "tag", tag)
    class Frame(list):
        pass
    def frame(position):
        live.append(len(value.live))
        result = Frame(original(position))
        refs.append(weakref.ref(result))
        return result
    monkeypatch.setattr(value, "_frame", frame)
    assert json.loads(b"".join(iter_bytes(value))) == {f"key-{i}": {"value": i} for i in range(20)}
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert max(live) <= 1 and len(value.live) == 0
    assert counter.decryptions == 20 and counter.encryptions == 0
    assert len(tags) == 20


def test_large_scalar_transport_is_bounded_and_complete():
    value = {"large": "𝄞\"\n" * 200_000}
    chunks = list(iter_bytes(value, ensure_ascii=False))
    assert max(map(len, chunks)) <= CHUNK_BYTES
    assert b"".join(chunks) == json.dumps(value, ensure_ascii=False).encode()


def test_http_export_preserves_json_bytes_and_authorization(signed):
    response = signed.get("/api/code-quality/clean/exports/json")
    assert response.status_code == 200
    assert response.content == json.dumps(response.json()).encode()
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == 'attachment; filename="ProjectTrace-quality.json"'
    assert signed.get("/api/code-quality/private/exports/json").status_code in (403, 404)


def test_sequence_export_is_nontracking_but_preserves_live_mutations(storage):  # noqa: F811
    generation, state = context(storage)
    state["rows"] = [{"value": i, "values": [i]} for i in range(300)]
    generation.save("SNAPSHOT", state)
    rows = generation.load("SNAPSHOT")["rows"]
    retained = rows[0]
    retained["values"].append(99)
    expected = [{"value": i, "values": [i, 99] if i == 0 else [i]} for i in range(300)]
    counter = CountingCipher(rows.owner.rows.key)
    rows.owner.rows.key = counter
    assert json.loads(b"".join(iter_bytes(rows))) == expected
    assert counter.decryptions == 300 and counter.encryptions == 0
    assert len(rows.live) == 1 and rows.live[0] is retained


def test_typed_finding_snapshots_remain_lazy_and_complete(storage):  # noqa: F811
    from backend.publication_state import FindingRecords
    generation, state = context(storage)
    findings = FindingRecords(generation.db, ({"id": f"finding-{i}", "data": {"title": str(i)}} for i in range(50)))
    state["findings"] = findings
    expected = "".join(json.JSONEncoder(default=encoded).iterencode(state))
    generation.save("SNAPSHOT", state)
    restored = generation.load("SNAPSHOT")
    assert dumps(restored, default=encoded) == expected
    assert json.loads(expected)["findings"]["$finding_records"] == [
        {"id": f"finding-{i}", "data": {"title": str(i)}} for i in range(50)]
    findings.data.close()


def test_live_values_are_authenticated_and_structural_mutations_fail(storage):  # noqa: F811
    generation, value, _ = counted_map(storage)
    retained = value["key-0"]
    retained["value"] = 99
    assert json.loads(dumps(value))["key-0"] == {"value": 99}
    damage_row(value, 0)
    with pytest.raises(InvalidToken):
        dumps(value)
    fresh = generation.load("SNAPSHOT")["map"]
    probe = observe_cursor(fresh)
    iterator = iter_text(fresh)
    for part in iterator:
        if part == '"key-0"':
            break
    fresh["new"] = 123
    with pytest.raises(RuntimeError, match="changed size"):
        list(iterator)
    assert probe.created == probe.closed == 1


@pytest.mark.parametrize("damage", ["ciphertext", "mid_read_close"])
def test_sequence_export_never_bypasses_authentication_or_owner_open(storage, monkeypatch, damage):  # noqa: F811
    from backend.checkpoint_pages import ReplayRows
    generation, state = context(storage)
    state["rows"] = [{"value": i} for i in range(20)]
    generation.save("SNAPSHOT", state)
    rows = generation.load("SNAPSHOT")["rows"]
    retained = rows[0]
    assert retained == {"value": 0}
    if damage == "ciphertext":
        connection = rows.owner.rows.connection
        ordinal = connection.execute("SELECT ordinal FROM positions WHERE collection=? AND position=0",
            (rows.collection,)).fetchone()[0]
        connection.execute("UPDATE rows SET ciphertext=? WHERE ordinal=?", (b"owned-corrupt-sequence", ordinal))
        expected, match = InvalidToken, None
    else:
        original = ReplayRows.__getitem__
        def close_after_read(owner, position):
            result = original(owner, position)
            if owner is rows:
                rows.close()
            return result
        monkeypatch.setattr(ReplayRows, "__getitem__", close_after_read)
        expected, match = ValueError, "closed"
    with pytest.raises(expected, match=match):
        dumps(rows)


def test_inner_corruption_closes_all_active_map_cursors(storage):  # noqa: F811
    generation, state = context(storage)
    state["map"] = {str(i): {"nested": {str(j): {"value": j} for j in range(200)}} for i in range(10)}
    generation.save("SNAPSHOT", state)
    value = generation.load("SNAPSHOT")["map"]
    nested = value["0"]["nested"]
    probe = observe_cursor(value)
    damage_row(nested, 3)
    with pytest.raises(InvalidToken) as retained:
        write_json(value, io.BytesIO())
    assert retained.value is not None
    assert probe.created == probe.closed == 2
    assert not value.rows.closed
    assert nested["199"] == {"value": 199}


def test_adapter_options_are_independent_of_document_size():
    for value in ({"small": 1}, list(range(100))):
        with pytest.raises(TypeError):
            dumps(value, sort_keys=True)


def test_sqlalchemy_json_binding_does_not_collect_lazy_items(storage, monkeypatch):  # noqa: F811
    generation, value, counter = counted_map(storage)
    original, peak = value._frame, []
    def frame(position):
        peak.append(len(value.live))
        return original(position)
    monkeypatch.setattr(value, "_frame", frame)
    table = Table("owned_export_json", MetaData(), Column("id", Integer, primary_key=True), Column("data", JSON))
    engine = generation.db.get_bind()
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(table.insert(), {"id": 1, "data": value})
        restored = connection.scalar(select(table.c.data))
    assert restored == {f"key-{i}": {"value": i} for i in range(20)}
    assert counter.decryptions == 20
    assert max(peak) <= 1


@pytest.mark.parametrize("count", [16, 10000, 50000])
def test_fresh_process_export_profiles(tmp_path, count, record_property):
    result = profile(tmp_path / "owned-export", count, ["stream", "string"])
    record_property("owned_export_profile", json.dumps(result))
    if count == 10000:
        assert result["expected"]["bytes"] == 3_808_908
    for sample in result["samples"]:
        assert sample["decryptions"] == count and sample["encryptions"] == 0
        assert sample["live_values_peak"] <= 1
        assert sample["cache_size"] == -1024
        if sample["mode"] == "stream":
            assert sample["maximum_write"] <= CHUNK_BYTES
        # Local process ceiling includes replay/imports, not Linux qualification.
        assert sample["after"].get("peak_rss_bytes", sample["after"]["rss_bytes"]) < 190_000_000
