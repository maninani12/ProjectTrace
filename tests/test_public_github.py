import io
import zipfile

import httpx
import pytest
from sqlalchemy import select

from backend import main
from backend.db import Record, SourceInventoryFile
from backend.intake_errors import IntakeError
from integrations.github.public import (
    PublicGitHub,
    comparable_archive_hashes,
    repository_archive_items,
    repository_url,
    validate_ref,
)


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://evil.example/a/b", "https://github.com@127.0.0.1/a/b",
                                   "https://github.com/a/b?token=bad", "https://github.com/a/b#ref", "https://github.com/a/b/tree/main",
                                   "https://github.com/a/%2e%2e", "https://github.com:443/a/b"])
def test_public_url_rejects_unsupported_or_unsafe_inputs(url):
    with pytest.raises(ValueError):
        repository_url(url)


@pytest.mark.parametrize("ref", ["../main", "refs//main", "main@{1}", "main\\x", "bad ref", "main:evil", "x.lock"])
def test_public_ref_validation(ref):
    with pytest.raises(IntakeError):
        validate_ref(ref)


def test_public_archive_paths_are_pinned_and_legacy_hashes_compare_by_repo_path():
    commit = "a" * 40
    provenance = {"repository": "owner/repo", "commit": commit}
    metadata = {"bytes": 7, "state": "UNSUPPORTED"}
    source = [(f"repo-{commit}/README.md", b"readme"), (f"repo-{commit}/meta.bin", metadata)]

    assert list(repository_archive_items(iter(source), provenance)) == [
        ("README.md", b"readme"),
        ("meta.bin", metadata),
    ]
    with pytest.raises(IntakeError) as failure:
        list(repository_archive_items(iter([("unexpected-root/README.md", b"x")]), provenance))
    assert failure.value.code == "PUBLIC_GITHUB_ARCHIVE_LAYOUT"
    with pytest.raises(IntakeError):
        list(repository_archive_items(iter([(f"repo-{commit}/", b"")]), provenance))

    legacy = {f"repo-{commit}/README.md": "same", f"repo-{commit}/main.tf": "changed"}
    legacy_view = comparable_archive_hashes(legacy, {**provenance, "source": "GITHUB_PUBLIC"})
    assert legacy_view.hashes is legacy
    assert list(legacy_view) == ["README.md", "main.tf"]
    assert dict(legacy_view) == {
        "README.md": "same",
        "main.tf": "changed",
    }
    ambiguous = {f"repo-{commit}/README.md": "old", "README.md": "other"}
    ambiguous_view = comparable_archive_hashes(ambiguous, provenance)
    assert ambiguous_view.get("README.md") is None


def public_fixture(monkeypatch, *, private=False, redirect=None, status=200, commit="a" * 40, files=None):
    files = files or {
        "app.py": "def unsafe(value):\n    return eval(value)\n",
        "README.md": "# API\nThe service validates user input.\n",
    }
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w") as archive:
        for path, content in files.items():
            archive.writestr(f"repo-{commit}/" + path, content)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert "authorization" not in request.headers
        if request.url.host == "codeload.github.com":
            assert request.url.path == "/owner/repo/zip/" + commit
            return httpx.Response(200, content=bundle.getvalue())
        if "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": commit})
        if redirect:
            return httpx.Response(302, headers={"location": redirect})
        return httpx.Response(status, json={"private": private, "full_name": "owner/repo", "default_branch": "main"})

    monkeypatch.setattr(PublicGitHub, "client", lambda self, base: httpx.Client(base_url=base, transport=httpx.MockTransport(handler)))
    return calls


def test_public_resolution_is_exact_and_no_app_credentials_required(monkeypatch):
    calls = public_fixture(monkeypatch)
    for name in ("SCM_GITHUB_KEY", "SCM_GITHUB_WEBHOOK", "GITHUB_PRIVATE_KEY", "GITHUB_APP_ID"):
        monkeypatch.delenv(name, raising=False)
    result = PublicGitHub("https://github.com/owner/repo.git").resolve()
    assert result["commit"] == "a" * 40 and result["ref"] == "main"
    assert result["mode"] == "ONE_TIME_SNAPSHOT" and len(calls) == 2


@pytest.mark.parametrize("patch,code", [({"private": True}, "PUBLIC_GITHUB_PRIVATE"),
                                         ({"redirect": "https://127.0.0.1/internal"}, "PUBLIC_GITHUB_REDIRECT"),
                                         ({"status": 429}, "PUBLIC_GITHUB_RATE_LIMIT"),
                                         ({"status": 503}, "PUBLIC_GITHUB_UNAVAILABLE")])
def test_provider_errors_and_redirects_are_actionable(monkeypatch, patch, code):
    public_fixture(monkeypatch, **patch)
    with pytest.raises(IntakeError) as failure:
        PublicGitHub("https://github.com/owner/repo").resolve()
    assert failure.value.code == code


def test_public_api_continuation_compares_pinned_snapshots_and_preserves_tenant_scope(client, monkeypatch, tmp_path):
    from tests.test_streaming_import import private_storage
    from workers import public_github
    private_storage(monkeypatch, tmp_path)
    marker = tmp_path / "public-source-must-not-execute"
    base_files = {
        "app.py": "def unsafe(value):\n    return eval(value)\n",
        "README.md": "# Storage contract\nProduction storage is private.\n",
        "main.tf": 'resource "aws_s3_bucket" "production" { acl = "private" }\n',
        "never_run.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
    }
    base_calls = public_fixture(monkeypatch, commit="a" * 40, files=base_files)
    response = client.post("/api/auth/register", json={"email": "public-test@example.com", "password": "Strong-test-password-123!", "organization": "Public test"})
    client.headers["x-csrf-token"] = response.json()["csrf"]
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setattr("backend.queue.dispatch", lambda db, job: None)
    body = {"url": "https://github.com/owner/repo", "request_key": "public-request-001"}
    imported = client.post("/api/github/public/import", json=body)
    assert imported.status_code == 202
    duplicate = client.post("/api/github/public/import", json=body)
    assert duplicate.json()["job_id"] == imported.json()["job_id"]
    assert duplicate.json()["duplicate"] is True
    assert client.post("/api/github/public/import", json={**body, "ref": "other"}).status_code == 409
    monkeypatch.setattr(public_github, "Session", main.Session)
    public_github.public_github_job.run(imported.json()["job_id"])
    with main.Session() as db:
        job = db.get(Record, imported.json()["job_id"])
        snapshot = db.get(Record, job.data["snapshot_id"])
        base_id = snapshot.id
        assert snapshot.data["commit"] == "a" * 40
        assert snapshot.data["commit_source"] == "GIT_SHA"
        assert snapshot.data["source_provenance"]["source"] == "GITHUB_PUBLIC"
        assert db.scalar(select(Record).where(Record.kind == "finding", Record.repository_id == job.repository_id))
        # Full historical prefixed paths/identities are exercised through actual
        # publication in test_public_snapshot_continuity, without rewriting BASE.
    assert len(base_calls) == 3
    assert not marker.exists()

    head_files = {
        **base_files,
        "main.tf": 'resource "aws_s3_bucket" "production" { acl = "public-read" }\n',
    }
    head_calls = public_fixture(monkeypatch, commit="b" * 40, files=head_files)
    next_body = {
        "url": "https://github.com/owner/repo",
        "request_key": "public-request-002",
        "repository_id": imported.json()["repository_id"],
        "base_snapshot_id": base_id,
    }
    queued_head = client.post("/api/github/public/import", json=next_body)
    assert queued_head.status_code == 202
    duplicate_head = client.post("/api/github/public/import", json=next_body)
    assert duplicate_head.status_code == 202
    assert duplicate_head.json()["job_id"] == queued_head.json()["job_id"]
    assert duplicate_head.json()["duplicate"] is True
    assert client.post(
        "/api/github/public/import",
        json={**next_body, "url": "https://github.com/owner/other"},
    ).status_code == 409
    with main.Session() as db:
        queued_job = db.get(Record, queued_head.json()["job_id"])
        assert queued_job.data["base_id"] == base_id

    public_github.public_github_job.run(queued_head.json()["job_id"])
    with main.Session() as db:
        head_job = db.get(Record, queued_head.json()["job_id"])
        head_snapshot = db.get(Record, head_job.data["snapshot_id"])
        assert head_snapshot.data["base_id"] == base_id
        assert head_snapshot.data["commit"] == "b" * 40
        assert head_snapshot.data["changed_files"] == ["main.tf"]
        assert head_snapshot.data["source_provenance"]["source"] == "GITHUB_PUBLIC"
        source_paths = db.scalars(
            select(SourceInventoryFile.path).where(
                SourceInventoryFile.inventory_id == head_snapshot.data["source_inventory_id"]
            )
        ).all()
        assert sorted(source_paths) == sorted(head_files)
        change = db.scalar(
            select(Record).where(
                Record.repository_id == head_job.repository_id,
                Record.kind == "engineering_change",
            )
        )
        assert change.data["base_snapshot_id"] == base_id
        assert change.data["head_snapshot_id"] == head_snapshot.id
    listing = client.get(
        "/api/engineering-changes?repository_id=" + imported.json()["repository_id"]
    ).json()
    detail = client.get("/api/engineering-changes/" + listing["items"][0]["id"]).json()
    comparison = next(
        item for item in detail["claim_comparisons"] if item["text"] == "Production storage is private."
    )
    assert comparison["before"]["status"] == "UNVERIFIED"
    assert comparison["after"]["status"] == "CONTRADICTED"
    assert comparison["document"]["path"] == "README.md"
    assert comparison["after"]["evidence"][0]["path"] == "main.tf"
    assert len(head_calls) == 3
    assert not marker.exists()

    wrong_source_type = client.post(
        "/api/github/public/import",
        json={
            "url": "https://github.com/owner/repo",
            "request_key": "public-request-zip-target",
            "repository_id": client.post(
                "/api/import", json={"name": "zip-target", "files": {"app.py": "x = 1\n"}}
            ).json()["repository_id"],
        },
    )
    assert wrong_source_type.status_code == 409

    response = client.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"})
    client.headers["x-csrf-token"] = response.json()["csrf"]
    assert client.get("/api/record/" + job.id).status_code == 404
    assert client.post(
        "/api/github/public/import",
        json={
            "url": "https://github.com/owner/repo",
            "request_key": "public-request-outsider",
            "repository_id": imported.json()["repository_id"],
        },
    ).status_code == 404


def test_public_explicit_base_remains_selected_when_a_newer_snapshot_exists(client, monkeypatch):
    response = client.post("/api/auth/register", json={
        "email": "explicit-base@example.com", "password": "Strong-test-password-123!",
        "organization": "Explicit BASE",
    })
    client.headers["x-csrf-token"] = response.json()["csrf"]
    monkeypatch.setenv("JOB_MODE", "celery")
    monkeypatch.setattr("backend.queue.dispatch", lambda db, job: None)
    body = {"url": "https://github.com/owner/repo", "request_key": "explicit-base-create"}
    created = client.post("/api/github/public/import", json=body).json()
    with main.Session() as db:
        job = db.get(Record, created["job_id"])
        for identity, timestamp in (("selected-base", "2026-10-01"), ("newer-base", "2026-10-02")):
            db.add(Record(id=identity, organization_id=job.organization_id, repository_id=job.repository_id,
                          kind="snapshot", natural_key=identity, created_at=timestamp,
                          data={"branch": "release", "commit": "a" * 40}))
        db.add(Record(id="foreign-base", organization_id="northstar", repository_id="private",
                      kind="snapshot", natural_key="foreign-base", data={"branch": "secret"}))
        db.commit()
    target = {**body, "repository_id": created["repository_id"]}
    explicit = client.post("/api/github/public/import", json={
        **target, "request_key": "explicit-base-selected", "base_snapshot_id": "selected-base",
    })
    implicit = client.post("/api/github/public/import", json={**target, "request_key": "legacy-base-latest"})
    assert explicit.status_code == implicit.status_code == 202
    assert client.post("/api/github/public/import", json={
        **target, "request_key": "explicit-base-selected", "base_snapshot_id": "newer-base",
    }).status_code == 409
    for invalid_base in ("missing-base", created["job_id"]):
        assert client.post("/api/github/public/import", json={
            **target, "request_key": "invalid-" + invalid_base, "base_snapshot_id": invalid_base,
        }).status_code == 404
    assert client.post("/api/github/public/import", json={
        **body, "request_key": "base-without-target", "base_snapshot_id": "selected-base",
    }).status_code == 422
    with main.Session() as db:
        assert db.get(Record, explicit.json()["job_id"]).data["base_id"] == "selected-base"
        assert db.get(Record, implicit.json()["job_id"]).data["base_id"] == "newer-base"
    assert client.post("/api/github/public/import", json={
        **target, "request_key": "cross-tenant-base", "base_snapshot_id": "foreign-base",
    }).status_code == 404
