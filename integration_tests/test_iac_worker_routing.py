"""Real Linux routing, cache and failure contracts for owned IaC workers."""

import subprocess
import sys
from pathlib import Path

import pytest

from analyzers import sandbox
from analyzers.engine import finding, safe_path
from analyzers.infrastructure import structured_iac_batch
from analyzers.isolated_analysis import native

DOCKERFILE = "FROM alpine:latest\nUSER root\n"
COMPOSE = "services:\n  api:\n    image: nginx:latest\n"
JSON_CONFIG = '{"services":{"api":{"image":"nginx:latest"}}}'
TF = 'variable "owned" { default = 1 }\n'


@pytest.fixture(autouse=True)
def required_worker():
    assert sandbox.required()
    assert sandbox.require_runtime()["enforced"] is True


@pytest.fixture
def launches(monkeypatch):
    actual = sandbox.invoke
    operations = []

    def observe(operation, value, **limits):
        operations.append(operation)
        return actual(operation, value, **limits)

    monkeypatch.setattr(sandbox, "invoke", observe)
    return operations


@pytest.mark.parametrize(("files", "operation"), [
    ({"nested/Dockerfile.ci": DOCKERFILE}, "iac_without_hcl"),
    ({"nested/compose.yml": COMPOSE}, "iac_without_hcl"),
    ({"nested/compose.json": JSON_CONFIG}, "iac_without_hcl"),
    ({"nested/main.tf": TF}, "iac"),
    ({"nested/main.tf.json": '{"variable":{"owned":{"default":1}}}'}, "iac"),
    ({"nested/main.tf": TF, "nested/Dockerfile": DOCKERFILE, "nested/compose.yaml": COMPOSE}, "iac"),
])
def test_real_iac_routes_and_retains_file_order(launches, files, operation):
    result = structured_iac_batch(files, finding)
    assert launches == [operation]
    assert list(result) == list(files)
    assert not any(row[2] for row in result.values())


def test_native_lexical_exclusions_do_not_promote_content_to_terraform(launches):
    files = {"owned/template.tf.backup": TF, "owned/plain.json": '{"value":1}', "owned/main.TF": TF,
             "owned/plan.TF.JSON": '{"variable":{"owned":{"default":1}}}', "owned/compose.yml": COMPOSE}
    result = native(files, {}, None)
    assert launches.count("iac_without_hcl") == 1
    assert "iac" not in launches
    assert set(result[6]) == set(files)


def test_malformed_terraform_stays_on_hcl_route(launches):
    result = structured_iac_batch({"owned/main.tf": "variable {"}, finding)
    assert launches == ["iac"]
    assert result["owned/main.tf"][2][0]["state"] == "PARTIAL"


def test_canonical_nested_archive_path_preserves_terraform_selection(launches):
    canonical = str(safe_path("archive/./nested//main.tf"))
    assert canonical == "archive/nested/main.tf"
    with pytest.raises(ValueError, match="traversal"):
        safe_path("archive/../main.tf")
    assert list(structured_iac_batch({canonical: TF}, finding)) == [canonical]
    assert launches == ["iac"]


def test_empty_and_fully_cached_native_batches_skip_iac_workers(launches):
    files = {"nested/Dockerfile": DOCKERFILE, "nested/compose.yml": COMPOSE}
    assert structured_iac_batch({}, finding) == {}
    assert launches == []
    cold = native(files, {}, None)
    assert launches.count("iac_without_hcl") == 1
    assert not cold[2] and set(cold[6]) == set(files)
    launches.clear()
    warm = native(files, cold[6], None)
    assert not any(op.startswith("iac") or op == "native" for op in launches)
    assert warm[6] == cold[6]
    assert warm[7] == len(files)
    launches.clear()
    changed = {**files, "nested/Dockerfile": DOCKERFILE + "RUN true\n"}
    updated = native(changed, cold[6], None)
    assert launches.count("iac_without_hcl") == 1
    assert updated[7] == 1


def test_misroute_is_attested_and_rejects_the_whole_batch(monkeypatch):
    actual = sandbox.validate_proof
    attestations = []

    def observe(header):
        proof = actual(header)
        attestations.append(proof)
        return proof

    monkeypatch.setattr(sandbox, "validate_proof", observe)
    raw, failure = sandbox.invoke("iac_without_hcl", {"files": {"owned/Dockerfile": DOCKERFILE,
                                                                 "owned/main.tf.json": "{}"}, "settings": {}})
    assert failure is None
    assert len(attestations) == 1 and attestations[0]["enforced"] is True
    assert sandbox.decode_packet(raw) == {"ok": False, "code": "IAC_PARSER_NOT_PREPARED"}


def test_attested_worker_exit_yields_partial_iac_and_no_results(monkeypatch):
    script = """
import os,runpy,sys
sys.path.insert(0,sys.argv[1])
worker=runpy.run_path(sys.argv[1]+"/analyzers/isolated_worker.py",run_name="owned")
def fail(operation,value,engine,sandbox,**kwargs):
    assert sandbox.ACTIVE
    os._exit(73)
worker["main"].__globals__["dispatch"]=fail
sys.argv=[sys.argv[0],sys.argv[2]]
worker["main"]()
"""
    actual = subprocess.Popen
    root = str(Path(__file__).resolve().parents[1])

    def after_attestation(command, *args, **kwargs):
        return actual([sys.executable, "-I", "-B", "-c", script, root, command[-1]], *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", after_attestation)
    result = structured_iac_batch({"owned/Dockerfile": DOCKERFILE}, finding)
    findings, assets, warnings = result["owned/Dockerfile"]
    assert findings == assets == []
    assert [(row["state"], row["code"]) for row in warnings] == [("PARTIAL", "HELPER_PROCESS_LIMIT")]
