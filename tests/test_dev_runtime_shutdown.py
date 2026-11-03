import json
from pathlib import Path

import pytest

from scripts import dev_runtime as runtime


def owned_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "STATE", tmp_path / "runtime.json")
    monkeypatch.setattr(runtime, "STOP", tmp_path / "api.stop")
    monkeypatch.setattr(runtime, "UI_STOP", tmp_path / "ui.stop")
    state = {
        "api": {"pid": 10, "identity": {"CommandLine": str(runtime.ROOT / "scripts/local_api.py")}},
        "ui": {"pid": 20, "identity": {"CommandLine": str(runtime.ROOT / "frontend/node_modules/vite/bin/vite.js")}},
    }
    runtime.STATE.write_text(json.dumps(state))
    return state


def test_missing_ui_watcher_retains_api_and_registration(monkeypatch, tmp_path):
    owned_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime, "verified", lambda entry: True)
    with pytest.raises(ValueError, match="no matching graceful shutdown watcher"):
        runtime.stop()
    assert runtime.STATE.exists()
    assert not runtime.STOP.exists() and not runtime.UI_STOP.exists()


def test_graceful_requests_preserve_state_on_ui_timeout(monkeypatch, tmp_path):
    owned_runtime(monkeypatch, tmp_path)
    Path(str(runtime.UI_STOP) + ".ready").write_text("20")
    monkeypatch.setattr(runtime, "verified", lambda entry: entry["pid"] == 20)
    ticks = iter([0, 31])
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ValueError, match="UI graceful shutdown timed out"):
        runtime.stop()
    assert runtime.STATE.exists() and runtime.UI_STOP.read_text() == "20"


def test_successful_shutdown_uses_no_os_termination(monkeypatch, tmp_path):
    owned_runtime(monkeypatch, tmp_path)
    Path(str(runtime.UI_STOP) + ".ready").write_text("20")
    monkeypatch.setattr(runtime, "verified", lambda entry: (
        not (runtime.STOP if entry["pid"] == 10 else runtime.UI_STOP).exists()
    ))
    monkeypatch.setattr(runtime.subprocess, "run", lambda *args, **kwargs: pytest.fail("OS termination is forbidden"))
    runtime.stop()
    assert not runtime.STATE.exists() and not runtime.STOP.exists()
    assert runtime.UI_STOP.read_text() == "20"


def test_wrong_project_ui_never_signals_api(monkeypatch, tmp_path):
    state = owned_runtime(monkeypatch, tmp_path)
    state["ui"]["identity"]["CommandLine"] = "unrelated-vite.js"
    runtime.STATE.write_text(json.dumps(state))
    monkeypatch.setattr(runtime, "verified", lambda entry: True)
    with pytest.raises(ValueError, match="outside this project"):
        runtime.stop()
    assert runtime.STATE.exists() and not runtime.STOP.exists()
