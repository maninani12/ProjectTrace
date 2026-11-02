"""Apply prototype DDL only after creation of a fresh owned fixture database."""

import argparse
import json
from pathlib import Path

from tests import snapshot_materialization_probe as pipeline
from tests.graph_index_prototype import install, listen_for_guards, mark


def run(root, mode, metrics, all_phases=False):
    original = pipeline.install
    installed, cleanup, counters = [], [], {}

    def instrumentation(recorder, count):
        from sqlalchemy import event

        from backend.db import Base, engine

        owners = original(recorder, count)

        def after_create(target, connection, **kwargs):
            raw = connection.connection.driver_connection
            mark(raw.execute("PRAGMA database_list").fetchone()[2])
            installed.append(install(raw, mode))

        event.listen(Base.metadata, "after_create", after_create)
        cleanup.append(lambda: event.remove(Base.metadata, "after_create", after_create))
        if mode == "validated_partial":
            cleanup.append(listen_for_guards(engine, counters))
        return owners

    pipeline.install = instrumentation
    try:
        result = pipeline.run(root, metrics, phases=("cold", "warm", "incremental") if all_phases else ("cold",))
    finally:
        for release in reversed(cleanup):
            release()
        pipeline.install = original
    result["index_prototype"] = {"mode": mode, "installed": installed, "query_guard_counters": counters}
    (root / "profile.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("mode")
    parser.add_argument("--metrics", type=int)
    parser.add_argument("--all-phases", action="store_true")
    args = parser.parse_args()
    result = run(args.root, args.mode, args.metrics, args.all_phases)
    print(
        json.dumps(
            {
                "mode": args.mode,
                "metrics": args.metrics,
                "states": result["states"],
                "integrity": result["integrity"],
                "generations": result["generation_states"],
                "pointers": result["pointers"],
            }
        )
    )
