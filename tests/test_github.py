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
