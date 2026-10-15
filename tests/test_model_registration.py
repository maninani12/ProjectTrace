import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("first", ["backend.admin_models", "backend.db", "backend.generation_models", "backend.onboarding_models"])
def test_models_register_for_every_supported_import_entry(first, tmp_path):
    script = f"""
import importlib
importlib.import_module({first!r})
from backend.db import Base
import backend.main
assert {{'analysis_generations','generation_records','application_activity','learning_journeys'}} <= set(Base.metadata.tables)
assert 'uq_activity_generation_scope' in {{i.name for i in Base.metadata.tables['application_activity'].indexes}}
"""
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "APP_ENV": "demo",
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "entry.db").replace("\\", "/")}, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode()
