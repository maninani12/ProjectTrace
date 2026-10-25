"""Portable IPC/policy tests; actual kernel enforcement lives in required Linux CI."""

import json
import os
import sys

import pytest

from analyzers import sandbox
from analyzers.parser_protocol import completed_packets


def test_helper_decoder_uses_bounded_python_scanning(monkeypatch):
    value = {"quoted": '[x] \\" α', "array": [None, True, 3, {"nested": False}]}
    raw = json.dumps(value).encode()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Native JSON scanner used")
    monkeypatch.setattr(json, "loads", forbidden)
    assert sandbox.decode_packet(raw) == value


@pytest.mark.parametrize("raw,code", [("[" * 101, "HELPER_PROTOCOL_DEPTH"), ("," * 1_000_001, "HELPER_PROTOCOL_NODES")])
def test_helper_protocol_rejects_excessive_structure(raw, code):
    with pytest.raises(sandbox.SandboxFailure, match=code):
        sandbox.decode_packet(raw)


@pytest.mark.parametrize("change", ["development", "unsupported-platform"])
def test_production_has_no_uncontained_mode(monkeypatch, change):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development" if change == "development" else "required")
    if change == "unsupported-platform":
        monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(sandbox.SandboxFailure, match="ISOLATION_REQUIRED"):
        sandbox.required()


def test_cache_policy_separates_explicit_development_from_required(monkeypatch):
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    assert sandbox.cache_policy() != sandbox.POLICY
    assert sandbox.status()["enforcement"] == "DEVELOPMENT_UNCONTAINED"
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "required")
    assert sandbox.cache_policy() == sandbox.POLICY


@pytest.mark.parametrize("invalid", ["wrong-schema", "wrong-path", "duplicate"])
def test_completed_packets_reject_unscoped_or_duplicate_output(invalid):
    packet = {"schema": "projecttrace-parser-packet-v1", "path": "app.py", "result": [], "seconds": 0.1, "state": "COMPLETED"}
    if invalid == "wrong-schema":
        packet["schema"] = "unexpected"
    if invalid == "wrong-path":
        packet["path"] = "other-tenant.py"
    raw = json.dumps(packet).encode() + b"\n"
    if invalid == "duplicate":
        raw *= 2
    with pytest.raises(ValueError):
        completed_packets(raw, {"app.py": "pass"}, 10000)


def test_completed_prefix_survives_a_truncated_next_packet():
    packet = {"schema": "projecttrace-parser-packet-v1", "path": "a.py", "result": ["owned"], "seconds": 0.1, "state": "COMPLETED"}
    raw = json.dumps(packet).encode() + b'\n{"schema":'
    assert completed_packets(raw, {"a.py": "pass", "b.py": "pass"}, 10000) == {"a.py": ["owned"]}


@pytest.mark.parametrize("header", [b"[]", b"null", b'"unexpected"'])
def test_non_object_attestation_is_rejected_with_safe_diagnostic(monkeypatch, header):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sandbox, "bounded_process", lambda *_args, **_kwargs: (header + b"\n{}", None))
    with pytest.raises(sandbox.SandboxFailure, match="ISOLATION_NOT_ATTESTED"):
        sandbox.invoke("probe", {})


@pytest.mark.skipif(os.name != "posix", reason="Linux-only pipe transport; Windows remains uncontained development")
def test_parent_pipe_transport_bounds_real_stdout_flood():
    with pytest.raises(sandbox.SandboxFailure, match="HELPER_OUTPUT_BUDGET"):
        sandbox.bounded_process([sys.executable, "-c", "import os; os.write(1,b'x'*2_000_000)"], b"",
                                seconds=3, maximum=65536, environment={"LANG": "C.UTF-8"})


@pytest.mark.skipif(os.name != "posix", reason="Linux-only pipe transport; Windows remains uncontained development")
def test_parent_pipe_transport_kills_owned_timeout():
    result, failure = sandbox.bounded_process([sys.executable, "-c", "import time; time.sleep(2)"], b"",
                                              seconds=0.1, maximum=65536, environment={"LANG": "C.UTF-8"})
    assert result == b"" and failure == "HELPER_TIMEOUT"
    assert os.name == "posix"  # This transport contract targets Linux only.
