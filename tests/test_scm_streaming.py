import base64
import hashlib

import httpx
import pytest

from integrations.github.connector import GitHubApp


def adapter(monkeypatch, *, truncated=False, count=1, oversized=False, corrupt=False):
    app = GitHubApp("1", "unused", "1", api_base_url="https://ghes.example/api/v3", allowed_hosts={"ghes.example"})
    raw = b"pass\n"
    digest = hashlib.sha1(b"blob 5\0" + raw).hexdigest()
    monkeypatch.setattr(app, "authenticate", lambda: "owned-token")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if "/trees/" in request.url.path:
            if truncated and "recursive" in request.url.params:
                return httpx.Response(200, json={"truncated": True, "tree": []})
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {
                            "path": f"module{i}.py",
                            "type": "blob",
                            "mode": "100644",
                            "sha": digest,
                            "size": 600000 if oversized else len(raw),
                        }
                        for i in range(count)
                    ]
                },
            )
        return httpx.Response(
            200, json={"encoding": "base64", "content": base64.b64encode(b"evil\n" if corrupt else raw).decode()}
        )

    monkeypatch.setattr(
        app,
        "client",
        lambda headers=None: httpx.Client(
            base_url=app.api_base_url, headers=headers, transport=httpx.MockTransport(handler)
        ),
    )
    return app, calls


def test_streaming_provider_exceeds_legacy_1000_file_adapter_without_source_dictionary(monkeypatch):
    app, calls = adapter(monkeypatch, count=1001)
    assert sum(1 for _ in app.iter_snapshot("owned/repo", "a" * 40)) == 1001
    assert all(path.startswith("/api/v3/") for path in calls)


def test_truncated_recursive_tree_falls_back_and_oversize_is_explicit(monkeypatch):
    app, calls = adapter(monkeypatch, truncated=True, oversized=True)
    result = list(app.iter_snapshot("owned/repo", "a" * 40))
    assert result == [("module0.py", {"bytes": 600000, "state": "SKIPPED_SIZE_LIMIT"})]
    assert len(calls) == 2 and all("/trees/" in path for path in calls)


def test_streaming_provider_rejects_blob_content_not_bound_to_tree(monkeypatch):
    app, _ = adapter(monkeypatch, corrupt=True)
    with pytest.raises(ValueError, match="integrity"):
        list(app.iter_snapshot("owned/repo", "a" * 40))
