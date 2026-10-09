"""Single local development runner using the same durable inputs and fenced workers."""

import logging
import threading

from sqlalchemy import select

from backend.db import Record

log = logging.getLogger("projecttrace.local_jobs")
_runner = None


class LocalTask:
    def retry(self, **kwargs):
        from celery.exceptions import Retry
        raise Retry("Local capacity is occupied; the durable job remains queued.")


class LocalJobs:
    def __init__(self, factory):
        self.factory = factory
        self.stopping, self.wake = threading.Event(), threading.Event()
        self.thread = threading.Thread(target=self.run, name="projecttrace-local-jobs", daemon=True)

    def start(self):
        global _runner
        if _runner is not None:
            raise RuntimeError("A local runner is already active in this API process.")
        _runner = self
        self.thread.start()

    def stop(self):
        global _runner
        self.stopping.set()
        self.wake.set()
        # Finish the fenced attempt; queued input stays durable for restart.
        from backend.jobs import inventory_time_budget
        self.thread.join(timeout=inventory_time_budget() + 30)
        if _runner is self:
            _runner = None

    def run(self):
        from celery.exceptions import Retry

        from backend.scheduling import recover_expired
        from workers.tasks import run_analysis

        while not self.stopping.is_set():
            try:
                with self.factory() as db:
                    recover_expired(db, execution="LOCAL")
                    jobs = list(db.scalars(select(Record).where(
                        Record.kind == "job", Record.data["execution"].as_string() == "LOCAL",
                        Record.data["state"].as_string() == "QUEUED",
                    ).order_by(Record.created_at).limit(100)))
                    pending = [(job.id, job.data.get("source")) for job in jobs]
                for job_id, source in pending:
                    if self.stopping.is_set():
                        break
                    try:
                        if source == "PUBLIC_GITHUB":
                            from workers.public_github import run_public_import
                            run_public_import(LocalTask(), job_id, session_factory=self.factory)
                        elif source in {"INVENTORY", "FILES", "ZIP"}:
                            run_analysis(LocalTask(), job_id, session_factory=self.factory)
                        else:
                            raise ValueError("Local imports do not run private SCM or advisory tasks.")
                    except Retry:
                        pass
                    except Exception as error:
                        log.warning("Local analysis stopped; job_id=%s error_type=%s", job_id, type(error).__name__)
            except Exception as error:
                log.warning("Local runner unavailable; error_type=%s", type(error).__name__)
            self.wake.wait(2)
            self.wake.clear()


def notify():
    if _runner is None or _runner.stopping.is_set():
        raise RuntimeError("Local runner is unavailable; restart ProjectTrace with JOB_MODE=local.")
    _runner.wake.set()


def ready():
    return _runner is not None and _runner.thread.is_alive() and not _runner.stopping.is_set()
