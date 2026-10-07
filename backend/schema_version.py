"""Installed migration identity for readiness; no imported project paths are used."""
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


@lru_cache(maxsize=1)
def expected_head():
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()
