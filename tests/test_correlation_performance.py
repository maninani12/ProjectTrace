"""Graph backpressure keeps full relationships, fencing and atomic publication."""

import math
import os
import subprocess
import sys
import time

import pytest
from sqlalchemy import event, select

from analyzers.performance import Performance
from backend.analysis_budget import checkpoint
from backend.db import Record
from backend.domain import add
from backend.jobs import execute_analysis
from scripts.benchmark_repository_analysis import Resources, process_stats, windows_measurement_api
from tests.test_repository_store import captured
from tests.test_repository_store import storage as storage


def test_local_database_cache_is_bounded_without_changing_durability(storage):
    db, _, _ = storage
    connection = db.connection()
    assert connection.exec_driver_sql("PRAGMA cache_size").scalar() == -32768
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 2


def test_deferred_graph_checkpoint_still_fences_and_failure_rolls_back(storage):
    db, user, repo = storage
    db.commit()
    checked = []

    def fence():
        checked.append(True)
        if len(checked) == 2:
            raise TimeoutError("Synthetic graph deadline")

    db.info["analysis_output_checkpoint"] = fence
    for i in range(30):
        add(db, user.organization_id, repo.id, "graph_node", {"title": str(i)}, defer_flush=True)
    checkpoint(db, force=True, flush=False)
    assert len(db.new) == 30
    with pytest.raises(TimeoutError):
        checkpoint(db, force=True, flush=False)
    db.rollback()
    db.info.clear()
    assert not db.scalars(select(Record).where(Record.kind == "graph_node")).all()


def test_function_graph_flushes_full_bounded_batches_and_preserves_each_function(storage, monkeypatch):
    db, user, repo = storage
    count = 600
    source = "".join(f"def inspect_{i}(value):\n    return value + {i}\n\n" for i in range(count))
    files = captured(storage, {"app.py": source})
    phase, sizes = [None], []
    original = Performance.record

    def measured(self, component, *args, **kwargs):
        original(self, component, *args, **kwargs)
        if component == "CONFIGURATION_GRAPH":
            phase[0] = "FUNCTION_GRAPH"
        elif component == "FUNCTION_GRAPH":
            phase[0] = "DONE"

    monkeypatch.setattr(Performance, "record", measured)

    @event.listens_for(db, "before_flush")
    def writes(session, *_):
        if phase[0] == "FUNCTION_GRAPH" and session.new:
            sizes.append(len(session.new) + len(session.dirty))

    snapshot, job = execute_analysis(db, user, repo, files)
    assert job.data["completed_analysis"]["publication_state"] == "PUBLISHED"
    records = list(db.scalars(select(Record)))
    functions = [r for r in records if r.kind == "graph_node" and r.data.get("class") == "FUNCTION"]
    links = [r for r in records if r.kind == "edge" and r.data.get("relationship") == "IMPLEMENTED_IN"]
    assert len(functions) == len(links) == count
    assert {r.data["title"] for r in functions} == {f"inspect_{i}" for i in range(count)}
    assert {r.data["source"] for r in links} == {r.id for r in functions}
    assert all(r.organization_id == user.organization_id and r.repository_id == repo.id for r in records)
    assert all(r.data["scope"]["snapshot_id"] == snapshot.id for r in functions)
    assert sizes and max(sizes) <= 250
    assert sizes.count(250) >= 4
    assert len(sizes) <= math.ceil(2 * count / 250) + 2


@pytest.mark.skipif(os.name != "nt", reason="Installed Windows measurement adapter")
def test_resource_sampler_reuses_layouts_and_retires_exited_helpers():
    assert windows_measurement_api() is windows_measurement_api()
    assert process_stats()["rss_bytes"] > 0
    with Resources() as resources:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(.25)"])
        child.wait(timeout=10)
        deadline = time.monotonic() + 5
        while resources.handles and time.monotonic() < deadline:
            time.sleep(.05)
        assert not resources.handles
    assert resources.result["helper_calls"] == 1
    assert resources.result["sampled_process_tree_peak_rss_bytes"] > 0


def test_quality_projection_cannot_exceed_graph_row_budget(storage):
    db, user, repo = storage
    files = captured(storage, {f"app{i}.py": "def inspect(value):\n" + "    eval(value)\n" * 20 for i in range(13)})
    db.commit()
    sizes = []

    @event.listens_for(db, "before_flush")
    def writes(session, *_):
        sizes.append(len(session.new) + len(session.dirty))

    snapshot, job = execute_analysis(db, user, repo, files)
    assert len(snapshot.data["findings"]) >= 260
    assert job.data["completed_analysis"]["publication_state"] == "PUBLISHED"
    assert max(sizes) <= 250
