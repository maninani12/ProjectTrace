"""Signed ping regression and installation-scope guards for per-connection delivery."""

import hashlib
import hmac
import json
import secrets

import pytest
from sqlalchemy import select

from backend import main
from backend.db import Audit, Delivery, Record, User
from tests.test_ghes import connected


@pytest.fixture
def webhook_connection(client, monkeypatch):
    saved, repository = connected(client, monkeypatch)
    secret = secrets.token_bytes(32).hex().encode()
    monkeypatch.setenv("SCM_FIXTURE_WEBHOOK", secret.decode())
    return saved["id"], repository, secret


def send(client, connection, payload, *, event="ping", delivery="regression", signature=None):
    identifier, _, secret = connection
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = {
        "x-github-event": event,
        "x-hub-signature-256": signature or "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest(),
    }
    if delivery is not None:
        headers["x-github-delivery"] = delivery
    return client.post("/api/github/webhook/" + identifier, content=raw, headers=headers)


def test_signed_ping_without_installation_is_audited_and_deduplicated(client, webhook_connection):
    payload = {"zen": "projecttrace-real-ping-shape-test"}
    response = send(client, webhook_connection, payload)
    assert response.status_code == 200
    assert response.json() == {"status": "RECEIVED", "analysis": "NOT_APPLICABLE"}
    assert send(client, webhook_connection, payload).json() == {"status": "DUPLICATE"}
    with main.Session() as db:
        assert len(list(db.scalars(select(Delivery).where(Delivery.event == "ping")))) == 1
        assert db.scalar(select(Audit).where(Audit.action == "SCM_DELIVERY_RECEIVED", Audit.target == webhook_connection[0]))
        assert db.scalar(select(Record).where(Record.kind == "job", Record.repository_id == webhook_connection[1])) is None


def test_ping_signature_is_checked_before_payload_or_delivery(client, webhook_connection):
    response = send(client, webhook_connection, b"{", delivery=None, signature="sha256=" + "0" * 64)
    assert response.status_code == 401


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_repository_events_with_correct_installation_enqueue(client, webhook_connection, event):
    payload = {"installation": {"id": 2}, "repository": {"id": 7}, "after": "a" * 40}
    if event == "pull_request":
        payload.update(action="opened", pull_request={
            "number": 1, "head": {"sha": "a" * 40, "repo": {"id": 7}}, "base": {"sha": "b" * 40},
        })
    response = send(client, webhook_connection, payload, event=event)
    assert response.status_code == 200
    assert response.json()["analysis"] == "QUEUED"
    with main.Session() as db:
        job = db.scalar(select(Record).where(Record.kind == "job", Record.repository_id == webhook_connection[1]))
        assert job.data["connection_id"] == webhook_connection[0]
        assert job.data["head_sha"] == "a" * 40


@pytest.mark.parametrize("event", ["push", "pull_request", "installation", "installation_repositories", "unsupported"])
@pytest.mark.parametrize("installation", [None, {"id": 999999999}])
def test_every_non_ping_event_requires_exact_installation(client, webhook_connection, event, installation):
    payload = {"repository": {"id": 7}, "after": "a" * 40, "action": "deleted"}
    if installation is not None:
        payload["installation"] = installation
    response = send(client, webhook_connection, payload, event=event)
    assert response.status_code == 422
    assert response.json()["detail"] == "SCM webhook installation scope is invalid."
    with main.Session() as db:
        assert db.get(Record, webhook_connection[0]).data["enabled"] is True
        assert db.scalar(select(Delivery)) is None


@pytest.mark.parametrize("raw", [b"{", b"[]", b"null", b'"text"', b"42", b"\xff"])
def test_ping_rejects_malformed_or_non_object_json(client, webhook_connection, raw):
    response = send(client, webhook_connection, raw)
    assert response.status_code == 422
    assert response.json()["detail"] == "SCM webhook payload is invalid."


@pytest.mark.parametrize("delivery", [None, "", "a" * 101])
def test_ping_requires_bounded_delivery(client, webhook_connection, delivery):
    response = send(client, webhook_connection, {}, delivery=delivery)
    assert response.status_code == 422
    assert response.json()["detail"] == "A bounded delivery identifier is required."


def test_delivery_boundary_and_replay_cannot_bypass_non_ping_scope(client, webhook_connection):
    delivery = "a" * 100
    assert send(client, webhook_connection, {}, delivery=delivery).status_code == 200
    assert send(client, webhook_connection, {}, delivery=delivery).json()["status"] == "DUPLICATE"
    assert send(client, webhook_connection, {}, event="push", delivery=delivery).status_code == 422


def test_unsupported_scoped_event_is_ignored(client, webhook_connection):
    response = send(client, webhook_connection, {"installation": {"id": 2}}, event="unsupported")
    assert response.status_code == 200
    assert response.json() == {"status": "IGNORED"}
    with main.Session() as db:
        assert db.scalar(select(Delivery)) is None


@pytest.mark.parametrize("unavailable", ["connection", "owner", "owner_tenant"])
def test_signed_ping_preserves_connection_and_owner_authorization(client, webhook_connection, unavailable):
    with main.Session() as db:
        connection = db.get(Record, webhook_connection[0])
        if unavailable == "connection":
            connection.data = {**connection.data, "enabled": False}
        elif unavailable == "owner_tenant":
            connection.data = {**connection.data, "owner_id": "outsider"}
        else:
            actor = db.get(User, connection.data["owner_id"])
            actor.enabled = False
        db.commit()
    response = send(client, webhook_connection, {})
    assert response.status_code == (410 if unavailable == "connection" else 503)
    with main.Session() as db:
        assert db.scalar(select(Delivery)) is None
