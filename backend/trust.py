"""Enforced egress policy and tamper-evident audit, without enterprise claims."""

import hashlib
import hmac
import json
import os

from fastapi import HTTPException
from sqlalchemy import func, select, update

from analyzers.engine import redact
from backend.db import Audit, AuditHead, AuditLink, Organization, TenantPolicy, now

DEFAULT_POLICY = {
    "source_egress": "NO_EXTERNAL_SOURCE_EGRESS",
    "ai_mode": "DISABLED",
    "package_coordinate_advisories": False,
    "github_check_metadata": False,
    "maximum_exception_days": 90,
}


def policy(db, organization_id):
    row = db.get(TenantPolicy, organization_id)
    return {**DEFAULT_POLICY, **(row.data if row else {}), "version": row.version if row else 0}


def require_egress(db, organization_id, purpose):
    key = {"OSV": "package_coordinate_advisories", "GITHUB_CHECK": "github_check_metadata"}.get(purpose)
    if not key or not policy(db, organization_id).get(key):
        raise HTTPException(403, "Tenant egress policy does not authorize this external metadata transfer.")


def safe_data(value):
    if isinstance(value, dict):
        return {str(key): safe_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_data(item) for item in value]
    return redact(value) if isinstance(value, str) else value


def canonical(event, sequence, previous):
    return json.dumps(
        {
            "schema": "projecttrace-audit-chain-v1",
            "sequence": sequence,
            "previous": previous,
            "event": {
                key: getattr(event, key)
                for key in ("id", "organization_id", "repository_id", "actor", "action", "target", "data", "created_at")
            },
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def append_audit(db, user, action, target, data, repo=None):
    import uuid

    # A write before reading the head serializes SQLite and PostgreSQL appenders.
    db.execute(update(Organization).where(Organization.id == user.organization_id).values(name=Organization.name))
    head = db.scalar(
        select(AuditHead)
        .where(AuditHead.organization_id == user.organization_id)
        .execution_options(populate_existing=True)
    )
    if head is None:
        head = AuditHead(organization_id=user.organization_id, sequence=0, digest="0" * 64)
        db.add(head)
    event = Audit(
        id=str(uuid.uuid4()),
        organization_id=user.organization_id,
        repository_id=repo,
        actor=user.email,
        action=action,
        target=target,
        data=safe_data(data),
        created_at=now(),
    )
    db.add(event)
    db.flush()
    sequence, previous = head.sequence + 1, head.digest
    digest = hashlib.sha256(canonical(event, sequence, previous).encode()).hexdigest()
    db.add(
        AuditLink(
            event_id=event.id,
            organization_id=user.organization_id,
            sequence=sequence,
            previous_digest=previous,
            digest=digest,
        )
    )
    head.sequence, head.digest = sequence, digest
    db.flush()


def integrity(db, organization_id):
    connection = db.connection()
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")
    db.scalar(select(Organization).where(Organization.id == organization_id).with_for_update())
    links = db.execute(
        select(AuditLink, Audit)
        .outerjoin(Audit, Audit.id == AuditLink.event_id)
        .where(AuditLink.organization_id == organization_id)
        .order_by(AuditLink.sequence)
    ).yield_per(500)
    previous, sequence, failures = "0" * 64, 0, []
    for link, event in links:
        sequence += 1
        if (
            not event
            or event.organization_id != organization_id
            or link.sequence != sequence
            or link.previous_digest != previous
            or link.digest != hashlib.sha256(canonical(event, link.sequence, previous).encode()).hexdigest()
        ):
            failures.append(link.sequence)
        previous = link.digest
    head = db.scalar(
        select(AuditHead).where(AuditHead.organization_id == organization_id).execution_options(populate_existing=True)
    )
    if head and (head.sequence != sequence or head.digest != previous):
        failures.append("HEAD")
    total = db.scalar(select(func.count()).select_from(Audit).where(Audit.organization_id == organization_id))
    result = {
        "schema": "projecttrace-audit-chain-v1",
        "organization_id": organization_id,
        "state": "TAMPER_DETECTED" if failures else "VERIFIED" if sequence else "NOT_STARTED",
        "linked_events": sequence,
        "legacy_unlinked_events": total - sequence,
        "sequence": head.sequence if head else 0,
        "digest": head.digest if head else "0" * 64,
        "failures": failures,
        "verified_at": now(),
        "immutable_archive": False,
        "limitations": [
            "Legacy events are unlinked. Database administrators can rewrite an entire chain; retain a signed checkpoint outside this database."
        ],
    }
    key = os.getenv("AUDIT_CHECKPOINT_KEY", "")
    if len(key) >= 32:
        payload = json.dumps(
            {k: result[k] for k in ("schema", "organization_id", "sequence", "digest")},
            sort_keys=True,
            separators=(",", ":"),
        )
        result["checkpoint"] = {
            "payload": payload,
            "signature": hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest(),
            "algorithm": "HMAC-SHA256",
            "key_id": os.getenv("AUDIT_CHECKPOINT_KEY_ID", "operator-managed"),
        }
    else:
        result["checkpoint"] = None
    return result


def verify_checkpoint(db, organization_id, checkpoint):
    """Verify a separately retained signed head against the corresponding current chain link."""
    key = os.getenv("AUDIT_CHECKPOINT_KEY", "")
    key_id = os.getenv("AUDIT_CHECKPOINT_KEY_ID", "operator-managed")
    try:
        payload, signature = checkpoint["payload"], checkpoint["signature"]
        if (
            not isinstance(payload, str)
            or len(payload) > 4096
            or not isinstance(signature, str)
            or len(signature) != 64
        ):
            raise ValueError()
        expected = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if (
            len(key) < 32
            or checkpoint.get("algorithm") != "HMAC-SHA256"
            or checkpoint.get("key_id") != key_id
            or not hmac.compare_digest(expected, signature)
        ):
            raise ValueError()
        value = json.loads(payload)
        if (
            value.get("schema") != "projecttrace-audit-chain-v1"
            or value.get("organization_id") != organization_id
            or type(value.get("sequence")) is not int
            or value["sequence"] < 0
        ):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValueError("Checkpoint signature, key, schema or organization scope is invalid.") from None
    observed = (
        db.scalar(
            select(AuditLink.digest).where(
                AuditLink.organization_id == organization_id, AuditLink.sequence == value["sequence"]
            )
        )
        if value["sequence"]
        else "0" * 64
    )
    current = integrity(db, organization_id)
    matched = (
        observed == value.get("digest")
        and current["sequence"] >= value["sequence"]
        and current["state"] in {"VERIFIED", "NOT_STARTED"}
    )
    return {
        "state": "VERIFIED_AGAINST_RETAINED_CHECKPOINT" if matched else "CHECKPOINT_MISMATCH",
        "organization_id": organization_id,
        "checkpoint_sequence": value["sequence"],
        "current_sequence": current["sequence"],
        "immutable_archive": False,
    }
