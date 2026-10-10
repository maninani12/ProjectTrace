"""Best-effort, bounded routine telemetry; required security audit is separate."""
import queue
import threading
import time
from collections import defaultdict

from backend.admin_models import ActivityEvent
from backend.db import now
from backend.domain import uid

_pending=queue.Queue(maxsize=1000)
_guard=threading.Lock()
_thread=None
_dropped=0
_written=0


def _write(batch):
    global _dropped,_written
    grouped=defaultdict(list)
    for factory,event in batch:
        grouped[factory].append(event)
    for factory,events in grouped.items():
        try:
            with factory() as db:
                db.add_all(ActivityEvent(**event) for event in events)
                db.commit()
            _written+=len(events)
        except Exception:
            # UI responses and authorization never depend on routine analytics.
            _dropped+=len(events)


def _run():
    while True:
        item=_pending.get()
        batch=[item]
        while len(batch)<100:
            try:
                batch.append(_pending.get_nowait())
            except queue.Empty:
                break
        try:
            _write(batch)
        finally:
            for _ in batch:
                _pending.task_done()


def emit(factory,*,organization_id,actor_id=None,action,category,outcome,target_id=None,repository_id=None,correlation_id=None,data=None):
    global _thread,_dropped
    from backend.admin_common import safe_metadata
    event={"id":uid(),"organization_id":organization_id,"actor_id":actor_id,"repository_id":repository_id,
        "action":action[:80],"category":category[:30],"outcome":outcome[:20],"target_id":target_id,
        "correlation_id":correlation_id,"data":safe_metadata(data or {}),"created_at":now()}
    with _guard:
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=_run,name="projecttrace-activity",daemon=True)
            _thread.start()
    try:
        _pending.put_nowait((factory,event))
    except queue.Full:
        _dropped+=1


def flush(timeout=2):
    until=time.monotonic()+timeout
    while _pending.unfinished_tasks and time.monotonic()<until:
        time.sleep(.01)
    return _pending.unfinished_tasks==0


def health():
    return {"backlog":_pending.qsize(),"capacity":1000,"written_this_process":_written,"dropped_this_process":_dropped,
        "durability":"Best effort routine telemetry; abrupt process loss may discard buffered events. Required administrative audit commits atomically."}
