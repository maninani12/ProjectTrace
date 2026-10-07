import io
import zipfile

from analyzers.engine import MAX_FILE_BYTES, analyze, read_zip
from tests.test_code_quality import import_repo


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
