"""Signed per-connection delivery; payload URLs never choose a transport destination."""

import json
import os
import re

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from analyzers.engine import hash_text, redact
from backend.db import Delivery, Record, User
from backend.domain import add, audit
from backend.scm_connections import reference
from integrations.github.connector import verify_signature

router = APIRouter(prefix="/api/github/webhook", tags=["GitHub Enterprise webhook"])


@router.post("/{connection_id}")
async def webhook(connection_id: str, request: Request):
    from backend.main import Session

    raw = await request.body()
    with Session() as db:
        connection = db.get(Record, connection_id)
        if not connection or connection.kind != "scm_connection":
            raise HTTPException(404, "SCM connection unavailable.")
        try:
            secret = reference(connection.data["webhook_secret_ref"])
        except ValueError:
            raise HTTPException(503, "SCM webhook credential reference is unavailable.") from None
        if not verify_signature(raw, request.headers.get("x-hub-signature-256", ""), secret):
            raise HTTPException(401, "SCM webhook signature is invalid.")
        try:
            payload = json.loads(raw)
            installation = str(payload.get("installation", {}).get("id", ""))
            if installation != connection.data["installation_id"]:
                raise ValueError()
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(422, "SCM webhook installation scope is invalid.") from None
        identifier = request.headers.get("x-github-delivery", "")
        if not identifier or len(identifier) > 100:
            raise HTTPException(422, "A bounded delivery identifier is required.")
        scoped_id = hash_text(connection.id + ":" + identifier)
        if db.get(Delivery, scoped_id):
            return {"status": "DUPLICATE"}
        event = request.headers.get("x-github-event", "")
        if event not in {"pull_request", "push", "ping", "installation", "installation_repositories"}:
            return {"status": "IGNORED"}
        db.add(Delivery(id=scoped_id, organization_id=connection.organization_id, event=event))
        actor = db.get(User, connection.data.get("owner_id"))
        if not actor or not actor.enabled or actor.organization_id != connection.organization_id:
            raise HTTPException(503, "SCM connection owner is unavailable.")
        try:
            if event == "installation" and payload.get("action") in {"deleted", "suspend"}:
                connection.data = {
                    **connection.data,
                    "enabled": False,
                    "status": "INSTALLATION_REMOVED",
                    "live_verification": "REVOKED",
                }
                audit(db, actor, "SCM_INSTALLATION_REVOKED", connection.id, {"action": payload["action"]})
                db.commit()
                return {"status": "REVOKED"}
            if not connection.data.get("enabled"):
                raise HTTPException(410, "SCM connection is disabled.")
            if event == "installation_repositories" and payload.get("action") == "removed":
                removed = {str(r.get("id")) for r in payload.get("repositories_removed", []) if isinstance(r, dict)}
                mappings = db.scalars(
                    select(Record).where(
                        Record.organization_id == connection.organization_id,
                        Record.kind == "repository_scm",
                        Record.data["connection_id"].as_string() == connection.id,
                    )
                )
                for mapping in mappings:
                    if mapping.data.get("provider_repository_id") in removed:
                        mapping.data = {
                            **mapping.data,
                            "enabled": False,
                            "revocation": "INSTALLATION_PERMISSION_REMOVED",
                        }
                        audit(
                            db,
                            actor,
                            "SCM_REPOSITORY_ACCESS_REVOKED",
                            mapping.repository_id,
                            {"connection_id": connection.id},
                            mapping.repository_id,
                        )
            if event in {"ping", "installation", "installation_repositories"}:
                audit(db, actor, "SCM_DELIVERY_RECEIVED", connection.id, {"event": event, "delivery_id": identifier})
                db.commit()
                return {"status": "RECEIVED", "analysis": "NOT_APPLICABLE"}
            if event == "pull_request" and payload.get("action") not in {
                "opened",
                "reopened",
                "synchronize",
                "ready_for_review",
            }:
                db.commit()
                return {"status": "IGNORED"}
            provider_repository_id = str(payload.get("repository", {}).get("id", ""))
            mapping = db.scalar(
                select(Record).where(
                    Record.organization_id == connection.organization_id,
                    Record.kind == "repository_scm",
                    Record.data["connection_id"].as_string() == connection.id,
                    Record.data["provider_repository_id"].as_string() == provider_repository_id,
                )
            )
            if not mapping:
                raise HTTPException(404, "Webhook repository is outside this SCM connection.")
            if not mapping.data.get("enabled", True):
                raise HTTPException(410, "SCM repository permission is revoked.")
            change = payload.get("pull_request", {}) if event == "pull_request" else {}
            head = change.get("head", {}).get("sha") if change else payload.get("after")
            base = change.get("base", {}).get("sha") if change else None
            if (
                not isinstance(head, str)
                or not re.fullmatch(r"[0-9a-f]{40}", head)
                or (base and (not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40}", base)))
            ):
                raise HTTPException(422, "Webhook commit scope is invalid.")
            fork = bool(
                change and change.get("head", {}).get("repo", {}).get("id") not in {None, int(provider_repository_id)}
            )
            number = change.get("number") if change else None
            if number is not None and (type(number) is not int or not 1 <= number <= 100000000):
                raise HTTPException(422, "Webhook PR identifier is invalid.")
            job_details = {
                "head_sha": head,
                "base_sha": base,
                "pr_number": number,
                "pr_title": redact(str(change.get("title", "")))[:250],
                "branch": str(change.get("head", {}).get("ref", "main") if change else payload.get("ref", "main"))[
                    :120
                ],
            }
            if not fork:
                from backend.db import Repository
                from backend.scheduling import enqueue_scm

                repository = db.get(Repository, mapping.repository_id)
                try:
                    job = enqueue_scm(
                        db,
                        repository,
                        job_details,
                        event=event,
                        delivery_id=identifier,
                        connection_id=connection.id,
                        actor=actor,
                    )
                except ValueError:
                    raise HTTPException(
                        429, "SCM analysis admission quota reached; retry this delivery later."
                    ) from None
            else:
                job = add(
                    db,
                    connection.organization_id,
                    mapping.repository_id,
                    "job",
                    {
                        "state": "PARTIAL" if fork else "QUEUED",
                        "event": event,
                        "delivery_id": identifier,
                        "connection_id": connection.id,
                        "repository_id": mapping.repository_id,
                        "provider_fetch": "FORK_HEAD_SCOPE_UNSUPPORTED" if fork else "PENDING_CONFIGURATION",
                        "reason": "Fork source is not automatically fetched outside the installed repository scope."
                        if fork
                        else "Awaiting provider worker",
                        "head_sha": head,
                        "base_sha": base,
                        "pr_number": number,
                        "pr_title": redact(str(change.get("title", "")))[:250],
                        "branch": str(
                            change.get("head", {}).get("ref", "main") if change else payload.get("ref", "main")
                        )[:120],
                    },
                )
            audit(
                db,
                actor,
                "SCM_DELIVERY_RECEIVED",
                job.id,
                {"event": event, "connection_id": connection.id},
                mapping.repository_id,
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"status": "DUPLICATE"}
        except (AttributeError, TypeError, ValueError):
            raise HTTPException(422, "SCM webhook change payload is invalid.") from None
        if not fork and os.getenv("JOB_MODE") == "celery":
            from backend.queue import dispatch

            dispatch(db, job)
        return {"status": "RECEIVED", "analysis": "PARTIAL" if fork else "QUEUED", "check_published": False}
