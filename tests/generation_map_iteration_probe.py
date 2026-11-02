"""Owned fresh-process map iteration measurements; never executes input code."""
import gc
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


class CountingCipher:
    def __init__(self, original):
        self.original = original
        self.decryptions, self.encryptions = 0, 0
        self.paths = []

    def decrypt(self, *args, **kwargs):
        self.decryptions += 1
        if len(self.paths) < 3:
            frame, path = sys._getframe(1), []
            try:
                for _ in range(6):
                    if frame is None:
                        break
                    path.append(frame.f_globals.get("__name__", "") + "." + frame.f_code.co_qualname)
                    frame = frame.f_back
                self.paths.append(path)
            finally:
                del frame
        return self.original.decrypt(*args, **kwargs)

    def encrypt(self, *args, **kwargs):
        self.encryptions += 1
        return self.original.encrypt(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.original, name)


def complete_hash(value):
    combined, size = hashlib.sha256(), 0
    for part in json.JSONEncoder(separators=(",", ":")).iterencode(value):
        raw = part.encode()
        combined.update(raw)
        size += len(raw)
    return {"sha256": combined.hexdigest(), "bytes": size}


def profile_owned_map(root, count, *, repeats=3):
    """Build owned input outside measured processes; keep its key in env only."""
    import pytest

    from tests.test_generation_context import context
    from tests.test_repository_store import storage
    root.mkdir()
    mp = pytest.MonkeyPatch()
    fixture = storage.__wrapped__(root, mp)
    source = next(fixture)
    generation, state = context(source)
    values = {str(i): {f"owned_{j}": j for j in range(28)} for i in range(count)}
    expected = complete_hash(values)
    state["map"] = values
    generation.save("SNAPSHOT", state)
    generation.db.close()
    del state, values, generation
    gc.collect()
    samples = []
    try:
        for _ in range(repeats):
            completed = subprocess.run([sys.executable, "-m", __name__, str(root)],
                env={**os.environ, "PYTHONHASHSEED": "0"}, capture_output=True, text=True, timeout=180)
            if completed.returncode:
                raise RuntimeError(completed.stderr[-3000:])
            sample = json.loads(completed.stdout)
            assert sample["logical"] == expected and sample["count"] == count
            samples.append(sample)
        return {"count": count, "expected": expected, "samples": samples}
    finally:
        fixture.close()
        mp.undo()


def measure(root):
    os.environ.update(APP_ENV="demo", PROJECTTRACE_PARSER_ISOLATION="development")
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    import backend.context_maps as maps
    from backend.db import make_engine
    from backend.generation_models import AnalysisGeneration
    from backend.generations import Generation
    from scripts.benchmark_repository_analysis import process_stats
    engine = make_engine("sqlite:///" + str(root / "source.db"))
    with sessionmaker(engine, expire_on_commit=False)() as db:
        row = db.scalar(select(AnalysisGeneration))
        generation = Generation(db, row.job_id, row.organization_id, row.repository_id, row.signature,
            lambda: None, inventory_id=row.inventory_id, content_key=row.content_key)
        started = time.perf_counter()
        value = generation.load("SNAPSHOT")["map"]
        load_seconds = time.perf_counter() - started
        owner = value.rows.owner.rows
        cipher = CountingCipher(owner.key)
        owner.key = cipher
        tag, tag_calls = maps.tag, 0
        def observed_tag(*args):
            nonlocal tag_calls
            tag_calls += 1
            return tag(*args)
        maps.tag = observed_tag
        gc.collect()
        before = process_stats()
        started = time.perf_counter()
        logical = complete_hash(value)
        seconds = time.perf_counter() - started
        after = process_stats()
        result = {"scope": "OWNED_FRESH_PROCESS_STREAMING_MAP_ITERATION", "count": len(value),
            "logical": logical, "load_seconds": load_seconds, "iteration_seconds": seconds,
            "decryptions": cipher.decryptions, "encryptions": cipher.encryptions, "hmac_tag_calls": tag_calls,
            "first_decryption_paths": cipher.paths, "before": before, "after": after,
            "cache_size": owner.connection.execute("PRAGMA cache_size").fetchone()[0],
            "headers": len(value.reader.memo), "python_base_slots": dict.__len__(value)}
        maps.tag = tag
        owner.close()
    engine.dispose()
    return result


if __name__ == "__main__":
    print(json.dumps(measure(Path(sys.argv[1]).resolve())))
