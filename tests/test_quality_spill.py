import copy
import json
import sqlite3

import pytest

from analyzers import engine
from analyzers.code_quality import core
from analyzers.observation_store import EncryptedRows, MetricRows, SignalRows
from tests.test_repository_store import storage  # noqa: F401 -- owned fixture


def test_metric_owner_index_preserves_order_ties_annotations_and_encryption():
    path = "OWNED-PRIVATE-PATH.py"
    rows = MetricRows(("tenant", "repo", "inventory"))
    try:
        original = [{"path": path, "name": "outer", "line": 1, "end_line": 30},
                    {"path": path, "name": "OWNED-PRIVATE-INNER-FIRST-NAME", "line": 5, "end_line": 10},
                    {"path": path, "name": "second", "line": 6, "end_line": 11},
                    {"path": "other.py", "name": "other", "line": 1, "end_line": 2}]
        rows.extend(original)
        assert list(rows.for_path(path)) == original[:3]
        assert rows.containing(path, 7) == original[1]
        assert rows.containing(path, 20) == original[0]
        assert rows.containing(path, 50) is None
        changed = {**rows[1], "new_code": True}
        rows._replace(1, changed)
        assert rows.containing(path, 7) == changed
        assert json.loads(json.dumps(rows)) == [original[0], changed, *original[2:]]
        assert path.encode() not in rows.connection.serialize()
        assert b"OWNED-PRIVATE-INNER-FIRST-NAME" not in rows.connection.serialize()
    finally:
        rows.close()


def test_derived_output_owner_checks_scope_and_closes_both_vectors():
    signals = SignalRows(("tenant-a", "repo", "inventory"))
    own, foreign = MetricRows(signals.scope), MetricRows(("tenant-b", "repo", "inventory"))
    try:
        with pytest.raises(ValueError, match="attempt scope"):
            signals.own(foreign)
        signals.own(own)
        signals.close()
        assert own.closed and not foreign.closed
        with pytest.raises(ValueError, match="closed"):
            signals.own(foreign)
    finally:
        signals.close()
        foreign.close()


def test_metric_owner_index_rejects_path_substitution():
    rows = MetricRows(("owned",))
    try:
        rows.extend([{"path": "a.py", "line": 1, "end_line": 2}, {"path": "b.py", "line": 1, "end_line": 2}])
        tag = rows.connection.execute("SELECT path FROM metric_lookup WHERE ordinal=0").fetchone()[0]
        rows.connection.execute("UPDATE metric_lookup SET path=? WHERE ordinal=1", (tag,))
        with pytest.raises(ValueError, match="encrypted row"):
            list(rows.for_path("a.py"))
    finally:
        rows.close()


def test_spooled_quality_preserves_complete_output_tokens_gate_and_hotspots(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    body = "def work(value):\n" + "".join(f"    item{i} = value + {i}\n" for i in range(18)) + "    return item0\n"
    files = {"a.py": body, "b.py": body, "nested.py": "def outer():\n    def inner():\n        return 1\n    return inner()\n"}
    native = engine.native_observations(files)
    original = copy.deepcopy(native[4])
    expected = core.build(files, native[4], native[1], native[0], native[2])
    metrics, signals = EncryptedRows(("owned",)), SignalRows(("owned",))
    try:
        metrics.extend(native[4])
        signals.extend(native[1])
        actual = core.build(files, metrics, signals, native[0], native[2], consume_metrics=True)
        for _, quality in (expected, actual):
            quality.pop("performance")
        assert json.loads(json.dumps(actual)) == json.loads(json.dumps(expected))
        assert isinstance(actual[1]["metrics"], MetricRows)
        assert isinstance(actual[1]["symbols"], EncryptedRows)
        assert actual[1]["duplication"]["groups"]
        assert list(metrics) == native[4] == original
        for position, metric in enumerate(expected[1]["metrics"]):
            metric["new_code"] = position % 2 == 0
            actual[1]["metrics"]._replace(position, metric)
        conditions = [{"id": "owned-"+field, "metric": field, "scope": scope, "operator": "LTE", "threshold": 1}
                      for field, scope in (("cyclomatic", "NEW_CODE"), ("length", "OVERALL"), ("nesting", "NEW_CODE"))]
        for _, quality in (expected, actual):
            quality["configuration"]["gate"]["conditions"] = conditions
        assert core.gate(actual[1], actual[0]) == core.gate(expected[1], expected[0])
        assert core.summary(actual[1], actual[0]) == core.summary(expected[1], expected[0])
        assert core.hotspot_rows(actual[1], actual[0]) == core.hotspot_rows(expected[1], expected[0])
    finally:
        signals.close()
        metrics.close()


def test_failed_quality_build_closes_new_outputs_without_mutating_input(monkeypatch):
    metrics = EncryptedRows(("owned",))
    created = []
    original = EncryptedRows.__init__
    def recorded(self, *a, **kw):
        original(self, *a, **kw)
        created.append(self)
    monkeypatch.setattr(EncryptedRows, "__init__", recorded)
    error = RuntimeError("owned observer failure")
    def stop(name, event):
        if (name, event) == ("QUALITY_SYMBOLS", "START"):
            raise error
    try:
        with pytest.raises(RuntimeError) as raised:
            core.build({}, metrics, [], [], [], observe=stop)
        assert raised.value is error
        assert len(created) == 2 and all(row.closed for row in created)
        assert not metrics.closed and list(metrics) == []
    finally:
        metrics.close()


def test_quality_checkpoint_cancellation_propagates_without_partial_output(monkeypatch):
    metrics = EncryptedRows(("owned",))
    created, checked = [], []
    original = EncryptedRows.__init__
    def recorded(self, *a, **kw):
        original(self, *a, **kw)
        created.append(self)
    monkeypatch.setattr(EncryptedRows, "__init__", recorded)
    failure = TimeoutError("Owned quality deadline")
    def checkpoint():
        checked.append(True)
        if len(checked) == 2:
            raise failure
    try:
        with pytest.raises(TimeoutError) as raised:
            core.build({}, metrics, [{"type": "parser", "path": "owned.py", "state": "COMPLETED"}], [], [],
                       checkpoint=checkpoint)
        assert raised.value is failure
        assert len(created) == 2 and all(row.closed for row in created)
        assert not metrics.closed
    finally:
        metrics.close()


def test_post_analysis_failure_closes_outputs_and_replays_complete_checkpoint(storage, monkeypatch):  # noqa: F811
    from sqlalchemy import func, select

    from backend import publication_units
    from backend.db import ParserArtifact, Record
    from backend.generation_models import PublishedGeneration
    from backend.jobs import execute_analysis
    from tests.test_repository_store import captured

    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    db, user, repo = storage
    files = captured(storage, {"app.py": "def work(value):\n    return value + 1\n"})
    outputs, own = [], SignalRows.own
    def owned(self, rows):
        own(self, rows)
        outputs.append(rows)
    monkeypatch.setattr(SignalRows, "own", owned)
    prepare = publication_units.prepare
    def interrupted(*_a, **_k):
        raise RuntimeError("Owned post-analysis interruption")
    monkeypatch.setattr(publication_units, "prepare", interrupted)
    with pytest.raises(RuntimeError, match="Owned post-analysis"):
        execute_analysis(db, user, repo, files)
    assert len(outputs) == 2 and all(row.closed for row in outputs)
    for row in outputs:
        with pytest.raises(sqlite3.ProgrammingError):
            row.connection.execute("SELECT 1")
    assert db.scalar(select(func.count()).select_from(ParserArtifact)) > 0
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 0
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0
    job = db.scalar(select(Record).where(Record.kind == "job"))
    monkeypatch.setattr(publication_units, "prepare", prepare)
    snapshot, retried = execute_analysis(db, user, repo, files, job=job)
    assert retried.data["performance"]["counters"]["global_analysis_checkpoint_hits"] == 1
    assert snapshot.data["file_count"] == 1
    assert db.scalar(select(func.count()).select_from(PublishedGeneration)) == 1


def test_computation_checks_leave_queue_unlocked_and_observe_cancellation(storage, monkeypatch):  # noqa: F811
    from sqlalchemy import event, update
    from sqlalchemy.orm import sessionmaker

    from backend import jobs
    from backend.db import QueueEntry
    from backend.domain import add
    from backend.scheduling import JobCancelled, claim, register

    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {"state": "QUEUED", "source": "INVENTORY",
        "execution": "CELERY", "user_id": user.id})
    register(db, job)
    db.commit()
    assert claim(db, job, 1800)["state"] == "CLAIMED"
    updates = []
    def compute(db, *_a, progress, **_k):
        progress("VERIFYING")
        connection = db.connection()
        @event.listens_for(connection, "before_cursor_execute")
        def writes(_c, _cursor, statement, *_rest):
            if statement.lstrip().upper().startswith("UPDATE QUEUE_ENTRIES"):
                updates.append(statement)
        progress.check_current()
        assert not updates
        # A separate cancellation writer must succeed while this computation
        # transaction is still open. This detects accidental renewal locks.
        with sessionmaker(bind=db.get_bind())() as other:
            other.connection().exec_driver_sql("PRAGMA busy_timeout=100")
            other.execute(update(QueueEntry).where(QueueEntry.job_id == job.id,
                QueueEntry.organization_id == user.organization_id, QueueEntry.repository_id == repo.id)
                .values(cancel_requested=True))
            other.commit()
        progress.check_current()
        raise AssertionError("Cancelled computation continued")
    monkeypatch.setattr(jobs, "persist_analysis", compute)
    with pytest.raises(JobCancelled):
        jobs.execute_analysis(db, user, repo, {}, job=job)
    assert job.data["state"] == "CANCELLED" and not updates
