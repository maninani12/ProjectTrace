"""Owned CI worker bootstrap: real application tasks, isolated broker keys and fault gates.

Never loaded by the API or production worker entry point. Gates pause execution;
the controller kills the actual prefork process group at the recorded boundary.
"""

import json
import os
import time
from pathlib import Path

from celery.signals import task_postrun

if os.getenv("PROJECTTRACE_BROKER_TESTS") != "owned-ci":
    raise RuntimeError("This worker bootstrap is restricted to owned CI acceptance.")

from workers import tasks  # noqa: E402

celery = tasks.celery
celery.conf.broker_transport_options = {
    **celery.conf.broker_transport_options,
    "global_keyprefix": os.environ["PROJECTTRACE_BROKER_PREFIX"],
}
runtime = Path(os.environ["PROJECTTRACE_BROKER_RUNTIME"])
original = tasks.execute_analysis


def gate(job, point):
    if os.getenv("PROJECTTRACE_BROKER_CUT") != point:
        return
    try:
        with (runtime / "boundary.json").open("x") as stream:
            json.dump({"job_id": job.id, "token": job.data["worker_token"], "boundary": point}, stream)
    except FileExistsError:
        return
    for _ in range(300):
        if (runtime / "release").exists():
            return
        time.sleep(0.1)
    raise RuntimeError("Owned fault gate was not released or terminated.")


def at_boundary(*args, **kwargs):
    gate(kwargs["job"], "BEFORE_ANALYSIS")
    result = original(*args, **kwargs)
    gate(result[1], "AFTER_PUBLICATION")
    return result


tasks.execute_analysis = at_boundary


@task_postrun.connect(weak=False)
def record_completion(task_id=None, state=None, retval=None, **_kwargs):
    # No source, keys, sessions, arbitrary return values or exception text.
    event = {"task_id": task_id, "state": state}
    if isinstance(retval, dict):
        event["result"] = {key: retval[key] for key in ("state", "recovered_jobs") if key in retval}
    with (runtime / "task-events.jsonl").open("a") as stream:
        stream.write(json.dumps(event) + "\n")
