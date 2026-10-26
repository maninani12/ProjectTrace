"""Differential privacy coverage for the fixed-introducer negative search."""
import hashlib
import random

import pytest

from analyzers import sanitization


def test_fixed_introducer_search_matches_original_scanner_on_owned_corpus():
    forms = [
        "ordinary identifier", "identifier:owned", "string_literal:" + "a" * 64,
        "-----BEGIN PRIVATE KEY-----\nowned material\n-----END PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----\nunfinished owned material",
        "-----BEGIN NOT-A-KEY-----", "-----begin private key-----",
        "PASSWORD=owned", "PREFIX_API_KEY=owned", "token: owned_value_123456",
        'api-key = "owned_value_123456"', "password='owned_value_123456'",
        "postgresql+psycopg://owned:owned-private@localhost/db",
        "mysql://owned:owned-private@localhost/db", "mongodb://owned:owned-private@localhost/db",
        "AKIA0123456789012345", "A\u212aIA0123456789012345",
        *[prefix + "x" * 30 for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "gHp_")],
        "passwd: owned_value_123456", "authorization: owned", "cookie: owned",
        "\u0130dentifier", "\u03a3\u03a3", "\U0001f600", "\ud800", "\x00",
    ]
    rng = random.Random(41001)
    corpus = list(forms)
    for _ in range(4000):
        separator = rng.choice(("", " ", "\n", "\r\n", "\t", "\u2028", "\x00", "'", '"', ":", "="))
        corpus.append(separator.join(rng.choices(forms, k=rng.randrange(1, 5))))
    corpus.extend(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1000))
    for text in corpus:
        assert sanitization.redact(text) == sanitization._redact_candidates(text)


def test_text_budget_and_subclass_cannot_evade_candidate_scanner():
    class Secret(str):
        def lower(self):
            return "ordinary"

    assert sanitization.redact(Secret("ghp_" + "x" * 30)) == "[REDACTED SECRET]"
    for value in (None, b"ordinary", "a" * (sanitization.MAX_TEXT + 1)):
        with pytest.raises(ValueError, match="budget or type"):
            sanitization.redact(value)


def test_negative_search_keeps_nested_sensitive_keys_and_collision_checks():
    value = sanitization.metadata({"value": "identifier:owned", "nested": {
        "credentials": ["owned-private"], "client-secret": "owned-private",
        "message": "postgres://owned:owned-private@localhost/db"}})
    assert value["value"] == "identifier:owned"
    assert value["nested"]["credentials"] == value["nested"]["client-secret"] == "[REDACTED]"
    assert "owned-private" not in str(value)
    with pytest.raises(ValueError, match="key collision"):
        sanitization.metadata({"ghp_" + "x" * 30: 1, "[REDACTED SECRET]": 2})
