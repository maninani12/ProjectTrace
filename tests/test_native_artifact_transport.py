import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from analyzers import sandbox
from analyzers.parser_protocol import completed_packets, expand_native_artifact, native_artifact
from analyzers.sanitization import metadata


def observations(path="owned.js", tokens=12):
    from analyzers.engine import PARSER_SIGNATURE, VERSION, hash_text
    from analyzers.infrastructure_deep import config

    artifact = {"hash": hashlib.sha256(b"function owned() {}\n").hexdigest(), "version": VERSION,
                "parser_signature": PARSER_SIGNATURE, "findings": [], "signals": [], "warnings": [],
                "assets": [], "quality_metrics": [{"path": path, "name": "owned", "duplicate_tokens": [
                    {"value": "identifier:" + str(i % 13), "line": i // 5 + 1} for i in range(tokens)]}],
                "infrastructure_signature": hash_text(json.dumps(config(None), sort_keys=True))}
    return [artifact["findings"], artifact["signals"], artifact["warnings"], artifact["assets"],
            artifact["quality_metrics"], [], {path: artifact}, 0, {}]


def packet(path, result):
    return json.dumps({"schema": "projecttrace-parser-packet-v1", "path": path, "result": result,
                       "seconds": 0.1, "state": "COMPLETED"}).encode() + b"\n"


def test_compact_native_packet_preserves_complete_data_privacy_and_independent_cache():
    expected = observations(tokens=2000)
    expected[4][0]["duplicate_tokens"][0]["value"] = "ghp_" + "x" * 30
    compact = packet("owned.js", native_artifact("owned.js", expected))
    legacy = packet("owned.js", expected)
    assert len(compact) < len(legacy) * 0.51
    files = {"owned.js": "function owned() {}\n"}
    actual = completed_packets(compact, files, 16_000_000, expand=expand_native_artifact)
    control = completed_packets(legacy, files, 16_000_000, expand=expand_native_artifact)
    assert actual == control
    assert "ghp_" not in str(actual)
    row = actual["owned.js"]
    assert row[4] is not row[6]["owned.js"]["quality_metrics"]
    row[4][0]["name"] = "discarded scratch mutation"
    assert row[6]["owned.js"]["quality_metrics"][0]["name"] == "owned"


def test_reconstructed_native_rows_keep_logical_structure_and_wire_budgets(monkeypatch):
    from analyzers import parser_protocol

    compact = native_artifact("owned.js", observations())
    assert metadata(compact, maximum_nodes=70)
    monkeypatch.setattr(parser_protocol, "metadata", lambda value: metadata(value, maximum_nodes=70))
    raw = packet("owned.js", compact)
    with pytest.raises(ValueError, match="structure budget"):
        completed_packets(raw, {"owned.js": ""}, 16_000_000, expand=expand_native_artifact)
    with pytest.raises(ValueError, match="output budget"):
        completed_packets(raw, {"owned.js": ""}, len(raw) - 1, expand=expand_native_artifact)


def test_compact_native_prefix_survives_truncated_next_packet():
    row = observations()
    raw = packet("owned.js", native_artifact("owned.js", row)) + b'{"schema":'
    actual = completed_packets(raw, {"owned.js": "", "next.js": ""}, 16_000_000,
                               expand=expand_native_artifact)
    assert actual == {"owned.js": metadata(row)}


@pytest.mark.parametrize("change,code", [
    ("hash", "HELPER_SOURCE_HASH"), ("foreign-signal", "HELPER_SCOPE"),
    ("signature", "HELPER_CACHE_SCHEMA"), ("extra-artifact", "HELPER_CACHE_SCHEMA"),
    ("wrong-array-type", "HELPER_SCOPE"), ("reused", "HELPER_SCOPE"),
])
def test_compact_result_still_crosses_parent_scope_and_cache_guards(monkeypatch, change, code):
    from analyzers import isolated_analysis

    value = native_artifact("owned.js", observations())
    if change == "hash":
        value["artifact"]["hash"] = "wrong"
    elif change == "foreign-signal":
        value["artifact"]["signals"] = [{"path": "foreign.js", "type": "function"}]
    elif change == "signature":
        value["artifact"]["parser_signature"] = "wrong"
    elif change == "extra-artifact":
        value["artifact"]["extra"] = True
    elif change == "wrong-array-type":
        value["artifact"]["signals"] = "wrong"
    else:
        value["reused"] = 1
    monkeypatch.setattr(sandbox, "require_runtime", lambda: None)
    monkeypatch.setattr("analyzers.lexical.describe", lambda files: {p: {"iac_candidate": False} for p in files})
    monkeypatch.setattr("analyzers.languages.analyze_languages", lambda *_a, **_kw: {})
    monkeypatch.setattr("analyzers.infrastructure.structured_iac_batch", lambda *_a, **_kw: {})
    monkeypatch.setattr(sandbox, "invoke", lambda *_a, **_kw: (packet("owned.js", value), None))
    with pytest.raises(sandbox.SandboxFailure, match=code):
        isolated_analysis.native({"owned.js": "function owned() {}\n"}, {}, None)


@pytest.mark.parametrize("change", ["schema", "extra", "missing-array"])
def test_compact_native_envelope_rejects_unknown_or_incomplete_framing(change):
    value = native_artifact("owned.js", observations())
    if change == "schema":
        value["schema"] = "unknown"
    elif change == "extra":
        value["extra"] = True
    else:
        value["artifact"].pop("quality_metrics")
    with pytest.raises(ValueError, match="envelope"):
        completed_packets(packet("owned.js", value), {"owned.js": ""}, 16_000_000,
                          expand=expand_native_artifact)


def test_helper_refuses_to_pack_inconsistent_observation_and_cache_payloads():
    row = observations()
    row[6] = copy.deepcopy(row[6])
    row[4][0]["name"] = "different"
    with pytest.raises(ValueError, match="inconsistent"):
        native_artifact("owned.js", row)


def test_owned_worker_dispatch_emits_complete_compact_native_result(monkeypatch):
    from analyzers.engine import native_observations

    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    files = {"owned.py": "def owned(value):\n    return value + 1\n"}
    # Exercise the real installed dispatch/emitter on owned inert input. This
    # portable check intentionally does not claim Linux bootstrap enforcement.
    code = """
import json,sys
from analyzers import engine,sandbox
from analyzers.isolated_worker import STREAMED,dispatch
value=json.loads(sys.stdin.buffer.read())
assert dispatch('native',value,engine,sandbox) is STREAMED
"""
    result = subprocess.run([sys.executable, "-c", code], input=json.dumps({"files": files, "cache": {},
        "settings": {}, "parsed": {"languages": {}, "iac": {}}}).encode(), capture_output=True,
        env=os.environ.copy(), timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["result"]["schema"] == "projecttrace-native-artifact-v1"
    actual = completed_packets(result.stdout, files, 16_000_000, expand=expand_native_artifact)["owned.py"]
    control = list(native_observations(files))
    control[5] = sorted(control[5])
    assert actual[:8] == control
