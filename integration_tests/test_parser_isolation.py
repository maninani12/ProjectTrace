"""Required real Linux SEC-002 acceptance: no optional skips or flag-only assertions."""

import ast
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from analyzers import sandbox


@pytest.fixture(autouse=True)
def required_boundary():
    assert sys.platform == "linux"
    assert sandbox.mode() == "required"
    assert sandbox.require_runtime()["enforced"] is True


def test_actual_filesystem_network_exec_environment_and_process_denial(tmp_path, monkeypatch):
    sentinel = tmp_path / "host-secret"
    sentinel.write_text("OWNED-SENTINEL-CONTENT")
    monkeypatch.setenv("DATABASE_URL", "private-fixture-value-must-not-be-inherited")
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", "private-fixture-key-must-not-be-inherited")
    result = sandbox.call("probe_denials", {"sentinel": str(sentinel), "write_path": str(tmp_path / "escaped"), "nonce": "owned"})
    assert all(result[key] is True for key in ("read", "write", "proc", "metadata", "exec", "fork")), result
    assert all(result["network"].values()), result
    assert result["nnp"] == 1 and result["seccomp"] == 2
    assert not {"DATABASE_URL", "ANALYSIS_INPUT_KEY", "HOME", "PATH", "PYTHONPATH"} & set(result["environment"])
    assert not (tmp_path / "escaped").exists()


def test_concurrent_owned_tenants_cannot_read_each_others_host_files(tmp_path):
    first, second = tmp_path / "tenant-a", tmp_path / "tenant-b"
    first.write_text("OWNED-A")
    second.write_text("OWNED-B")
    def attempt(path, nonce):
        return sandbox.call("probe_denials", {"sentinel": str(path), "write_path": str(path), "nonce": nonce})
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(attempt, second, "A"), pool.submit(attempt, first, "B")
        a, b = a.result(), b.result()
    assert a["nonce"] == "A" and b["nonce"] == "B"
    assert a["read"] and a["write"] and b["read"] and b["write"]
    assert first.read_text() == "OWNED-A" and second.read_text() == "OWNED-B"


@pytest.mark.parametrize("operation,seconds,code", [
    ("probe_timeout", 8, "HELPER_TIMEOUT"), ("probe_cpu", 10, "HELPER_PROCESS_LIMIT"),
    ("probe_crash", 10, "HELPER_PROCESS_LIMIT"), ("probe_malformed", 10, "HELPER_PROTOCOL"),
])
def test_actual_timeout_cpu_crash_and_malformed_output_fail_safely(operation, seconds, code):
    with pytest.raises(sandbox.SandboxFailure) as result:
        sandbox.call(operation, {}, seconds=seconds)
    assert result.value.code == code


def test_memory_and_stdout_exhaustion_are_contained():
    assert sandbox.call("probe_memory", {}) == {"contained": True}
    with pytest.raises(sandbox.SandboxFailure, match="HELPER_OUTPUT_BUDGET"):
        sandbox.call("probe_output", {}, maximum=65536)


SOURCES = {
    "README.md": "Authentication uses JWT.\nBackend uses FastAPI.\n",
    "app.py": "from fastapi import FastAPI\nfrom starlette.middleware.sessions import SessionMiddleware\napp=FastAPI()\napp.add_middleware(SessionMiddleware, secret_key=settings.session_key)\n",
    "app.ts": "export function run(input: string) { return eval(input); }\n",
    "View.tsx": "export function View() { return <div>Owned</div>; }\n",
    "Service.java": "class Service { int run(int x) { if(x>0) return x; return 0; } }\n",
    "main.tf": 'resource "aws_s3_bucket" "owned" {\n acl="public-read"\n}\n',
    "workload.yaml": "apiVersion: v1\nkind: Pod\nmetadata: {name: owned}\nspec:\n containers:\n - name: app\n   image: nginx:latest\n   securityContext: {privileged: true}\n",
    "package.json": '{"name":"owned","dependencies":{"react":"19.0.0"}}',
    "pom.xml": "<project><dependencies><dependency><groupId>owned</groupId><artifactId>example</artifactId><version>1.0</version></dependency></dependencies></project>",
}


def test_meaningful_normal_results_match_development_baseline_and_measure_overhead(tmp_path):
    script = """
import json,sys,time
from analyzers.engine import analyze
files=json.load(sys.stdin)
start=time.perf_counter()
result=analyze(files)
print(json.dumps({'seconds':time.perf_counter()-start,'result':result}))
"""
    captured = {}
    for mode in ("development", "required"):
        completed = subprocess.run([sys.executable, "-c", script], input=json.dumps(SOURCES), text=True,
                                   capture_output=True, timeout=90,
                                   env={**os.environ, "PROJECTTRACE_PARSER_ISOLATION": mode})
        assert completed.returncode == 0, completed.stderr[-2000:]
        captured[mode] = json.loads(completed.stdout)
    # Parser policy/signature deliberately invalidates old observation caches.
    def meaningful(result):
        return {"claims": [(c["text"], c["status"], c.get("reason")) for c in result["claims"]],
                "findings": [(f["rule"], f["path"], f["line"], f.get("fingerprint")) for f in result["findings"]],
                "signals": result["signals"], "dependencies": result["dependencies"], "assets": result["cloud_assets"]}
    assert meaningful(captured["required"]["result"]) == meaningful(captured["development"]["result"])
    assert {k: v["state"] for k, v in captured["required"]["result"]["engines"].items()} == {
        k: v["state"] for k, v in captured["development"]["result"]["engines"].items()}
    assert any(c["status"] == "CONTRADICTED" for c in captured["required"]["result"]["claims"])
    assert captured["required"]["result"]["findings"]
    output = Path(os.environ["PROJECTTRACE_SANDBOX_EVIDENCE"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "overhead.json").write_text(json.dumps({mode: {"wall_seconds": row["seconds"]} for mode, row in captured.items()}))


def test_python_ast_never_runs_in_host_and_cache_is_deterministic(monkeypatch):
    from analyzers.engine import native_observations
    files = {"app.py": "import subprocess\nsubprocess.run(command, shell=True)\n"}
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Untrusted AST parsed in host")
    monkeypatch.setattr(ast, "parse", forbidden)
    cold = native_observations(files)
    warm = native_observations(files, cold[6])
    repeated = native_observations(files)
    assert cold[:6] == warm[:6] == repeated[:6]
    assert cold[7] == 0 and warm[7] == 1
    assert cold[0] and cold[1]


def test_production_refuses_explicit_development_downgrade(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    with pytest.raises(sandbox.SandboxFailure, match="ISOLATION_REQUIRED"):
        sandbox.required()
