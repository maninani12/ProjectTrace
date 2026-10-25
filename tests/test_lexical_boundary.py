"""Portable algorithms/protocol/privacy tests; Linux enforcement is tested separately."""

import json
import re
import time

import pytest

from analyzers import lexical_worker, sandbox
from analyzers.engine import ENV_SECRET_RE, PRIVATE_RE, SECRET_RE
from analyzers.lexical import changed_ranges, digest, packet, validate_description
from analyzers.parser_protocol import completed_packets
from analyzers.sanitization import metadata, redact
from analyzers.source_input import SourceFiles


@pytest.fixture(autouse=True)
def algorithm_mode(monkeypatch):
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    monkeypatch.setenv("APP_ENV", "demo")


def legacy_redaction(text):
    text = PRIVATE_RE.sub("[REDACTED PRIVATE KEY]", text)
    text = re.sub(r"(?i)((?:postgres(?:ql)?|mysql|mongodb)(?:\+\w+)?://[^\s/:]+:)[^\s/@]+(@)", r"\1[REDACTED]\2", text)
    text = re.sub(r"(?m)^(?:[A-Z_]*(?:PASSWORD|TOKEN|SECRET|API_KEY))\s*=\s*[^\n]+$", "[REDACTED ENVIRONMENT SECRET]", text)
    return SECRET_RE.sub("[REDACTED SECRET]", ENV_SECRET_RE.sub("[REDACTED ENVIRONMENT SECRET]", text))


@pytest.mark.parametrize("text", [
    "plain source\nno credentials\n", "API_KEY=owned-private-value\n",
    "token: owned_fixture_credential_123456", "x = 'postgresql+psycopg://db:owned-private-password@localhost/db'",
    'api_key = "owned_fixture_credential_123456"', "token='ghp_abcdefghijklmnopqrstuvwxyz1234'",
    "access=AKIA0123456789012345", "-----BEGIN RSA PRIVATE KEY-----\nowned-private-material\n-----END PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----\nowned-incomplete-material", "PREFIX_PASSWORD=short",
    "prefix mysql://name:private@localhost and mongodb://name:another@host",
])
def test_trusted_redactor_retains_supported_baseline_forms(text):
    assert redact(text) == legacy_redaction(text)


def test_env_redaction_intentionally_preserves_newlines_for_evidence_offsets():
    text = "token: owned_fixture_credential_123456\n"
    assert legacy_redaction(text) == "[REDACTED ENVIRONMENT SECRET]"
    assert redact(text) == "[REDACTED ENVIRONMENT SECRET]\n"


def test_trusted_redactor_is_bounded_for_adversarial_long_candidates():
    source = ("secret " * 60000) + ("-----BEGIN NOT-A-KEY----- " * 8000)
    started = time.perf_counter()
    assert redact(source) == source
    assert time.perf_counter() - started < 5
    with pytest.raises(ValueError):
        redact("x" * 1_000_001)


@pytest.mark.parametrize("value", [{"ordinary": float("nan")}, {"ordinary": object()},
                                   {"ghp_abcdefghijklmnopqrstuvwxyz111": 1, "ghp_abcdefghijklmnopqrstuvwxyz222": 2}])
def test_metadata_guard_rejects_invalid_scalars_and_redacted_key_collision(value):
    with pytest.raises(ValueError):
        metadata(value)


def test_metadata_guard_redacts_sensitive_containers_and_rejects_cycles():
    value = metadata({"credentials": ["owned-password"], "nested": {"password": {"value": "owned-password"}},
                      "notice": "postgres://owned:owned-private@host/db"})
    assert "owned-password" not in json.dumps(value) and "owned-private" not in json.dumps(value)
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError):
        metadata(cycle)


def test_metadata_guard_preserves_typed_tuple_contract_while_sanitizing_children():
    value = metadata({"changed_lines": {"owned.py": [(1, 1)]}, "typed": ("ghp_abcdefghijklmnopqrstuvwxyz1234",)})
    assert value["changed_lines"]["owned.py"] == [(1, 1)]
    assert value["typed"] == ("[REDACTED SECRET]",)
    assert json.loads(json.dumps(value))["changed_lines"]["owned.py"] == [[1, 1]]


@pytest.mark.parametrize("field,value", [("path", "foreign.py"), ("request_hash", "wrong"),
                                       ("bytes", 999), ("source_language", "VERIFIED"), ("generated_header", "true")])
def test_description_schema_cannot_substitute_scope_or_counts(field, value):
    request = packet("a.py", "pass\n")
    description = lexical_worker.describe([request])[0]
    description[field] = value
    with pytest.raises(sandbox.SandboxFailure):
        validate_description(description, request)


@pytest.mark.parametrize("changes", [{"seconds": float("nan")}, {"seconds": -1}, {"state": "VERIFIED"}, {"extra": True}])
def test_completed_packet_rejects_manipulated_control_metadata(changes):
    packet = {"schema": "projecttrace-parser-packet-v1", "path": "a.py", "result": [], "seconds": 0.1, "state": "COMPLETED"}
    packet.update(changes)
    with pytest.raises(ValueError):
        completed_packets(json.dumps(packet).encode() + b"\n", {"a.py": "pass"}, 10000)


def test_persistence_guard_redacts_even_when_parser_omits_sanitization(storage):  # noqa: F811 -- imported fixture
    from backend.domain import add
    db, user, repo = storage
    row = add(db, user.organization_id, repo.id, "owned_privacy_probe", {
        "credentials": {"password": "owned-private"}, "nested": ["ghp_abcdefghijklmnopqrstuvwxyz1234"]})
    db.commit()
    db.refresh(row)
    assert "owned-private" not in json.dumps(row.data) and "abcdefghijklmnopqrstuvwxyz" not in json.dumps(row.data)


@pytest.mark.parametrize("state", ["BINARY", "OVERSIZED", "UNSUPPORTED_ENCODING"])
def test_unreadable_codeowners_cannot_become_absent_or_reuse_cached_ownership(state):
    from analyzers.lexical import Ownership, ownership_rules
    files = SourceFiles({"a.py": "pass"}, intake=[{"path": "CODEOWNERS", "state": state, "bytes": 600000}])
    files._contained_ownership = Ownership("")
    with pytest.raises(sandbox.SandboxFailure, match="CODEOWNERS_UNREADABLE"):
        ownership_rules(files)


@pytest.mark.parametrize("ranges", [[[1, 999]], [[True, 1]], [[2, 2], [1, 1]]])
def test_diff_schema_rejects_out_of_range_or_unordered_results(monkeypatch, ranges):
    monkeypatch.setattr(sandbox, "call", lambda *_a, **_kw: {
        "path": "a.py", "signature": digest(["a.py", "old", "new"]), "ranges": ranges})
    with pytest.raises(sandbox.SandboxFailure, match="DIFF_SCHEMA"):
        changed_ranges("a.py", "old", "new")


@pytest.mark.parametrize("row,warnings,code", [
    ({"path": "foreign.md"}, [], "HELPER_RESULT_SCOPE"),
    ({"path": "README.md", "text": "x", "category": "TECHNOLOGY", "expected": "fastapi", "line": 999,
      "assertion_family": "declaration"}, [], "HELPER_DOCUMENT_SCHEMA"),
    ({"path": "README.md"}, [{"path": "foreign.md"}], "HELPER_WARNING_SCOPE"),
])
def test_document_result_identity_and_line_contract_is_independently_validated(row, warnings, code):
    from analyzers.isolated_analysis import validate_source_rows
    with pytest.raises(sandbox.SandboxFailure, match=code):
        validate_source_rows([row], warnings, {"README.md": "Owned\n"}, documentation=True)


@pytest.mark.parametrize("value", [None, {}, [[], [], []]])
def test_source_result_rejects_malformed_envelope(monkeypatch, value):
    from analyzers.isolated_analysis import source_reply
    monkeypatch.setattr(sandbox, "call", lambda *_args, **_kwargs: value)
    with pytest.raises(sandbox.SandboxFailure, match="HELPER_RESULT_SCHEMA"):
        source_reply("documentation", {"README.md": "Owned"})


def test_manifest_parent_validation_preserves_legacy_json_license_metadata():
    from analyzers.isolated_analysis import validate_source_rows
    row = {"path": "package-lock.json", "manifest": "package-lock.json", "name": "owned", "version": "1.0.0",
           "ecosystem": "npm", "direct": True, "dependency_kind": "DIRECT", "version_kind": "EXACT",
           "license": {"type": "MIT", "url": "https://example.invalid/license"}}
    validate_source_rows([row], [], {"package-lock.json": "{}"})
    assert row["license"]["type"] == "MIT"


@pytest.mark.parametrize("operation", ["documentation", "sections", "storage"])
def test_large_reply_line_validation_scans_each_source_once(monkeypatch, operation):
    import hashlib

    from analyzers.isolated_analysis import validate_source_rows
    from analyzers.lexical import section_map, storage_claims
    class Counted(str):
        scans = 0
        def splitlines(self, *args, **kwargs):
            self.scans += 1
            return super().splitlines(*args, **kwargs)
    source = Counted("# Owned\n" * 60000)  # 480 KB; many valid-looking helper observations.
    files = {"README.md": source}
    digest_value = hashlib.sha256(source.encode()).hexdigest()
    if operation == "documentation":
        rows = [{"path": "README.md", "line": n, "text": "Owned", "category": "TECHNOLOGY",
                 "expected": "fastapi", "assertion_family": "declaration"} for n in range(1, 1001)]
        validate_source_rows(rows, [], files, documentation=True)
    elif operation == "sections":
        rows = [{"title": "Owned", "line": n} for n in range(1, 1001)]
        monkeypatch.setattr(sandbox, "call", lambda *_a, **_kw: {
            "README.md": {"hash": digest_value, "sections": rows}})
        assert len(section_map(files)["README.md"]) == 1000
    else:
        rows = [{"path": "README.md", "line": n, "category": "CLOUD_SECURITY", "expected": "private_storage",
                 "status": "UNVERIFIED"} for n in range(1, 1001)]
        monkeypatch.setattr(sandbox, "call", lambda *_a, **_kw: {"hashes": {"README.md": digest_value}, "claims": rows})
        assert len(storage_claims(files, [])) == 1000
    assert source.scans == 1, "Reply cardinality must not multiply source scanning in the trusted coordinator"


from tests.test_repository_store import storage  # noqa: E402,F401 -- shared owned SQLite fixture
