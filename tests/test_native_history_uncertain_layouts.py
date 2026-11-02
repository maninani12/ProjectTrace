"""Defensive persisted metadata fixtures, not claims about real GitHub archives."""
from collections import Counter

import pytest
from sqlalchemy import select

from backend.db import FindingOccurrence, QualityAnalysis
from backend.jobs import execute_analysis
from backend.repository_store import RepositoryFiles, capture
from tests.test_public_snapshot_continuity import public_snapshot
from tests.test_repository_store import storage  # noqa: F401


@pytest.mark.parametrize("malformation", ["MISSING_PROVENANCE", "MIXED_ROOTS"])
def test_uncertain_stored_layout_does_not_verify_history(storage, malformation):  # noqa: F811
    db, actor, repo = storage
    repo.provider, repo.name = "GITHUB_PUBLIC", "owner/repo"
    body = "def work(items=[]):\n    return items\n"
    root = "repo-" + "a" * 40 + "/"
    items = [(root + "one/app.py", body.encode()),
             (("two/app.py" if malformation == "MIXED_ROOTS" else root + "two/app.py"), body.encode())]
    inventory = capture(db, actor.organization_id, repo, items, source="GITHUB_PUBLIC_ARCHIVE")
    if malformation != "MISSING_PROVENANCE":
        inventory.data = {**inventory.data, "provenance": {"source": "GITHUB_PUBLIC", "repository": "owner/repo",
            "commit": "a" * 40, "ref": "main"}}
    db.commit()
    base, _ = execute_analysis(db, actor, repo, RepositoryFiles(db, actor.organization_id, repo.id, inventory.id),
                               branch="main", git_commit="a" * 40)
    head = public_snapshot(storage, {"one/app.py": body, "two/app.py": body}, "b" * 40, base=base.id)
    assert head.data["status"] == "PARTIAL"
    events = list(db.scalars(select(FindingOccurrence).where(FindingOccurrence.snapshot_id == head.id)))
    assert events and all(e.status == "NOT_OBSERVED" for e in events)
    quality = db.get(QualityAnalysis, head.id).data
    assert quality["comparison_identity_unresolved"]
    assert not quality["resolved"] and not quality["deltas"].get("NEW", 0)
    assert quality["gate"]["status"] == "REVIEW_REQUIRED"
    assert quality["deltas"] == dict(Counter(f["delta"] for f in head.data["findings"] if f["category"] == "QUALITY"))
