"""Explicit opt-in scalar subjects for immutable legacy assertions and fixtures."""

import hashlib
import json
import os
from pathlib import Path

from tests import graph_index_prototype as original
from tests import graph_scalar_prototype as scalar

SAVED = {}


def pytest_configure(config):
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"])
    manifest = json.loads((root / "preserved.json").read_text())
    source = root.parent / "graph-index-prototype-20261027/test_candidate_contract.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["historical_strict_sha256"]
    for name, value in (("install", scalar.install), ("listen_for_guards", scalar.enable_compiler)):
        SAVED[name] = getattr(original, name)
        setattr(original, name, value)


def pytest_collection_modifyitems(config, items):
    bindings = []
    for module in {item.module for item in items}:
        if Path(module.__file__).name == "test_candidate_contract.py":
            for name in ("install", "query_results"):
                setattr(module, name, getattr(scalar, name))
                bindings.append(
                    {
                        "module": module.__file__,
                        "subject": name,
                        "implementation": "tests.graph_scalar_prototype." + name,
                    }
                )
    root = Path(os.environ["SCALE001_PROTOTYPE_ROOT"])
    label = config.getoption("--junitxml", default=None)
    path = root / ((Path(label).stem if label else "pytest") + "-bindings.json")
    if path.exists():
        raise ValueError("Never overwrite a binding receipt.")
    path.write_text(
        json.dumps(
            {
                "bindings": bindings,
                "assertions_or_expected_rows_modified": False,
                "historical_mode_labels": "Three independent database copies of ONE full-membership projection candidate; not three different architectures.",
                "legacy_guard_utility": "The nine original static guard-proof assertions still test the unchanged legacy utility. It is not used by this candidate's readers.",
                "known_gate_conflict": "The original legacy test requires WHERE kind != 'snapshot' on all indexes after upgrade, which contradicts full membership. That assertion remains unchanged and may fail.",
            },
            indent=2,
        )
    )


def pytest_unconfigure(config):
    for name, value in SAVED.items():
        setattr(original, name, value)
