"""Safe synthetic fixtures: no uploaded repository, dependency or application runs."""

import json

import pytest

from analyzers import engine
from analyzers.engine import analyze, redact, sbom
from analyzers.verifiers import claim_key


def documentation(result):
    return [claim for claim in result["claims"] if claim["origin"] == "DOCUMENTATION"]


def test_normalizes_equivalent_wording_and_decomposes_atomic_claims():
    first = documentation(analyze({"README.md": "Our backend is built with FastAPI, Postgres and JSON Web Tokens."}))
    second = documentation(analyze({"README.md": "Backend uses FastAPI, PostgreSQL and JWT."}))
    assert {claim["expected"] for claim in first} == {"fastapi", "postgresql", "jwt"}
    assert {claim_key(claim) for claim in first} == {claim_key(claim) for claim in second}
    assert all(claim["status"] == "UNVERIFIED" for claim in first)


def test_future_negative_and_code_block_examples_do_not_become_affirmative_claims():
    result = analyze(
        {
            "README.md": "Backend will use FastAPI.\nBackend does not use JWT.\nBackend uses Redis, not PostgreSQL.\n```python\nBackend uses Django.\n```"
        }
    )
    assert {claim["expected"] for claim in documentation(result)} == {"redis"}


def test_specialized_verifiers_keep_imports_and_dependencies_inferred():
    result = analyze(
        {
            "README.md": "The application uses Flask.\nDatabase uses MySQL.\nTesting uses pytest.\nCI uses GitHub Actions.\nInfrastructure uses Docker.",
            "app.py": "import flask\nDATABASE_URL='mysql://localhost/application'",
            "requirements.txt": "pytest>=8",
            ".github/workflows/test.yaml": "jobs:\n  unit:\n    runs-on: ubuntu-latest",
            "Dockerfile": "FROM python:3.11-slim",
        }
    )
    claims = {claim["expected"]: claim for claim in documentation(result)}
    assert claims["flask"]["status"] == "INFERRED"
    assert claims["mysql"]["status"] == "VERIFIED" and claims["mysql"]["verifier"] == "DatabaseVerifier"
    assert claims["pytest"]["status"] == "INFERRED" and claims["pytest"]["verifier"] == "TestingVerifier"
    assert claims["github actions"]["status"] == "VERIFIED"
    assert claims["docker"]["status"] == "VERIFIED"


def test_unrelated_string_literal_does_not_select_a_database():
    result = analyze(
        {"README.md": "Database uses PostgreSQL.", "app.py": "message='postgresql://example/documentation'"}
    )
    assert documentation(result)[0]["status"] == "UNVERIFIED"


def test_verifier_cache_invalidation_handles_added_deleted_and_unrelated_evidence():
    files = {
        "README.md": "Authentication uses JWT. Backend uses FastAPI.",
        "app.py": "from fastapi import FastAPI\napp=FastAPI()",
    }
    first = analyze(files)
    second = analyze(
        {**files, "notes.txt": "an unrelated file"},
        first["analysis_cache"],
        verification_context=first["verification_cache"],
    )
    assert second["reused_verifications"] == 2 and second["reverified_claims"] == 0
    third = analyze(
        {**files, "auth.py": "import jwt\njwt.decode(token, key)"},
        second["analysis_cache"],
        verification_context=second["verification_cache"],
    )
    assert third["reused_verifications"] == 1 and third["reverified_claims"] == 1
    assert next(claim for claim in documentation(third) if claim["expected"] == "jwt")["status"] == "VERIFIED"
    deleted = analyze(files, third["analysis_cache"], verification_context=third["verification_cache"])
    assert deleted["reused_verifications"] == 1 and deleted["reverified_claims"] == 1
    assert next(claim for claim in documentation(deleted) if claim["expected"] == "jwt")["status"] == "UNVERIFIED"
    stale = analyze(files, verification_context={**first["verification_cache"], "version": "old"})
    assert stale["reused_verifications"] == 0


def test_changed_dependency_invalidates_only_its_technology_claim():
    files = {
        "README.md": "Backend uses React. Database uses Redis.",
        "package.json": '{"dependencies":{"react":"19.0.0"}}',
    }
    first = analyze(files)
    second = analyze(
        {**files, "package.json": '{"dependencies":{"react":"19.1.0"}}'},
        first["analysis_cache"],
        verification_context=first["verification_cache"],
    )
    assert second["reverified_claims"] == 1 and second["reused_verifications"] == 1


@pytest.mark.parametrize(
    "source,rule",
    [
        ("import requests\nurl=request.args.get('url')\nrequests.get(url)", "PT-SAST-008"),
        ("import tempfile\ntempfile.mktemp()", "PT-SAST-009"),
        ("import jwt\njwt.decode(token, key, options={'verify_signature': False})", "PT-SAST-010"),
        ("from os import system as run\nrun(command)", "PT-SAST-002"),
        ("from hashlib import md5 as digest\ndigest(data)", "PT-SAST-004"),
        ("sql=f'SELECT * FROM users WHERE id={value}'\ndb.execute(sql)", "PT-SAST-001"),
    ],
)
def test_ast_security_expansion_reports_precise_metadata(source, rule):
    finding = next(item for item in analyze({"app.py": source})["findings"] if item["rule"] == rule)
    assert finding["rule_id"] == rule and finding["language"] == "Python"
    assert finding["line"] >= 1 and finding["end_line"] >= finding["line"]
    assert finding["rule_version"] and finding["explanation"] and finding["remediation"]


@pytest.mark.parametrize(
    "source",
    [
        "import requests\nrequests.get('https://fixed.example/path')",
        "import requests\nurl=request.args.get('url')\nurl='https://fixed.example'\nrequests.get(url)",
        "import requests\nrequests.get(url)\nurl=request.args.get('url')",
        "import tempfile\ntempfile.NamedTemporaryFile()",
        "import jwt\njwt.decode(token, key, algorithms=['HS256'])",
        "def outer():\n    value=request.args.get('url')\ndef other(value):\n    requests.get(value)",
    ],
)
def test_ast_security_false_positive_traps(source):
    assert not {finding["rule"] for finding in analyze({"app.py": source})["findings"]} & {
        "PT-SAST-008",
        "PT-SAST-009",
        "PT-SAST-010",
    }


def test_python_quality_depth_class_size_and_bare_exceptions():
    nested = (
        "def deeply_nested(value):\n"
        + "".join("    " * level + "if value:\n" for level in range(1, 6))
        + "    " * 6
        + "return value\n"
    )
    source = (
        nested
        + "class Oversized:\n"
        + "".join(f"    field_{index} = {index}\n" for index in range(202))
        + "try:\n    task()\nexcept:\n    pass\n"
    )
    rules = {finding["rule"] for finding in analyze({"app.py": source})["findings"]}
    assert {"PT-QUALITY-003", "PT-QUALITY-004", "PT-QUALITY-005"} <= rules
    assert "PT-QUALITY-005" not in {
        finding["rule"] for finding in analyze({"app.py": "try:\n    task()\nexcept:\n    raise"})["findings"]
    }


def test_nested_definition_does_not_inflate_parent_complexity():
    source = (
        "def outer():\n    def inner(value):\n"
        + "".join(f"        if value == {index}: value += 1\n" for index in range(12))
        + "    return inner\n"
    )
    findings = [item for item in analyze({"app.py": source})["findings"] if item["rule"] == "PT-QUALITY-001"]
    assert len(findings) == 1 and findings[0]["line"] == 2


def test_js_patterns_ignore_comments_and_string_bodies():
    source = "/*\neval(user_input)\n*/\nconst example = 'eval(user_input)';\nelement.innerHTML = 'fixed';\n// element.innerHTML = request;"
    assert not analyze({"app.js": source})["findings"]
    found = analyze({"app.ts": "eval(user_input);\nelement.innerHTML = input;"})["findings"]
    assert {item["rule"] for item in found} == {"PT-SAST-005", "PT-SAST-006"}


@pytest.mark.parametrize(
    "path,source,context",
    [
        ("tests/test_auth.py", "token='fictional_credential_12345678'", "TEST_FIXTURE"),
        ("config/example.env", "webhook_secret=fictional_credential_12345678", "EXAMPLE_CREDENTIAL"),
        ("config.env", "oauth_token=fictional_credential_12345678", "UNKNOWN"),
        ("production/settings.env", "token='ghp_abcdefghijklmnopqrstuvwxyz1234'", "LIKELY_PRODUCTION"),
    ],
)
def test_secrets_remain_detected_redacted_and_contextualized(path, source, context):
    result = analyze({path: source})
    found = next(item for item in result["findings"] if item["category"] == "SECRET")
    assert found["secret_context"] == context
    assert "fictional_credential" not in redact(source)
    assert "fictional_credential" not in json.dumps(result["findings"])


def test_incomplete_private_key_and_lowercase_unquoted_yaml_are_masked():
    for source in ["-----BEGIN RSA PRIVATE KEY-----\nfictional_key_material", "token: fictional_credential_12345678"]:
        assert "fictional" not in redact(source)
        assert analyze({"config.yaml": source})["findings"]
    assert not analyze({"config.env": 'secret="${PROJECTTRACE_SECRET}"'})["findings"]


def test_inventory_pnpm_yarn_uv_and_optional_groups():
    result = analyze(
        {
            "pnpm-lock.yaml": "lockfileVersion: '9.0'\npackages:\n  react@19.0.0: {}\n  '@scope/tool@1.2.3': {}\n",
            "yarn.lock": '"left-pad@^1.3.0":\n  version "1.3.0"\n',
            "uv.lock": 'version = 1\n[[package]]\nname="fastapi"\nversion="0.115.0"\n',
            "pyproject.toml": '[project.optional-dependencies]\nsecurity=["argon2-cffi>=23"]\n[dependency-groups]\ntest=["pytest==8.0.0"]',
        }
    )
    dependencies = result["dependencies"]
    assert {"react", "@scope/tool", "left-pad", "fastapi", "argon2-cffi", "pytest"} <= {
        item["name"] for item in dependencies
    }
    assert next(item for item in dependencies if item["name"] == "react")["dependency_kind"] == "UNKNOWN"
    assert next(item for item in dependencies if item["name"] == "argon2-cffi")["version_kind"] == "CONSTRAINT"
    assert result["engines"]["DEPENDENCIES"]["state"] == "COMPLETED"
    assert all(item["manifest"] == item["path"] for item in dependencies)


def test_sbom_deduplicates_declarations_and_uses_maven_purl():
    dependencies = analyze(
        {
            "package.json": '{"dependencies":{"react":"19.0.0"}}',
            "package-lock.json": '{"packages":{"":{"dependencies":{"react":"19.0.0"}},"node_modules/react":{"version":"19.0.0","license":"MIT"}}}',
            "pom.xml": "<project><dependency><groupId>org.example</groupId><artifactId>demo</artifactId><version>1.2.3</version></dependency></project>",
        }
    )["dependencies"]
    bom = sbom(dependencies)
    assert len(bom["components"]) == 2
    assert len({item["bom-ref"] for item in bom["components"]}) == 2
    assert (
        next(item for item in bom["components"] if item["name"] == "org.example:demo")["purl"]
        == "pkg:maven/org.example/demo@1.2.3"
    )
    assert next(item for item in bom["components"] if item["name"] == "react")["licenses"] == [
        {"license": {"name": "MIT"}}
    ]


def test_openapi_supported_route_and_unknown_router_stay_distinct():
    result = analyze(
        {
            "app.py": "from flask import Flask\napp=Flask(__name__)\n@app.route('/health', methods=['GET'])\ndef health(): return True",
            "openapi.json": json.dumps(
                {"openapi": "3.0.0", "paths": {"/health": {"get": {}}, "/unknown": {"post": {}}}}
            ),
        }
    )
    claims = {item["expected"]: item for item in documentation(result)}
    assert claims["GET /health"]["status"] == "VERIFIED"
    assert claims["POST /unknown"]["status"] == "UNVERIFIED"
    assert result["engines"]["API"]["state"] == "COMPLETED"


def test_independent_native_failure_is_safe_partial_and_not_cached_as_success(monkeypatch):
    def broken(*args):
        raise RuntimeError("sensitive source must never appear")

    monkeypatch.setattr(engine, "python_analysis", broken)
    first = analyze({"app.py": "import fastapi", "requirements.txt": "fastapi==0.115.0"})
    assert first["engines"]["SAST"]["state"] == "FAILED"
    assert first["engines"]["DEPENDENCIES"]["state"] == "COMPLETED"
    assert first["warnings"] and "sensitive source" not in json.dumps(first)
    second = analyze(first["files"], first["analysis_cache"])
    assert second["engines"]["SAST"]["state"] == "FAILED" and second["reused_files"] == 1


def test_parse_and_manifest_failures_have_truthful_independent_coverage():
    result = analyze({"app.py": "def broken(:", "package.json": "{bad json", "README.md": "Authentication uses JWT."})
    assert result["engines"]["PARSING"]["state"] == "PARTIAL"
    assert result["engines"]["QUALITY"]["state"] == "PARTIAL"
    assert result["engines"]["DEPENDENCIES"]["state"] == "PARTIAL"
    assert result["engines"]["CLAIMS"]["state"] == "COMPLETED"
    assert documentation(result)[0]["status"] == "UNVERIFIED"


def test_unsupported_language_quality_is_disclosed_not_reported_clean():
    result = analyze({"app.java": "class Demo {}"})
    assert result["engines"]["QUALITY"]["state"] == "SKIPPED_UNSUPPORTED"
    assert result["engines"]["SAST"]["limitations"]


def test_secret_patterns_cannot_escape_through_routes_imports_or_manifest_metadata():
    material = "ghp_synthetic_credential_shape_1234567890"
    result = analyze(
        {
            "README.md": f"The API exposes /{material}.",
            "app.py": f"import {material}\n@app.get('/{material}')\ndef endpoint(): return True",
            "package.json": json.dumps({"dependencies": {"react": material}}),
            "package-lock.json": json.dumps(
                {"packages": {"node_modules/react": {"version": "19.0.0", "license": material}}}
            ),
        }
    )
    for key in ["claims", "signals", "dependencies", "analysis_cache", "verification_cache"]:
        assert material not in json.dumps(result[key])
    assert material not in json.dumps(sbom(result["dependencies"]))


def test_cookie_hints_infer_sessions_without_proving_configuration():
    result = analyze({"README.md": "Authentication uses sessions.", "app.py": "session=request.cookies.get('session')"})
    assert documentation(result)[0]["status"] == "INFERRED"


def test_iac_patterns_do_not_scan_quoted_examples_as_configuration():
    result = analyze(
        {
            "notes.yaml": "example: 'privileged: true'\n# privileged: true",
            "example.tf": "description = \"acl = 'public-read'\"",
        }
    )
    assert not result["findings"]
