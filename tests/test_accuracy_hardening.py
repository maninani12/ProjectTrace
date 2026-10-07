import pytest

from analyzers.engine import analyze
from scripts.evaluate_accuracy import wilson


@pytest.mark.parametrize(
    "path,positive,negative",
    [
        ("app.py", "eval(request_value)", "def eval(value):\n    return value\neval(request_value)"),
        ("app.py", "def work(value):\n    return eval(value)", "def work(eval, value):\n    return eval(value)"),
        ("app.js", "function work(value) { eval(value); }", "function eval(value) {return value;} eval('safe');"),
        (
            "app.ts",
            "function work(value:string) { eval(value); }",
            "function work(eval:Function, value:string) { eval(value); }",
        ),
    ],
)
def test_builtin_evaluation_models_respect_explicit_local_bindings(path, positive, negative):
    assert any(f["rule"] == "PT-SAST-005" for f in analyze({path: positive})["findings"])
    assert not any(f["rule"] == "PT-SAST-005" for f in analyze({path: negative})["findings"])


def test_plain_environment_file_is_scanned_and_placeholder_is_not_credential():
    material = "ghp_synthetic_benchmark_token_123456789"
    result = analyze({".env": "API_KEY=" + material})
    assert any(f["rule"] == "PT-SECRET-001" for f in result["findings"])
    assert material not in str(result["findings"])
    assert not any(
        f["rule"] == "PT-SECRET-001" for f in analyze({".env": "API_KEY=${FROM_SECRET_MANAGER}"})["findings"]
    )


def test_import_only_claim_is_inferred_and_instantiation_is_static_verification():
    for source, expected in (
        ("import fastapi", "INFERRED"),
        ("from fastapi import FastAPI\napp=FastAPI()", "VERIFIED"),
    ):
        result = analyze({"README.md": "Backend uses FastAPI.", "app.py": source})
        assert next(c for c in result["claims"] if c.get("origin") == "DOCUMENTATION")["status"] == expected


def test_accuracy_api_distinguishes_population_limits_and_auth(signed):
    report = signed.get("/api/trust/accuracy").json()
    assert report["production_precision"] == "UNMEASURED" and report["default_blocking_qualification"] == "NONE"
    assert all(not row["blocking_eligible"] for row in report["groups"])
    assert "source" not in report["observations"][0]
    assert wilson(1, 1)[0] < 0.3 and wilson(0, 0) is None
    signed.post("/api/auth/logout", json={})
    assert signed.get("/api/trust/accuracy").status_code == 401
