import json
from pathlib import Path

import pytest
from cryptography.fernet import InvalidToken

from analyzers.code_quality.core import build
from analyzers.engine import native_observations
from analyzers.observation_store import EncryptedRows, ObservationBudgetExceeded


def test_spill_is_lossless_ordered_encrypted_and_streams_json(tmp_path):
    rows = EncryptedRows(("tenant-a", "repo", "inventory"), directory=tmp_path)
    expected = [{"path": f"source/{i}.py", "nested": ["OWNED-PRIVATE-SENTINEL", i]} for i in range(500)]
    rows.extend(expected)
    assert rows == expected and expected == rows
    assert rows[-1] == expected[-1] and rows[2:5] == expected[2:5]
    assert list(rows.select(lambda r: r["nested"][1] % 2 == 0)) == expected[::2]
    assert json.loads(json.dumps({"rows": rows})) == {"rows": expected}
    assert json.loads("".join(json.JSONEncoder(sort_keys=True).iterencode(rows))) == expected
    # Encryption and sqlite paging must not leave plaintext in any spill file.
    assert all(b"OWNED-PRIVATE-SENTINEL" not in p.read_bytes() for p in Path(rows.temporary.name).iterdir())
    rows[0]["nested"].append("discarded mutation")
    assert rows[0] == expected[0]
    root = Path(rows.temporary.name)
    rows.close()
    assert not root.exists()
    with pytest.raises(ValueError, match="closed"):
        rows[0]


def test_spill_rejects_tenant_row_swap_tampering_and_reordering():
    a, b = EncryptedRows(("a",)), EncryptedRows(("b",))
    try:
        a.extend([{"value": 1}, {"value": 2}])
        b.append({"value": 3})
        ciphertext = a.connection.execute("SELECT ciphertext FROM rows WHERE ordinal=0").fetchone()[0]
        b.connection.execute("UPDATE rows SET ciphertext=? WHERE ordinal=0", (ciphertext,))
        with pytest.raises(InvalidToken):
            b[0]
        a.connection.execute("UPDATE rows SET ciphertext=? WHERE ordinal=1", (ciphertext,))
        with pytest.raises(ValueError, match="scope or ordinal"):
            a[1]
    finally:
        a.close()
        b.close()


def test_spill_limits_never_truncate_or_mutate_previous_rows():
    rows = EncryptedRows(("a",), maximum_bytes=1500, row_bytes=500)
    try:
        rows.append({"value": "preserved"})
        with pytest.raises(ObservationBudgetExceeded, match="row budget"):
            rows.append({"value": "x" * 501})
        with pytest.raises(ObservationBudgetExceeded, match="byte budget"):
            while True:
                rows.append({"value": "x" * 300})
        assert rows[0] == {"value": "preserved"}
        assert rows.bytes <= 1500
        with pytest.raises(TypeError, match="immutable"):
            rows.clear()
    finally:
        rows.close()


def test_spill_quality_preserves_duplication_symbols_findings_and_cache(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    body = "def work(x):\n" + "".join(f"    value{i} = x + {i}\n" for i in range(15)) + "    return value0\n"
    files = {"a.py": body, "b.py": body, "README.md": "The app uses JWT authentication."}
    f, s, w, _, m, *_ = native_observations(files)
    expected = build(files, m, s, f, w)
    signals, metrics = EncryptedRows(("a",)), EncryptedRows(("a",))
    try:
        signals.extend(s)
        metrics.extend(m)
        actual = build(files, metrics, signals, f, w, consume_metrics=True)
        for _, quality in (expected, actual):
            quality.pop("performance")
        assert actual == expected
        assert actual[1]["duplication"]["groups"]
        assert list(metrics) == m  # Immutable tokens and artifact input remain intact.
    finally:
        signals.close()
        metrics.close()


def test_spill_exhaustion_closes_private_state_without_publication(storage, monkeypatch, tmp_path):
    from sqlalchemy import func, select

    from backend import partitioned_analysis
    from backend.db import Record
    from backend.jobs import execute_analysis
    from tests.test_repository_store import captured

    db, user, repo = storage
    files = captured(storage, {"app.py": "def work(value):\n    return eval(value)\n"})
    stores = []
    def bounded(scope):
        store = EncryptedRows(scope, maximum_bytes=1, row_bytes=1, directory=tmp_path)
        stores.append(store)
        return store
    monkeypatch.setattr(partitioned_analysis, "EncryptedRows", bounded)
    with pytest.raises(ObservationBudgetExceeded):
        execute_analysis(db, user, repo, files)
    assert stores and all(store.closed for store in stores)
    assert all(not Path(store.temporary.name).exists() for store in stores)
    job = db.scalar(select(Record).where(Record.kind == "job"))
    assert job.data["state"] == "FAILED" and job.data["error_code"] == "ANALYSIS_OBSERVATION_BUDGET"
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    monkeypatch.setattr(partitioned_analysis, "EncryptedRows", EncryptedRows)
    snapshot, recovered = execute_analysis(db, user, repo, files)
    assert recovered.data["snapshot_id"] == snapshot.id
    assert recovered.data["state"] == "COMPLETED"

from tests.test_repository_store import storage as storage  # noqa: E402 -- pytest fixture re-export
