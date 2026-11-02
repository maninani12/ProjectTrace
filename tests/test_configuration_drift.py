"""Configuration claims use static declarations and preserve their evidence scope."""

import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from analyzers.engine import analyze
from backend import main
from backend.db import Record
from tests.test_code_quality import import_repo
from tests.test_engineering_changes import advance

FIXTURE = json.loads(Path("samples/configuration-drift.json").read_text(encoding="utf-8"))


def privacy_claim(result):
    return next(claim for claim in result["claims"] if claim["assertion_family"] == "storage_privacy")


@pytest.mark.parametrize(
    ("resource", "status", "evidence"),
    [
        ('resource "aws_s3_bucket" "production" { acl = "public-read" }', "CONTRADICTED", True),
        ('resource "aws_s3_bucket" "production" { acl = "private" }', "UNVERIFIED", False),
        ('resource "aws_s3_bucket" "development" { acl = "public-read" }', "UNVERIFIED", False),
        ('# resource "aws_s3_bucket" "production" { acl = "public-read" }', "UNVERIFIED", False),
    ],
)
def test_storage_privacy_uses_only_scoped_positive_configuration(resource, status, evidence):
    claim = privacy_claim(analyze({"README.md": "Production storage is private.\n", "main.tf": resource}))
    assert claim["status"] == status
    assert claim["verification_scope"] == "DECLARED_CONFIGURATION"
    assert bool(claim["signals"]) is evidence


@pytest.mark.parametrize(
    "markdown",
    [
        "~~~text\nProduction storage is private.\n~~~\n",
        "````text\nProduction storage is private.\n```\n~~~\nProduction storage is private.\n````\n",
        "    Production storage is private.\n",
    ],
)
def test_storage_privacy_ignores_markdown_code_examples(markdown):
    result = analyze(
        {
            "README.md": markdown,
            "main.tf": 'resource "aws_s3_bucket" "production" { acl = "public-read" }',
        }
    )

    assert not any(claim["assertion_family"] == "storage_privacy" for claim in result["claims"])


def test_storage_privacy_resumes_after_a_matching_markdown_fence():
    result = analyze(
        {
            "README.md": "~~~text\nProduction storage is private.\n~~~\nProduction storage is private.\n",
            "main.tf": 'resource "aws_s3_bucket" "production" { acl = "public-read" }',
        }
    )
    claim = privacy_claim(result)

    assert claim["status"] == "CONTRADICTED"
    assert claim["line"] == 4


def test_captured_storage_configuration_drift_preserves_source_scope_and_tenant_isolation(signed, tmp_path):
    sentinel = tmp_path / "imported-configuration-code-executed"
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"
    base_files = {**FIXTURE["base"], "never_run.py": source}
    repo, baseline = import_repo(signed, base_files)
    with main.Session() as db:
        original = copy.deepcopy(db.get(Record, baseline).data)

    head = advance(signed, repo, baseline, {**FIXTURE["head"], "never_run.py": source})
    with main.Session() as db:
        head_snapshot = copy.deepcopy(db.get(Record, head).data)
    listing = signed.get(f"/api/engineering-changes?repository_id={repo}").json()
    change = next(item for item in listing["items"] if item["head_snapshot_id"] == head)
    detail = signed.get("/api/engineering-changes/" + change["id"]).json()
    comparison = next(item for item in detail["claim_comparisons"] if item["text"] == "Production storage is private.")

    assert comparison["before"]["status"] == "UNVERIFIED"
    assert comparison["after"]["status"] == "CONTRADICTED"
    assert "live deployment is unobserved" in comparison["after"]["reason"]
    assert comparison["document"]["path"] == "README.md"
    assert comparison["after"]["evidence"][0]["path"] == "main.tf"
    assert original["hashes"]["main.tf"] != head_snapshot["hashes"]["main.tf"]

    claim = signed.get("/api/record/" + comparison["after"]["claim_id"]).json()
    assert claim["verification_scope"] == "DECLARED_CONFIGURATION"
    assert claim["verifier"] == "NATIVE_STATIC_STORAGE_PRIVACY"
    with main.Session() as db:
        assert db.get(Record, baseline).data == original
        rows = list(db.scalars(select(Record).where(Record.repository_id == repo, Record.kind == "claim")))
        assert any(row.data.get("verification_scope") == "DECLARED_CONFIGURATION" for row in rows)
    assert not sentinel.exists()

    outsider = signed.post(
        "/api/auth/login",
        json={"email": "outside@example.com", "password": "Strong-test-password-123!"},
    )
    assert outsider.status_code == 200
    assert signed.get("/api/engineering-changes/" + change["id"]).status_code == 404
    assert signed.get("/api/record/" + comparison["after"]["claim_id"]).status_code == 404
