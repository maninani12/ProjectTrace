"""Pinned TCP destinations with original-host TLS verification and no proxy transport."""

import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit

import httpcore
import httpx

ERRORS = (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError, httpcore.UnsupportedProtocol)


class DestinationPolicyError(httpcore.ConnectError):
    failure_code = "DNS_ADDRESS_POLICY"


class DestinationResolutionError(httpcore.ConnectError):
    failure_code = "DNS_LOOKUP"


class ProviderTransportError(httpx.TransportError):
    """Sanitized transport category; no URL, headers, tokens or raw OS message."""
    def __init__(self, error):
        code, retryable = "NETWORK_TRANSPORT", True
        current = error
        for _ in range(8):
            if current is None:
                break
            if isinstance(current, DestinationPolicyError):
                code, retryable = "DNS_ADDRESS_POLICY", False
                break
            if isinstance(current, ssl.SSLCertVerificationError):
                code, retryable = "TLS_CERTIFICATE", False
                break
            if isinstance(current, httpcore.UnsupportedProtocol):
                code, retryable = "PROTOCOL_POLICY", False
                break
            if isinstance(current, DestinationResolutionError):
                code = "DNS_LOOKUP"
            elif isinstance(current, httpcore.TimeoutException):
                code = "NETWORK_TIMEOUT"
            elif isinstance(current, ssl.SSLError):
                code, retryable = "TLS_HANDSHAKE", False
            current = current.__cause__ or current.__context__
        super().__init__("Provider transport failed: " + code + ".")
        self.failure_code, self.retryable = code, retryable


def destination(url, allowed_hosts):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in allowed_hosts
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Destination must be an operator-approved HTTPS host without credentials/query/fragment.")
    return parsed.hostname.lower(), parsed.port or 443


class PinnedBackend(httpcore.SyncBackend):
    def __init__(self, host, port, private_cidrs=()):
        self.host, self.port = host, port
        self.private_cidrs = [ipaddress.ip_network(c, strict=True) for c in private_cidrs]
        self.delegate = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host.lower() != self.host or port != self.port:
            raise DestinationPolicyError("Destination scope mismatch.")
        try:
            resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            addresses = sorted({entry[4][0] for entry in resolved})
            if not addresses:
                raise ValueError()
            for value in addresses:
                address = ipaddress.ip_address(value)
                address = getattr(address, "ipv4_mapped", None) or address
                if address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
                    raise ValueError()
                if not address.is_global and not any(address in network for network in self.private_cidrs):
                    raise ValueError()
        except OSError:
            raise DestinationResolutionError("Destination DNS lookup failed.") from None
        except ValueError:
            raise DestinationPolicyError("Destination DNS/address policy rejected.") from None
        # The DNS name is never resolved again for this connection. httpcore keeps
        # the original URL host for TLS SNI and certificate hostname verification.
        deadline = time.monotonic() + (timeout if timeout is not None else 20)
        for address in addresses[:4]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise httpcore.ConnectTimeout("Approved destination connection budget expired.")
            try:
                return self.delegate.connect_tcp(address, port, remaining, local_address, socket_options)
            except (httpcore.NetworkError, httpcore.TimeoutException):
                if address == addresses[:4][-1]:
                    raise

    def connect_unix_socket(self, *args, **kwargs):
        raise httpcore.ConnectError("Unix sockets are not authorized for provider transport.")


class ResponseStream(httpx.SyncByteStream):
    def __init__(self, response, maximum=24 * 1024 * 1024):
        self.response = response
        self.maximum = maximum

    def __iter__(self):
        try:
            total = 0
            for chunk in self.response.iter_stream():
                total += len(chunk)
                if total > self.maximum:
                    raise ProviderResponseBudget(total, self.maximum)
                yield chunk
        except ERRORS as error:
            raise ProviderTransportError(error) from None

    def close(self):
        self.response.close()


class ProviderResponseBudget(httpx.TransportError):
    def __init__(self, actual, maximum):
        super().__init__("Provider response exceeds its configured transport budget.")
        self.actual, self.maximum = actual, maximum


class PinnedTransport(httpx.BaseTransport):
    def __init__(self, url, allowed_hosts, private_cidrs=(), ca_file=None, max_response_bytes=24 * 1024 * 1024):
        if not isinstance(max_response_bytes, int) or not 1 <= max_response_bytes <= 1_000_000_000:
            raise ValueError("Provider transport byte budget is outside supported bounds.")
        self.max_response_bytes = max_response_bytes
        self.host, self.port = destination(url, allowed_hosts)
        self.context = ssl.create_default_context(cafile=ca_file)
        self.pool = httpcore.ConnectionPool(
            ssl_context=self.context,
            network_backend=PinnedBackend(self.host, self.port, private_cidrs),
            max_connections=4,
            max_keepalive_connections=2,
            retries=0,
        )

    def handle_request(self, request):
        if (
            request.url.scheme != "https"
            or request.url.host.lower() != self.host
            or (request.url.port or 443) != self.port
        ):
            raise httpx.TransportError("Provider request escaped the configured destination.")
        try:
            response = self.pool.handle_request(
                httpcore.Request(
                    method=request.method,
                    url=httpcore.URL(
                        scheme=request.url.raw_scheme,
                        host=request.url.raw_host,
                        port=request.url.port,
                        target=request.url.raw_path,
                    ),
                    headers=request.headers.raw,
                    content=request.stream,
                    extensions=request.extensions,
                )
            )
        except ERRORS as error:
            raise ProviderTransportError(error) from None
        return httpx.Response(
            response.status, headers=response.headers, stream=ResponseStream(response, self.max_response_bytes), extensions=response.extensions
        )

    def close(self):
        self.pool.close()
