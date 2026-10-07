import json
import logging
import math
import os
import re
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError

from analyzers.engine import MAX_TOTAL_BYTES, read_zip, redact, sbom
from backend import rate_limit
from backend.db import Audit, Delivery, Grant, Organization, Record, Repository, Session, User, now
from backend.domain import add, audit, policy_gate, uid
from backend.engineering_changes import router as engineering_router
from backend.finding_api import router as finding_router
from backend.graph_api import router as graph_router
from backend.jobs import execute_analysis
from backend.oidc import router as oidc_router
from backend.quality_api import router as quality_router
from backend.scm_connections import router as scm_router
from backend.scm_webhook import router as scm_webhook_router
from backend.security import allowed_repositories, authenticate, create_session, passwords, require_repo
from backend.trust_api import router as trust_router

APP_ENV = os.getenv("APP_ENV", "demo")
PRODUCTION = APP_ENV == "production"
ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5181,http://127.0.0.1:5181,http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8011",
).split(",")
if PRODUCTION and (
    "*" in ORIGINS or not os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg://"))
):
    raise RuntimeError("Production requires PostgreSQL and explicit CORS origins.")
if PRODUCTION and (
    os.getenv("JOB_MODE") != "celery" or not os.getenv("REDIS_URL") or not os.getenv("ANALYSIS_INPUT_KEY")
):
    raise RuntimeError("Production requires Celery, Redis and an encrypted analysis input key.")
log = logging.getLogger("projecttrace")


@asynccontextmanager
async def lifespan(app):
    with Session() as db:
        db.execute(text("SELECT 1"))
        db.execute(select(Organization.id).limit(1))
    yield


app = FastAPI(
    title="ProjectTrace",
    version="1.6.0",
    lifespan=lifespan,
    docs_url=None if PRODUCTION else "/api/docs",
    openapi_url=None if PRODUCTION else "/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
rate_windows = rate_limit.windows


@app.middleware("http")
async def security_boundary(request, call_next):
    started = time.perf_counter()
    request_id = uid()
    request.state.request_id = request_id
    streaming_archive = request.method == "POST" and (
        request.url.path == "/api/archive/stream/import"
        or re.fullmatch(r"/api/repositories/[^/]+/source-archive", request.url.path) is not None
    )
    if streaming_archive:
        from backend.repository_store import limits

        body_limit = limits()["archive_bytes"]
    else:
        body_limit = MAX_TOTAL_BYTES + 100_000
    content_length = request.headers.get("content-length", "")
    if content_length and (not content_length.isdigit() or int(content_length) > body_limit):
        return Response("Request exceeds the configured body limit.", status_code=413)
    # Bound streamed bodies too, before JSON/multipart parsing.
    if request.method == "POST" and not streaming_archive:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_TOTAL_BYTES + 100_000:
                return Response("Request exceeds the configured body limit.", status_code=413)
        request._body = bytes(body)
    if request.method == "POST" and not (
        request.url.path == "/api/github/webhook" or request.url.path.startswith("/api/github/webhook/")
    ):
        if request.headers.get("origin") not in ORIGINS:
            return Response("Origin is not authorized.", status_code=403)
    try:
        permitted = rate_limit.allow(
            request.client.host if request.client else "unknown",
            rate_limit.bucket(request.url.path, request.method),
            distributed=PRODUCTION,
        )
    except Exception:
        return Response("Rate limit service unavailable.", status_code=503, headers={"Retry-After": "10"})
    if not permitted:
        return Response("Rate limit reached. Try again in one minute.", status_code=429, headers={"Retry-After": "60"})
    response = await call_next(request)
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
        }
    )
    if PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    log.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
    )
    return response


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class Register(StrictModel):
    email: str = Field(min_length=5, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=16, max_length=200)
    organization: str = Field(min_length=1, max_length=120)


class Import(StrictModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[\w .-]+$")
    system: str = Field(default="Imported System", min_length=1, max_length=120)
    owner: str = Field(default="Engineering Team", min_length=1, max_length=120)
    files: dict[str, str]


class Analyze(StrictModel):
    files: dict[str, str]
    branch: str = Field(default="main", max_length=120)
    base_id: str | None = None


class Review(StrictModel):
    action: Literal[
        "CONFIRM",
        "FALSE_POSITIVE",
        "ACCEPT_RISK",
        "REQUEST_MORE_EVIDENCE",
        "ASSIGN",
        "RESOLVE",
        "CREATE_EXCEPTION",
        "IN_REVIEW",
        "REOPEN",
    ]
    reason: str = Field(min_length=10, max_length=2000)
    owner: str | None = Field(default=None, max_length=120)
    expires_days: int = Field(default=7, ge=1, le=90)
    expected_version: int


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=1000)
    repository_id: str | None = None


class AWSInventoryBody(StrictModel):
    repository_id: str
    account_id: str = Field(pattern=r"^[0-9]{12}$")
    region: str = Field(default="us-east-1", pattern=r"^[a-z]{2}(?:-[a-z]+)+-\d$")


class NativeProfileBody(StrictModel):
    repository_id: str | None = None
    version: int | None = None
    rules: dict = Field(default_factory=dict)
    licenses: dict[str, list[str]] = Field(default_factory=dict)
    gate_scope: Literal["ALL_FINDINGS", "NEW_FINDINGS"] = "ALL_FINDINGS"
    infrastructure: dict | None = None


class ConnectGitHub(StrictModel):
    repository_id: int = Field(gt=0)
    system: str = Field(min_length=1, max_length=120)
    owner: str = Field(min_length=1, max_length=120)
    checks_enabled: bool = False
    connection_id: str | None = Field(default=None, max_length=80)


def packed(record):
    return {
        "id": record.id,
        "kind": record.kind,
        "repository_id": record.repository_id,
        "version": record.version,
        "created_at": record.created_at,
        **record.data,
    }


def snapshot_preview(snapshot):
    value = packed(snapshot)
    for key in (
        "analysis_cache",
        "verification_cache",
        "hashes",
        "claims",
        "findings",
        "quality_metrics",
        "analysis_coverage",
    ):
        value.pop(key, None)
    value["changed_file_count"] = len(value.get("changed_files", []))
    value["changed_files"] = value.get("changed_files", [])[:500]
    value["metadata_preview"] = True
    if isinstance(value.get("impact"), dict):
        value["impact"] = {
            key: entry[:500] if isinstance(entry, list) else entry for key, entry in value["impact"].items()
        }
    return value


def scope_query(db, user, model=Record):
    ids = [r.id for r in allowed_repositories(db, user)]
    query = select(model).where(
        model.organization_id == user.organization_id, or_(model.repository_id.is_(None), model.repository_id.in_(ids))
    )
    if model is Record and user.role not in {"ORG_OWNER", "ADMIN"}:
        query = query.where(Record.kind.not_in(["scm_connection", "oidc_provider", "oidc_provider_version"]))
    return query


def authorized_record(db, user, record_id):
    record = db.get(Record, record_id)
    if not record or record.organization_id != user.organization_id:
        raise HTTPException(404, "Record not available in your authorized scope.")
    if record.kind in {"scm_connection", "oidc_provider", "oidc_provider_version"} and user.role not in {
        "ORG_OWNER",
        "ADMIN",
    }:
        raise HTTPException(404, "Record not available in your authorized scope.")
    if record.repository_id:
        require_repo(db, user, record.repository_id)
    return record


def current_snapshots(db, user):
    ranked = (
        scope_query(db, user)
        .where(Record.kind == "snapshot")
        .with_only_columns(
            Record.id,
            func.row_number()
            .over(partition_by=Record.repository_id, order_by=(Record.created_at.desc(), Record.id.desc()))
            .label("position"),
        )
        .subquery()
    )
    return {
        row.repository_id: row
        for row in db.scalars(select(Record).join(ranked, ranked.c.id == Record.id).where(ranked.c.position == 1))
    }


def workspace_snapshots(db, user):
    from types import SimpleNamespace

    ranked = (
        scope_query(db, user)
        .where(Record.kind == "snapshot")
        .with_only_columns(
            Record.id,
            func.row_number()
            .over(partition_by=Record.repository_id, order_by=(Record.created_at.desc(), Record.id.desc()))
            .label("position"),
        )
        .subquery()
    )
    fields = [
        "branch",
        "commit",
        "scope",
        "status",
        "file_count",
        "gate",
        "changed_files",
        "engines",
        "impact",
        "reused_files",
        "analyzer_version",
        "base_id",
        "warnings",
        "claim_extraction",
        "commit_source",
        "analyzer_results",
        "parser_signature",
        "analysis_at",
        "source_storage",
    ]
    query = (
        select(
            Record.id,
            Record.repository_id,
            Record.version,
            Record.created_at,
            *(Record.data[key].label(key) for key in fields),
        )
        .join(ranked, ranked.c.id == Record.id)
        .where(ranked.c.position == 1)
    )
    return {
        row.repository_id: SimpleNamespace(
            id=row.id,
            kind="snapshot",
            repository_id=row.repository_id,
            version=row.version,
            created_at=row.created_at,
            data={key: row._mapping[key] for key in fields if row._mapping[key] is not None},
        )
        for row in db.execute(query)
    }


def queued_input(db, user, repo, content, request, *, source="FILES", **options):
    if os.getenv("JOB_MODE") != "celery":
        return None
    from backend.queue import enqueue_analysis

    job = enqueue_analysis(db, user, repo, content, source=source, request_id=request.state.request_id, **options)
    return JSONResponse(
        status_code=202,
        content={
            "repository_id": repo.id,
            "snapshot_id": None,
            "job_id": job.id,
            "state": "QUEUED",
            "dispatch": job.data["dispatch"],
        },
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/ready")
def ready():
    try:
        with Session() as db:
            db.execute(select(Organization.id).limit(1))
            if PRODUCTION:
                from backend.schema_version import expected_head
                revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
                if revision != expected_head():
                    raise ValueError("Migration head mismatch")
        if PRODUCTION:
            import redis
            client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=2, socket_connect_timeout=2)
            try:
                client.ping()
            finally:
                client.close()
        return {"status": "ready", "database": "reachable", "worker": "not_checked"}
    except Exception:
        raise HTTPException(503, "Database or migrations are not ready.")


@app.post("/api/auth/demo")
def demo(request: Request, response: Response):
    if APP_ENV != "demo":
        raise HTTPException(404, "Demo login is disabled in this environment.")
    with Session() as db:
        user = db.get(User, "demo-engineer")
        if not user:
            raise HTTPException(503, "Run the demo seed command before opening the demo.")
        csrf = create_session(db, user, response, previous_token=request.cookies.get("pt_session"))
        db.commit()
        return {"csrf": csrf, "email": user.email, "role": user.role, "demo": True}


@app.get("/api/auth/options")
def auth_options(request: Request):
    """Public navigation flags only; no tenant, account, session or source metadata."""
    with Session() as db:
        authenticated = False
        if request.cookies.get("pt_session"):
            try:
                authenticate(db, request)
                authenticated = True
            except HTTPException as error:
                if error.status_code not in (401, 403):
                    raise
        return {
            "authenticated": authenticated,
            "local_registration": not PRODUCTION,
            "demo_available": APP_ENV == "demo" and db.get(User, "demo-engineer") is not None,
        }


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    with Session() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower()))
        try:
            if (
                not user
                or not user.enabled
                or not user.local_login_allowed
                or not passwords.verify(user.password_hash, body.password)
            ):
                raise ValueError()
        except Exception:
            raise HTTPException(401, "Email or password is incorrect.")
        csrf = create_session(db, user, response, PRODUCTION, previous_token=request.cookies.get("pt_session"))
        db.commit()
        return {
            "csrf": csrf,
            "email": user.email,
            "role": user.role,
            "demo": APP_ENV == "demo" and user.organization_id == "northstar",
        }


@app.post("/api/auth/register")
def register(body: Register, request: Request, response: Response):
    if PRODUCTION:
        raise HTTPException(404, "Self-service local registration is disabled in production.")
    with Session() as db:
        if db.scalar(select(User).where(User.email == body.email.lower())):
            raise HTTPException(409, "This local email is already registered.")
        organization = Organization(id=uid(), name=body.organization)
        db.add(organization)
        db.flush()
        user = User(
            id=uid(),
            organization_id=organization.id,
            email=body.email.lower(),
            password_hash=passwords.hash(body.password),
            role="ORG_OWNER",
        )
        db.add(user)
        db.flush()
        audit(db, user, "WORKSPACE_CREATED", organization.id, {})
        csrf = create_session(db, user, response)
        db.commit()
        return {"email": user.email, "role": user.role, "csrf": csrf, "organization": organization.name, "demo": False}


@app.get("/api/auth/me")
def me(request: Request):
    with Session() as db:
        user, session = authenticate(db, request)
        return {
            "email": user.email,
            "role": user.role,
            "csrf": session.csrf,
            "organization": db.get(Organization, user.organization_id).name,
            "demo": APP_ENV == "demo" and user.organization_id == "northstar",
        }


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    with Session() as db:
        _, session = authenticate(db, request, True, edit=False)
        db.delete(session)
        db.commit()
        response.delete_cookie("pt_session", path="/")
    return {"status": "signed_out"}


@app.get("/api/workspace")
def workspace(request: Request, repository_id: str | None = None, summary: bool = False):
    with Session() as db:
        user, _ = authenticate(db, request)
        repos = allowed_repositories(db, user)
        if repository_id:
            require_repo(db, user, repository_id)
            repos = [repo for repo in repos if repo.id == repository_id]
        snapshots = workspace_snapshots(db, user)
        snapshots = {rid: snapshot for rid, snapshot in snapshots.items() if rid in {repo.id for repo in repos}}
        if summary:
            return {
                "organization": db.get(Organization, user.organization_id).name,
                "demo": APP_ENV == "demo" and user.organization_id == "northstar",
                "analysis": {
                    "state": "COMPLETED" if snapshots else "NO_REPOSITORY",
                    "truncated": False,
                    "warnings": [],
                },
                "repositories": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "system": r.system,
                        "component": r.component,
                        "owner": r.owner,
                        "provider": r.provider,
                        "snapshot": {
                            "id": snapshots[r.id].id,
                            **{
                                k: snapshots[r.id].data.get(k)
                                for k in ["branch", "commit", "scope", "status", "file_count", "gate", "changed_files"]
                            },
                        }
                        if r.id in snapshots
                        else None,
                    }
                    for r in repos
                ],
                **{
                    k: []
                    for k in [
                        "claim",
                        "finding",
                        "evidence",
                        "edge",
                        "dependency",
                        "drift",
                        "pr",
                        "review",
                        "exception",
                        "job",
                        "graph_node",
                        "risk_path",
                    ]
                },
                "limitations": ["Quality uses authorized paginated projections and lazy source inspection."],
            }
        snapshot_ids = {s.id for s in snapshots.values()}
        query = scope_query(db, user).where(
            or_(
                Record.kind.in_(["job", "integration", "policy"]),
                Record.data["scope"]["snapshot_id"].as_string().in_(snapshot_ids),
                Record.data["snapshot_id"].as_string().in_(snapshot_ids),
            )
        )
        if repository_id:
            query = query.where(or_(Record.repository_id == repository_id, Record.repository_id.is_(None)))
        records = list(db.scalars(query.order_by(Record.created_at.desc()).limit(5001)))
        truncated = len(records) > 5000
        records = records[:5000]
        snapshot_ids = {s.id for s in snapshots.values()}
        current = [
            r
            for r in records
            if r.data.get("scope", {}).get("snapshot_id") in snapshot_ids
            or r.data.get("snapshot_id") in snapshot_ids
            or r.kind in {"pr", "review", "exception", "job", "integration", "policy"}
        ]
        grouped = {
            kind: [
                {
                    key: value
                    for key, value in packed(r).items()
                    if not (kind == "evidence" and key in {"source", "source_blob_digest"})
                }
                for r in current
                if r.kind == kind
            ]
            for kind in [
                "claim",
                "finding",
                "evidence",
                "edge",
                "dependency",
                "drift",
                "pr",
                "review",
                "exception",
                "job",
                "graph_node",
                "risk_path",
            ]
        }
        latest_jobs = {}
        for record in records:
            if record.kind == "job":
                latest_jobs.setdefault(record.repository_id, packed(record))
        states = []
        for r in repos:
            job = latest_jobs.get(r.id, {})
            snapshot_state = snapshots[r.id].data["status"] if r.id in snapshots else "READY"
            state = job.get("state") or snapshot_state
            if (
                job.get("type") == "ADVISORIES"
                and state in {"COMPLETED", "COMPLETED_NO_FINDINGS"}
                and snapshot_state == "PARTIAL"
            ):
                state = "PARTIAL"
            states.append(state)
        state = (
            "NO_REPOSITORY"
            if not repos
            else "PARTIAL"
            if truncated
            else next(
                (
                    s
                    for s in [
                        "FAILED",
                        "PARTIAL",
                        "FETCHING",
                        "VALIDATING",
                        "PARSING",
                        "ANALYZING",
                        "BUILDING_EVIDENCE",
                        "EXTRACTING_CLAIMS",
                        "VERIFYING",
                        "CORRELATING",
                        "FINALIZING",
                        "QUEUED",
                        "READY",
                        "CANCELLED",
                    ]
                    if s in states
                ),
                "COMPLETED" if "COMPLETED" in states else "COMPLETED_NO_FINDINGS",
            )
        )
        return {
            "organization": db.get(Organization, user.organization_id).name,
            "capabilities": {
                "job_mode": os.getenv("JOB_MODE", "sync"),
                "advisories_enabled": os.getenv("JOB_MODE") == "celery" and os.getenv("OSV_ENABLED") == "1",
            },
            "demo": APP_ENV == "demo" and user.organization_id == "northstar",
            "analysis": {
                "state": state,
                "truncated": truncated,
                "warnings": ["Workspace result limit reached; select a repository or use paginated records."]
                if truncated
                else [],
            },
            "repositories": [
                {
                    "id": r.id,
                    "name": r.name,
                    "system": r.system,
                    "component": r.component,
                    "owner": r.owner,
                    "provider": r.provider,
                    "snapshot": snapshot_preview(snapshots[r.id]) if r.id in snapshots else None,
                    "latest_job": latest_jobs.get(r.id),
                }
                for r in repos
            ],
            **grouped,
            "limitations": ["Static analysis scope only.", "External AI and live cloud inventory are not configured."],
        }


@app.get("/api/records/{kind}")
def records(kind: str, request: Request, offset: int = 0, limit: int = 100):
    with Session() as db:
        user, _ = authenticate(db, request)
        result = db.scalars(
            scope_query(db, user)
            .where(Record.kind == kind)
            .order_by(Record.created_at.desc())
            .offset(max(0, offset))
            .limit(min(max(1, limit), 200))
        )
        return [packed(r) for r in result]


@app.get("/api/record/{record_id}")
def record(record_id: str, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request)
        item = authorized_record(db, user, record_id)
        result = packed(item)
        if item.kind == "evidence" and item.data.get("source_blob_digest"):
            from backend.repository_store import BlobStore

            try:
                result["source"] = (
                    BlobStore().read(user.organization_id, item.data["source_blob_digest"]).decode("utf-8")
                )
            except ValueError:
                raise HTTPException(503, "Encrypted evidence source is unavailable or failed its integrity check.")
        return result


@app.get("/api/audit")
def events(request: Request, offset: int = 0, limit: int = 100, repository_id: str | None = None):
    with Session() as db:
        user, _ = authenticate(db, request)
        query = scope_query(db, user, Audit)
        if repository_id:
            require_repo(db, user, repository_id)
            query = query.where(Audit.repository_id == repository_id)
        result = db.scalars(
            query.order_by(Audit.created_at.desc()).offset(max(0, offset)).limit(min(max(1, limit), 200))
        )
        return [
            {
                "id": a.id,
                "actor": a.actor,
                "action": a.action,
                "target": a.target,
                "data": a.data,
                "repository_id": a.repository_id,
                "created_at": a.created_at,
            }
            for a in result
        ]


@app.post("/api/import")
def import_repo(body: Import, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        if user.organization_id == "northstar":
            raise HTTPException(
                409, "Sign in to your real organization workspace to import source; demo data remains separate."
            )
        if len(allowed_repositories(db, user)) >= 20:
            raise HTTPException(429, "Local workspace repository quota (20) reached.")
        repo = Repository(
            id=uid(),
            organization_id=user.organization_id,
            name=body.name,
            system=body.system,
            component=body.name,
            owner=body.owner,
            provider="LOCAL",
        )
        db.add(repo)
        db.flush()
        db.add(Grant(user_id=user.id, repository_id=repo.id))
        try:
            queued = queued_input(db, user, repo, body.files, request)
            if queued:
                return queued
            snapshot, job = execute_analysis(
                db, user, repo, body.files, request_id=request.state.request_id, advisory_cache=local_advisories()
            )
        except Exception as error:
            raise HTTPException(
                422 if isinstance(error, (ValueError, RecursionError)) else 500,
                "Analysis failed; inspect the repository job for details.",
            )
        return {"repository_id": repo.id, "snapshot_id": snapshot.id, "job_id": job.id, "state": job.data["state"]}


@app.post("/api/repositories/{repo_id}/analyze")
def analyze_repo(repo_id: str, body: Analyze, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        repo = require_repo(db, user, repo_id)
        if body.base_id:
            base = authorized_record(db, user, body.base_id)
            if base.kind != "snapshot" or base.repository_id != repo.id:
                raise HTTPException(422, "Base must be a snapshot of the same repository.")
        try:
            queued = queued_input(db, user, repo, body.files, request, branch=body.branch, base_id=body.base_id)
            if queued:
                return queued
            snapshot, _ = execute_analysis(
                db,
                user,
                repo,
                body.files,
                branch=body.branch,
                base_id=body.base_id,
                request_id=request.state.request_id,
                advisory_cache=local_advisories(),
            )
        except Exception as error:
            raise HTTPException(
                422 if isinstance(error, ValueError) else 500,
                "Analysis failed; inspect the repository job for details.",
            )
        return packed(snapshot)


class ComponentAssignment(StrictModel):
    version: int | None = None
    configuration: dict


@app.get("/api/repositories/{repo_id}/components")
def repository_components(repo_id: str, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request)
        require_repo(db, user, repo_id)
        row = db.scalar(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.repository_id == repo_id,
                Record.kind == "component_assignment",
            )
        )
        return packed(row) if row else {"version": None, "configuration": {"version": 1, "components": []}}


@app.post("/api/repositories/{repo_id}/components")
def assign_components(repo_id: str, body: ComponentAssignment, request: Request):
    from backend.repository_store import component_boundaries

    with Session() as db:
        user, _ = authenticate(db, request, True)
        require_repo(db, user, repo_id)
        if user.role not in {"ADMIN", "ORG_OWNER"}:
            raise HTTPException(403, "An organization administrator must assign component boundaries.")
        try:
            component_boundaries(body.configuration, basis="HUMAN_ASSIGNMENT")
        except ValueError as error:
            raise HTTPException(422, str(error))
        row = db.scalar(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.repository_id == repo_id,
                Record.kind == "component_assignment",
            )
        )
        if body.version != (row.version if row else None):
            raise HTTPException(409, "Component assignment changed; reload its current version.")
        data = {"configuration": body.configuration, "basis": "HUMAN_ASSIGNMENT", "applies_to": "FUTURE_INVENTORIES"}
        if row:
            add(
                db,
                user.organization_id,
                repo_id,
                "component_assignment_version",
                {**row.data, "assignment_version": row.version},
            )
            row.data = data
            row.version += 1
        else:
            row = add(db, user.organization_id, repo_id, "component_assignment", data)
        audit(db, user, "COMPONENT_ASSIGNMENT_UPDATED", row.id, {"version": row.version}, repo_id)
        db.commit()
        return packed(row)


async def streamed_archive(request, db, user, repo, base_id=None):
    from backend.encrypted_archive import EncryptedArchive
    from backend.queue import check_capacity
    from backend.repository_store import RepositoryFiles, archive_items, capture, limits

    check_capacity(db, user, repo)
    db.commit()  # Release the short admission lock before reading the upload stream.
    try:
        policy = limits()
        with EncryptedArchive(policy["archive_bytes"]) as spool:
            async for chunk in request.stream():
                spool.append(chunk)
            inventory = capture(
                db, user.organization_id, repo, archive_items(spool, policy), source="ZIP_STREAM", quota=policy
            )
        files = RepositoryFiles(db, user.organization_id, repo.id, inventory.id)
        queued = queued_input(db, user, repo, files, request, source="INVENTORY", base_id=base_id)
        if queued:
            return queued
        snapshot, job = execute_analysis(
            db,
            user,
            repo,
            files,
            base_id=base_id,
            request_id=request.state.request_id,
            advisory_cache=local_advisories(),
        )
        return {"repository_id": repo.id, "snapshot_id": snapshot.id, "job_id": job.id, "state": job.data["state"]}
    except (ValueError, zipfile.BadZipFile, UnicodeError):
        raise HTTPException(422, "Archive is invalid or exceeds its configured intake budgets.")


@app.post("/api/archive/stream/import")
async def archive_stream_import(
    request: Request,
    name: str = Query(default="Imported repository", min_length=1, max_length=120, pattern=r"^[\w .-]+$"),
):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        if user.organization_id == "northstar":
            raise HTTPException(409, "Sign in to your organization workspace before importing source.")
        if len(allowed_repositories(db, user)) >= 20:
            raise HTTPException(429, "Workspace repository quota reached.")
        repo = Repository(
            id=uid(),
            organization_id=user.organization_id,
            name=name,
            system="Imported System",
            component=name,
            owner="Engineering Team",
            provider="LOCAL",
        )
        db.add(repo)
        db.flush()
        db.add(Grant(user_id=user.id, repository_id=repo.id))
        return await streamed_archive(request, db, user, repo)


@app.post("/api/repositories/{repo_id}/source-archive")
async def archive_stream_analyze(repo_id: str, request: Request, base_id: str | None = None):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        repo = require_repo(db, user, repo_id)
        if base_id:
            base = authorized_record(db, user, base_id)
            if base.kind != "snapshot" or base.repository_id != repo.id:
                raise HTTPException(422, "Base must be a snapshot of the same repository.")
        if user.organization_id == "northstar":
            raise HTTPException(409, "Upload snapshots in your real workspace.")
        if not base_id:
            previous = current_snapshots(db, user).get(repo.id)
            base_id = previous.id if previous else None
        return await streamed_archive(request, db, user, repo, base_id)


@app.post("/api/archive/import")
async def archive_import(
    request: Request,
    name: str = Query(default="Imported repository", min_length=1, max_length=120, pattern=r"^[\w .-]+$"),
):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        if user.organization_id == "northstar":
            raise HTTPException(
                409, "Sign in to your real organization workspace to import source; demo data remains separate."
            )
        if len(allowed_repositories(db, user)) >= 20:
            raise HTTPException(429, "Local workspace repository quota (20) reached.")
        repo = Repository(
            id=uid(),
            organization_id=user.organization_id,
            name=name,
            system="Imported System",
            component=name,
            owner="Engineering Team",
            provider="LOCAL",
        )
        db.add(repo)
        db.flush()
        blob = await request.body()
        db.add(Grant(user_id=user.id, repository_id=repo.id))
        try:
            queued = queued_input(db, user, repo, blob, request, source="ZIP")
            if queued:
                return queued
            snapshot, job = execute_analysis(
                db,
                user,
                repo,
                lambda: read_zip(blob, keep_excluded=True),
                request_id=request.state.request_id,
                advisory_cache=local_advisories(),
            )
        except Exception as error:
            raise HTTPException(
                422 if isinstance(error, (ValueError, OSError, RuntimeError, zipfile.BadZipFile)) else 500,
                "Archive analysis failed; inspect the persisted repository job for details.",
            )
        return {"repository_id": repo.id, "snapshot_id": snapshot.id, "job_id": job.id, "state": job.data["state"]}


@app.post("/api/repositories/{repo_id}/archive/analyze")
async def archive_analyze(repo_id: str, request: Request, base_id: str | None = None):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        repo = require_repo(db, user, repo_id)
        if user.organization_id == "northstar":
            raise HTTPException(409, "Upload snapshots in your real workspace.")
        if base_id:
            base = authorized_record(db, user, base_id)
            if base.kind != "snapshot" or base.repository_id != repo.id:
                raise HTTPException(422, "Base must belong to this repository.")
        else:
            base = current_snapshots(db, user).get(repo.id)
            base_id = base.id if base else None
        blob = await request.body()
        try:
            queued = queued_input(db, user, repo, blob, request, source="ZIP", base_id=base_id)
            if queued:
                return queued
            snapshot, job = execute_analysis(
                db,
                user,
                repo,
                lambda: read_zip(blob, keep_excluded=True),
                base_id=base_id,
                request_id=request.state.request_id,
                advisory_cache=local_advisories(),
            )
        except Exception as error:
            raise HTTPException(
                422 if isinstance(error, (ValueError, OSError, RuntimeError, zipfile.BadZipFile)) else 500,
                "Archive analysis failed; inspect the persisted repository job for details.",
            )
        return {"repository_id": repo.id, "snapshot_id": snapshot.id, "job_id": job.id, "state": job.data["state"]}


def local_advisories():
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "samples" / "osv-lodash.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "npm:lodash@4.17.20": [
            {
                "id": v["id"],
                "summary": v.get("summary", ""),
                "url": "https://osv.dev/vulnerability/" + v["id"],
                "affected": v.get("affected", []),
                "severity": {"MODERATE": "MEDIUM", "HIGH": "HIGH", "LOW": "LOW", "CRITICAL": "CRITICAL"}.get(
                    v.get("database_specific", {}).get("severity"), "UNKNOWN"
                ),
            }
            for v in data.get("vulns", [])
        ]
    }


@app.post("/api/record/{record_id}/review")
def review(record_id: str, body: Review, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        record = authorized_record(db, user, record_id)
        if record.kind not in {"claim", "finding", "drift", "pr"}:
            raise HTTPException(422, "This record does not support review.")
        if record.version != body.expected_version:
            raise HTTPException(409, "Record changed since it was opened. Refresh before reviewing.")
        if body.action in {"ACCEPT_RISK", "CREATE_EXCEPTION"} and user.role not in {
            "ADMIN",
            "ORG_OWNER",
            "SECURITY_REVIEWER",
        }:
            raise HTTPException(403, "Accepting risk requires an administrator or security reviewer.")
        old = record.data.get("review_status", "OPEN")
        status = {
            "CONFIRM": "CONFIRMED",
            "FALSE_POSITIVE": "FALSE_POSITIVE",
            "RESOLVE": "RESOLVED",
            "REQUEST_MORE_EVIDENCE": "REVIEW_REQUIRED",
            "IN_REVIEW": "IN_REVIEW",
            "REOPEN": "OPEN",
        }.get(body.action, old)
        if record.data.get("category") == "QUALITY":
            status = {"ACCEPT_RISK": "ACCEPTED", "CREATE_EXCEPTION": "EXCEPTION"}.get(body.action, status)
        record.data = {
            **record.data,
            "review_status": status,
            "owner": body.owner or record.data.get("owner"),
            "review_reason": redact(body.reason),
            "review_identity_id": record.data.get("review_identity_id") or record.data.get("identity_id"),
        }
        details = {
            "target": record.id,
            "action": body.action,
            "reason": redact(body.reason),
            "actor": user.email,
            "scope": record.data.get("scope"),
            "old_status": old,
            "new_status": status,
            "identity_id": record.data.get("review_identity_id") or record.data.get("identity_id"),
            "rule": record.data.get("rule"),
            "rule_version": record.data.get("rule_version"),
            "language": record.data.get("language"),
            "framework": record.data.get("framework", "UNKNOWN"),
        }
        add(db, user.organization_id, record.repository_id, "review", details)
        if body.action in {"ACCEPT_RISK", "CREATE_EXCEPTION"}:
            from backend.trust import policy

            if body.expires_days > policy(db, user.organization_id)["maximum_exception_days"]:
                raise HTTPException(422, "Exception exceeds the organization duration policy.")
            add(
                db,
                user.organization_id,
                record.repository_id,
                "exception",
                {
                    **details,
                    "owner": body.owner or user.email,
                    "approver": user.email,
                    "expires_at": (datetime.now(timezone.utc) + timedelta(days=body.expires_days)).isoformat(),
                },
            )
        audit(db, user, "HUMAN_REVIEW", record.id, details, record.repository_id)
        db.commit()
        return packed(record)


@app.get("/api/gate/{snapshot_id}")
def gate(snapshot_id: str, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request)
        snapshot = authorized_record(db, user, snapshot_id)
        if snapshot.kind != "snapshot":
            raise HTTPException(422, "A snapshot is required.")
        records = list(db.scalars(scope_query(db, user).where(Record.repository_id == snapshot.repository_id)))
        claims = [
            packed(r)
            for r in records
            if r.kind == "claim" and r.data.get("scope", {}).get("snapshot_id") == snapshot.id
        ]
        findings = [
            packed(r)
            for r in records
            if r.kind == "finding" and r.data.get("scope", {}).get("snapshot_id") == snapshot.id
        ]
        exceptions = [r.data for r in records if r.kind == "exception"]
        from backend.db import QualityAnalysis
        from backend.quality_api import effective_gate
        from backend.quality_domain import merge_gate

        projection = db.get(QualityAnalysis, snapshot.id)
        engineering = policy_gate(
            claims,
            [f for f in findings if not projection or f.get("category") != "QUALITY"],
            exceptions,
            new_findings_only=snapshot.data.get("native_profile", {}).get("gate_scope") == "NEW_FINDINGS",
        )
        return merge_gate(engineering, effective_gate(db, projection)) if projection else engineering


@app.get("/api/sbom/{snapshot_id}")
def export_sbom(snapshot_id: str, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request)
        snapshot = authorized_record(db, user, snapshot_id)
        if snapshot.kind != "snapshot":
            raise HTTPException(422, "A snapshot is required.")
        return sbom(snapshot.data.get("dependencies", []))


@app.post("/api/ask")
def ask(body: Question, request: Request):
    with Session() as db:
        user, _ = authenticate(db, request, True, edit=False)
        if body.repository_id:
            require_repo(db, user, body.repository_id)
        snapshots = current_snapshots(db, user)
        # Deterministic retrieval: token overlap + claim category + evidence authority.
        stopwords = {
            "the",
            "is",
            "a",
            "an",
            "of",
            "on",
            "in",
            "what",
            "how",
            "does",
            "our",
            "it",
            "to",
            "and",
            "are",
            "with",
        }
        tokens = set(re.findall(r"[a-z0-9_/]+", body.question.lower())) - stopwords
        fulltext = {}
        if db.bind.dialect.name == "postgresql":
            from sqlalchemy import bindparam, text

            ids = [
                claim["id"]
                for rid, snap in snapshots.items()
                if not body.repository_id or rid == body.repository_id
                for claim in snap.data.get("claims", [])
            ]
            if ids:
                query = text(
                    "SELECT id, ts_rank_cd(to_tsvector('english', coalesce(data->>'text', '') || ' ' || coalesce(data->>'category', '')), plainto_tsquery('english', :question)) AS rank FROM records WHERE organization_id = :org AND kind = 'claim' AND id IN :ids"
                ).bindparams(bindparam("ids", expanding=True))
                fulltext = {
                    row.id: float(row.rank)
                    for row in db.execute(query, {"question": body.question, "org": user.organization_id, "ids": ids})
                }
        candidates = []
        for repo_id, snap in snapshots.items():
            if body.repository_id and repo_id != body.repository_id:
                continue
            for claim in snap.data.get("claims", []):
                words = set(re.findall(r"[a-z0-9_/]+", (claim["text"] + " " + claim["category"]).lower())) - stopwords
                score = len(tokens & words) + (
                    3 if any(t.startswith("auth") for t in tokens) and claim["category"] == "AUTHENTICATION" else 0
                )
                score += fulltext.get(claim["id"], 0) * 4
                if score:
                    score += 0.25 if claim["status"] == "CONTRADICTED" else 0.1 if claim["status"] == "VERIFIED" else 0
                    candidates.append((score, claim))
        candidates.sort(key=lambda c: c[0], reverse=True)
        claims = [c for _, c in candidates[:5]]
        evidence_ids = list(dict.fromkeys(eid for c in claims for eid in c["evidence_ids"]))
        evidence = [packed(authorized_record(db, user, eid)) for eid in evidence_ids]
        auth = next((c for c in claims if c["category"] == "AUTHENTICATION"), None)
        answer = (
            "The current static evidence configures server-side session authentication."
            if auth and auth["status"] == "CONTRADICTED" and auth["expected"] == "jwt"
            else claims[0]["text"] + " " + claims[0]["reason"]
            if claims
            else "Insufficient evidence in your authorized snapshots to answer this question."
        )
        return {
            "answer": answer,
            "verification": "INFERRED"
            if auth and auth["status"] == "CONTRADICTED"
            else claims[0]["status"]
            if claims
            else "UNVERIFIED",
            "confidence": "MEDIUM" if claims else "LOW",
            "claims": claims,
            "evidence": evidence,
            "provider": "Deterministic evidence retrieval",
            "retrieval": {
                "full_text": "POSTGRESQL" if fulltext else "LOCAL_TOKEN",
                "metadata": ["authorized_repository", "current_snapshot", "claim_category", "verification_status"],
                "graph_neighborhood": [
                    packed(item)
                    for item in db.scalars(
                        scope_query(db, user).where(
                            Record.kind == "edge",
                            Record.data["snapshot_id"]
                            .as_string()
                            .in_(
                                [
                                    snap.id
                                    for rid, snap in snapshots.items()
                                    if not body.repository_id or rid == body.repository_id
                                ]
                            ),
                        )
                    )
                    if item.data.get("source") in {claim["id"] for claim in claims}
                    or item.data.get("target") in {claim["id"] for claim in claims}
                ][:50],
                "semantic_vectors": "NOT_CONFIGURED",
            },
            "limitations": [
                "No language model was called.",
                "Static evidence only; runtime and omitted files may differ.",
                "Keyword retrieval does not support every engineering question.",
            ],
        }


@app.post("/api/cloud/aws/inventory")
def sync_aws_inventory(body: AWSInventoryBody, request: Request):
    from analyzers.engine import finding
    from backend.db import CloudAsset
    from integrations.cloud import aws_inventory, configured_clients

    with Session() as db:
        user, _ = authenticate(db, request, True)
        if user.role not in {"ORG_OWNER", "ADMIN"}:
            raise HTTPException(403, "Only administrators can authorize cloud inventory.")
        repo = require_repo(db, user, body.repository_id)
        snapshot = current_snapshots(db, user).get(repo.id)
        if not snapshot:
            raise HTTPException(409, "Analyze the repository before correlating cloud inventory.")
        try:
            clients = configured_clients(user.organization_id, body.region)
            inventory = aws_inventory(clients, body.account_id, body.region)
        except ValueError:
            raise HTTPException(
                409, "Tenant-scoped AWS credentials are missing or do not match this account."
            ) from None
        except Exception:
            raise HTTPException(502, "Read-only cloud inventory failed; provider details are withheld.") from None
        scope = {**snapshot.data["scope"], "cloud_account": body.account_id, "cloud_region": body.region}
        observation = add(
            db,
            user.organization_id,
            repo.id,
            "evidence",
            {
                "class": "CLOUD_INVENTORY",
                "authority": "CLOUD_API",
                "path": "aws-control-plane/" + body.account_id,
                "source": json.dumps(inventory),
                "scope": scope,
                "observed_at": now(),
                "provider": "AWS direct read-only API",
            },
        )
        nodes = []
        for asset in inventory["assets"]:
            node = add(
                db,
                user.organization_id,
                repo.id,
                "graph_node",
                {
                    **asset,
                    "class": "CLOUD_IDENTITY" if asset["asset_kind"] == "CloudIdentity" else "CLOUD_RESOURCE",
                    "title": asset["identity"],
                    "scope": scope,
                    "owner": repo.owner,
                    "evidence_ids": [observation.id],
                },
            )
            db.add(
                CloudAsset(
                    id=node.id,
                    organization_id=user.organization_id,
                    repository_id=repo.id,
                    snapshot_id=snapshot.id,
                    provider="AWS",
                    resource_id=asset["identity"],
                    asset_kind=asset["asset_kind"],
                    exposure=asset["public"],
                    encryption=asset["encryption"],
                    observed_at=now(),
                )
            )
            nodes.append(node.id)
            add(
                db,
                user.organization_id,
                repo.id,
                "edge",
                {
                    "source": node.id,
                    "target": observation.id,
                    "relationship": "OBSERVED_IN",
                    "snapshot_id": snapshot.id,
                },
            )
            rule = (
                "PT-CLOUD-002"
                if asset["public"] == "INTERNET_INGRESS_OBSERVED"
                else "PT-CLOUD-001"
                if asset["public"] == "PUBLIC_ACL_OBSERVED"
                and not asset.get("public_access_block", {}).get("IgnorePublicAcls")
                else None
            )
            if rule:
                issue = add(
                    db,
                    user.organization_id,
                    repo.id,
                    "finding",
                    {
                        **finding(
                            rule,
                            observation.data["path"],
                            1,
                            "Read-only control-plane observation; effective access and workload reachability are unverified.",
                            "MEDIUM",
                        ),
                        "classification": "SECURITY_HOTSPOT",
                        "scope": scope,
                        "resource_identity": asset["identity"],
                        "evidence_ids": [observation.id],
                        "owner": repo.owner,
                        "provider": "ProjectTrace native CSPM",
                    },
                )
                add(
                    db,
                    user.organization_id,
                    repo.id,
                    "edge",
                    {"source": issue.id, "target": node.id, "relationship": "AFFECTS", "snapshot_id": snapshot.id},
                )
        account = add(
            db,
            user.organization_id,
            repo.id,
            "cloud_account",
            {
                "provider": "AWS",
                "status": inventory["state"],
                "live_verification": "CONTROL_PLANE_OBSERVED",
                "account_id": body.account_id,
                "region": body.region,
                "scope": scope,
                "last_sync": now(),
                "asset_ids": nodes,
                "warnings": inventory["warnings"],
                "permissions": "Only configured read operations",
                "credential_storage": "TENANT_SCOPED_HOST_REFERENCE",
            },
        )
        audit(
            db,
            user,
            "AWS_READ_ONLY_INVENTORY",
            account.id,
            {"asset_count": len(nodes), "state": inventory["state"]},
            repo.id,
        )
        db.commit()
        return {"id": account.id, **account.data}


@app.get("/api/native/rules")
def native_rules(request: Request):
    from analyzers.engine import RULES, VERSION
    from analyzers.native_rules import registry

    with Session() as db:
        authenticate(db, request)
    return {"provider": "ProjectTrace native", "version": VERSION, "rules": registry(RULES, VERSION)}


@app.get("/api/native/profile")
def native_profile(request: Request, repository_id: str | None = None):
    from backend.native import profile_scope

    with Session() as db:
        user, _ = authenticate(db, request)
        row = db.scalar(profile_scope(db, user, repository_id))
        return (
            {"version": row.version, "repository_id": row.repository_id, **row.data}
            if row
            else {"version": 0, "repository_id": repository_id, "rules": {}, "licenses": {}}
        )


@app.post("/api/native/profile")
def update_native_profile(body: NativeProfileBody, request: Request):
    from backend.native import save_profile

    if body.licenses.keys() - {"approved", "restricted"} or any(
        len(items) > 100 or any(not re.fullmatch(r"[A-Za-z0-9.+-]{1,70}", item) for item in items)
        for items in body.licenses.values()
    ):
        raise HTTPException(422, "Use bounded observed SPDX license identifiers.")
    with Session() as db:
        user, _ = authenticate(db, request, True)
        return save_profile(db, user, body)


@app.get("/api/integrations")
@app.get("/api/connections")
def integrations(request: Request):
    with Session() as db:
        user, _ = authenticate(db, request)
        connection = db.scalar(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.kind == "integration",
                Record.natural_key == "github",
            )
        )
        github_data = connection.data if connection else None
        cloud_connection = db.scalar(
            scope_query(db, user).where(Record.kind == "cloud_account").order_by(Record.created_at.desc())
        )
        aws_data = cloud_connection.data if cloud_connection else None
    result = [
        {
            "name": name,
            "group": group,
            "optional": True,
            "implementation": implementation,
            "status": "NOT_CONFIGURED",
            "live_verification": "NOT_VERIFIED",
            "permissions": permissions,
            "last_sync": None,
        }
        for name, group, implementation, permissions in [
            (
                "GitHub App",
                "SCM",
                "CREDENTIAL_GATED",
                "Contents and pull requests: read; Checks: write only when explicitly enabled",
            ),
            ("GitLab", "SCM", "DEFERRED", "Read-only SCM adapter planned"),
            (
                "AWS",
                "Cloud Accounts",
                "READ_ONLY_ADAPTER",
                "Authorized list/describe inventory only; live verification requires account credentials",
            ),
            ("Azure", "Cloud Accounts", "DEFERRED", "Reader inventory adapter planned"),
            ("GCP", "Cloud Accounts", "DEFERRED", "Viewer inventory adapter planned"),
            ("External AI", "AI Providers", "DISABLED", "Optional; no source is sent to a provider"),
        ]
    ]
    if github_data:
        result[0].update(
            {
                "status": github_data["status"],
                "live_verification": github_data["live_verification"],
                "last_sync": github_data.get("last_sync"),
            }
        )
    if aws_data:
        result[2].update(
            {
                "status": aws_data["status"],
                "live_verification": aws_data["live_verification"],
                "last_sync": aws_data.get("last_sync"),
            }
        )
    return result


@app.post("/api/github/connect")
def connect_github(body: ConnectGitHub, request: Request):
    import httpx

    from workers.github import configured_app

    with Session() as db:
        user, _ = authenticate(db, request, True)
        if user.role not in {"ORG_OWNER", "ADMIN"}:
            raise HTTPException(403, "Connecting an SCM installation requires an organization administrator.")
        from backend.scm_connections import authorized_connection

        metadata = authorized_connection(db, user, body.connection_id) if body.connection_id else None
        try:
            adapter = configured_app(metadata) if metadata else configured_app()
            candidates = adapter.repositories()
        except (ValueError, httpx.HTTPError):
            raise HTTPException(503, "GitHub App credentials are missing or the installation connection test failed.")
        candidate = next((r for r in candidates if r["id"] == body.repository_id), None)
        if not candidate:
            raise HTTPException(404, "Repository is outside the authorized GitHub installation.")
        provider_type = metadata.data["provider_type"] if metadata else "GITHUB"
        provider_identity = (
            (metadata.data["api_base_url"].rstrip("/") + "/" + str(body.repository_id))
            if metadata
            else str(body.repository_id)
        )
        existing = db.scalar(
            select(Repository).where(Repository.provider == provider_type, Repository.provider_id == provider_identity)
        )
        if existing:
            raise HTTPException(409, "This provider repository is already connected.")
        repo = Repository(
            id=uid(),
            organization_id=user.organization_id,
            name=candidate["full_name"],
            system=body.system,
            component=candidate["name"],
            owner=body.owner,
            provider=provider_type,
            provider_id=provider_identity,
        )
        db.add(repo)
        db.flush()
        db.add(Grant(user_id=user.id, repository_id=repo.id))
        connection = db.scalar(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.kind == "integration",
                Record.natural_key == ("github:" + metadata.id if metadata else "github"),
            )
        )
        details = {
            "status": "CONNECTED",
            "live_verification": "CONNECTION_TESTED",
            "owner_id": user.id,
            "checks_enabled": body.checks_enabled,
            "last_sync": None,
            "installation_id": metadata.data["installation_id"] if metadata else os.environ["GITHUB_INSTALLATION_ID"],
            "connection_id": metadata.id if metadata else None,
        }
        if connection:
            connection.data = details
        else:
            add(
                db,
                user.organization_id,
                None,
                "integration",
                details,
                "github:" + metadata.id if metadata else "github",
            )
        add(
            db,
            user.organization_id,
            repo.id,
            "repository_scm",
            {
                "connection_id": metadata.id if metadata else None,
                "provider_repository_id": str(body.repository_id),
                "provider_type": provider_type,
                "enabled": True,
            },
            repo.id,
        )
        if metadata:
            metadata.data = {**metadata.data, "status": "CONNECTED", "live_verification": "CONNECTION_TESTED"}
        audit(
            db,
            user,
            "GITHUB_CONNECTED",
            repo.id,
            {"checks_enabled": body.checks_enabled, "permissions": "read source; optional write checks"},
            repo.id,
        )
        db.commit()
        return {"repository_id": repo.id, "status": "CONNECTED", "analysis_verification": "NOT_VERIFIED"}


@app.post("/api/github/webhook")
async def webhook(request: Request):
    from integrations.github.connector import verify_signature

    raw = await request.body()
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "GitHub webhook is not configured.")
    if not verify_signature(raw, request.headers.get("x-hub-signature-256", ""), secret):
        raise HTTPException(401, "Webhook signature is invalid.")
    delivery_id = request.headers.get("x-github-delivery", "")
    if not delivery_id or len(delivery_id) > 100:
        raise HTTPException(422, "A valid delivery identifier is required.")
    try:
        payload = json.loads(raw)
        provider_id = str(payload.get("repository", {}).get("id", ""))
    except (ValueError, AttributeError):
        raise HTTPException(422, "Webhook payload is invalid.")
    with Session() as db:
        repo = db.scalar(
            select(Repository).where(Repository.provider == "GITHUB", Repository.provider_id == provider_id)
        )
        if not repo:
            raise HTTPException(404, "Webhook repository is not connected.")
        if db.get(Delivery, delivery_id):
            return {"status": "DUPLICATE"}
        event = request.headers.get("x-github-event", "")
        if event not in {"pull_request", "push", "ping"}:
            return {"status": "IGNORED"}
        db.add(Delivery(id=delivery_id, organization_id=repo.organization_id, event=event))
        try:
            change = payload.get("pull_request", {}) if event == "pull_request" else {}
            details = {
                "head_sha": change.get("head", {}).get("sha") if change else payload.get("after"),
                "base_sha": change.get("base", {}).get("sha") if change else None,
                "branch": change.get("head", {}).get("ref", "main")
                if change
                else str(payload.get("ref", "main"))[:120],
                "pr_number": change.get("number"),
                "pr_title": redact(str(change.get("title", "")))[:250],
            }
        except (AttributeError, TypeError):
            raise HTTPException(422, "Webhook change scope is invalid.")
        # Durable receipt is distinct from provider fetch/check publication.
        from backend.scheduling import enqueue_scm
        try:
            job = enqueue_scm(db, repo, details, event=event, delivery_id=delivery_id)
        except ValueError:
            raise HTTPException(429, "SCM analysis admission quota reached; retry this delivery later.") from None
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"status": "DUPLICATE"}
        if os.getenv("JOB_MODE") == "celery":
            from workers.tasks import celery

            try:
                celery.send_task("projecttrace.github_delivery", args=[job.id], task_id=job.id)
            except Exception:
                # Receipt remains durable; an operator can dispatch this job again.
                job.data = {**job.data, "dispatch": "PENDING_RETRY"}
                db.commit()
    return {"status": "RECEIVED", "analysis": "QUEUED", "check_published": False}


@app.post("/api/jobs/{job_id}/{action}")
def control_job(job_id: str, action: Literal["retry", "cancel"], request: Request):
    with Session() as db:
        user, _ = authenticate(db, request, True)
        job = authorized_record(db, user, job_id)
        if job.kind != "job":
            raise HTTPException(422, "An analysis job is required.")
        if action == "cancel":
            if job.data.get("state") in {"COMPLETED", "COMPLETED_NO_FINDINGS", "CANCELLED"}:
                raise HTTPException(409, "This job has already finished.")
            from backend.db import AnalysisInput

            retained = db.get(AnalysisInput, job.id)
            from backend.scheduling import cancel
            result = cancel(db, job)
            if retained and result == "CANCELLED":
                db.delete(retained)
            audit(db, user, "JOB_CANCELLED", job.id, {}, job.repository_id)
            db.commit()
            if result == "CANCELLATION_REQUESTED":
                return {**packed(job), "cancellation_requested": True}
        else:
            if os.getenv("JOB_MODE") != "celery":
                raise HTTPException(503, "The Redis/Celery worker must be configured before retrying provider jobs.")
            lease = job.data.get("lease_expires_at")
            stale = (
                job.data.get("state") not in {"COMPLETED", "COMPLETED_NO_FINDINGS", "CANCELLED"}
                and lease
                and datetime.fromisoformat(lease) <= datetime.now(timezone.utc)
            )
            if job.data.get("state") not in {"FAILED", "PARTIAL", "QUEUED"} and not stale:
                raise HTTPException(409, "This job cannot be retried in its current state.")
            from backend.db import AnalysisInput
            from backend.queue import dispatch

            if job.data.get("source") in {"ZIP", "FILES", "INVENTORY"} and not db.get(AnalysisInput, job.id):
                raise HTTPException(409, "Retained input is unavailable; upload a fresh snapshot.")

            if job.data.get("retry_count", 0) >= 2:
                raise HTTPException(409, "Retry limit reached; upload a fresh snapshot or advisory job.")
            job.data = {
                **job.data,
                "state": "QUEUED",
                "stage": "QUEUED",
                "finished_at": None,
                "retry_count": job.data.get("retry_count", 0) + 1,
            }
            audit(db, user, "JOB_RETRIED", job.id, {"retry_count": job.data["retry_count"]}, job.repository_id)
            db.commit()
            dispatch(db, job)
        return packed(job)


@app.get("/api/analysis/metrics")
def analysis_metrics(request: Request, repository_id: str | None = None):
    with Session() as db:
        user, _ = authenticate(db, request)
        query = scope_query(db, user).where(Record.kind == "job").order_by(Record.created_at.desc()).limit(1000)
        if repository_id:
            require_repo(db, user, repository_id)
            query = query.where(Record.repository_id == repository_id)
        jobs = list(db.scalars(query))
        samples = sorted(j.data["duration_ms"] for j in jobs if isinstance(j.data.get("duration_ms"), (int, float)))
        waits = sorted(j.data["queue_wait_ms"] for j in jobs if isinstance(j.data.get("queue_wait_ms"), (int, float)))

        def percentiles(values):
            return {
                name: values[max(0, math.ceil(len(values) * p) - 1)] if values else None
                for name, p in [("p50", 0.5), ("p95", 0.95), ("p99", 0.99)]
            }

        return {
            "scope": "Authorized latest 1000 persisted jobs",
            "samples": len(samples),
            "duration_ms": percentiles(samples),
            "queue_wait_ms": percentiles(waits),
            "states": {
                state: sum(j.data.get("state") == state for j in jobs)
                for state in sorted({j.data.get("state", "UNKNOWN") for j in jobs})
            },
        }


@app.post("/api/snapshots/{snapshot_id}/advisories")
def check_advisories(snapshot_id: str, request: Request):
    if os.getenv("JOB_MODE") != "celery" or os.getenv("OSV_ENABLED") != "1":
        raise HTTPException(503, "Enable OSV_ENABLED=1 and the Celery worker for background advisory checks.")
    with Session() as db:
        user, _ = authenticate(db, request, True)
        snapshot = authorized_record(db, user, snapshot_id)
        if snapshot.kind != "snapshot":
            raise HTTPException(422, "A snapshot is required.")
        repo = require_repo(db, user, snapshot.repository_id)
        from backend.advisories import enqueue_advisories

        try:
            job = enqueue_advisories(db, user, repo, snapshot)
        except ValueError:
            raise HTTPException(429, "Advisory queue quota reached.")
        return JSONResponse(status_code=202, content={"job_id": job.id, "state": job.data["state"]})


app.include_router(quality_router)
app.include_router(finding_router)
app.include_router(graph_router)
app.include_router(engineering_router)
app.include_router(trust_router)
app.include_router(oidc_router)
app.include_router(scm_router)
app.include_router(scm_webhook_router)
