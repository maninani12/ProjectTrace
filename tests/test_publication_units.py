"""Private publication units survive a real child-process termination."""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from backend.db import AnalysisInput, PublicationUnit, QueueEntry, Record
from backend.domain import add
from backend.publication_units import Drafts, key, prepare
from tests.test_repository_store import captured, storage  # noqa: F401


def test_private_preparation_survives_actual_process_exit(storage):  # noqa: F811
    db, user, repo = storage
    from backend.queue import cipher
    from backend.scheduling import claim, ensure_current, recover_expired, register
    files = captured(storage, {"app.py": "def work():\n    return 1\n", "README.md": "# Overview\n"})
    job = add(db, user.organization_id, repo.id, "job", {"state": "QUEUED", "source": "INVENTORY"})
    register(db, job)
    db.add(AnalysisInput(job_id=job.id, organization_id=user.organization_id, repository_id=repo.id,
        ciphertext=cipher().encrypt(json.dumps({"inventory_id": files.inventory_id}).encode()).decode(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()))
    db.commit()
    script = '''
import os,sys
from sqlalchemy.orm import sessionmaker
from backend.db import Record,make_engine
from backend.repository_store import RepositoryFiles
from backend.publication_units import prepare
from backend.scheduling import claim,ensure_current
engine=make_engine(sys.argv[1])
with sessionmaker(engine,expire_on_commit=False)() as db:
 files=RepositoryFiles(db,'tenant','repo',sys.argv[3])
 job=db.get(Record,sys.argv[2])
 assert claim(db,job,120)['state']=='CLAIMED'
 calls=0
 def checkpoint():
  global calls
  ensure_current(db,job,renew_seconds=120)
  calls+=1
  if calls==5: os._exit(73)
 prepare(db,sys.argv[2],files,'a'*64,{'files':list(files),'signals':[]},checkpoint)
'''
    completed = subprocess.run([sys.executable, "-c", script, str(db.get_bind().url), job.id, files.inventory_id],
                               env=os.environ.copy(), timeout=30, capture_output=True)
    assert completed.returncode == 73, completed.stderr.decode()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(PublicationUnit)) == 3
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind.in_(["snapshot", "evidence", "graph_node", "edge"]))) == 0
    before = db.get(PublicationUnit, (job.id, key("a" * 64, "EVIDENCE", next(iter(files))))).ciphertext
    old_token = db.get(QueueEntry, job.id).worker_token
    db.get(QueueEntry, job.id).lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    db.commit()
    assert recover_expired(db) == [job.id]
    db.refresh(job)
    assert claim(db, job, 120)["token"] != old_token
    def fenced():
        ensure_current(db, job, renew_seconds=120)
    drafts = prepare(db, job.id, files, "a" * 64, {"files": list(files), "signals": []}, fenced)
    assert drafts.require("FILE_GRAPH", "README.md")["sections"] == [{"title": "Overview", "line": 1}]
    assert db.get(PublicationUnit, (job.id, key("a" * 64, "EVIDENCE", next(iter(files))))).ciphertext == before
    assert db.scalar(select(func.count()).select_from(PublicationUnit)) == 6
    drafts = prepare(db, job.id, files, "a" * 64, {"files": list(files), "signals": []}, fenced)
    assert drafts.completed == 0


def test_stage_dependency_digest_and_scope_fail_closed(storage):  # noqa: F811
    db, user, repo = storage
    captured(storage, {"app.py": "VALUE=1"})
    job = add(db, user.organization_id, repo.id, "job", {})
    db.commit()
    drafts = Drafts(db, job.id, user.organization_id, repo.id, "a" * 64, lambda: None)
    with pytest.raises(ValueError, match="dependency"):
        drafts.save("FILE_GRAPH", "app.py", {}, ("EVIDENCE", "app.py"))
    db.rollback()
    with pytest.raises(ValueError, match="scope"):
        Drafts(db, job.id, "other", repo.id, "a" * 64, lambda: None)
    drafts.save("MANIFEST", "", {"paths": ["app.py"]})
    row = db.get(PublicationUnit, (job.id, key("a" * 64, "MANIFEST")))
    row.result_digest = "0" * 64
    db.commit()
    with pytest.raises(ValueError, match="digest"):
        drafts.load("MANIFEST")


def test_windows_long_source_storage_path(storage, monkeypatch, tmp_path):  # noqa: F811
    import os
    if os.name != "nt":
        pytest.skip("Windows extended-length path regression")
    from backend.repository_store import BlobStore
    db, user, _ = storage
    directory = tmp_path / ("long-storage-" + "a" * 80) / ("nested-" + "b" * 80)
    monkeypatch.setenv("SOURCE_BLOB_DIR", str(directory))
    store = BlobStore()
    raw = b"Private long-path source fixture"
    digest, _ = store.put(db, user.organization_id, raw)
    db.commit()
    assert len(str(store.path(user.organization_id, digest))) > 260
    assert store.read(user.organization_id, digest) == raw
    assert raw not in store.path(user.organization_id, digest).read_bytes()

@pytest.mark.parametrize("change", ["REPLACED", "CANCELLED"])
def test_publication_unit_writer_is_fenced_by_queue_lease(storage, change):  # noqa: F811
    from backend.db import QueueEntry
    from backend.scheduling import JobCancelled, claim, ensure_current, register
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {"state": "QUEUED", "source": "INVENTORY"})
    register(db, job)
    db.commit()
    assert claim(db, job, 120)["state"] == "CLAIMED"
    drafts = Drafts(db, job.id, user.organization_id, repo.id, "a" * 64,
                    lambda: ensure_current(db, job, renew_seconds=120))
    queue = db.get(QueueEntry, job.id)
    if change == "REPLACED":
        queue.worker_token = "replacement-token"
    else:
        queue.cancel_requested = True
    db.commit()
    with pytest.raises(JobCancelled):
        drafts.save("MANIFEST", "", {"paths": []})
    db.rollback()
    assert db.scalar(select(func.count()).select_from(PublicationUnit)) == 0


def test_publication_units_reject_direct_sql_tenant_substitution(storage):  # noqa: F811
    from sqlalchemy.exc import IntegrityError
    db, user, repo = storage
    job = add(db, user.organization_id, repo.id, "job", {})
    db.commit()
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        db.execute(PublicationUnit.__table__.insert().values(job_id=job.id,unit_key="a"*64,
            organization_id="other",repository_id=repo.id,signature="b"*64,stage="MANIFEST",
            ciphertext="inert",result_digest="c"*64,expires_at="2099-01-01"))
    db.rollback()
