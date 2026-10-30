import json

import pytest

from analyzers.observation_store import SignalRows
from analyzers.verifiers import verify_claim

SIGNALS = [
    {"type": "auth", "value": "jwt", "path": "auth.py", "line": 1},
    {"type": "auth", "value": "session", "path": "other.py", "line": 1},
    {"type": "auth_hint", "value": "Cookie Session store", "path": "auth.py", "line": 2},
    {"type": "import", "value": "PyJWT.algorithms", "path": "auth.py", "line": 3},
    {"type": "import", "value": "pytest.mark", "path": "test.py", "line": 1},
    {"type": "technology", "value": "Pytest", "path": "test.py", "line": 2},
    {"type": "database", "value": "PostgreSQL", "path": "db.py", "line": 1},
    {"type": "route", "value": "GET /example", "path": "app.py", "line": 1},
    {"type": "parser", "state": "COMPLETED", "path": "app.py"},
]


@pytest.mark.parametrize("category,expected", [
    ("AUTHENTICATION", "jwt"), ("AUTHENTICATION", "session"), ("AUTHENTICATION", "oauth"),
    ("API", "GET /example"), ("API", "POST /absent"), ("TECHNOLOGY", "postgresql"),
    ("TECHNOLOGY", "unknown"), ("TESTING", "pytest"), ("ARCHITECTURE", "kafka"),
    ("DEPENDENCY", "react"), ("CI", "github actions"), ("SECURITY_CONTROL", "tls"),
])
@pytest.mark.parametrize("subset", [SIGNALS, [], [SIGNALS[2], SIGNALS[3]]])
def test_index_retains_exact_verdict_evidence_fingerprint_unknowns_and_reuse(category, expected, subset):
    claim = {"category": category, "expected": expected}
    dependencies = [{"ecosystem": "npm", "name": "react", "version": "1", "path": "package.json"}]
    rows = SignalRows(("owned", "repo", "inventory"))
    try:
        rows.extend(subset)
        # Duplicates and unknown/parser metadata stay in the lossless sequence.
        rows.extend(subset)
        plain = subset * 2
        expected_result = verify_claim(claim, plain, dependencies)
        actual = verify_claim(claim, rows, dependencies)
        assert actual == expected_result
        assert json.loads(json.dumps(rows)) == plain
        assert verify_claim(claim, rows, dependencies, actual[0]) == verify_claim(claim, plain, dependencies, actual[0])
    finally:
        rows.close()


def test_verification_cost_is_independent_of_unrelated_signal_payload_count():
    class Measured(SignalRows):
        reads = 0
        def __getitem__(self, index):
            self.reads += 1
            return super().__getitem__(index)
    rows = Measured(("owned-cost",))
    signals = [{"type": "route", "value": f"GET /owned/{i}", "path": "app.py", "line": i + 1} for i in range(1000)]
    signals.append({"type": "auth", "value": "session", "path": "auth.py", "line": 1})
    try:
        rows.extend(signals)
        for _ in range(20):
            claim = {"category": "AUTHENTICATION", "expected": "jwt"}
            assert verify_claim(claim, rows, []) == verify_claim(claim, signals, [])
        assert rows.reads == 20  # All configured modes remain evidence; unrelated routes never decrypt.
    finally:
        rows.close()


def test_index_keys_are_private_and_scoped_and_malformed_signals_fail():
    a, b = SignalRows(("tenant-a",)), SignalRows(("tenant-b",))
    try:
        value = "OWNED-PRIVATE-INDEX-SENTINEL"
        a.append({"type": "route", "value": value, "path": "a.py", "line": 1})
        b.append({"type": "route", "value": "other", "path": "b.py", "line": 1})
        assert value.encode() not in a.connection.serialize()
        assert list(b.verifier_inputs({"route"}, value.lower(), {value.lower()})) == []
        with pytest.raises(ValueError, match="typed value"):
            a.append({"type": "auth", "value": {"invalid": True}})
        with pytest.raises(ValueError, match="valid type"):
            a.append({"value": "missing type"})
    finally:
        a.close()
        b.close()
