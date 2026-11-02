"""Unresolved history stays explicit when publication restores a stage receipt."""
import pytest
from sqlalchemy import select

from backend.db import Record
from backend.generation_models import AnalysisGeneration
from backend.generations import Generation
from backend.jobs import execute_analysis
from backend.repository_store import RepositoryFiles
from tests.test_public_snapshot_continuity import public_snapshot
from tests.test_repository_store import storage  # noqa: F401


@pytest.mark.parametrize("stage", ["CORRELATION", "POLICY"])
def test_unresolved_native_replay_retains_partial_status_and_explanation(storage, monkeypatch, stage):  # noqa: F811
    db, actor, repo = storage
    sources = {"app.py": "import subprocess\ndef work(command):\n    subprocess.run(command, shell=True)\n    subprocess.run(command, shell=True)\n"}
    base = public_snapshot(storage, sources, "a" * 40, legacy=True)
    save = Generation.save

    def interrupt(self, name, state):
        save(self, name, state)
        if name == stage:
            raise RuntimeError("Owned unresolved history interruption")

    monkeypatch.setattr(Generation, "save", interrupt)
    with pytest.raises(RuntimeError, match="Owned unresolved history"):
        public_snapshot(storage, sources, "b" * 40, base=base.id)
    pending = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.state == "STAGING"))
    monkeypatch.setattr(Generation, "save", save)
    head, _ = execute_analysis(db, actor, repo,
        RepositoryFiles(db, actor.organization_id, repo.id, pending.inventory_id),
        job=db.get(Record, pending.job_id), branch="main", git_commit="b" * 40, base_id=base.id)
    assert head.data["status"] == "PARTIAL"
    assert any(w.get("analyzer") == "NATIVE_HISTORY" for w in head.data["warnings"])
    assert head.data["quality_gate"]["status"] == "REVIEW_REQUIRED"
