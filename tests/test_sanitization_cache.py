import pytest

from analyzers import sanitization


def test_repeated_text_still_redacts_secrets_and_preserves_key_collision_guard(monkeypatch):
    original = sanitization.redact
    calls = []

    def counted(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(sanitization, "redact", counted)
    secret = "ghp_" + "x" * 30
    values = [secret, "password='owned-password-123'", "postgres://user:owned-secret@host/db"]
    rows = [{"value": value, "password": "hidden"} for value in values for _ in range(30)]
    expected = [{"value": original(row["value"]), "password": "[REDACTED]"} for row in rows]
    assert sanitization.metadata(rows) == expected
    assert calls.count("value") == 1 and all(calls.count(value) == 1 for value in values)
    assert "hidden" not in calls
    sanitization.metadata(rows)
    assert calls.count("value") == 2  # No packet/tenant shares cached input.
    with pytest.raises(ValueError, match="key collision"):
        sanitization.metadata({secret: 1, "[REDACTED SECRET]": 2})


def test_repeated_cached_values_cannot_bypass_node_depth_or_scalar_checks():
    with pytest.raises(ValueError, match="structure budget"):
        sanitization.metadata(["repeat"] * 20, maximum_nodes=20)
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="structure budget"):
        sanitization.metadata(cycle)
    for value in (float("nan"), float("inf")):
        with pytest.raises(ValueError, match="Non-finite"):
            sanitization.metadata(["repeat", value])


def test_short_text_cache_has_bounded_entries_and_bypasses_long_strings(monkeypatch):
    original = sanitization.redact
    calls = []

    def counted(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(sanitization, "redact", counted)
    distinct = [f"owned-{i}" for i in range(129)]
    long = "x" * 257
    values = distinct + [distinct[0], long, long]
    assert sanitization.metadata(values) == values
    assert calls.count(distinct[0]) == 2 and calls.count(long) == 2

