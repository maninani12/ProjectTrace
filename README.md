# ProjectTrace

ProjectTrace connects engineering claims to current software evidence, then shows what changed, what needs review, and who owns the next action.

**Current release: ProjectTrace 1.3.3, a native engineering-integrity platform with bounded static analysis.** Its quality, security, dependency, secrets and infrastructure engines run independently. Northstar’s maintained fixtures are synthetic demo data; this existing workspace also retains an older local import with its historical provenance. Real PostgreSQL, Redis and non-root Linux Celery prefork execution and recovery were validated. Live cloud accounts and GitHub installations remain unverified, and full enterprise release gates remain incomplete. No external AI call is made. See [FINAL_PRODUCT_VALIDATION.md](FINAL_PRODUCT_VALIDATION.md) for the measured scope.

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

## Native version 1.3.3

The attached latest source ZIP matched all 123 baseline source files at commit `b358f36`. This release evolves the same ProjectTrace folder and preserves the existing accounts, real repositories, history, reviews, URL routes and working version 1.2 behavior.

Native Python AST and maintained JavaScript/TypeScript/TSX/Java syntax parsers produce explainable quality metrics. Bounded Python source-to-sink flow traces distinguish modeled static findings from context-dependent hotspots. Structured Terraform, CloudFormation, Kubernetes, Compose and Dockerfile checks produce source-backed cloud assets and risk paths. Settings supports versioned organization/repository rule, license and new-findings gate profiles. Native code/cloud evidence uses the existing Claim Ledger and Evidence Graph.

The direct AWS adapter performs only allowlisted reads, verifies the credential account, and records control-plane authority separately from static declarations. Use **Cloud → Sync read-only AWS inventory** after a host administrator configures an authorized credential reference. No live cloud connection is claimed in this installation. Azure/GCP inventory, effective IAM permissions and deployment reachability remain deferred. See [Native coverage](docs/NATIVE_PLATFORM.md) and [Cloud permissions](docs/CLOUD_READ_ONLY.md).

Historical version 1.1/1.2 repair reports remain in `docs/` as historical evidence. Their statements about unexecuted PostgreSQL/Redis are superseded by the current validation report. Local imports still default to bounded synchronous execution; `JOB_MODE=celery` queues encrypted source input and sends only job IDs through Redis.

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

`--pool=solo` is a local Windows option, not a validated production pool. Failed broker dispatch leaves a retained `PENDING_RETRY` job. Authenticated retry/cancel APIs append audit events; retries are bounded to two. Expired worker leases can be retried while input is retained. Production requires PostgreSQL, Redis, Celery, explicit CORS origins and an input-encryption key. Real queue, duplicate delivery, broker outage, cancellation and lease recovery checks passed in a disposable Linux VM. Production-host deployment, sustained load, backups/restores and container-image validation remain required.

## What works

- Snapshot-scoped deterministic claim extraction and verification; VERIFIED / INFERRED / UNVERIFIED / CONTRADICTED, with STALE history during reverification.
- Evidence graph, inspector, source viewer, atomic compound claims, changed-file impact and drift history.
- Python AST checks and maintained JS/TS/TSX/Java syntax metrics; bounded Python flow evidence; masked secret detection; structured infrastructure and static cloud evidence.
- npm lockfile and pinned Python dependencies, cached exact-version OSV demo advisories, CycloneDX export.
- Advisory PR gates, transactional human review, optimistic concurrency, expiring privileged risk exceptions, append-oriented audit.
- Tenant/repository access checks, Argon2 local passwords, HttpOnly sessions, CSRF, origin checks, input limits and safe ZIP ingestion.
- Signed/idempotent GitHub webhook intake; credential-gated installation test, bounded source fetch, worker workflow and opt-in neutral check publication. Live end-to-end verification is pending.
- React/TypeScript interface, focused graph, command search, accessible dialogs, responsive desktop/mobile review, bundled offline fonts.

## Architecture and status

FastAPI modular monolith + SQLAlchemy/Alembic; PostgreSQL deployment configuration; explicit SQLite local adapter; Celery/Redis worker entry point; React/Vite/TanStack Query/Table/React Flow frontend.

Source is never executed. Repository import does not install dependencies or run builds. The source files in samples are deliberately unsafe **data fixtures**.

See [Architecture](ARCHITECTURE.md), [Security](SECURITY.md), [CEO demo](docs/CEO-DEMO.md), [Testing](docs/TESTING.md), [Release status](docs/RELEASE.md), and [Delivery report](docs/DELIVERY_REPORT.md).
