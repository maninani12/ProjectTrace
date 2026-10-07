import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft4Validator, FormatChecker

from analyzers.code_quality.core import gate
from analyzers.code_quality.coverage import absent, import_report
from analyzers.code_quality.duplication import detect
from analyzers.code_quality.rules import config, registry
from analyzers.engine import analyze, read_zip


def repeat_body(operator="+", prefix="value"):
    return "\n".join(f"    {prefix}{i} = x {operator} {i}" for i in range(12)) + f"\n    return {prefix}0"


RULE_CASES = [
    (
        "001",
        "app.py",
        "def work(x):\n" + "\n".join(f"    if x == {i}: return {i}" for i in range(11)),
        "def work(x):\n    return x\n",
    ),
    (
        "002",
        "app.py",
        "def work():\n" + "\n".join(f"    value{i} = {i}" for i in range(81)),
        "def work():\n    return 1\n",
    ),
    (
        "003",
        "app.py",
        "def work(x):\n" + "\n".join("    " * (i + 1) + "if x:" for i in range(5)) + "\n" + "    " * 6 + "return x",
        "def work(x):\n    if x: return x\n",
    ),
    (
        "004",
        "app.py",
        "class Large:\n" + "\n".join(f"    value{i} = {i}" for i in range(201)),
        "class Small:\n    value = 1\n",
    ),
    (
        "005",
        "app.py",
        "try:\n    work()\nexcept:\n    recover()",
        "try:\n    work()\nexcept ValueError:\n    recover()",
    ),
    (
        "006",
        "app.js",
        "function work(){ try { run(); } catch(error) {} }",
        "function work(){ try { run(); } catch(error) { throw error; } }",
    ),
    (
        "007",
        "app.py",
        "def first(x):\n" + repeat_body() + "\ndef second(x):\n" + repeat_body(prefix="local"),
        "def first(x):\n" + repeat_body() + "\ndef second(x):\n" + repeat_body("-"),
    ),
    (
        "008",
        "app.py",
        "def work(x):\n" + "\n".join("    " * (i + 1) + "if x:" for i in range(6)) + "\n" + "    " * 7 + "return x",
        "def work(x):\n    return x\n",
    ),
    ("009", "app.py", "def work(a,b,c,d,e,f,g,h):\n    return a\n", "def work(a,b):\n    return a\n"),
    ("010", "app.py", "def work():\n    return 1\n    run()\n", "def work(x):\n    if x: return 1\n    run()\n"),
    (
        "011",
        "app.py",
        "def work(items=[]):\n    return items\n",
        "def work(items=None):\n    return [] if items is None else items\n",
    ),
    ("012", "app.py", "def work(x):\n    return x is 1000\n", "def work(x):\n    return x == 1000\n"),
]


@pytest.mark.parametrize("rule,path,positive,negative", RULE_CASES)
def test_labeled_rule_positive_and_negative(rule, path, positive, negative):
    key = "PT-QUALITY-" + rule
    hit = analyze({path: positive})
    clear = analyze({path: negative})
    assert any(f["rule"] == key for f in hit["findings"]), (key, hit["warnings"])
    assert not any(f["rule"] == key for f in clear["findings"])
    # Same trigger is not promoted out of an explicitly generated scope.
    excluded = analyze(
        {path: "# @generated\n" + positive}
        if path.endswith(".py")
        else {"generated/" + path: positive, "README.md": "Generated fixture"}
    )
    assert not any(f["rule"] == key for f in excluded["findings"])


def test_quality_scope_cache_thresholds_and_parser_honesty():
    files = {
        "app.py": "def work(x):\n    if x: return x\n    return 0",
        "test_work.py": "def work(a,b,c,d,e,f,g,h):\n    return a",
        "vendor/helper.py": "def work(a,b,c,d,e,f,g,h):\n    return a",
        "backend.go": "package main",
        "broken.ts": "function bad( {",
    }
    first = analyze(files)
    assert first["code_quality"]["scope_counts"]["EXCLUDED_VENDOR"] == 1
    assert first["code_quality"]["scope_counts"]["UNSUPPORTED"] == 1
    assert first["code_quality"]["state"] == "PARTIAL"
    assert not any(f["rule"] == "PT-QUALITY-009" for f in first["findings"])
    second = analyze(
        files, first["analysis_cache"], profile={"quality": {"rules": {"PT-QUALITY-001": {"threshold": 1}}}}
    )
    assert second["reused_files"] >= 2
    assert any(f["rule"] == "PT-QUALITY-001" and f["threshold"] == 1 for f in second["findings"])
    override = analyze({"app.py": "x=1"}, profile={"quality": {"scope": {"language_overrides": {"app.py": "Java"}}}})
    assert override["code_quality"]["inventory"][0]["parser_state"] == "UNSUPPORTED_OVERRIDE"
    assert all(r["maturity"] in {"PARTIAL", "UNSUPPORTED"} for r in first["code_quality"]["languages"])


def test_duplicate_boundaries_and_explicit_work_budget():
    result = analyze(
        {"app.py": "def first(x):\n" + repeat_body() + "\ndef second(x):\n" + repeat_body(prefix="renamed")}
    )
    groups = result["code_quality"]["duplication"]["groups"]
    assert groups and all(o["end_line"] > o["line"] for g in groups for o in g["occurrences"])
    raw = [m for entry in result["analysis_cache"].values() for m in entry["quality_metrics"]]
    bounded = detect(raw, window_budget=1)
    assert bounded["state"] == "PARTIAL"
    assert bounded["windows_examined"] == 2


@pytest.mark.parametrize(
    "report,format,path,expected",
    [
        ("SF:app.py\nDA:1,1\nDA:2,0\nBRDA:1,0,0,1\nBRDA:1,0,1,0\nend_of_record\n", "lcov", "app.py", (50, 50)),
        (
            '<coverage><packages><package><classes><class filename="app.py"><lines><line number="1" hits="1" branch="true" condition-coverage="50% (1/2)"/><line number="2" hits="0"/></lines></class></classes></package></packages></coverage>',
            "coverage.py",
            "app.py",
            (50, 50),
        ),
        (
            '<?xml version="1.0"?><!DOCTYPE report PUBLIC "-//JACOCO//DTD_Report_1.1//EN" "report.dtd"><report name="x"><package name=""><sourcefile name="app.py"><line nr="1" ci="1" mb="1" cb="1"/><line nr="2" ci="0" mb="0" cb="0"/></sourcefile></package></report>',
            "jacoco",
            "app.py",
            (50, 50),
        ),
    ],
)
def test_real_report_counters_and_mapping(report, format, path, expected):
    result = import_report(
        report,
        {path: "first\nsecond"},
        format=format,
        declared_commit="abc",
        snapshot_commit="abc",
        changed_lines={path: [(2, 2)]},
    )
    assert result["state"] == "VALID", result
    assert (result["line_percent"], result["branch_percent"]) == expected
    assert result["changed_line_percent"] == 0
    assert result["producer_commit_matches_snapshot"] is True
    assert result["report_hash"]


@pytest.mark.parametrize(
    "report",
    [
        "SF:../app.py\nDA:1,1\nend_of_record",
        "SF:app.py\nDA:99,1\nend_of_record",
        "SF:app.py\nDA:1,1",
        '<!DOCTYPE coverage [<!ENTITY x SYSTEM "file:///secret">]><coverage>&x;</coverage>',
        '<coverage><class filename="app.py"><lines><line number="1" hits="-1"/></lines></class></coverage>',
        "SF:app.py\nDA:1,1\nBRDA:1,0,0,1\nBRDA:1,0,0,0\nend_of_record",
    ],
)
def test_hostile_invalid_report_never_returns_coverage(report):
    result = import_report(report, {"app.py": "x=1"})
    assert result["state"] == "REPORT_INVALID"
    assert result["line_percent"] is None


def test_report_absence_mismatch_ambiguous_and_partial():
    assert absent()["line_percent"] is None
    report = "SF:app.py\nDA:1,1\nend_of_record"
    assert (
        import_report(report, {"app.py": "x"}, declared_commit="old", snapshot_commit="head")["state"]
        == "REPORT_SNAPSHOT_MISMATCH"
    )
    assert import_report(report, {"app.py": "x", "src/app.py": "x"}, source_root="src")["state"] == "REPORT_INVALID"
    assert import_report(report, {"app.py": "x"})["state"] == "PARTIAL"


def test_quality_gate_beta_and_missing_evidence():
    result = analyze({"app.py": "def work(x):\n    return x"})
    quality = result["code_quality"]
    assert gate(quality, result["findings"])["status"] == "REVIEW_REQUIRED"
    quality["base_id"] = "chosen"
    assert gate(quality, result["findings"])["status"] == "PASS"
    quality["configuration"]["gate"]["min_changed_coverage"] = 80
    assert gate(quality, result["findings"])["status"] == "REVIEW_REQUIRED"
    assert all(r["status"] in {"STABLE", "BETA"} for r in registry())
    with pytest.raises(ValueError):
        config({"rules": {"PT-QUALITY-011": {"threshold": 3}}})


def import_repo(client, files):
    registration = client.post(
        "/api/auth/register",
        json={
            "email": "quality-fixture@example.com",
            "password": "Strong-test-password-123!",
            "organization": "Quality regression",
        },
    )
    assert registration.status_code == 200
    client.headers["x-csrf-token"] = registration.json()["csrf"]
    response = client.post("/api/import", json={"name": "Quality fixtures", "files": files})
    assert response.status_code == 200, response.text
    return response.json()["repository_id"], response.json()["snapshot_id"]


def test_history_movement_reviews_resolution_reopen_and_rename(signed):
    original = "def work(items=[]):\n    return items\n"
    repo, base = import_repo(signed, {"app.py": original})
    url = f"/api/code-quality/{repo}"
    first = signed.get(url + "/findings").json()["items"][0]
    reviewed = signed.post(
        f"/api/record/{first['id']}/review",
        json={
            "action": "FALSE_POSITIVE",
            "reason": "Explicit fixture behavior is documented.",
            "expected_version": first["version"],
        },
    )
    assert reviewed.status_code == 200
    moved = signed.post(
        f"/api/repositories/{repo}/analyze", json={"base_id": base, "files": {"app.py": "\n" * 20 + original}}
    ).json()
    existing = signed.get(url + f"/findings?snapshot_id={moved['id']}").json()["items"][0]
    assert existing["fingerprint"] == first["fingerprint"] and existing["delta"] == "EXISTING"
    assert existing["review_status"] == "FALSE_POSITIVE" and existing["line"] == first["line"] + 20
    clear = signed.post(
        f"/api/repositories/{repo}/analyze",
        json={"base_id": moved["id"], "files": {"app.py": "def work(items=None):\n    return items"}},
    ).json()
    assert signed.get(url + f"/overview?snapshot_id={clear['id']}").json()["summary"]["resolved"] == 1
    reopened = signed.post(
        f"/api/repositories/{repo}/analyze", json={"base_id": clear["id"], "files": {"app.py": original}}
    ).json()
    current = signed.get(url + f"/findings?snapshot_id={reopened['id']}").json()["items"][0]
    assert current["delta"] == "REOPENED" and current["machine_status"] == "REOPENED"
    renamed = signed.post(
        f"/api/repositories/{repo}/analyze", json={"base_id": reopened["id"], "files": {"new.py": original}}
    ).json()
    issue = signed.get(url + f"/findings?snapshot_id={renamed['id']}").json()["items"][0]
    assert issue["fingerprint"] != first["fingerprint"] and issue["delta"] == "EXISTING"
    assert issue["identity_id"] == first["identity_id"]


def test_authorized_profiles_pagination_reports_gate_and_sarif(signed):
    repo, snapshot = import_repo(signed, {"app.py": "def work(items=[]):\n    return items\n"})
    url = f"/api/code-quality/{repo}"
    assert signed.get("/api/code-quality/private/overview").status_code == 404
    assert signed.get("/api/code-quality/clean/overview?snapshot_id=" + snapshot).status_code == 404
    overview = signed.get(url + "/overview").json()
    profile = signed.get("/api/code-quality/profiles/current?repository_id=" + repo).json()
    settings = profile["configuration"]
    settings["baseline_id"] = snapshot
    settings["gate"]["min_changed_coverage"] = 90
    response = signed.post(
        "/api/code-quality/profiles/current",
        json={"repository_id": repo, "expected_version": profile["version"], "configuration": settings},
    )
    assert response.status_code == 200, response.text
    assert (
        signed.post(
            "/api/code-quality/profiles/current",
            json={"repository_id": repo, "expected_version": profile["version"], "configuration": settings},
        ).status_code
        == 409
    )
    assert signed.get(url + "/findings?limit=1").json()["total"] == 1
    assert signed.get(url + "/findings?severity=INFO").json()["total"] == 0
    assert signed.get(url + "/findings?limit=101").status_code == 422
    body = {
        "snapshot_id": snapshot,
        "report": "SF:app.py\nDA:1,1\nDA:2,0\nend_of_record",
        "declared_commit": overview["commit"],
    }
    assert signed.post(url + "/coverage", json={**body, "declared_commit": "different"}).status_code == 422
    report = signed.post(url + "/coverage", json=body)
    assert report.status_code == 200, report.text
    assert signed.get(url + "/coverage").json()["line_percent"] == 50
    sarif = signed.get(url + "/export").json()
    schema = json.loads((Path(__file__).parent / "schemas/sarif-2.1.0.json").read_text(encoding="utf-8"))
    Draft4Validator(schema, format_checker=FormatChecker()).validate(sarif)
    assert signed.get(url + "/exports/csv").headers["content-type"].startswith("text/csv")
    assert signed.get(url + "/exports/json").json()["snapshot_id"] == snapshot
    assert "quality_gate" in signed.get("/api/gate/" + snapshot).json()
    light = signed.get("/api/workspace?summary=1").json()
    assert not light["evidence"] and not light["finding"]
    assert all("analysis_cache" not in (r["snapshot"] or {}) for r in light["repositories"])


def test_native_parser_parameter_metrics_and_literal_safety():
    result = analyze(
        {
            "app.ts": "const work = (a:number,b:number) => { if(a) { return b; } return a; };",
            "App.java": "class App { App(int a) {} int work(int a,int b) { if(a>0) return b; return a; } }",
        }
    )
    metrics = result["quality_metrics"]
    assert any(
        m["language"] == "TypeScript" and m["parameters"] == 2 and m["qualified_name"] == "work" for m in metrics
    )
    assert any(m["language"] == "Java" and m["kind"] == "CONSTRUCTOR" for m in metrics)
    assert all(sum(c["cognitive"] for c in m["contributors"]) == m["cognitive_approximation"] for m in metrics)


def test_worsened_existing_complexity_is_new_code_and_model_upgrade_is_not_resolution(signed):
    base_source = "def work(x):\n" + "\n".join(f"    if x == {i}: return {i}" for i in range(11))
    repo, base = import_repo(signed, {"app.py": base_source})
    head_source = base_source + "\n" + "\n".join(f"    if x == {i}: return {i}" for i in range(11, 24))
    head = signed.post(
        f"/api/repositories/{repo}/analyze", json={"base_id": base, "files": {"app.py": head_source}}
    ).json()
    issues = signed.get(f"/api/code-quality/{repo}/findings").json()["items"]
    complexity = next(f for f in issues if f["rule"] == "PT-QUALITY-001")
    assert complexity["delta"] == "EXISTING" and complexity["new_code"] is True
    assert signed.get("/api/gate/" + head["id"]).json()["quality_gate"]["status"] == "REVIEW_REQUIRED"
    from analyzers.code_quality.core import compare

    result = analyze({"app.py": "def clean():\n    return 1"})
    quality = compare(result["code_quality"], [], issues, {}, base_id=base, model_changed=True)
    assert quality["resolved"] == []


def test_zip_encoding_diagnostics_prevent_false_complete_and_preserve_binary_inventory():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("app.py", "def work():\n    return 1".encode("utf-16"))
        archive.writestr("logo.png", b"\x89PNG\xff\x00")
        archive.writestr("vendor/legacy.py", b"\xff\x00")
    files = read_zip(stream.getvalue(), keep_excluded=True)
    assert not files and len(files.intake) == 3
    result = analyze(files)
    quality = result["code_quality"]
    assert quality["state"] == "PARTIAL"
    assert quality["scope_counts"] == {"UNSUPPORTED_ENCODING": 1, "EXCLUDED_BINARY": 1, "EXCLUDED_VENDOR": 1}
    assert quality["metrics"] == [] and gate(quality, result["findings"])["status"] == "REVIEW_REQUIRED"
    assert all(r["parser_state"] == "NOT_ANALYZED" for r in quality["inventory"])
    assert "def work" not in json.dumps(quality)


def test_quality_cli_exit_codes_and_reports_are_based_on_inert_zip_data(tmp_path):
    def archive(name, source):
        target = tmp_path / name
        with zipfile.ZipFile(target, "w") as bundle:
            bundle.writestr("app.py", source)
        return target

    clean = archive("clean.zip", "def work(values=None):\n    return values\n")
    bad = archive("bad.zip", "def work(values=[]):\n    return values\n")
    for head, base, expected in [(clean, clean, 0), (bad, clean, 3), (clean, None, 3)]:
        command = [sys.executable, "-m", "scripts.quality_gate", "--head", str(head)]
        if base:
            command.extend(["--base", str(base)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected, result.stdout + result.stderr
        assert json.loads(result.stdout)["gate"]["status"] == {0: "PASS", 2: "FAIL", 3: "REVIEW_REQUIRED"}[expected]
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"Not an archive")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.quality_gate", "--head", str(invalid)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 4 and json.loads(result.stdout)["state"] == "INVALID_INPUT"


def test_quality_profile_rejects_invalid_duplicate_threshold_and_override_paths():
    with pytest.raises(ValueError):
        config({"rules": {"PT-QUALITY-007": {"threshold": 1}}})
    with pytest.raises(ValueError):
        config({"scope": {"language_overrides": {"../app.py": "Python"}}})


def test_generated_parse_error_does_not_distort_quality_scope():
    result = analyze({"app.py": "def work(): return 1", "generated/bad.py": "not valid syntax {{"})
    assert result["code_quality"]["state"] == "COMPLETED"
    assert result["code_quality"]["scope_counts"]["EXCLUDED_GENERATED"] == 1


def test_duplicate_token_work_budget_returns_partial_instead_of_unbounded_extension():
    tokens = [{"value": str(i), "line": i // 5 + 1} for i in range(500)]
    metrics = [{"path": f"{i}.py", "name": "work", "language": "Python", "duplicate_tokens": tokens} for i in range(2)]
    result = detect(metrics, token_budget=100)
    assert result["state"] == "PARTIAL" and result["token_work"] <= 150


def test_quality_owner_graph_pr_impact_and_accepted_risk_expiry(signed):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from backend import main
    from backend.db import Record, Repository, User
    from backend.jobs import execute_analysis

    files = {"app.py": "def work(items=None):\n    return items\n", "CODEOWNERS": "/app.py @quality-team\n"}
    repo, base = import_repo(signed, files)
    with main.Session() as db:
        repository = db.get(Repository, repo)
        user = db.scalar(select(User).where(User.organization_id == repository.organization_id))
        snapshot, _ = execute_analysis(
            db,
            user,
            repository,
            {**files, "app.py": "def work(items=[]):\n    return items\n"},
            base_id=base,
            pr_number=17,
        )
        head = snapshot.id
    issue = signed.get(f"/api/code-quality/{repo}/findings").json()["items"][0]
    assert issue["owner"] == "@quality-team"
    workspace = signed.get(f"/api/workspace?repository_id={repo}").json()
    relations = {
        e["relationship"] for e in workspace["edge"] if e["source"] == issue["id"] or e["target"] == issue["id"]
    }
    assert {"DETECTED_IN", "AFFECTS_FUNCTION", "OWNED_BY", "DERIVED_FROM"} <= relations
    with main.Session() as db:
        pull_request = db.scalar(select(Record).where(Record.repository_id == repo, Record.kind == "pr"))
        assert pull_request.data["gate"]["quality_gate"]["status"] == "REVIEW_REQUIRED"
        assert issue["id"] in pull_request.data["impact"]["affected_findings"]
        assert pull_request.data["impact"]["affected_policies"]
    accepted = signed.post(
        f"/api/record/{issue['id']}/review",
        json={
            "action": "ACCEPT_RISK",
            "reason": "Time-limited fixture acceptance.",
            "expires_days": 1,
            "expected_version": issue["version"],
        },
    )
    assert accepted.status_code == 200
    assert signed.get("/api/gate/" + head).json()["quality_gate"]["status"] == "PASS"
    with main.Session() as db:
        exception = db.scalar(select(Record).where(Record.repository_id == repo, Record.kind == "exception"))
        exception.data = {**exception.data, "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
        db.commit()
    assert signed.get("/api/gate/" + head).json()["quality_gate"]["status"] == "REVIEW_REQUIRED"
    assert signed.get(f"/api/code-quality/{repo}/findings").json()["items"][0]["review_status"] == "ACCEPTED"


def test_quality_profile_write_requires_admin_and_report_write_requires_csrf(client):
    identity = client.post(
        "/api/auth/login", json={"email": "viewer@example.com", "password": "Strong-test-password-123!"}
    ).json()
    client.headers["x-csrf-token"] = identity["csrf"]
    profile = client.get("/api/code-quality/profiles/current?repository_id=clean").json()
    assert (
        client.post(
            "/api/code-quality/profiles/current",
            json={
                "repository_id": "clean",
                "expected_version": profile["version"],
                "configuration": profile["configuration"],
            },
        ).status_code
        == 403
    )

    del client.headers["x-csrf-token"]
    assert (
        client.post(
            "/api/code-quality/clean/coverage",
            json={"snapshot_id": "private", "report": "SF:app.py\nDA:1,1\nend_of_record"},
        ).status_code
        == 403
    )


def test_file_metrics_and_qualified_class_symbols_have_structural_provenance():
    result = analyze(
        {
            "app.py": "# file comment\nclass Outer:\n    class Inner:\n        value = 1\n",
            "app.js": "// comment\nclass App { work() { return 1; } }\n",
        }
    )
    inventory = {r["path"]: r for r in result["code_quality"]["inventory"]}
    assert inventory["app.py"]["classes"] == 2 and inventory["app.py"]["logical_statements"] == 3
    assert inventory["app.py"]["comment_lines"] == 1 and inventory["app.js"]["comment_lines"] == 1
    assert all(len(row["hash"]) == 64 for row in inventory.values())
    assert any(s["qualified_name"] == "Outer.Inner" and len(s["hash"]) == 64 for s in result["code_quality"]["symbols"])
