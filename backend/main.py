import json
import logging
import os
import re
import time
import zipfile
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError

from analyzers.engine import MAX_TOTAL_BYTES, read_zip, redact, sbom
from backend.db import Audit, Delivery, Grant, Organization, Record, Repository, Session, User
from backend.domain import add, audit, persist_analysis, policy_gate, uid
from backend.security import allowed_repositories, authenticate, create_session, passwords, require_repo

APP_ENV = os.getenv("APP_ENV", "demo")
PRODUCTION = APP_ENV == "production"
ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5181,http://127.0.0.1:5181,http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8011",
).split(",")
if PRODUCTION and (
    "*" in ORIGINS or os.getenv("DATABASE_URL", "").startswith("sqlite") or not os.getenv("DATABASE_URL")
):
    raise RuntimeError("Production requires PostgreSQL and explicit CORS origins.")
log = logging.getLogger("projecttrace")


@asynccontextmanager
async def lifespan(app):
    with Session() as db:
        db.execute(text("SELECT 1"))
        db.execute(select(Organization.id).limit(1))
    yield


app = FastAPI(
    title="ProjectTrace",
    version="1.0.0",
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
rate_windows = defaultdict(deque)


@app.middleware("http")
async def security_boundary(request, call_next):
    started = time.perf_counter()
    request_id = uid()
    content_length = request.headers.get("content-length", "")
    if content_length and (not content_length.isdigit() or int(content_length) > MAX_TOTAL_BYTES + 100_000):
        return Response("Request exceeds the 10 MB limit.", status_code=413)
    # Bound streamed bodies too, before JSON/multipart parsing.
    if request.method == "POST":
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_TOTAL_BYTES + 100_000:
                return Response("Request exceeds the 10 MB limit.", status_code=413)
        request._body = bytes(body)
    if request.method == "POST" and request.url.path not in {"/api/github/webhook"}:
        if request.headers.get("origin") not in ORIGINS:
            return Response("Origin is not authorized.", status_code=403)
    key = (request.client.host if request.client else "unknown", request.url.path.startswith("/api/auth"))
    window = rate_windows[key]
    t = time.monotonic()
    while window and t - window[0] > 60:
        window.popleft()
    if len(window) >= (15 if key[1] else 240):
        return Response("Rate limit reached. Try again in one minute.", status_code=429, headers={"Retry-After": "60"})
    window.append(t)
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
        "CONFIRM", "FALSE_POSITIVE", "ACCEPT_RISK", "REQUEST_MORE_EVIDENCE", "ASSIGN", "RESOLVE", "CREATE_EXCEPTION"
    ]
    reason: str = Field(min_length=10, max_length=2000)
    owner: str | None = Field(default=None, max_length=120)
    expires_days: int = Field(default=7, ge=1, le=90)
    expected_version: int


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=1000)
    repository_id: str | None = None


class ConnectGitHub(StrictModel):
    repository_id: int = Field(gt=0)
    system: str = Field(min_length=1, max_length=120)
    owner: str = Field(min_length=1, max_length=120)
    checks_enabled: bool = False


def packed(record):
    return {
        "id": record.id,
        "kind": record.kind,
        "repository_id": record.repository_id,
        "version": record.version,
        "created_at": record.created_at,
        **record.data,
    }


def scope_query(db, user, model=Record):
    ids = [r.id for r in allowed_repositories(db, user)]
    return select(model).where(
        model.organization_id == user.organization_id, or_(model.repository_id.is_(None), model.repository_id.in_(ids))
    )


def authorized_record(db, user, record_id):
    record = db.get(Record, record_id)
    if not record or record.organization_id != user.organization_id:
        raise HTTPException(404, "Record not available in your authorized scope.")
    if record.repository_id:
        require_repo(db, user, record.repository_id)
    return record


def current_snapshots(db, user):
    records = list(
        db.scalars(scope_query(db, user).where(Record.kind == "snapshot").order_by(Record.created_at.desc()))
    )
    result = {}
    for record in records:
        result.setdefault(record.repository_id, record)
    return result


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/ready")
def ready():
    try:
        with Session() as db:
            db.execute(select(Organization.id).limit(1))
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


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    with Session() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower()))
        try:
            if not user or not passwords.verify(user.password_hash, body.password):
                raise ValueError()
        except Exception:
            raise HTTPException(401, "Email or password is incorrect.")
        csrf = create_session(db, user, response, PRODUCTION, previous_token=request.cookies.get("pt_session"))
        db.commit()
        return {"csrf": csrf, "email": user.email, "role": user.role, "demo": APP_ENV == "demo"}


@app.get("/api/auth/me")
def me(request: Request):
    with Session() as db:
        user, session = authenticate(db, request)
        return {
            "email": user.email,
            "role": user.role,
            "csrf": session.csrf,
            "organization": db.get(Organization, user.organization_id).name,
            "demo": APP_ENV == "demo",
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
def workspace(request: Request):
    with Session() as db:
        user, _ = authenticate(db, request)
        repos = allowed_repositories(db, user)
        snapshots = current_snapshots(db, user)
        records = list(db.scalars(scope_query(db, user).order_by(Record.created_at.desc()).limit(5000)))
        snapshot_ids = {s.id for s in snapshots.values()}
        current = [
            r
            for r in records
            if r.data.get("scope", {}).get("snapshot_id") in snapshot_ids
            or r.data.get("snapshot_id") in snapshot_ids
            or r.kind in {"pr", "review", "exception", "job", "integration", "policy"}
        ]
        grouped = {
            kind: [packed(r) for r in current if r.kind == kind]
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
            ]
        }
        return {
            "organization": db.get(Organization, user.organization_id).name,
            "demo": APP_ENV == "demo",
            "repositories": [
                {
                    "id": r.id,
                    "name": r.name,
                    "system": r.system,
                    "component": r.component,
                    "owner": r.owner,
                    "provider": r.provider,
                    "snapshot": packed(snapshots[r.id]) if r.id in snapshots else None,
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
        return packed(authorized_record(db, user, record_id))


@app.get("/api/audit")
def events(request: Request, offset: int = 0, limit: int = 100):
    with Session() as db:
        user, _ = authenticate(db, request)
        result = db.scalars(
            scope_query(db, user, Audit)
            .order_by(Audit.created_at.desc())
            .offset(max(0, offset))
            .limit(min(max(1, limit), 200))
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
            snapshot = persist_analysis(db, user, repo, body.files)
            db.commit()
        except (ValueError, RecursionError) as error:
            raise HTTPException(422, str(error))
        return {"repository_id": repo.id, "snapshot_id": snapshot.id}


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
            snapshot = persist_analysis(db, user, repo, body.files, body.branch, body.base_id)
            db.commit()
        except ValueError as error:
            raise HTTPException(422, str(error))
        return packed(snapshot)


@app.post("/api/archive/import")
async def archive_import(request: Request, name: str = "Imported repository"):
    try:
        files = read_zip(await request.body())
    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile) as error:
        raise HTTPException(422, str(error))
    return import_repo(Import(name=name, files=files), request)


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
        }.get(body.action, old)
        record.data = {
            **record.data,
            "review_status": status,
            "owner": body.owner or record.data.get("owner"),
            "review_reason": redact(body.reason),
        }
        details = {
            "target": record.id,
            "action": body.action,
            "reason": redact(body.reason),
            "actor": user.email,
            "scope": record.data.get("scope"),
            "old_status": old,
            "new_status": status,
        }
        add(db, user.organization_id, record.repository_id, "review", details)
        if body.action in {"ACCEPT_RISK", "CREATE_EXCEPTION"}:
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
        return policy_gate(claims, findings, exceptions)


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
        candidates = []
        for repo_id, snap in snapshots.items():
            if body.repository_id and repo_id != body.repository_id:
                continue
            for claim in snap.data.get("claims", []):
                words = set(re.findall(r"[a-z0-9_/]+", (claim["text"] + " " + claim["category"]).lower())) - stopwords
                score = len(tokens & words) + (
                    3 if any(t.startswith("auth") for t in tokens) and claim["category"] == "AUTHENTICATION" else 0
                )
                if score:
                    candidates.append((score, claim))
        candidates.sort(key=lambda c: c[0], reverse=True)
        claims = [c for _, c in candidates[:5]]
        evidence_ids = list(dict.fromkeys(eid for c in claims for eid in c["evidence_ids"]))
        evidence = [packed(authorized_record(db, user, eid)) for eid in evidence_ids]
        auth = next((c for c in claims if c["category"] == "AUTHENTICATION"), None)
        answer = (
            "The current static evidence configures server-side session authentication."
            if auth and auth["status"] == "CONTRADICTED" and auth["expected"] == "jwt"
            else claims[0]["reason"]
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
            "limitations": [
                "No language model was called.",
                "Static evidence only; runtime and omitted files may differ.",
                "Keyword retrieval does not support every engineering question.",
            ],
        }


@app.get("/api/integrations")
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
    result = [
        {
            "name": n,
            "status": "NOT_CONFIGURED",
            "live_verification": "NOT_VERIFIED",
            "permissions": p,
            "last_sync": None,
        }
        for n, p in [
            ("GitHub App", "Contents: read; Pull requests: read; Checks: write only when enabled"),
            ("SonarQube", "Read-only finding ingestion"),
            ("Wiz", "Read-only external evidence; live adapter deferred"),
            ("Cloud inventory", "Read-only; live inventory deferred"),
            ("External AI", "Disabled; no source is sent to a provider"),
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
    return result


@app.post("/api/github/connect")
def connect_github(body: ConnectGitHub, request: Request):
    import httpx

    from workers.github import configured_app

    with Session() as db:
        user, _ = authenticate(db, request, True)
        if user.role not in {"ORG_OWNER", "ADMIN"}:
            raise HTTPException(403, "Connecting an SCM installation requires an organization administrator.")
        try:
            adapter = configured_app()
            candidates = adapter.repositories()
        except ValueError, httpx.HTTPError:
            raise HTTPException(503, "GitHub App credentials are missing or the installation connection test failed.")
        candidate = next((r for r in candidates if r["id"] == body.repository_id), None)
        if not candidate:
            raise HTTPException(404, "Repository is outside the authorized GitHub installation.")
        existing = db.scalar(
            select(Repository).where(Repository.provider == "GITHUB", Repository.provider_id == str(body.repository_id))
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
            provider="GITHUB",
            provider_id=str(body.repository_id),
        )
        db.add(repo)
        db.flush()
        db.add(Grant(user_id=user.id, repository_id=repo.id))
        connection = db.scalar(
            select(Record).where(
                Record.organization_id == user.organization_id,
                Record.kind == "integration",
                Record.natural_key == "github",
            )
        )
        details = {
            "status": "CONNECTED",
            "live_verification": "CONNECTION_TESTED",
            "owner_id": user.id,
            "checks_enabled": body.checks_enabled,
            "last_sync": None,
            "installation_id": os.environ["GITHUB_INSTALLATION_ID"],
        }
        if connection:
            connection.data = details
        else:
            add(db, user.organization_id, None, "integration", details, "github")
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
    except ValueError, AttributeError:
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
        except AttributeError, TypeError:
            raise HTTPException(422, "Webhook change scope is invalid.")
        # Durable receipt is distinct from provider fetch/check publication.
        job = add(
            db,
            repo.organization_id,
            repo.id,
            "job",
            {
                "state": "QUEUED",
                "event": event,
                "delivery_id": delivery_id,
                "repository_id": repo.id,
                "provider_fetch": "PENDING_CONFIGURATION",
                **details,
            },
        )
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
            if job.data.get("state") not in {"QUEUED", "FAILED", "PARTIAL"}:
                raise HTTPException(409, "Only queued or stopped jobs can be cancelled.")
            job.data = {**job.data, "state": "CANCELLED"}
            audit(db, user, "JOB_CANCELLED", job.id, {}, job.repository_id)
            db.commit()
        else:
            if os.getenv("JOB_MODE") != "celery":
                raise HTTPException(503, "The Redis/Celery worker must be configured before retrying provider jobs.")
            if job.data.get("state") not in {"FAILED", "PARTIAL", "QUEUED"}:
                raise HTTPException(409, "This job cannot be retried in its current state.")
            from workers.tasks import celery

            job.data = {**job.data, "state": "QUEUED"}
            db.commit()
            celery.send_task("projecttrace.github_delivery", args=[job.id], task_id=job.id)
        return packed(job)
