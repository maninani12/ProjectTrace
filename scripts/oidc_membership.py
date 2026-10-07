"""Operator-only explicit subject binding to an existing local member; no JIT or role elevation."""

import argparse
import os
from types import SimpleNamespace
from urllib.parse import urlsplit

from sqlalchemy import delete, select

from backend.db import OIDCSubject, Session, SessionToken, User
from backend.domain import audit, uid


def bind(db, email, issuer, subject, enabled=True):
    parsed = urlsplit(issuer)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.username
        or not 1 <= len(subject) <= 250
    ):
        raise ValueError("A configured HTTPS issuer and explicit subject are required.")
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user:
        raise ValueError("Create an approved local member first; no users or roles are provisioned by this command.")
    row = db.scalar(
        select(OIDCSubject).where(OIDCSubject.issuer == issuer, OIDCSubject.subject == subject).with_for_update()
    )
    if row and (row.user_id != user.id or row.organization_id != user.organization_id):
        raise ValueError("Subject belongs to a different member; reassignment is not automatic.")
    if not row:
        row = OIDCSubject(
            id=uid(),
            issuer=issuer,
            subject=subject,
            user_id=user.id,
            organization_id=user.organization_id,
            enabled=enabled,
        )
        db.add(row)
    row.enabled = enabled
    if not enabled:
        db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    audit(
        db,
        SimpleNamespace(organization_id=user.organization_id, email="operator-cli"),
        "OIDC_OPERATOR_BINDING",
        user.id,
        {"membership_id": row.id, "enabled": enabled, "issuer": issuer},
    )
    db.commit()
    return row.id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    with Session() as db:
        identity = bind(db, args.email, os.getenv("OIDC_ISSUER", ""), args.subject, not args.disable)
    print("Explicit OIDC membership updated: " + identity)
