import io
import zipfile

import httpx
import pytest
from sqlalchemy import select

from backend import main
from backend.db import Record
from backend.intake_errors import IntakeError
from integrations.github.public import PublicGitHub, repository_url, validate_ref


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


def public_fixture(monkeypatch, *, private=False, redirect=None, status=200):
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("repo-commit/app.py", "def unsafe(value):\n    return eval(value)\n")
        archive.writestr("repo-commit/README.md", "# API\nThe service validates user input.\n")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert "authorization" not in request.headers
        if request.url.host == "codeload.github.com":
            assert request.url.path == "/owner/repo/zip/" + "a" * 40
            return httpx.Response(200, content=bundle.getvalue())
        if "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": "a" * 40})
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


def test_public_api_real_worker_snapshot_idempotency_and_tenant_scope(client, monkeypatch, tmp_path):
    from tests.test_streaming_import import private_storage
    from workers import public_github
    private_storage(monkeypatch, tmp_path)
    calls = public_fixture(monkeypatch)
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
        assert snapshot.data["commit"] == "a" * 40
        assert snapshot.data["commit_source"] == "GIT_SHA"
        assert snapshot.data["source_provenance"]["source"] == "GITHUB_PUBLIC"
        assert db.scalar(select(Record).where(Record.kind == "finding", Record.repository_id == job.repository_id))
    assert len(calls) == 3
    response = client.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"})
    client.headers["x-csrf-token"] = response.json()["csrf"]
    assert client.get("/api/record/" + job.id).status_code == 404
