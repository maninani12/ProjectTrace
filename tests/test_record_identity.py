"""Storage ordering must not alter snapshot keys, semantic identity or tenant fencing."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend import main, record_identity
from backend.domain import add


def test_portable_uuid7_layout_and_clock_rollback(monkeypatch):
    milliseconds = 1_720_000_000_000
    monkeypatch.setattr(record_identity.time, 'time_ns', lambda: milliseconds * 1_000_000)
    monkeypatch.setattr(record_identity.secrets, 'randbits', lambda bits: (1 << bits) - 1)
    value = uuid.UUID(record_identity.record_uid())
    assert value.version == 7 and value.variant == uuid.RFC_4122
    assert value.int >> 80 == milliseconds
    assert value.int & ((1 << 62) - 1) == (1 << 62) - 1
    monkeypatch.setattr(record_identity.time, 'time_ns', lambda: (milliseconds-1) * 1_000_000)
    assert uuid.UUID(record_identity.record_uid()).int >> 80 == milliseconds - 1


def test_csprng_ids_are_unique_across_concurrent_allocators():
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: record_identity.record_uid(), range(10000)))
    assert len(set(ids)) == 10000
    assert all(uuid.UUID(value).version == 7 for value in ids)


def test_new_storage_ids_preserve_explicit_keys_old_records_and_tenant_guards(signed):
    with main.Session() as db:
        first = add(db, 'northstar', 'identity', 'identity_fixture', {'identity_id':'stable-semantic-id'}, natural_key='explicit-stable-key')
        second = add(db, 'northstar', 'identity', 'identity_fixture', {})
        assert first.natural_key == 'explicit-stable-key'
        assert first.data['identity_id'] == 'stable-semantic-id'
        assert second.natural_key == second.id and uuid.UUID(second.id).version == 7
        db.commit()
        before = first.id, first.version, first.data.copy()
        db.refresh(first)
        assert (first.id, first.version, first.data) == before
        with pytest.raises(ValueError, match='Cross-tenant'):
            add(db, 'other', 'identity', 'identity_fixture', {})
        db.rollback()
