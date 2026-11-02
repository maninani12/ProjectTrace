"""Actual crypto operation counts, iteration semantics and resource ownership."""
import gc
import json
import weakref

import pytest
from cryptography.fernet import InvalidToken

from tests.generation_map_iteration_probe import CountingCipher, profile_owned_map
from tests.test_generation_context import context
from tests.test_repository_store import storage  # noqa: F401


@pytest.mark.parametrize("count", [10000, 50000])
def test_large_map_iteration_decrypts_each_entry_once(tmp_path, count, record_property):
    result = profile_owned_map(tmp_path / "owned-map", count)
    record_property("owned_iteration_profile", json.dumps(result))
    assert all(sample["decryptions"] == count for sample in result["samples"])
    assert all(sample["encryptions"] == 0 for sample in result["samples"])
    assert all(sample["hmac_tag_calls"] == count for sample in result["samples"])
    assert all(sample["cache_size"] == -1024 and sample["headers"] == 1 for sample in result["samples"])


def counted_map(storage, *, count=20):  # noqa: F811
    generation, state = context(storage)
    state["map"] = {f"key-{i}": {"value": i} for i in range(count)}
    generation.save("SNAPSHOT", state)
    value = generation.load("SNAPSHOT")["map"]
    counter = CountingCipher(value.rows.owner.rows.key)
    value.rows.owner.rows.key = counter
    return generation, value, counter


@pytest.mark.parametrize("operation", ["items", "values", "keys"])
def test_iteration_operation_counts(storage, operation):  # noqa: F811
    _, value, counter = counted_map(storage)
    list(getattr(value, operation)())
    assert counter.decryptions == len(value)


def test_direct_lookup_reuses_its_verified_frame(storage):  # noqa: F811
    _, value, counter = counted_map(storage)
    assert value["key-0"] == {"value": 0}
    assert counter.decryptions == 1


class ObservedCursor:
    def __init__(self, original, probe):
        self.original, self.probe = original, probe
        self.closed = False

    def fetchone(self):
        return self.original.fetchone()

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.original)

    def close(self):
        self.original.close()
        assert not self.closed
        self.closed = True
        self.probe.closed += 1

    def __getattr__(self, name):
        return getattr(self.original, name)


class ObservedConnection:
    def __init__(self, original):
        self.original, self.created, self.closed = original, 0, 0

    def execute(self, statement, parameters=()):
        result = self.original.execute(statement, parameters)
        if statement.startswith("SELECT position,tag FROM context_map_keys"):
            self.created += 1
            return ObservedCursor(result, self)
        return result

    def __getattr__(self, name):
        return getattr(self.original, name)


def observe_cursor(value):
    owner = value.rows.owner.rows
    probe = ObservedConnection(owner.connection)
    owner.connection = probe
    return probe


def test_item_and_value_views_remain_live_after_creation(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    items, values = value.items(), value.values()
    value["key-0"] = {"value": 100}
    assert next(iter(items)) == ("key-0", {"value": 100})
    assert next(iter(values)) == {"value": 100}
    assert ("key-0", {"value": 100}) in items


def test_value_replacement_and_nested_mutation_never_reuse_stale_frames(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    iterator = iter(value.items())
    key, old = next(iterator)
    assert key == "key-0"
    old["value"] = 101
    assert value[key]["value"] == 101
    value[key] = {"value": 999}
    old["value"] = -1
    assert value[key]["value"] == 999
    value["key-1"] = {"value": 202}
    assert next(iterator) == ("key-1", {"value": 202})
    assert [key for key, _ in iterator] == [f"key-{i}" for i in range(2, 20)]


@pytest.mark.parametrize("operation", ["items", "values", "keys"])
@pytest.mark.parametrize("mutation", ["insert", "delete", "delete_reinsert", "clear"])
def test_structural_mutation_invalidates_iterator_and_closes_cursor(storage, operation, mutation):  # noqa: F811
    _, value, _ = counted_map(storage)
    probe = observe_cursor(value)
    iterator = iter(getattr(value, operation)())
    next(iterator)
    if mutation == "insert":
        value["new"] = 1
    elif mutation == "delete":
        del value["key-19"]
    elif mutation == "delete_reinsert":
        value["key-19"] = value.pop("key-19")
    else:
        value.clear()
    with pytest.raises(RuntimeError, match="changed size"):
        next(iterator)
    assert probe.created == probe.closed == 1


def test_interleaved_iterators_keep_independent_positions_and_current_values(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    probe = observe_cursor(value)
    first, second = iter(value.items()), iter(value.values())
    assert next(first)[0] == "key-0"
    assert next(first)[0] == "key-1"
    value["key-0"] = {"value": 100}
    assert next(second) == {"value": 100}
    assert next(first)[0] == "key-2"
    first.close()
    assert len(list(second)) == 19
    assert probe.created == probe.closed == 2


@pytest.mark.parametrize("operation", ["items", "values", "keys"])
def test_close_and_exhaustion_release_cursor_without_closing_owner(storage, operation):  # noqa: F811
    _, value, _ = counted_map(storage)
    probe = observe_cursor(value)
    iterator = iter(getattr(value, operation)())
    next(iterator)
    assert probe.created == 1 and probe.closed == 0
    iterator.close()
    assert probe.closed == 1 and not value.rows.closed
    assert len(list(getattr(value, operation)())) == 20
    assert probe.created == probe.closed == 2
    assert value["key-19"] == {"value": 19}


def test_decoded_frame_does_not_survive_yield_or_iterator_close(storage, monkeypatch):  # noqa: F811
    _, value, counter = counted_map(storage)
    refs, original = [], value._frame
    class Frame(list):
        pass
    def observed(position):
        frame = Frame(original(position))
        refs.append(weakref.ref(frame))
        return frame
    monkeypatch.setattr(value, "_frame", observed)
    iterator = iter(value.items())
    item = next(iterator)
    assert item == ("key-0", {"value": 0})
    assert counter.decryptions == 1 and len(refs) == 1
    assert refs[0]() is None
    del item
    iterator.close()
    gc.collect()
    assert len(value.live) == 0


def test_iterator_retains_lazy_owner_until_release(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    owner = weakref.ref(value.rows.owner.rows)
    connection = value.rows.owner.rows.connection
    iterator = iter(value.items())
    next(iterator)
    del value
    gc.collect()
    assert owner() is not None
    assert next(iterator)[0] == "key-1"
    iterator.close()
    gc.collect()
    assert owner() is None
    import sqlite3
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_explicit_owner_close_stops_suspended_iterator(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    iterator = iter(value.items())
    next(iterator)
    value.rows.close()
    with pytest.raises(ValueError, match="closed"):
        next(iterator)


@pytest.mark.parametrize("operation", ["lookup", "items"])
def test_owner_closed_during_frame_read_never_returns_value(storage, monkeypatch, operation):  # noqa: F811
    _, value, _ = counted_map(storage)
    original = value._frame
    def close_after_read(position):
        frame = original(position)
        value.rows.close()
        return frame
    monkeypatch.setattr(value, "_frame", close_after_read)
    with pytest.raises(ValueError, match="closed"):
        if operation == "lookup":
            value["key-0"]
        else:
            next(iter(value.items()))


def damage_row(value, position):
    connection = value.rows.owner.rows.connection
    ordinal = connection.execute("SELECT ordinal FROM positions WHERE collection=? AND position=?",
        (value.collection, position)).fetchone()[0]
    connection.execute("UPDATE rows SET ciphertext=? WHERE ordinal=?", (b"invalid-owned-ciphertext", ordinal))


def test_live_mutable_value_never_bypasses_fresh_authentication(storage):  # noqa: F811
    _, value, counter = counted_map(storage)
    iterator = iter(value.items())
    key, retained = next(iterator)
    assert retained == {"value": 0}
    damage_row(value, 0)
    before = counter.decryptions
    with pytest.raises(InvalidToken):
        value[key]
    assert counter.decryptions == before + 1
    iterator.close()


def test_upcoming_ciphertext_corruption_fails_and_closes_cursor(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    probe = observe_cursor(value)
    iterator = iter(value.items())
    next(iterator)
    damage_row(value, 1)
    with pytest.raises(InvalidToken):
        next(iterator)
    assert probe.created == probe.closed == 1


def test_ordered_iteration_still_checks_index_hmac_and_completeness(storage):  # noqa: F811
    _, value, _ = counted_map(storage)
    connection = value.connection
    connection.execute("UPDATE context_map_keys SET tag=? WHERE collection=? AND position=0", (b"x" * 32, value.collection))
    with pytest.raises(ValueError, match="index does not match"):
        list(value.items())
    connection.execute("DELETE FROM context_map_keys WHERE collection=?", (value.collection,))
    with pytest.raises(ValueError, match="incomplete"):
        list(value.values())


def test_typed_values_keep_mutations_and_complete_receipt_replay(storage):  # noqa: F811
    generation, state = context(storage)
    state["map"] = {f"key-{i}": {"record": state["snapshot"], "nested": {"value": i}} for i in range(20)}
    generation.save("SNAPSHOT", state)
    value = generation.load("SNAPSHOT")["map"]
    key, item = next(iter(value.items()))
    assert item["record"].id == state["snapshot"].id
    item["nested"]["value"] = 101
    from tests.test_generation_maps import streaming_hash
    expected = streaming_hash(value)
    generation.enter("EVIDENCE")
    generation.save("EVIDENCE", {"map": value})
    replayed = generation.load("EVIDENCE")["map"]
    assert streaming_hash(replayed) == expected
    assert replayed[key]["nested"]["value"] == 101
