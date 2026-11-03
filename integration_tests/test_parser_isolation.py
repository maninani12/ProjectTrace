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
                with pytest.raises(sandbox.SandboxFailure, match="HELPER_PROTOCOL"):
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


HCL_FACTORY_SOURCES = {
    "empty": "",
    "resource": 'resource "aws_s3_bucket" "owned" {\n acl = "public-read"\n}\n',
    "nested": 'variable "owned" {\n default = { nested = [1, true, { label = "owned" }] }\n}\n',
    "expressions": 'locals {\n doubled = [for n in [1, 2, 3] : n * 2 if n > 1]\n label = "owned-${var.name}"\n}\n',
    "heredoc": 'locals {\n text = <<-OWNED\n  owned ${var.name}\n  second line\n OWNED\n}\n',
    "comments_unicode": '# owned comment\nlocals { label = "café" /* owned */ }\n',
    "policy": 'resource "aws_iam_policy" "owned" {\n policy = jsonencode({ Statement = [{ Effect = "Allow", Action = "*", Resource = "*" }] })\n}\n',
    "bounded_large": "".join(f'resource "aws_s3_bucket" "owned{i}" {{\n acl = "private"\n}}\n' for i in range(80)),
    "invalid": 'resource "aws_s3_bucket" "owned" {\n acl =\n',
}


def hcl_factory_probe():
    # A fresh interpreter owns each parser. Never populate the upstream parser
    # cache before measuring bootstrap, or the original defect is hidden.
    script = r'''
import hashlib,json,sys
sys.path.insert(0,sys.argv[1])
import hcl2,hcl2.api
from lark import Lark
from analyzers.isolated_worker import prepare
sources=json.load(sys.stdin)
original=Lark.open
upstream=hcl2.loads
factory=hcl2.api._get_parser
calls=[]
def opened(cls,filename,*args,**kwargs):
 if str(filename).endswith('hcl2.lark'):
  calls.append(kwargs.get('cache') is False)
 return original(filename,*args,**kwargs)
Lark.open=classmethod(opened)
prepared=prepare('iac')
loader=prepared[-1] if callable(prepared[-1]) else upstream
after_prepare=len(calls)
def captured(load,text,options):
 try:
  return {'value':load(text,serialization_options=options)}
 except Exception as error:
  return {'error':type(error).__module__+'.'+type(error).__name__}
options=[None,hcl2.SerializationOptions(strip_string_quotes=True,with_meta=True)]
actual={key:[captured(loader,text,option) for option in options] for key,text in sources.items()}
repeated=[captured(loader,sources['resource'],options[1]) for _ in range(3)]
after_parsing=len(calls)
Lark.open=original
expected={key:[captured(upstream,text,option) for option in options] for key,text in sources.items()}
assert hcl2.loads is upstream and hcl2.api._get_parser is factory
print(json.dumps({'after_prepare':after_prepare,'after_parsing':after_parsing,'cache_disabled':calls,
 'public_results_equal':{key:actual[key]==expected[key] for key in sources},
 'errors':{key:[row.get('error') for row in value] for key,value in actual.items()},
 'repeated_equal':all(row==actual['resource'][1] for row in repeated),
 'explicit_loader':loader is not upstream,'upstream_bindings_unchanged':True,
 'result_sha256':hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()}))
'''
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(Path(__file__).resolve().parents[1])],
        input=json.dumps(HCL_FACTORY_SOURCES), text=True, capture_output=True, timeout=30,
        env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PROJECTTRACE_PARSER_ISOLATION": "required"},
    )
    assert completed.returncode == 0, completed.stderr[-1000:]
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def hcl_factory_result():
    return hcl_factory_probe()


def test_hcl_cold_worker_prepares_exactly_one_grammar(hcl_factory_result):
    assert hcl_factory_result["after_prepare"] == 1
    assert hcl_factory_result["after_parsing"] == 1
    assert hcl_factory_result["cache_disabled"] == [True]
    assert hcl_factory_result["explicit_loader"] and hcl_factory_result["upstream_bindings_unchanged"]


@pytest.mark.parametrize("case", list(HCL_FACTORY_SOURCES))
def test_hcl_prepared_parser_preserves_public_outputs_and_errors(hcl_factory_result, case):
    assert hcl_factory_result["public_results_equal"][case]
    errors = hcl_factory_result["errors"][case]
    assert all(error is not None for error in errors) if case == "invalid" else errors == [None, None]


def test_hcl_repeated_parsing_and_independent_worker_ownership(hcl_factory_result):
    independent = hcl_factory_probe()
    assert independent == hcl_factory_result
    assert independent["repeated_equal"] and independent["after_parsing"] == 1


@pytest.mark.parametrize("failure", ["FileNotFoundError", "PermissionError"])
def test_hcl_missing_grammar_fails_before_attestation_and_next_worker_recovers(failure, monkeypatch):
    from analyzers.engine import finding
    from analyzers.infrastructure import structured_iac_batch

    # Fault only the just-created owned worker's installed grammar open. The
    # real parent transport/proof validator must fail closed; no package file changes.
    script = r'''
import runpy,sys
sys.path.insert(0,sys.argv[1])
from lark import Lark
error={'FileNotFoundError':FileNotFoundError,'PermissionError':PermissionError}[sys.argv[2]]
def unavailable(*args,**kwargs):
 raise error('Owned unavailable grammar fixture')
Lark.open=unavailable
sys.argv=[sys.argv[1]+'/analyzers/isolated_worker.py','iac']
runpy.run_path(sys.argv[0],run_name='__main__')
'''
    original = subprocess.Popen
    root = str(Path(__file__).resolve().parents[1])
    def failed_worker(command, *args, **kwargs):
        assert command[-1] == "iac" and command[-2].endswith("isolated_worker.py")
        return original([sys.executable, "-I", "-B", "-c", script, root, failure], *args, **kwargs)
    files = {"owned/main.tf": HCL_FACTORY_SOURCES["resource"]}
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", failed_worker)
        with pytest.raises(sandbox.SandboxFailure) as stopped:
            structured_iac_batch(files, finding)
        assert stopped.value.code == "ISOLATION_NOT_ATTESTED"
    recovered = structured_iac_batch(files, finding)
    assert recovered["owned/main.tf"][0] and not recovered["owned/main.tf"][2]


def test_hcl_required_batch_preserves_order_locations_privacy_and_json_variant(monkeypatch):
    from analyzers.engine import finding
    from analyzers.infrastructure import structured_iac_batch

    token = "ghp_" + "a" * 36
    files = {"owned/one.tf": HCL_FACTORY_SOURCES["resource"], "owned/empty.tf": "",
             "owned/invalid.tf": HCL_FACTORY_SOURCES["invalid"],
             "owned/policy.tf": HCL_FACTORY_SOURCES["policy"],
             "owned/two.tf.json": json.dumps({"resource": {"aws_s3_bucket": {"owned": {"acl": "public-read", "token": token}}}})}
    original, pids = subprocess.Popen, []
    def counted(*args, **kwargs):
        child = original(*args, **kwargs)
        pids.append(child.pid)
        return child
    monkeypatch.setattr(subprocess, "Popen", counted)
    first = structured_iac_batch(files, finding)
    second = structured_iac_batch(files, finding)
    assert first == second and list(first) == list(files)
    assert len(pids) == len(set(pids)) == 2
    assert first["owned/one.tf"][1][0]["line"] == 1
    assert {f["rule"] for f in first["owned/one.tf"][0]} == {"PT-IAC-003"}
    assert first["owned/empty.tf"] == ([], [], [])
    assert first["owned/invalid.tf"][2][0]["state"] == "PARTIAL"
    assert not first["owned/two.tf.json"][2]
    assert token not in json.dumps(first)
