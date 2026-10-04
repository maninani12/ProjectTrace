# ProjectTrace

ProjectTrace connects engineering claims to current software evidence, then shows what changed, what needs review, and who owns the next action.

**Current release: tested local engineering-integrity demo and bounded static-analysis MVP. The full industry specification and production release gates are not complete.** Northstar Labs is deterministic demo data. Live GitHub/cloud/security providers have not been verified with credentials. No external AI call is made.

## Start on Windows PowerShell

Python 3.14 and Node 24 are required. The exact installed dependency set is recorded in the lockfiles.

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
New-Item -ItemType Directory -Force -Path data | Out-Null
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m backend.seed
Set-Location frontend
npm.cmd ci
Set-Location ..
& .\scripts\start.ps1
```

Open **http://127.0.0.1:5181** and select **Explore Northstar demo**. API: http://127.0.0.1:8011. Existing processes using 8000/5173 are unaffected. Check `data/api-error.log` and `data/ui-error.log` if ports 8011/5181 are occupied.

For foreground development, run the API and UI in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

```powershell
Set-Location frontend
npm.cmd run dev
```

## Windows CMD

```cmd
cd /d "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
if not exist data mkdir data
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m backend.seed
cd frontend
npm ci
npm run dev
```

In a second CMD window:

```cmd
cd /d "C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace"
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

## Validate

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .\data\pytest-tmp
.\.venv\Scripts\ruff.exe check backend analyzers integrations workers tests scripts
.\.venv\Scripts\pip-audit.exe -r requirements.lock
Set-Location frontend
npm.cmd run build
npm.cmd test
npm.cmd audit
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

Use a dedicated temporary directory for pytest; pytest manages that directory. Browser tests require both local servers running and write human-review events into the demo workspace. The tests do not connect external services.

## Repairs in version 1.1

Native implementation claims populate repositories whose README uses other wording. ZIP jobs persist real completion/partial/failure states and sanitized diagnostics. The global repository selector scopes results; Upload new snapshot compares versions; initial contradictions are consistency findings. Connections lists optional enrichment separately. See docs/CURRENT_STATE_AUDIT.md and docs/REPAIR_REPORT.md for evidence and limits.

## Current version 1.2

The supplied updated ZIP matched all 104 working source files before edits. Seven multi-exception handlers now use portable tuple syntax. Python 3.14 accepts the old syntax, but Python 3.11 does not; the formatter targets 3.11 syntax while the installed runtime/dependencies remain Python 3.14.

Version 1.2 adds broader deterministic atomic claims, verifier-specific cache reuse, stable claim/finding identities, reverse evidence-graph impact including deleted files, rule-only analysis changes separated from software drift, independent analyzer diagnostics, additional conservative Python security/quality checks, safe lockfile inventory subsets, deduplicated SBOM/SCA findings and canonical browser routes. Northstar remains explicitly labeled demo data; real repositories and prior history remain separate.

Local imports default to bounded synchronous execution. `JOB_MODE=celery` returns queued jobs immediately and sends only job IDs through Redis; worker source input is encrypted in the database, expires after 72 hours, and is removed on completion/cancellation. PostgreSQL serializes per-tenant admission; production middleware requires distributed Redis limits. Worker/Redis/PostgreSQL deployment has **not been executed on this Windows host**. See [the fresh audit](docs/CURRENT_IMPLEMENTATION_AUDIT_V2.md) and [the version 1.2 delivery report](docs/DELIVERY_REPORT_V2.md) for actual validation and deferred capabilities.

### Queued imports and optional advisories

Generate a Fernet key and keep it outside source control:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the same `DATABASE_URL`, `REDIS_URL`, `ANALYSIS_INPUT_KEY`, and `JOB_MODE=celery` in API and worker environments. Enable `OSV_ENABLED=1` to check exact package versions asynchronously. Only package ecosystem/name/version go to the fixed OSV endpoint; repository source stays local. Select an analyzed repository and use **Dependencies → Check advisories**. Constraints stay `UNKNOWN_VERSION`; unchecked and failed queries remain explicit. OSV results are cached per tenant for 24 hours with provider timestamps; each job has a 32-query/75-second network budget. Repeated jobs can extend coverage.

Run the worker and expiry scheduler in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m celery -A workers.tasks worker --pool=solo --loglevel=INFO
.\.venv\Scripts\python.exe -m celery -A workers.tasks beat --loglevel=INFO --schedule=data/celerybeat-schedule
```

`--pool=solo` is a local Windows option, not a validated production pool. Failed broker dispatch leaves a retained `PENDING_RETRY` job. Authenticated retry/cancel APIs append audit events; retries are bounded to two. Expired worker leases can be retried while input is retained. Production requires PostgreSQL, Redis, Celery, explicit CORS origins and an input-encryption key; live deployment/recovery/load validation remains required.

## What works

- Snapshot-scoped deterministic claim extraction and verification; VERIFIED / INFERRED / UNVERIFIED / CONTRADICTED, with STALE history during reverification.
- Evidence graph, inspector, source viewer, atomic compound claims, changed-file impact and drift history.
- Python AST checks; conservative JavaScript/Java patterns; masked secret detection; static privileged-container/public-ACL/root-user checks.
- npm lockfile and pinned Python dependencies, cached exact-version OSV demo advisories, CycloneDX export.
- Advisory PR gates, transactional human review, optimistic concurrency, expiring privileged risk exceptions, append-oriented audit.
- Tenant/repository access checks, Argon2 local passwords, HttpOnly sessions, CSRF, origin checks, input limits and safe ZIP ingestion.
- Signed/idempotent GitHub webhook intake; credential-gated installation test, bounded source fetch, worker workflow and opt-in neutral check publication. Live end-to-end verification is pending.
- React/TypeScript interface, focused graph, command search, accessible dialogs, responsive desktop/mobile review, bundled offline fonts.

## Architecture and status

FastAPI modular monolith + SQLAlchemy/Alembic; PostgreSQL deployment configuration; explicit SQLite local adapter; Celery/Redis worker entry point; React/Vite/TanStack Query/Table/React Flow frontend.

Source is never executed. Repository import does not install dependencies or run builds. The source files in samples are deliberately unsafe **data fixtures**.

See [Architecture](ARCHITECTURE.md), [Security](SECURITY.md), [CEO demo](docs/CEO-DEMO.md), [Testing](docs/TESTING.md), [Release status](docs/RELEASE.md), and [Delivery report](docs/DELIVERY_REPORT.md).
