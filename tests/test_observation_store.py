import json
import sqlite3

import pytest
from cryptography.fernet import InvalidToken

from analyzers.code_quality.core import build
from analyzers.engine import native_observations
from analyzers.observation_store import EncryptedRows, ObservationBudgetExceeded


def test_spill_is_lossless_ordered_encrypted_and_streams_json(tmp_path):
    rows = EncryptedRows(("tenant-a", "repo", "inventory"))
    expected = [{"path": f"source/{i}.py", "nested": ["OWNED-PRIVATE-SENTINEL", i]} for i in range(500)]
    rows.extend(expected)
    assert rows == expected and expected == rows
    assert rows[-1] == expected[-1] and rows[2:5] == expected[2:5]
    assert expected[0] in rows and {"absent": True} not in rows
    assert rows.count(expected[0]) == 1 and rows.index(expected[-1]) == len(expected) - 1
    assert list(reversed(rows)) == list(reversed(expected))
    assert list(rows.select(lambda r: r["nested"][1] % 2 == 0)) == expected[::2]
    assert json.loads(json.dumps({"rows": rows})) == {"rows": expected}
    assert json.loads("".join(json.JSONEncoder(sort_keys=True).iterencode(rows))) == expected
    # Encryption and sqlite paging must not leave plaintext in any spill file.
    assert b"OWNED-PRIVATE-SENTINEL" not in rows.connection.serialize()
    rows[0]["nested"].append("discarded mutation")
    assert rows[0] == expected[0]
    rows.close()
    with pytest.raises(sqlite3.ProgrammingError):
        rows.connection.execute("SELECT 1")
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


def test_metric_token_spill_compression_is_lossless_without_raising_budgets():
    rows = EncryptedRows(("owned-compression",), maximum_bytes=50_000, row_bytes=40_000)
    metric = {"path": "owned.py", "duplicate_tokens": [
        {"value": "identifier:" + str(i % 11), "line": i // 5 + 1} for i in range(500)
    ]}
    try:
        envelope = [rows.identity, list(rows.scope), 0, metric]
        raw = json.dumps(envelope, ensure_ascii=True, separators=(",", ":")).encode()
        legacy_ciphertext_size = len(rows.key.encrypt(raw))
        rows.append(metric)
        assert rows[0] == metric
        assert rows.bytes < legacy_ciphertext_size / 2
        assert rows.maximum_bytes == 50_000 and rows.row_bytes == 40_000
        assert len(rows[0]["duplicate_tokens"]) == 500
        assert json.loads(json.dumps(rows)) == [metric]
    finally:
        rows.close()


@pytest.mark.parametrize("malformation", ["oversized", "truncated", "trailing", "unknown_encoding"])
def test_authenticated_compressed_rows_reject_bombs_and_invalid_framing(malformation):
    import zlib
    rows = EncryptedRows(("owned-malformation",), maximum_bytes=4096, row_bytes=2048)
    try:
        rows.append({"preserved": True})
        packed = b"PTZ1" + zlib.compress(b"x" * 4096 if malformation == "oversized" else b"[]")
        if malformation == "truncated":
            packed = packed[:-1]
        elif malformation == "trailing":
            packed += b"unexpected"
        elif malformation == "unknown_encoding":
            packed = b"UNKNOWN"
        ciphertext = rows.key.encrypt(packed)  # ProjectTrace-owned corruption probe.
        rows.connection.execute("UPDATE rows SET ciphertext=? WHERE ordinal=0", (ciphertext,))
        with pytest.raises(ValueError, match="encoding|decoded row"):
            rows[0]
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
        store = EncryptedRows(scope, maximum_bytes=1, row_bytes=1)
        stores.append(store)
        return store
    monkeypatch.setattr(partitioned_analysis, "EncryptedRows", bounded)
    with pytest.raises(ObservationBudgetExceeded):
        execute_analysis(db, user, repo, files)
    assert stores and all(store.closed for store in stores)
    for store in stores:
        with pytest.raises(sqlite3.ProgrammingError):
            store.connection.execute("SELECT 1")
    job = db.scalar(select(Record).where(Record.kind == "job"))
    assert job.data["state"] == "FAILED" and job.data["error_code"] == "ANALYSIS_OBSERVATION_BUDGET"
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    monkeypatch.setattr(partitioned_analysis, "EncryptedRows", EncryptedRows)
    snapshot, recovered = execute_analysis(db, user, repo, files)
    assert recovered.data["snapshot_id"] == snapshot.id
    assert recovered.data["state"] == "COMPLETED"

from tests.test_repository_store import storage as storage  # noqa: E402 -- pytest fixture re-export


def test_mutable_spill_keeps_order_and_rejects_over_budget_update():
    from analyzers.observation_store import EncryptedMapping
    values = EncryptedMapping(("tenant-a", "repo", "generation"))
    try:
        values["a"] = {"value": "OWNED-MAPPING-SENTINEL"}
        values["b"] = {"value": "other"}
        for i in range(100):
            values["a"] = {"number": i}
        assert len(values) == 2 and "a" in values and "missing" not in values
        assert values["a"] == {"number": 99}
        assert list(values.snapshots()) == [{"id": "a", "data": {"number": 99}}, {"id": "b", "data": {"value": "other"}}]
        assert json.loads(json.dumps(values.snapshots())) == list(values.snapshots())
        values.rows.maximum_bytes = values.rows.bytes
        with pytest.raises(ObservationBudgetExceeded):
            values["a"] = {"value": "x" * 1000}
        assert values["a"] == {"number": 99}
        assert b"OWNED-MAPPING-SENTINEL" not in values.rows.connection.serialize()
        with pytest.raises(KeyError):
            values["missing"]
    finally:
        values.close()


def test_spill_finalization_outside_creating_thread():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as pool:
        rows = pool.submit(lambda: EncryptedRows(("owned",))).result()
    rows.close()
    with pytest.raises(sqlite3.ProgrammingError):
        rows.connection.execute("SELECT 1")


def test_linux_spill_is_unlinked_and_reclaimed_on_worker_death():
    import subprocess
    import sys
    import textwrap
    if sys.platform != "linux":
        pytest.skip("Linux unnamed SQLite lifecycle only")
    code = textwrap.dedent('''
        import json,os,time
        from pathlib import Path
        from analyzers.observation_store import EncryptedRows
        rows=EncryptedRows(('owned-lifecycle',))
        for i in range(100): rows.append({'value':os.urandom(20000).hex()})
        paths=[]
        for path in Path('/proc/self/fd').iterdir():
            try:
                value=str(path.readlink())
                if 'etilqs_' in value: paths.append(value)
            except FileNotFoundError: pass
        print(json.dumps(paths),flush=True)
        time.sleep(30)
    ''')
    process = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        paths = json.loads(process.stdout.readline())
        assert paths and all(path.endswith(" (deleted)") for path in paths)
        process.kill()
        assert process.wait(timeout=5) == -9
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def test_spilled_metric_reverse_iteration_preserves_non_python_identity(monkeypatch):
    import copy

    from analyzers.finding_identity import annotate
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    files = {"a.js": "function work() {}"}
    metrics = [{"path": "a.js", "name": "work", "qualified_name": "work", "body_hash": "body", "file_structure_hash": "file"}]
    findings = [{"rule": "PT-QUALITY-001", "path": "a.js", "line": 1, "symbol": "work", "category": "QUALITY",
                 "measured": 11, "metric": "cyclomatic", "observation_hash": "observation"}]
    expected = annotate(files, copy.deepcopy(findings), metrics)
    rows = EncryptedRows(("owned",))
    try:
        rows.extend(metrics)
        actual = annotate(files, copy.deepcopy(findings), rows)
        assert actual == expected
        assert actual[0]["identity_method"] == "PARSER_SYMBOL" and actual[0]["identity_confidence"] == "HIGH"
    finally:
        rows.close()
