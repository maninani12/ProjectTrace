import pytest

from integrations.github.connector import GitHubApp


def test_fetcher_rejects_arbitrary_url_before_authentication():
    app = GitHubApp("1", "unused", "1")
    with pytest.raises(ValueError):
        app.fetch_snapshot("https://169.254.169.254", "a" * 40)
    with pytest.raises(ValueError):
        app.fetch_snapshot("owner/repository", "../../metadata")


def test_advisory_check_stays_neutral(monkeypatch):
    import integrations.github.connector as connector

    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": 9}

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "https://api.github.com"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, path, **kwargs):
            calls.append(kwargs["json"])
            return Response()

    monkeypatch.setattr(connector.httpx, "Client", Client)
    monkeypatch.setattr(GitHubApp, "authenticate", lambda _: "synthetic-token")
    result = GitHubApp("1", "unused", "1").publish_check(
        "owner/repo", "a" * 40, {"overall": "REVIEW_REQUIRED", "results": []}
    )
    assert result == 9
    assert calls[0]["conclusion"] == "neutral"


def test_check_metadata_omits_source_backed_reasons(monkeypatch):
    import integrations.github.connector as connector

    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": 9}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, path, **kwargs):
            calls.append(kwargs["json"])
            return Response()

    monkeypatch.setattr(connector.httpx, "Client", Client)
    monkeypatch.setattr(GitHubApp, "authenticate", lambda _: "synthetic-token")
    GitHubApp("1", "unused", "1").publish_check(
        "owner/repo",
        "a" * 40,
        {
            "overall": "REVIEW_REQUIRED",
            "results": [
                {
                    "result": "REVIEW_REQUIRED",
                    "policy": "Review contradicted engineering claims",
                    "reason": "PRIVATE-SOURCE-CONTENT",
                }
            ],
        },
    )
    assert "PRIVATE-SOURCE-CONTENT" not in str(calls)


def test_provider_intake_keeps_unknown_language_and_encoding_diagnostics(monkeypatch):
    import base64

    import integrations.github.connector as connector

    class Response:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, path, **kwargs):
            if "/trees/" in path:
                return Response(
                    {
                        "tree": [
                            {"path": "app.go", "mode": "100644", "type": "blob", "size": 16, "sha": "b" * 40},
                            {"path": "image.bin", "mode": "100644", "type": "blob", "size": 2, "sha": "c" * 40},
                        ]
                    }
                )
            raw = b"package fixture\n" if path.endswith("b" * 40) else b"\xff\xfe"
            return Response({"encoding": "base64", "content": base64.b64encode(raw).decode()})

    monkeypatch.setattr(connector.httpx, "Client", Client)
    monkeypatch.setattr(GitHubApp, "authenticate", lambda _: "synthetic-token")
    files = GitHubApp("1", "unused", "1").fetch_snapshot("owner/repo", "a" * 40)
    assert "app.go" in files and files.intake[0]["path"] == "image.bin"
