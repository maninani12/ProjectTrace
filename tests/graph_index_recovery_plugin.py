"""Explicit opt-in v2 subjects for frozen assertions and disposable regressions.

No assertion, fixture input, expected row or frozen source file is rewritten.
Historical modes retain their own DDL; every repaired mode validates snapshots.
The manifest records exactly which test dependencies are rebound to v2.
"""

import hashlib
import json
import os
from pathlib import Path

from tests import graph_index_prototype as original
from tests import graph_index_recovery as recovery

SAVED = {}


def pytest_configure(config):
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"]).resolve()
    manifest = json.loads((root / "preserved.json").read_text())
    source = root.parent / "graph-index-prototype-20261027" / "test_candidate_contract.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["historical_strict_sha256"]
    for name in ("install", "listen_for_guards"):
        SAVED[name] = getattr(original, name)
        setattr(original, name, getattr(recovery, name))


def pytest_collection_modifyitems(config, items):
    rebound = []
    for module in {item.module for item in items}:
        if Path(module.__file__).name != "test_candidate_contract.py":
            continue
        for name, value in recovery.frozen_api_bindings().items():
            setattr(module, name, value)
            rebound.append(
                {
                    "test_module": module.__file__,
                    "subject": name,
                    "implementation": value.__module__ + "." + value.__name__,
                }
            )
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"])
    label = config.getoption("--junitxml", default=None)
    destination = root / ((Path(label).stem if label else "pytest") + "-bindings.json")
    if destination.exists():
        raise ValueError("Never overwrite a previous test dependency receipt.")
    destination.write_text(
        json.dumps(
            {
                "revision": 2,
                "expected_results_modified": False,
                "frozen_test_file_modified": False,
                "bindings": rebound,
                "mode_contract": "Partial and CASE keep their actual DDL; both now receive the validated candidate's snapshot triggers. Readers replay the installed schema with recursive guards and legacy traversal ordering.",
            },
            indent=2,
        )
    )


def pytest_unconfigure(config):
    for name, value in SAVED.items():
        setattr(original, name, value)
