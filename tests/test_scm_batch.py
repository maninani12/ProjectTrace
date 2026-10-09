"""Large GitHub source batching retains immutable blob and bounded-intake guarantees."""
import base64
import hashlib
import json
import re

import httpx
import pytest

from integrations.github.connector import GitHubApp


def adapter(monkeypatch, *, extra=None, node_patch=None, errors=False, large=False, utf16=False, corrupt_rest=False):
    app = GitHubApp("1", "unused", "1")
    monkeypatch.setattr(app, "authenticate", lambda: "fixture-token")
    sources = {f"file{i}.py": f"VALUE = {i}\n".encode() for i in range(1001)}
    if large:
        sources.update({f"file{i}.py": (str(i) + "x" * 399998 + "\n").encode() for i in range(12)})
    if utf16:
        sources["DataModelSchema"] = '{"schema":"fixture"}'.encode("utf-16")
    entries, blobs, calls = [], {}, []
    for path, raw in sources.items():
        sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        blobs[sha] = raw
        entries.append({"path": path, "sha": sha, "mode": "100644", "type": "blob", "size": len(raw)})
    entries.extend(extra or [])

    def handler(request):
        assert request.url.host == "api.github.com"
        calls.append(request)
        if "/trees/" in request.url.path:
            return httpx.Response(200, json={"tree": entries, "truncated": False})
        if request.url.path == "/graphql":
            body = json.loads(request.content)
            assert body["variables"] == {"owner": "owned", "name": "repo"}
            assert "mutation" not in body["query"] and "expression" not in body["query"]
            aliases = re.findall(r'(b\d+):object\(oid:"([a-f0-9]{40})"\)', body["query"])
            assert len(aliases) <= 100 and sum(len(blobs[sha]) for _, sha in aliases) <= 2_000_000
            result = {}
            for alias, sha in aliases:
                raw = blobs[sha]
                text = raw.decode("utf-16") if raw.startswith(b"\xff\xfe") else raw.decode()
                node = {"oid": sha, "byteSize": len(raw), "isBinary": False, "isTruncated": False, "text": text}
                result[alias] = {**node, **(node_patch or {})}
            return httpx.Response(200, json={"data": {"repository": result}, **({"errors": [{"type": "FIXTURE"}]} if errors else {})})
        sha = request.url.path.rsplit("/", 1)[-1]
        assert sha in blobs, "Skipped link/submodule/oversized content must never be fetched"
        raw = b"X" * len(blobs[sha]) if corrupt_rest else blobs[sha]
        return httpx.Response(200, json={"encoding": "base64", "content": base64.b64encode(raw).decode()})

    monkeypatch.setattr(app, "client", lambda headers=None: httpx.Client(
        base_url=app.api_base_url, headers=headers, transport=httpx.MockTransport(handler), follow_redirects=False,
    ))
    return app, sources, calls


def test_large_github_batches_match_all_original_bytes_with_fewer_requests(monkeypatch):
    app, expected, calls = adapter(monkeypatch)
    assert dict(app.iter_snapshot("owned/repo", "a" * 40)) == expected
    assert sum(c.url.path == "/graphql" for c in calls) == 11
    assert len(calls) == 12


def test_batch_byte_budget_is_enforced_in_addition_to_file_count(monkeypatch):
    app, expected, calls = adapter(monkeypatch, large=True)
    assert dict(app.iter_snapshot("owned/repo", "a" * 40)) == expected
    assert len(calls) > 12  # Size boundary forces an earlier batch.


@pytest.mark.parametrize("patch,reason", [
    ({"oid": "f" * 40}, "identity or size"),
    ({"byteSize": True}, "identity or size"),
])
def test_batch_rejects_corrupt_source_identity_and_declared_size(monkeypatch, patch, reason):
    app, _, _ = adapter(monkeypatch, node_patch=patch)
    with pytest.raises(ValueError, match=reason):
        list(app.iter_snapshot("owned/repo", "a" * 40))


@pytest.mark.parametrize("text", ["corrupt", "INVALID=00\n", "EVILX = 0\n"])
def test_changed_provider_text_is_never_accepted_and_raw_bytes_are_verified(monkeypatch, text):
    app, expected, calls = adapter(monkeypatch, node_patch={"text": text})
    assert dict(app.iter_snapshot("owned/repo", "a" * 40)) == expected
    assert any("/blobs/" in call.url.path for call in calls)


def test_transcoded_utf16_provider_text_uses_original_verified_bytes(monkeypatch):
    app, expected, calls = adapter(monkeypatch, utf16=True)
    assert dict(app.iter_snapshot("owned/repo", "a" * 40)) == expected
    assert sum("/blobs/" in call.url.path for call in calls) == 1


def test_corrupted_rest_fallback_still_fails_git_integrity(monkeypatch):
    app, _, _ = adapter(monkeypatch, node_patch={"text": "EVILX = 0\n"}, corrupt_rest=True)
    with pytest.raises(ValueError, match="integrity"):
        list(app.iter_snapshot("owned/repo", "a" * 40))


@pytest.mark.parametrize("patch", [{"isBinary": True, "text": None}, {"isTruncated": True, "text": "prefix"}])
def test_binary_or_truncated_graphql_uses_original_verified_rest_bytes(monkeypatch, patch):
    app, expected, calls = adapter(monkeypatch, node_patch=patch)
    assert dict(app.iter_snapshot("owned/repo", "a" * 40)) == expected
    assert sum("/blobs/" in c.url.path for c in calls) == 1001


def test_graphql_partial_errors_fail_closed(monkeypatch):
    app, _, _ = adapter(monkeypatch, errors=True)
    with pytest.raises(ValueError, match="incomplete"):
        list(app.iter_snapshot("owned/repo", "a" * 40))


def test_links_submodules_and_large_files_are_metadata_without_fetch(monkeypatch):
    extra = [
        {"path": "link.py", "type": "blob", "mode": "120000", "sha": "c" * 40, "size": 8},
        {"path": "other-repository", "type": "commit", "mode": "160000", "sha": "d" * 40},
        {"path": "huge.py", "type": "blob", "mode": "100644", "sha": "e" * 40, "size": 512001},
    ]
    app, expected, _ = adapter(monkeypatch, extra=extra)
    result = dict(app.iter_snapshot("owned/repo", "a" * 40))
    assert len(result) == len(expected) + 3
    assert result["link.py"] == {"bytes": 8, "state": "UNSUPPORTED", "source_kind": "SYMLINK"}
    assert result["other-repository"] == {"bytes": 0, "state": "UNSUPPORTED", "source_kind": "SUBMODULE"}
    assert result["huge.py"]["state"] == "SKIPPED_SIZE_LIMIT"


@pytest.mark.parametrize("entry", [
    {"path": "file0.py", "size": 8}, {"path": "../escape.py", "size": 8},
    {"path": "bad.py", "size": -1}, {"path": "bad.py", "size": True},
    {"path": "bad.py", "size": 8, "sha": "untrusted-oid"},
])
def test_batch_rejects_duplicate_traversal_and_invalid_metadata(monkeypatch, entry):
    extra = [{"type": "blob", "mode": "100644", "sha": "c" * 40, **entry}]
    app, _, _ = adapter(monkeypatch, extra=extra)
    with pytest.raises(ValueError):
        list(app.iter_snapshot("owned/repo", "a" * 40))


def test_whole_repository_file_limit_still_rejects(monkeypatch):
    monkeypatch.setenv("REPOSITORY_MAX_FILES", "1000")
    app, _, _ = adapter(monkeypatch)
    with pytest.raises(ValueError, match="bounded scope"):
        list(app.iter_snapshot("owned/repo", "a" * 40))
