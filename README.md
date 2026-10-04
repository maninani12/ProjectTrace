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
