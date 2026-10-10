"""Admin-owned SCM metadata. Secret values remain in operator-owned references."""
import os
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import select

from backend.db import Record
from backend.domain import add, audit
from backend.governance import require_permission
from backend.security import authenticate
from integrations.secure_http import destination

router = APIRouter(prefix="/api/github/connections", tags=["GitHub Enterprise"])


class ConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str | None = Field(default=None, max_length=80)
    expected_version: int = Field(default=0, ge=0)
    provider_type: str = Field(pattern=r"^(GITHUB|GHES)$")
    label: str = Field(min_length=1, max_length=100)
    web_url: str = Field(max_length=500)
    api_base_url: str = Field(max_length=500)
    app_id: str = Field(pattern=r"^[0-9]{1,20}$")
    installation_id: str = Field(pattern=r"^[0-9]{1,20}$")
    private_key_ref: str = Field(pattern=r"^ENV:SCM_[A-Z0-9_]{1,80}$")
    webhook_secret_ref: str = Field(pattern=r"^ENV:SCM_[A-Z0-9_]{1,80}$")
    ca_bundle_ref: str | None = Field(default=None, pattern=r"^ENV:SCM_[A-Z0-9_]{1,80}$")
    api_version: str = Field(default="2022-11-28", pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    enabled: StrictBool = True


def approved_hosts():
    return {"github.com", "api.github.com"} | {
        h.strip().lower() for h in os.getenv("GHES_ALLOWED_HOSTS", "").split(",") if h.strip()
    }


def validate_metadata(data):
    web_host, web_port = destination(data["web_url"], approved_hosts())
    api_host, api_port = destination(data["api_base_url"], approved_hosts())
    web, api = urlsplit(data["web_url"]), urlsplit(data["api_base_url"])
    if data["provider_type"] == "GITHUB":
        if (
            data["web_url"].rstrip("/") != "https://github.com"
            or data["api_base_url"].rstrip("/") != "https://api.github.com"
        ):
            raise ValueError("GitHub.com requires its canonical public web and API origins.")
    elif web_host != api_host or web_port != api_port or web.path not in {"", "/"} or api.path.rstrip("/") != "/api/v3":
        raise ValueError("GHES web/API hosts must agree; the API base must end in /api/v3.")
    return data


def reference(value):
    if not value or not re.fullmatch(r"ENV:SCM_[A-Z0-9_]{1,80}", value):
        raise ValueError("SCM credential reference is invalid.")
    result = os.getenv(value[4:])
    if not result:
        raise ValueError("Operator SCM credential reference is unavailable.")
    return result


def private_cidrs():
    return [c.strip() for c in os.getenv("GHES_ALLOWED_PRIVATE_CIDRS", "").split(",") if c.strip()]


def authorized_connection(db, user, connection_id):
    row = db.get(Record, connection_id) if connection_id else None
    if not row or row.kind != "scm_connection" or row.organization_id != user.organization_id:
        raise HTTPException(404, "SCM connection unavailable in this organization.")
    return row


@router.get("")
def connections(request: Request):
    from backend.main import Session

    with Session() as db:
        user, _ = authenticate(db, request)
        require_permission(db,user,"organization.settings.manage")
        rows = db.scalars(
            select(Record)
            .where(Record.organization_id == user.organization_id, Record.kind == "scm_connection")
            .limit(101)
        ).all()
        return {
            "items": [{"id": r.id, "version": r.version, **r.data} for r in rows[:100]],
            "truncated": len(rows) > 100,
        }


@router.post("")
def configure(body: ConnectionBody, request: Request):
    from backend.main import Session

    with Session() as db:
        user, _ = authenticate(db, request, True)
        require_permission(db,user,"organization.settings.manage")
        row = authorized_connection(db, user, body.connection_id) if body.connection_id else None
        if body.expected_version != (row.version if row else 0):
            raise HTTPException(409, "SCM connection changed; refresh its version.")
        try:
            data = validate_metadata(body.model_dump(exclude={"connection_id", "expected_version"}))
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        if row and any(
            row.data.get(k) != data[k]
            for k in ("provider_type", "api_base_url", "web_url", "app_id", "installation_id")
        ):
            if db.scalar(
                select(Record.id)
                .where(
                    Record.organization_id == user.organization_id,
                    Record.kind == "repository_scm",
                    Record.data["connection_id"].as_string() == row.id,
                )
                .limit(1)
            ):
                raise HTTPException(
                    409, "Connected provider identity cannot be reassigned; configure a new SCM connection."
                )
        data.update(
            status="CONFIGURED_UNVERIFIED" if body.enabled else "DISABLED",
            live_verification="NOT_VERIFIED",
            owner_id=user.id,
        )
        if row:
            row.data = data
        else:
            row = add(db, user.organization_id, None, "scm_connection", data)
        db.flush()
        audit(db, user, "SCM_CONNECTION_CONFIGURED", row.id, {"version": row.version, **data})
        db.commit()
        return {"id": row.id, "version": row.version, **data}


@router.get("/{connection_id}/repositories")
def repositories(connection_id: str, request: Request):
    from backend.main import Session
    from workers.github import configured_app

    with Session() as db:
        user, _ = authenticate(db, request)
        require_permission(db,user,"organization.settings.manage")
        connection = authorized_connection(db, user, connection_id)
        try:
            rows = configured_app(connection).repositories()
        except Exception:
            raise HTTPException(
                503, "SCM credential, TLS or installation discovery failed; check operator configuration."
            ) from None
        return {
            "items": [{k: r.get(k) for k in ("id", "full_name", "name", "private")} for r in rows],
            "source": "AUTHORIZED_INSTALLATION_METADATA",
            "source_fetched": False,
        }
