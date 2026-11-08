"""Contracts for the opt-in SCALE diagnostic receipt."""

import gc
import json
import subprocess

import pytest

from analyzers import isolated_analysis, parser_protocol, sandbox
from analyzers.performance import Performance
from scripts.scale_diagnostic import MAX_RECEIPT_BYTES, counter_delta, diagnostic, route, snapshot

IDENTITY = {"revision": "candidate", "cache": "fixture", "source_sha256": "1"*64,
            "slice_sha256": "2"*64, "image_sha256": "3"*64}


def test_fixed_routes_follow_supported_terraform_names():
    assert route("iac", ["owned/main.TF"]) == "HCL_TERRAFORM"
    assert route("iac", ["owned/plan.tf.json", "owned/compose.yaml"]) == "HCL_MIXED"
    assert route("iac", ["owned/compose.yaml"]) == "HCL_UNNEEDED"
    assert route("iac_without_hcl", ["owned/main.tf"]) == "NO_HCL_MISROUTE"
    assert route("iac_without_hcl", ["owned/Dockerfile"]) == "NO_HCL_DOCKERFILE"
    assert route("iac_without_hcl", ["owned/compose.json"]) == "NO_HCL_JSON"
    assert route("iac_without_hcl", ["owned/compose.yaml"]) == "NO_HCL_YAML"


def test_cgroup_deltas_distinguish_zero_unavailable_and_reset(tmp_path):
    events = tmp_path / "memory.events"
    events.write_text("max 0\noom 2\noom_kill 0\n")
    (tmp_path / "io.stat").write_text("8:0 rbytes=0 wbytes=11\n8:1 rbytes=0 wbytes=5\n")
    (tmp_path / "cpu.max").write_text("200000 100000\n")
    a = snapshot(tmp_path)
    events.write_text("max 0\noom 1\noom_kill 0\n")
    (tmp_path / "io.stat").write_text("8:0 rbytes=0 wbytes=13\n8:1 rbytes=0 wbytes=10\n")
    b = snapshot(tmp_path)
    delta = counter_delta(a, b)
    assert b["memory.current"] is None and b["cpu.max"] == "200000 100000"
    assert delta["memory.events"] == {"low": None, "high": None, "max": 0, "oom": None, "oom_kill": 0}
    assert delta["io.stat"]["rbytes"] == 0 and delta["io.stat"]["wbytes"] == 7
    assert delta["io.pressure"]["full"] is None


def test_disabled_and_failed_diagnostic_restore_hooks_and_strip_paths(tmp_path):
    original = (subprocess.Popen, sandbox.invoke, parser_protocol.metadata, Performance.switch, tuple(gc.callbacks))
    with diagnostic(None):
        assert (subprocess.Popen, sandbox.invoke, parser_protocol.metadata, Performance.switch, tuple(gc.callbacks)) == original

    path = tmp_path / "receipt.json"
    filename = "owned/private-fixture.py"
    contents = "owned-plaintext-sentinel"
    packet = json.dumps({"schema": "projecttrace-parser-packet-v1", "path": filename,
                         "result": {"value": contents}, "seconds": 0, "state": "COMPLETED"}).encode() + b"\n"
    with pytest.raises(RuntimeError, match=contents):
        with diagnostic(path, **IDENTITY):
            Performance().switch("ANALYZING")
            assert isolated_analysis.completed_packets(packet, {filename: ""}, 1024) == {filename: {"value": contents}}
            raise RuntimeError(contents)
    assert (subprocess.Popen, sandbox.invoke, parser_protocol.metadata, Performance.switch, tuple(gc.callbacks)) == original
    raw = path.read_bytes()
    assert len(raw) < MAX_RECEIPT_BYTES and all(x.encode() not in raw for x in (filename, contents))
    receipt = json.loads(raw)
    assert receipt["state"] == "FAILED" and receipt["stage"] == "ANALYZING" and receipt["failure_code"] == "OTHER"
    counters = receipt["packets"]["NATIVE/PYTHON"]
    assert counters["admitted"] == counters["validated"] == counters["frames"] == counters["guard_observations"] == 1
    assert counters["logical_nodes"] == 2 and counters["node_samples"] == 1
