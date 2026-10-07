import io
import zipfile

import pytest

from analyzers.code_quality.core import gate
from analyzers.engine import MAX_FILE_BYTES, analyze, read_zip
from analyzers.infrastructure_deep import config as infrastructure_config
from backend import main
from backend.db import Grant, ParserArtifact, Record, Repository, User
from backend.partitioned_analysis import analyze_inventory, artifact_key
from backend.repository_store import RepositoryFiles, archive_items, capture
from backend.security import passwords
from tests.test_code_quality import import_repo
from tests.test_repository_store import storage  # noqa: F401 - shared isolated storage fixture


def closure_sources():
    files = {
        "ok.py": "def work():\n    return 1\n",
        "ok.js": "function work() { return 1; }\n",
        "ok.ts": "function work(): number { return 1; }\n",
        "Ok.java": "class Ok { int work() { return 1; } }\n",
        "app.go": "package main\n",
        "app.rs": "fn main() {}\n",
        "app.c": "int main() { return 0; }\n",
        "app.cpp": "int main() {}\n",
        "app.cs": "class App {}\n",
        "app.kt": "fun main() {}\n",
        "app.rb": "puts 'fixture'\n",
        "app.php": "<?php echo 'fixture';\n",
        "app.sh": "#!/bin/sh\necho fixture\n",
        "app.vue": "<template>fixture</template>\n",
        "app.svelte": "<p>fixture</p>\n",
        "app.sql": "SELECT 1;\n",
        "main.tf": 'resource "aws_s3_bucket" "fixture" {}\n',
        "cfn.yaml": "Resources:\n  Bucket:\n    Type: AWS::S3::Bucket\n",
        "k8.yaml": "apiVersion: v1\nkind: ConfigMap\nmetadata: {name: fixture}\n",
        "compose.yaml": "services:\n  app: {image: fixture:v1}\n",
        "Dockerfile": "FROM scratch\nUSER 65532\n",
        "README.md": "Fixture documentation.\n",
        "settings.json": '{"fixture": true}\n',
        "logo.png": b"\x89PNG\xff\x00",
        "ascii.bin": b"binary-shaped",
        "invalid.py": b"\xff",
        "nul.py": b"value=1\x00",
        "huge.py": b"#" * (MAX_FILE_BYTES + 1),
        "huge.md": b"x" * (MAX_FILE_BYTES + 1),
        "broken.py": "def broken(:\n",
        "broken.js": "function broken( {\n",
        "broken.ts": "function broken(: {\n",
        "Broken.java": "class Broken { int x( {\n",
        "broken.tf": 'resource "aws_s3_bucket" "broken" {\n',
        "broken-cfn.yaml": "Resources: [\n",
        "broken-k8.yaml": "apiVersion: v1\nkind: Pod\nspec: [\n",
        "broken-compose.yaml": "services: [\n",
        "Dockerfile.broken": "FROM\n",
        "header.py": "# @generated do not edit\ndef work(): return 1\n",
        "app.exotic": "fixture unknown source\n",
        "scripts/run": "#!/usr/bin/env python3\nprint('fixture')\n",
        "Makefile": "all:\n\techo fixture\n",
        ".gitignore": "local.db\n",
        ".git/private.py": "pass\n",
    }
    for directory in ("node_modules", "vendor", ".venv", "dist", "build", "target", "generated", "coverage"):
        files[directory + "/excluded.py"] = "def excluded():\n    return 1\n"
    return files


def fixture_zip(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, value in files.items():
            archive.writestr(path, value)
    return stream.getvalue()


def test_phase2_complete_inventory_and_streaming_parity(storage):  # noqa: F811 - imported pytest fixture
    sources = closure_sources()
    payload = fixture_zip(sources)
    legacy = analyze(read_zip(payload, keep_excluded=True))
    db, user, repo = storage
    inventory = capture(db, user.organization_id, repo, archive_items(io.BytesIO(payload)))
    files = RepositoryFiles(db, user.organization_id, repo.id, inventory.id)
    streaming = analyze_inventory(db, files)
    coverage = legacy["analysis_coverage"]
    rows = {r["path"]: r for r in coverage["inventory"]}
    assert set(rows) == set(sources)
    assert coverage["summary"] == streaming["analysis_coverage"]["summary"]
    fields = (
        "language",
        "kind",
        "analysis_state",
        "loc",
        "bytes",
        "source_parser_completed",
        "native_scan_performed",
        "coverage_source",
    )
    assert {r["path"]: tuple(r[f] for f in fields) for r in streaming["analysis_coverage"]["inventory"]} == {
        p: tuple(r[f] for f in fields) for p, r in rows.items()
    }
    for p in ("ok.py", "ok.js", "ok.ts", "Ok.java"):
        assert rows[p]["analysis_state"] == "PARTIAL" and rows[p]["source_parser_completed"]
    for p in (
        "app.go",
        "app.rs",
        "app.c",
        "app.cpp",
        "app.cs",
        "app.kt",
        "app.rb",
        "app.php",
        "app.sh",
        "app.vue",
        "app.svelte",
        "app.sql",
        "app.exotic",
        "scripts/run",
        "Makefile",
    ):
        assert rows[p]["analysis_state"] == "UNSUPPORTED" and rows[p]["coverage_source"]
    for p in (
        "broken.py",
        "broken.js",
        "broken.ts",
        "Broken.java",
        "broken.tf",
        "broken-cfn.yaml",
        "broken-k8.yaml",
        "broken-compose.yaml",
        "Dockerfile.broken",
    ):
        assert rows[p]["analysis_state"] in {"PARSE_FAILED", "PARTIAL"}, p
        assert not rows[p]["source_parser_completed"], p
    for p in ("logo.png", "ascii.bin", "nul.py"):
        assert rows[p]["analysis_state"] == "BINARY" and rows[p]["loc"] is None
    for p in ("huge.py", "huge.md"):
        assert rows[p]["analysis_state"] == "SKIPPED_SIZE_LIMIT" and rows[p]["loc"] is None
        assert not rows[p]["source_parser_completed"]
    assert rows["invalid.py"]["analysis_state"] == "UNSUPPORTED" and rows["invalid.py"]["loc"] is None
    for p in ("node_modules/excluded.py", "vendor/excluded.py", ".venv/excluded.py"):
        assert rows[p]["analysis_state"] == "EXCLUDED_VENDOR"
    for p in (
        "dist/excluded.py",
        "build/excluded.py",
        "target/excluded.py",
        "generated/excluded.py",
        "coverage/excluded.py",
        "header.py",
    ):
        assert rows[p]["analysis_state"] == "EXCLUDED_GENERATED"
    # 4 parsed + 15 unsupported + 4 broken programming sources + invalid encoding + oversized source.
    assert coverage["summary"]["files_discovered"] == 52
    assert coverage["summary"]["source_files"] == 25
    assert coverage["summary"]["source_files_parsed"] == 4
    assert coverage["summary"]["source_analysis_percent"] == 16
    assert sum(coverage["summary"]["states"].values()) == 52
    assert coverage["summary"]["states"] == {
        "PARTIAL": 11,
        "UNSUPPORTED": 16,
        "PARSE_FAILED": 9,
        "EXCLUDED_GENERATED": 6,
        "EXCLUDED_VENDOR": 3,
        "SKIPPED_SIZE_LIMIT": 2,
        "BINARY": 3,
        "IGNORED_BY_POLICY": 2,
    }
    for language in coverage["languages"]:
        group = [r for r in rows.values() if r["language"] == language["language"]]
        assert language["files"] == len(group)
        assert language["loc"] == sum(r["loc"] or 0 for r in group)
        assert language["loc_unknown_files"] == sum(r["loc"] is None for r in group)
    assert all("excluded.py" not in m["path"] and m["path"] != "header.py" for m in legacy["code_quality"]["metrics"])
    assert coverage["authority"] == "STATIC / DECLARED" and coverage["runtime_evidence"] == "UNOBSERVED"
    assert all(
        coverage[k] is False for k in ("customer_code_executed", "external_llm_used", "source_sent_to_external_ai")
    )
    failed_paths = {p for p, r in rows.items() if r["analysis_state"] == "PARSE_FAILED"}
    assert not any(db.get(ParserArtifact, artifact_key(files, p, infrastructure_config(None))) for p in failed_paths)
    rerun = analyze_inventory(db, files)
    assert rerun["analysis_coverage"]["summary"] == coverage["summary"]
    assert rerun["source_storage"]["parser_cache_misses"] >= len(failed_paths)


@pytest.mark.parametrize(
    "files,expected,measured",
    [
        ({"app.py": "pass\n"}, "PASS", 100),
        ({"app.py": "pass\n", "app.go": "package main\n"}, "FAIL", 50),
        ({"app.go": "package main\n"}, "FAIL", 0),
        ({"app.py": "def broken(:\n"}, "FAIL", 0),
        ({"README.md": "Fixture\n"}, "REVIEW_REQUIRED", None),
    ],
)
def test_phase2_minimum_coverage_gate(files, expected, measured):
    result = analyze(files, profile={"quality": {"gate": {"min_analysis_coverage_percent": 100}}})
    evaluated = gate(result["code_quality"], result["findings"])
    condition = next(r for r in evaluated["results"] if r["policy"] == "Quality: parsed-file analysis coverage")
    assert condition["result"] == expected and condition["measured"] == measured
    if expected != "PASS":
        assert evaluated["status"] != "PASS"


def test_phase2_coverage_gate_does_not_round_a_gap_to_100_percent():
    result = analyze({"app.py": "pass\n"}, profile={"quality": {"gate": {"min_analysis_coverage_percent": 100}}})
    quality = result["code_quality"]
    quality["inventory"] = [quality["inventory"][0]] * 20000 + [
        {"path": "gap.go", "language": "Go", "kind": "UNSUPPORTED", "parser_state": "NOT_ANALYZED"}
    ]
    evaluated = gate(quality, result["findings"])
    condition = next(r for r in evaluated["results"] if r["policy"] == "Quality: parsed-file analysis coverage")
    assert 99.99 < condition["measured"] < 100
    assert condition["result"] == "FAIL" and evaluated["status"] != "PASS"


def test_phase2_excluded_iac_and_text_size_metadata_are_honest(storage):  # noqa: F811
    sources = {"generated/broken.tf": 'resource "aws_s3_bucket" "broken" {\n', "large.tf": b"#" * (MAX_FILE_BYTES + 1)}
    payload = fixture_zip(sources)
    db, user, repo = storage
    captured = capture(db, user.organization_id, repo, archive_items(io.BytesIO(payload)))
    for result in (
        analyze(read_zip(payload, keep_excluded=True)),
        analyze_inventory(db, RepositoryFiles(db, user.organization_id, repo.id, captured.id)),
    ):
        rows = {r["path"]: r for r in result["analysis_coverage"]["inventory"]}
        assert rows["generated/broken.tf"]["analysis_state"] == "EXCLUDED_GENERATED"
        assert not rows["generated/broken.tf"]["source_parser_completed"]
        assert rows["large.tf"]["language"] == "Terraform"
        assert rows["large.tf"]["analysis_state"] == "SKIPPED_SIZE_LIMIT"
        assert rows["large.tf"]["loc"] is None
        assert result["analysis_coverage"]["summary"]["source_files"] == 0
    from analyzers.engine import validate_files

    files = validate_files({"huge.py": "#" * (MAX_FILE_BYTES + 1)}, keep_excluded=True)
    assert files.intake[0]["physical_lines"] is None
    with pytest.raises(ValueError, match="duplicate paths"):
        validate_files({"app.py": "pass\n", "./app.py": "pass\n"}, keep_excluded=True)


@pytest.mark.parametrize(
    "path",
    [
        "broken.py",
        "broken.js",
        "broken.ts",
        "Broken.java",
        "broken.tf",
        "broken-cfn.yaml",
        "broken-k8.yaml",
        "broken-compose.yaml",
        "Dockerfile.broken",
    ],
)
def test_phase2_malformed_input_never_passes_coverage_gate(path):
    result = analyze(
        {path: closure_sources()[path]}, profile={"quality": {"gate": {"min_analysis_coverage_percent": 100}}}
    )
    assert gate(result["code_quality"], result["findings"])["status"] != "PASS"


def test_phase2_history_grants_paging_and_safe_projection(signed):
    secret = "ghp_" + "X" * 32
    sources = {f"src/app{i}.py": f"api_key = '{secret}'\n" for i in range(53)}
    sources["broken.py"] = f"def broken(: # {secret}\n"
    repo, base = import_repo(signed, sources)
    head_response = signed.post(
        f"/api/repositories/{repo}/analyze", json={"base_id": base, "files": {"new.go": "package main\n"}}
    )
    assert head_response.status_code == 200
    head = head_response.json()["id"]
    url = f"/api/trust/coverage?repository_id={repo}&snapshot_id={base}"
    before = signed.get(url).json()
    assert before["summary"]["files_discovered"] == 54
    assert signed.get(f"/api/trust/coverage?repository_id={repo}").json()["snapshot_id"] == head
    page1 = signed.get(url + "&limit=50").json()
    page2 = signed.get(url + "&offset=50&limit=50").json()
    assert page1["has_more"] and not page2["has_more"]
    assert len({r["path"] for r in page1["items"] + page2["items"]}) == 54
    assert signed.get(url + "&state=PARSE_FAILED&q=BROKEN").json()["total"] == 1
    assert secret not in str(before) and "api_key =" not in str(before)
    with main.Session() as db:
        snapshot = db.get(Record, base)
        original = snapshot.data.copy()
        coverage = snapshot.data["analysis_coverage"]
        injected = {**coverage["inventory"][0], "source": secret, "credentials": secret, "encrypted_input": secret}
        snapshot.data = {
            **snapshot.data,
            "analysis_coverage": {**coverage, "source": secret, "inventory": [injected, *coverage["inventory"][1:]]},
        }
        tenant = db.get(Repository, repo).organization_id
        db.add(
            User(
                id="coverage-reader",
                organization_id=tenant,
                email="coverage-reader@example.com",
                password_hash=passwords.hash("Strong-test-password-123!"),
                role="VIEWER",
            )
        )
        db.commit()
    projected = signed.get(url).json()
    assert secret not in str(projected)
    assert not any(k in projected["items"][0] for k in ("source", "credentials", "encrypted_input"))
    identity = signed.post(
        "/api/auth/login", json={"email": "coverage-reader@example.com", "password": "Strong-test-password-123!"}
    ).json()
    signed.headers["x-csrf-token"] = identity["csrf"]
    assert signed.get(url + "&q=app&offset=1").status_code == 404
    with main.Session() as db:
        db.add(Grant(user_id="coverage-reader", repository_id=repo))
        db.commit()
    assert signed.get(url).status_code == 200
    assert signed.get(f"/api/trust/coverage?repository_id={repo}&snapshot_id={head}").status_code == 200
    # Preserve an actual legacy representation; reads cannot manufacture or persist coverage.
    with main.Session() as db:
        snapshot = db.get(Record, base)
        legacy = {k: v for k, v in original.items() if k != "analysis_coverage"}
        snapshot.data = legacy
        db.commit()
    assert signed.get(url).json()["state"] == "LEGACY_NOT_MEASURED"
    with main.Session() as db:
        assert db.get(Record, base).data == legacy
    identity = signed.post(
        "/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"}
    ).json()
    signed.headers["x-csrf-token"] = identity["csrf"]
    for suffix in ("", "&q=app&offset=50", "&state=UNSUPPORTED"):
        assert signed.get(url + suffix).status_code == 404
    assert signed.get(f"/api/trust/coverage?snapshot_id={head}").status_code == 404


def test_inventory_captures_supported_unsupported_failures_and_scope():
    files = {
        "ok.py": "def work(): return 1",
        "broken.py": "def work(:",
        "app.go": "package main",
        "vendor/dep.py": "pass",
        "generated/output.ts": "const x = 1",
        "README.md": "Project",
        "compose.yaml": "services:\n  app:\n    privileged: true\n",
    }
    result = analyze(files)
    coverage = result["analysis_coverage"]
    rows = {r["path"]: r for r in coverage["inventory"]}
    assert set(rows) == set(files)
    assert rows["ok.py"]["source_parser_completed"] and rows["ok.py"]["analysis_state"] == "PARTIAL"
    assert rows["app.go"]["analysis_state"] == "UNSUPPORTED"
    assert rows["broken.py"]["analysis_state"] == "PARSE_FAILED"
    assert rows["vendor/dep.py"]["analysis_state"] == "EXCLUDED_VENDOR"
    assert rows["generated/output.ts"]["analysis_state"] == "EXCLUDED_GENERATED"
    assert rows["compose.yaml"]["language"] == "Compose" and rows["compose.yaml"]["source_parser_completed"]
    assert coverage["runtime_evidence"] == "UNOBSERVED" and not coverage["external_llm_used"]


def test_zip_binary_and_oversize_inventory_does_not_claim_parse_success():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("ok.py", "pass\n")
        archive.writestr("big.py", b"#" * (MAX_FILE_BYTES + 1))
        archive.writestr("logo.png", b"\x89PNG\xff\x00")
    files = read_zip(stream.getvalue(), keep_excluded=True)
    assert "big.py" not in files
    result = analyze(files)
    rows = {r["path"]: r for r in result["analysis_coverage"]["inventory"]}
    assert rows["big.py"]["analysis_state"] == "SKIPPED_SIZE_LIMIT" and rows["big.py"]["loc"] is None
    assert not rows["big.py"]["native_scan_performed"]
    assert rows["logo.png"]["analysis_state"] == "BINARY"
    assert result["code_quality"]["state"] == "PARTIAL"


def test_coverage_snapshot_authorization_paging_and_source_exclusion(signed):
    repo, snapshot = import_repo(signed, {"app.py": "secret_marker = 'fixture'\n", "app.go": "package main"})
    url = f"/api/trust/coverage?repository_id={repo}&snapshot_id={snapshot}"
    result = signed.get(url + "&limit=1").json()
    assert result["total"] == 2 and len(result["items"]) == 1 and result["has_more"]
    assert "secret_marker" not in str(result) and result["job_id"]
    assert signed.get(url + "&state=UNSUPPORTED").json()["items"][0]["language"] == "Go"
    assert signed.get(url + "&q=missing").json()["total"] == 0
    assert signed.get(url + "&limit=101").status_code == 422
    assert signed.get("/api/trust/coverage?repository_id=private").status_code == 404
    assert signed.get("/api/trust/coverage?repository_id=clean&snapshot_id=" + snapshot).status_code == 404
    identity = signed.post(
        "/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"}
    ).json()
    signed.headers["x-csrf-token"] = identity["csrf"]
    assert signed.get(url).status_code == 404
