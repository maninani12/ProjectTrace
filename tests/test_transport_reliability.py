import socket
import ssl
from types import SimpleNamespace

import httpcore
import httpx
import pytest

from integrations.github.connector import GitHubApp
from integrations.secure_http import DestinationPolicyError, PinnedBackend, ProviderTransportError


def test_only_verified_public_addresses_are_tried_with_one_total_connect_budget(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("1.1.1.1", 443))])
    calls = []
    def connect(address, port, timeout, *args):
        calls.append((address, timeout))
        if len(calls) == 1:
            raise httpcore.ConnectError("Synthetic unreachable first address")
        return "connected"
    backend = PinnedBackend("api.github.com", 443)
    backend.delegate = SimpleNamespace(connect_tcp=connect)
    assert backend.connect_tcp("api.github.com", 443, timeout=2) == "connected"
    assert [r[0] for r in calls] == ["1.1.1.1", "8.8.8.8"]
    assert 0 < calls[1][1] <= calls[0][1] <= 2
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(DestinationPolicyError):
        backend.connect_tcp("api.github.com", 443, timeout=2)
    assert len(calls) == 2


def test_token_retry_is_bounded_and_policy_failures_are_never_retried(monkeypatch):
    app = GitHubApp("1", "synthetic-key", "2")
    monkeypatch.setattr("integrations.github.connector.jwt.encode", lambda *a, **kw: "synthetic-assertion")
    monkeypatch.setattr("integrations.github.connector.time.sleep", lambda _: None)
    calls = []
    failure = [ProviderTransportError(httpcore.ConnectTimeout("Synthetic transient timeout"))]
    def handler(request):
        calls.append(request.url.path)
        if failure:
            raise failure.pop()
        return httpx.Response(200, json={"token": "synthetic-token"})
    monkeypatch.setattr(app, "client", lambda: httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    assert app.authenticate() == "synthetic-token" and len(calls) == 2
    failure.extend([ProviderTransportError(DestinationPolicyError("private IP"))])
    with pytest.raises(ProviderTransportError) as rejected:
        app.authenticate()
    assert rejected.value.failure_code == "DNS_ADDRESS_POLICY" and len(calls) == 3
    assert "private IP" not in str(rejected.value)
    certificate = ProviderTransportError(ssl.SSLCertVerificationError("untrusted certificate"))
    assert certificate.failure_code == "TLS_CERTIFICATE" and not certificate.retryable
