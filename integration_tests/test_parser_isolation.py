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
    assert all(result[key] is True for key in ("read", "write", "proc", "metadata", "opath", "exec", "fork")), result
    assert all(result["network"].values()), result
    assert result["nnp"] == 1 and result["seccomp"] == 2
    assert not {"DATABASE_URL", "ANALYSIS_INPUT_KEY", "HOME", "PATH", "PYTHONPATH"} & set(result["environment"])
    assert not (tmp_path / "escaped").exists()
    assert result["denial_errno"] and set(result["denial_errno"]) <= {1, 13}
    evidence = Path(os.environ["PROJECTTRACE_SANDBOX_EVIDENCE"])
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "host-denials.json").write_text(json.dumps(result))


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


def test_actual_openapi_batch_preserves_escaped_keys_syntax_states_and_source_identity():
    import hashlib

    files = {"contract.json": '{"open\\u0061pi":"3.0.0","paths":{"/owned":{"get":{}}}}',
             "unrelated.json": '{"private":"OWNED-NONCONTRACT-SENTINEL"}',
             "invalid.json": '{"openapi":'}
    result = sandbox.call("openapi_batch", {"files": files})
    assert set(result) == set(files)
    assert result["contract.json"]["contract"]["paths"] == {"/owned": {"get": {}}}
    assert result["contract.json"]["mentions_openapi"] is False
    assert result["invalid.json"]["invalid"] is True and result["invalid.json"]["mentions_openapi"] is True
    assert result["unrelated.json"]["contract"] is None
    assert "OWNED-NONCONTRACT-SENTINEL" not in json.dumps(result)
    assert all(row["source_hash"] == hashlib.sha256(files[path].encode()).hexdigest()
               for path, row in result.items())


def test_actual_openapi_reader_batches_without_per_file_helpers(monkeypatch):
    from analyzers.isolated_analysis import OpenAPIContracts

    files = {f"owned-{i}.json": '{"entity":"owned"}' for i in range(205)}
    invoke, calls = sandbox.invoke, []

    def counted(operation, value, **limits):
        calls.append((operation, len(value["files"]), sum(len(s.encode()) for s in value["files"].values())))
        return invoke(operation, value, **limits)

    monkeypatch.setattr(sandbox, "invoke", counted)
    reader = OpenAPIContracts(files)
    assert all(reader.read(path) == (None, False, False) for path in files)
    assert calls == [("openapi_batch", 100, 1800), ("openapi_batch", 100, 1800), ("openapi_batch", 5, 90)]


def test_actual_openapi_reader_retains_single_source_nesting_guard():
    from analyzers.isolated_analysis import OpenAPIContracts

    for depth in (97, 99):
        source = '{"openapi":"3","paths":{},"nested":' + '[' * depth + '0' + ']' * depth + '}'
        reader = OpenAPIContracts({"owned.json": source})
        try:
            if depth == 97:
                assert reader.read("owned.json") == (json.loads(source), True, False)
            else:
                with pytest.raises(sandbox.SandboxFailure, match="HELPER_PROTOCOL_DEPTH"):
                    reader.read("owned.json")
        finally:
            reader.close()


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
    output = Path(os.environ["PROJECTTRACE_SANDBOX_EVIDENCE"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "compatibility.json").write_text(json.dumps(captured))
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


def test_actual_kernel_api_unavailable_fails_closed_in_production():
    # An owned outer process installs a real inherited filter denying the
    # Landlock create syscall. No configuration mock simulates kernel absence.
    script = """
import ctypes,errno
from analyzers import sandbox
lib=ctypes.CDLL('libseccomp.so.2')
lib.seccomp_init.argtypes=[ctypes.c_uint32]
lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p]
libc=ctypes.CDLL(None)
assert libc.prctl(38,1,0,0,0)==0
context=lib.seccomp_init(0x7fff0000)
assert context
assert lib.seccomp_rule_add(context,0x00050000|errno.ENOSYS,444,0)==0
assert lib.seccomp_load(context)==0
try:
 sandbox.require_runtime()
except sandbox.SandboxFailure as error:
 print(error.code)
else:
 raise AssertionError('Unsafe production fallback')
"""
    completed = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True, timeout=30,
                               env={**os.environ, "APP_ENV": "production"})
    assert completed.returncode == 0, completed.stderr[-1000:]
    assert completed.stdout.strip() == "LANDLOCK_ABI_3_REQUIRED"


def test_real_parser_interruption_preserves_only_completed_file_prefix(monkeypatch):
    from analyzers.languages import analyze_languages
    invoke = sandbox.invoke
    def interrupted(operation, value, **limits):
        return invoke("probe_language_prefix_crash" if operation == "languages" else operation, value, **limits)
    monkeypatch.setattr(sandbox, "invoke", interrupted)
    result = analyze_languages({"completed.ts": "eval(input);", "interrupted.ts": "eval(input);"})
    assert isinstance(result["completed.ts"], list)
    assert any(row["rule"] == "PT-SAST-005" for row in result["completed.ts"][0])
    assert result["interrupted.ts"]["code"] == "HELPER_PROCESS_LIMIT"


def test_real_native_crash_publishes_no_successful_observation_cache(monkeypatch):
    from analyzers.engine import analyze, native_observations
    invoke = sandbox.invoke
    def crashed(operation, value, **limits):
        return invoke("probe_crash" if operation == "native" else operation, value, **limits)
    monkeypatch.setattr(sandbox, "invoke", crashed)
    files = {"app.py": "import subprocess\nsubprocess.run(command,shell=True)\n",
             "main.tf": 'resource "aws_s3_bucket" "owned" {\n acl="public-read"\n}\n',
             "README.md": "Authentication uses JWT.\n"}
    result = native_observations(files)
    assert not result[0] and not result[1] and not result[6]
    assert {"PARSING", "QUALITY", "SAST", "SECRETS", "IAC", "CLAIMS", "API"} <= result[5]
    assert result[2] and all(row["state"] == "PARTIAL" for row in result[2])
    assert result[2][0]["code"] == "HELPER_PROCESS_LIMIT"
    analysis = analyze(files, observations=result)
    assert all(analysis["engines"][name]["state"] == "FAILED" for name in result[5])
    assert not any(row["status"] == "VERIFIED" for row in analysis["claims"])


@pytest.mark.parametrize("format,text", [
    ("lcov", "SF:app.py\nDA:1,1\nDA:2,0\nend_of_record\n"),
    ("cobertura", '<coverage><packages><package><classes><class filename="app.py"><lines>'
     '<line number="1" hits="1"/><line number="2" hits="0"/>'
     '</lines></class></classes></package></packages></coverage>'),
])
def test_contained_coverage_reports_retain_meaningful_counts_and_safe_failure(format, text, monkeypatch):
    from analyzers.code_quality.coverage import import_report
    files = {"app.py": "first=1\nsecond=2\n"}
    options = {"format": format, "declared_commit": "a" * 40, "snapshot_commit": "a" * 40}
    result = import_report(text, files, **options)
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    baseline = import_report(text, files, **options)
    assert result == baseline
    assert result["state"] == "VALID" and result["line_total"] == 2 and result["line_covered"] == 1
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "required")
    invoke = sandbox.invoke
    def crashed(operation, value, **limits):
        return invoke("probe_crash" if operation == "coverage" else operation, value, **limits)
    monkeypatch.setattr(sandbox, "invoke", crashed)
    failed = import_report(text, files, **options)
    assert failed["state"] == "REPORT_INVALID" and failed["error_code"] == "HELPER_PROCESS_LIMIT"
