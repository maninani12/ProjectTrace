"""External evidence normalization, deliberately separate from native results."""

from typing import Protocol

from analyzers.engine import hash_text, redact


class Connector(Protocol):
    def authenticate(self): ...
    def test_connection(self): ...
    def sync(self): ...
    def normalize(self, payload): ...
    def get_health(self): ...


def normalize(provider, payload):
    required = {"id", "path", "line", "rule", "severity", "title"}
    if not required <= payload.keys() or payload["severity"] not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        raise ValueError("External evidence does not match the normalization contract.")
    return {
        **{k: payload[k] for k in required},
        "title": redact(payload["title"]),
        "provider": provider,
        "provider_id": payload["id"],
        "fingerprint": hash_text(f"{payload['rule']}:{payload['path']}:{payload['line']}"),
        "source": "EXTERNAL_TOOL",
        "provider_timestamp": payload.get("timestamp"),
        "reference": payload.get("reference"),
    }
