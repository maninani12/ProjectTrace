"""Publication checkpoints also cover computation that does not insert records."""

import time


def checkpoint(db, *, force=False, flush=True):
    callback = db.info.get("analysis_output_checkpoint")
    if not callback:
        return
    steps = db.info.get("analysis_output_steps", 0) + 1
    current = time.perf_counter()
    previous = db.info.get("analysis_output_checked_at", current)
    if force or steps >= 250 or current - previous >= 1:
        callback()
        # Updates can accumulate without add(). Flush their bounded work batch
        # only after the deadline/fenced lease check; never commit output here.
        # Explicit bounded graph writers schedule their own flushes. A lease
        # check counts computation steps, not output rows; flushing on those
        # checks fragments graph batches without improving their row bound.
        if flush and (db.new or db.dirty):
            db.flush()
        db.info["analysis_output_steps"] = 0
        db.info["analysis_output_checked_at"] = current
    else:
        db.info["analysis_output_steps"] = steps
        db.info.setdefault("analysis_output_checked_at", current)


def clear(db):
    for key in ("analysis_output_checkpoint", "analysis_output_records", "analysis_output_steps",
                "analysis_output_checked_at"):
        db.info.pop(key, None)
