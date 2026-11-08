"""Privacy, atomicity and size tests for candidate artifact projection."""

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.export_scale_diagnostics import NATIVE, RESOURCES, export_snapshots
from scripts.scale_diagnostic import MAX_RECEIPT_BYTES, Diagnostic

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="SCALE export uses Linux file flags")
IDENTITY = {"source_sha256": "1"*64, "slice_sha256": "2"*64, "image_sha256": "3"*64}
SCHEMA = Path(__file__).parents[1] / "docs/evidence/SCALE001_DIAGNOSTIC_SCHEMA_V1.json"


@pytest.fixture
def paths(tmp_path):
    source, destination = tmp_path/"input", tmp_path/"output"
    source.mkdir()
    destination.mkdir()
    return source, destination, Draft202012Validator(json.loads(SCHEMA.read_bytes()))


def snapshot(source, phase, state, code=None):
    path = source/f"scale-diagnostic-{phase}.json"
    observed = Diagnostic(path, revision="candidate", cache=phase, **IDENTITY)
    observed.stage = "ANALYZING"
    observed.routes["NATIVE"].update(starts=1)
    observed.write(state, code)
    return path


def pair(destination):
    paths = list((destination/"receipts").iterdir())
    assert {p.name for p in paths} == {NATIVE, RESOURCES}
    assert all(p.stat().st_size <= MAX_RECEIPT_BYTES for p in paths)
    return {p.name: json.loads(p.read_bytes()) for p in paths}


def test_two_projections_preserve_terminal_failure_and_unavailable_values(paths):
    source, destination, validator = paths
    cold = snapshot(source, "cold", "FAILED", "GLOBAL_CHECKPOINT_BUDGET")
    row = json.loads(cold.read_bytes())
    row["cgroup_scope"] = None
    cold.write_text(json.dumps(row))
    assert export_snapshots(source, destination, validator, IDENTITY)
    data = pair(destination)
    for receipt in data.values():
        assert receipt["phases"]["warm"] == {"capture": "MISSING", "observation": None}
        assert receipt["phases"]["cold"]["capture"] == "TERMINAL"
        assert receipt["phases"]["cold"]["observation"]["state"] == "FAILED"
        assert receipt["phases"]["cold"]["observation"]["failure_code"] == "GLOBAL_CHECKPOINT_BUDGET"
    assert data[RESOURCES]["phases"]["cold"]["observation"]["cgroup_scope"] is None
    assert "routes" not in data[RESOURCES]["phases"]["cold"]["observation"]
    assert "cgroup" not in data[NATIVE]["phases"]["cold"]["observation"]


def test_interrupted_collection_and_missing_baseline_never_claim_success(paths):
    source, destination, validator = paths
    assert export_snapshots(source, destination, validator, IDENTITY)
    assert not list(destination.iterdir())
    snapshot(source, "cold", "RUNNING")
    assert export_snapshots(source, destination, validator, IDENTITY)
    cold = pair(destination)[NATIVE]["phases"]["cold"]
    assert cold["capture"] == "INCOMPLETE" and cold["observation"]["state"] == "RUNNING"


@pytest.mark.parametrize("bad", ["truncated", "unknown_key", "wrong_label", "wrong_hash", "symlink", "duplicate", "oversized"])
def test_invalid_snapshot_is_withheld_without_losing_valid_peer(paths, bad):
    source, destination, validator = paths
    snapshot(source, "cold", "COMPLETED")
    warm = snapshot(source, "warm", "COMPLETED")
    row = json.loads(warm.read_bytes())
    sensitive = "owned-private-content-sentinel"
    if bad == "symlink":
        warm.unlink()
        target = source/"arbitrary.json"
        target.write_text(json.dumps(row))
        warm.symlink_to(target)
    elif bad == "truncated":
        warm.write_text('{"raw": "'+sensitive)
    elif bad == "duplicate":
        warm.write_text(warm.read_text()[:-1]+',"stage":"ANALYZING"}')
    elif bad == "oversized":
        warm.write_bytes(warm.read_bytes()+b" "*MAX_RECEIPT_BYTES)
    else:
        if bad == "unknown_key":
            row["cgroup"]["owned/private.py"] = sensitive
        elif bad == "wrong_hash":
            row["identity"]["image_sha256"] = "9"*64
        else:
            row["identity"]["revision"] = "baseline"
        warm.write_text(json.dumps(row))
    assert not export_snapshots(source, destination, validator, IDENTITY)
    assert pair(destination)[NATIVE]["phases"]["warm"] == {"capture": "REJECTED", "observation": None}
    assert all(sensitive not in p.read_text() for p in (destination/"receipts").iterdir())


def test_near_cap_output_is_bounded_and_atomic(paths, monkeypatch):
    source, destination, validator = paths
    path = snapshot(source, "cold", "COMPLETED")
    row = json.loads(path.read_bytes())
    fields = validator.schema["$defs"]["route"]["properties"]
    route_names = list(validator.schema["properties"]["routes"]["properties"])
    width = 730
    for name in route_names:
        row["routes"][name] = {field: 10**width for field in fields}
    path.write_text(json.dumps(row, separators=(",", ":")))
    assert 175_000 < path.stat().st_size <= MAX_RECEIPT_BYTES
    assert export_snapshots(source, destination, validator, IDENTITY)
    assert (destination/"receipts"/NATIVE).stat().st_size > 175_000
    pair(destination)

    snapshot(source, "warm", "COMPLETED")
    row["identity"]["cache"] = "warm"
    (source/"scale-diagnostic-warm.json").write_text(json.dumps(row, separators=(",", ":")))
    other = destination.parent/"other"
    other.mkdir()
    with pytest.raises(ValueError, match="byte budget"):
        export_snapshots(source, other, validator, IDENTITY)
    assert not list(other.iterdir())

    (source/"scale-diagnostic-warm.json").unlink()
    write = Path.write_bytes

    def fail_resource(path, data):
        if path.name == RESOURCES:
            raise OSError("owned write fault")
        return write(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_resource)
    with pytest.raises(OSError, match="owned write fault"):
        export_snapshots(source, other, validator, IDENTITY)
    assert not list(other.iterdir())
    with pytest.raises(ValueError, match="fresh"):
        export_snapshots(source, destination, validator, IDENTITY)
