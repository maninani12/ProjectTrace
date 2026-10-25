"""Mandatory SEC-002B: real Linux workers and coordinator-only privacy checks."""

import copy
import fnmatch
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import select

from analyzers import sandbox
from analyzers.code_quality.classification import classify, ownership, ownership_rules
from analyzers.lexical import describe_one
from analyzers.source_input import SourceFiles
from backend.db import Record
from backend.generation_models import AnalysisGeneration
from backend.jobs import execute_analysis
from integration_tests.test_parser_isolation import required_boundary  # noqa: F401 -- mandatory actual enforcement
from tests.test_repository_store import captured, storage  # noqa: F401

FILES = SourceFiles({
    "scripts/start": "#!/usr/bin/env python3\nprint('owned')\n", "λ.py": "# @generated do not edit\npass\n",
    "src/main.py": "VALUE=1\n", "src/tests/a.ts": "export const a=1;\n", "vendor/lib.py": "pass\n",
    "workload.yaml": "#" * 3000 + "\napiVersion: v1\nkind: Pod\nmetadata: {name: owned}\n",
    "compose.yaml": "services:\n app: {image: owned:v1}\n", "README.md": "# Owned\n",
}, intake=[{"path": "bad.py", "bytes": 1, "physical_lines": None},
           {"path": "blob.bin", "bytes": 2, "physical_lines": None, "state": "BINARY"}])


def test_real_classification_equals_baseline_without_host_regex_or_glob_interpretation(monkeypatch):
    scope = {"vendor_patterns": ["vendor/**"], "test_paths": ["**/tests/**"]}
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    baseline = classify(FILES, scope)
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "required")
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Repository grammar executed in coordinator")
    monkeypatch.setattr(re, "search", forbidden)
    monkeypatch.setattr(fnmatch, "translate", forbidden)
    assert classify(FILES, scope) == baseline
    assert describe_one("workload.yaml", FILES["workload.yaml"])["infrastructure_format"] == "Kubernetes"


@pytest.mark.parametrize("source,path", [
    ("* @all\n/src/ @source\nsrc/a.py @first\nsrc/a.py @last", "src/a.py"),
    ("**/tests/** @tests\n*.py @python", "repo/tests/test_λ.py"),
    ("λ/*.py @unicode\n*.ts @ts", "λ/space name.py"),
    ("src/[ab].py @range\nsrc/* @fallback", "src/a.py"),
    ("*.py @one @two\n*.py @three", "a.py"),
    ("*.py @python", "README.md"),
])
def test_real_supported_codeowners_matching_and_precedence_remain_compatible(monkeypatch, source, path):
    files = {"CODEOWNERS": source}
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    baseline = ownership(path, files, "Assigned team")
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "required")
    def forbidden(*_args, **_kwargs):
        raise AssertionError("CODEOWNERS compiled in coordinator")
    monkeypatch.setattr(fnmatch, "translate", forbidden)
    result = ownership(path, files, "Assigned team")
    assert {key: result[key] for key in baseline} == baseline
    assert result["ownership_state"] == "SUPPORTED_RULES"


@pytest.mark.parametrize("bad", ["!src/** @unsupported", "../escape.py @outside", "src\\a.py @escape", "pattern-without-owner"])
def test_unsupported_rules_never_infer_an_owner_and_expose_uncertainty(bad):
    result = ownership("src/a.py", {"CODEOWNERS": bad}, "Assigned team")
    assert result["owner"] == "Assigned team"
    assert result["owner_source"] == "ProjectTrace repository assignment"
    assert result["ownership_state"] == "PARTIAL_UNSUPPORTED_RULES"
    assert "UNSUPPORTED_CODEOWNERS_SYNTAX" in result["ownership_diagnostics"]


def test_excessive_codeowners_pattern_is_rejected_inside_actual_worker():
    with pytest.raises(sandbox.SandboxFailure, match="CODEOWNERS_PATTERN_BUDGET"):
        ownership("a.py", {"CODEOWNERS": "*" * 4097 + " @owned"}, "Assigned team")


def test_pathological_wildcard_work_is_bounded_and_does_not_execute_source():
    source = ("*a" * 1000) + "b @unmatched\n*.py @supported"
    started = time.monotonic()
    result = ownership("a" * 230 + ".py", {"CODEOWNERS": source}, "Assigned team")
    assert result["owner"] == "@supported" and time.monotonic() - started < 10


@pytest.mark.parametrize("fault,code", [("probe_crash", "HELPER_PROCESS_LIMIT"), ("probe_timeout", "HELPER_TIMEOUT")])
def test_actual_ownership_crash_and_timeout_never_produce_negative_ownership(monkeypatch, fault, code):
    invoke = sandbox.invoke
    def routed(operation, value, **limits):
        if operation == "lexical_ownership":
            return invoke(fault, value, seconds=5)
        return invoke(operation, value, **limits)
    monkeypatch.setattr(sandbox, "invoke", routed)
    with pytest.raises(sandbox.SandboxFailure, match=code):
        ownership("a.py", {"CODEOWNERS": "* @owned"}, "Assigned team")


def test_actual_worker_scope_substitution_is_rejected(monkeypatch):
    invoke = sandbox.invoke
    def routed(operation, value, **limits):
        return invoke("lexical_probe_wrong_description" if operation == "lexical_describe" else operation, value, **limits)
    monkeypatch.setattr(sandbox, "invoke", routed)
    with pytest.raises(sandbox.SandboxFailure, match="LEXICAL_OUTPUT_SCOPE"):
        describe_one("owned.py", "pass\n")


def test_coordinator_redacts_real_helper_output_without_trusting_worker_sanitization():
    value = sandbox.call("lexical_probe_metadata", {})
    encoded = json.dumps(value)
    assert "abcdefghijklmnopqrstuvwxyz" not in encoded and "owned-private" not in encoded
    assert value["credentials"] == "[REDACTED]"


def test_concurrent_ownership_contexts_and_mutation_do_not_reuse_another_input():
    def resolve(team):
        return ownership("a.py", {"CODEOWNERS": "* @" + team}, "Assigned")
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(resolve, "tenantA"), pool.submit(resolve, "tenantB")
        assert a.result()["owner"] == "@tenantA" and b.result()["owner"] == "@tenantB"
    files = SourceFiles({"CODEOWNERS": "* @before"})
    first = ownership_rules(files)
    assert ownership_rules(files) is first
    files["CODEOWNERS"] = "* @after"
    assert ownership_rules(files) is not first
    assert ownership("a.py", files, "Assigned")["owner"] == "@after"


def test_real_ownership_failure_cannot_publish_and_recovery_preserves_baseline(storage, monkeypatch):  # noqa: F811
    db, actor, repo = storage
    baseline, _ = execute_analysis(db, actor, repo, captured(storage, {"app.py": "VALUE=1\n", "CODEOWNERS": "* @one"}))
    baseline_id, original = baseline.id, copy.deepcopy(baseline.data)
    files = captured(storage, {"app.py": "VALUE=2\n", "CODEOWNERS": "* @two"})
    invoke = sandbox.invoke
    def crash(operation, value, **limits):
        return invoke("probe_crash" if operation == "lexical_ownership" else operation, value, **limits)
    monkeypatch.setattr(sandbox, "invoke", crash)
    with pytest.raises(sandbox.SandboxFailure):
        execute_analysis(db, actor, repo, files, base_id=baseline_id)
    assert db.get(Record, baseline_id).data == original
    private = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.state == "STAGING"))
    assert private is not None
    job = db.get(Record, private.job_id)
    assert job.data["state"] == "FAILED" and job.data["error_code"].startswith("PARSER_ISOLATION_")
    monkeypatch.setattr(sandbox, "invoke", invoke)
    files._contained_ownership = None
    snapshot, recovered = execute_analysis(db, actor, repo, files, job=job, base_id=baseline_id)
    assert recovered.data["state"] in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"}
    assert snapshot.id != baseline_id and db.get(Record, baseline_id).data == original


def test_lexical_overhead_is_recorded_on_identical_owned_inputs(monkeypatch):
    elapsed = {}
    for mode in ("development", "required"):
        monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", mode)
        start = time.perf_counter()
        rows = classify(FILES, {})
        selected = ownership("a.py", {"CODEOWNERS": "* @owned"}, "Assigned")
        elapsed[mode] = time.perf_counter() - start
        assert rows and selected["owner"] == "@owned"
    target = Path(os.environ["PROJECTTRACE_SANDBOX_EVIDENCE"])
    target.mkdir(parents=True, exist_ok=True)
    (target / "lexical-overhead.json").write_text(json.dumps(elapsed))
