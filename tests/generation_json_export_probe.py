"""Owned export profiling, in fresh processes; no input code is executed."""
import gc
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from tests.generation_map_iteration_probe import CountingCipher, complete_hash


def profile(root, count, modes, repeats=2):
    import pytest

    from tests.test_generation_context import context
    from tests.test_repository_store import storage
    root.mkdir()
    mp = pytest.MonkeyPatch()
    fixture = storage.__wrapped__(root, mp)
    source = next(fixture)
    generation, state = context(source)
    values = {str(i): {f"owned_{j}": j for j in range(28)} for i in range(count)}
    expected = complete_hash({"claims_by_id": values})
    state["map"] = values
    generation.save("SNAPSHOT", state)
    generation.db.close()
    del state, values, generation
    gc.collect()
    try:
        samples = []
        for mode in modes:
            for _ in range(repeats):
                run = subprocess.run([sys.executable, "-m", __name__, str(root), mode],
                    env={**os.environ, "PYTHONHASHSEED": "0"}, capture_output=True, text=True, timeout=240)
                if run.returncode:
                    raise RuntimeError(run.stderr[-4000:])
                sample = json.loads(run.stdout)
                assert sample["logical"] == expected
                samples.append(sample)
        return {"count": count, "expected": expected, "samples": samples}
    finally:
        fixture.close()
        mp.undo()


class Sink:
    def __init__(self):
        self.hash, self.size, self.maximum_write = hashlib.sha256(), 0, 0

    def write(self, raw):
        self.hash.update(raw)
        self.size += len(raw)
        self.maximum_write = max(self.maximum_write, len(raw))
        return len(raw)


def measure(root, mode):
    os.environ.update(APP_ENV="demo", PROJECTTRACE_PARSER_ISOLATION="development")
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from backend.db import make_engine
    from backend.generation_models import AnalysisGeneration
    from backend.generations import Generation
    from scripts.benchmark_repository_analysis import process_stats
    engine = make_engine("sqlite:///" + str(root / "source.db"))
    with sessionmaker(engine, expire_on_commit=False)() as db:
        row = db.scalar(select(AnalysisGeneration))
        generation = Generation(db, row.job_id, row.organization_id, row.repository_id, row.signature,
            lambda: None, inventory_id=row.inventory_id, content_key=row.content_key)
        start = time.perf_counter()
        value = generation.load("SNAPSHOT")["map"]
        load_seconds = time.perf_counter() - start
        owner = value.rows.owner.rows
        cipher = CountingCipher(owner.key)
        owner.key = cipher
        original, live_peak = value._frame, 0
        def frame(position):
            nonlocal live_peak
            live_peak = max(live_peak, len(value.live))
            return original(position)
        value._frame = frame
        gc.collect()
        before = process_stats()
        sink = Sink()
        start_cpu, start = time.process_time(), time.perf_counter()
        document = {"claims_by_id": value}
        if mode == "dumps":
            text = json.dumps(document, separators=(",", ":"))
            sink.write(text.encode())
        elif mode == "join":
            text = "".join(json.JSONEncoder(separators=(",", ":")).iterencode(document))
            sink.write(text.encode())
        elif mode == "stream":
            from backend.json_export import write_json
            write_json(document, sink, separators=(",", ":"))
        elif mode == "string":
            from backend.json_export import dumps
            text = dumps(document, separators=(",", ":"))
            sink.write(text.encode())
        else:
            raise ValueError(mode)
        result = {"mode": mode, "scope": "OWNED_FRESH_PROCESS_EXPORT", "count": len(value),
            "logical": {"sha256": sink.hash.hexdigest(), "bytes": sink.size},
            "seconds": time.perf_counter() - start, "cpu_seconds": time.process_time() - start_cpu,
            "load_seconds": load_seconds, "decryptions": cipher.decryptions, "encryptions": cipher.encryptions,
            "live_values_peak": live_peak, "maximum_write": sink.maximum_write,
            "before": before, "after": process_stats(), "cache_size": owner.connection.execute("PRAGMA cache_size").fetchone()[0]}
        owner.close()
    engine.dispose()
    return result


if __name__ == "__main__":
    print(json.dumps(measure(Path(sys.argv[1]), sys.argv[2])))
