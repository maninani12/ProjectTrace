# ProjectTrace new-laptop development handoff

Date: 2026-11-02. Repository: https://github.com/maninani12/ProjectTrace

Development branch: `codex/scale-001-local-continuation`.
Source consolidation commit: recorded in the documentation follow-up after consolidation.
Pre-backup HEAD: `9e21509591bfa5457cc829ebd5637f95be68d573`.

**Commercial V1 — DEVELOPMENT IN PROGRESS. SCALE-001 — NOT QUALIFIED.**
This is a development backup, not a release or deployment. The owner explicitly authorized normal commits/pushes of this continuation for laptop handoff on 2026-11-02. Earlier dated no-push instructions remain historical. No main/shared-PR branch, migration execution, deployment or workflow dispatch is authorized by this backup.

## Clone the actual continuation

Run in PowerShell on the new laptop, in the parent directory where you want the project. This per-command Git setting avoids OS-dependent checkout newline translation; it does not change global Git configuration.

```powershell
git -c core.autocrlf=false clone --branch codex/scale-001-local-continuation --single-branch https://github.com/maninani12/ProjectTrace.git ProjectTrace
Set-Location ProjectTrace
git branch --show-current
git rev-parse HEAD
git log -3 --oneline
git status --short
git ls-remote origin refs/heads/codex/scale-001-local-continuation
```

The branch must match, the working tree should be clean, and HEAD must match the remote branch tip. A documentation-only follow-up can have a newer tip than the source commit above. The final migration receipt in the originating chat records the exact final tip; use the remote-tip command rather than the old 9e215095 base. Do not check out main or the shared cloud branch to continue this work.

## Architecture and preserved work

- FastAPI modular backend, SQLAlchemy models and Alembic migrations, SQLite development adapter and PostgreSQL deployment path.
- Encrypted source inventories/blob storage, isolated parser/lexical workers, retained job inputs, fenced retries, private resumable generations and atomic published pointers.
- Local durable runner for ZIP/public imports; Redis/Celery workers and scheduler for distributed/private-SCM operation.
- React/TypeScript/Vite frontend with TanStack Query/Table and React Flow. Existing APIs, tenant scopes, immutable BASE/HEAD evidence and verdict classes remain authoritative.
- Preserved work includes checkpoint/context paging investigations, indexed generation maps, bounded iterator reuse, incremental JSON export, retention/recovery changes and migration 0026; disposable graph experiments remain opt-in, rejected/unqualified evidence rather than adopted production indexes. Read the integrated qualification and policy documents before changing admission or persistence semantics.
- Product milestones include Markdown storage-privacy fence handling, public GitHub ingestion with explicit BASE selection, legacy full-SHA codeload path continuity, and native finding/quality-history continuity. Historical paths, evidence IDs, hashes and citations are not rewritten. Unknown comparison identity remains PARTIAL/NOT_OBSERVED/REVIEW_REQUIRED; unsupported evidence is never invented as a contradiction.

Current details: [progress](../PROJECTTRACE_PROGRESS.md), [release gates](COMMERCIAL_V1_RELEASE_GATES.md), [integrated SCALE-001 gate](SCALE001_INTEGRATED_QUALIFICATION_GATE.md), [checkpoint rollback/retention](CHECKPOINT_RETENTION_AND_ROLLBACK.md), and pending [ADR 0007](adr/0007-bounded-published-snapshot-segments.md). Backing up experimental code does not approve a policy or architectural proposal.

## Windows prerequisites and dependency setup

Existing supported tools: Git, Python **3.14**, Node **24**, npm and PowerShell. This handoff machine reports Python 3.14.3, Node 24.16.0 and npm 11.13.0. Python packages are locked in `requirements.lock`; frontend dependencies are locked in `frontend/package-lock.json`. Use the lockfiles, not an ad hoc dependency upgrade. No new dependency installation was needed or performed during the backup.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Push-Location frontend
npm.cmd ci
Pop-Location
```

These are the existing README/CI installation mechanisms adapted to the clone directory. They are setup instructions for the new machine, not a claim that this backup installed or tested a new environment.

## Fresh local database and launch

Only for a new isolated local installation. Do not point these commands at an existing deployment or overwrite an old data directory.

```powershell
$env:APP_ENV = 'demo'
$env:DATABASE_URL = 'sqlite:///./data/projecttrace.db'
$env:CORS_ORIGINS = 'http://127.0.0.1:5181,http://localhost:5181'
New-Item -ItemType Directory -Force -Path data | Out-Null
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The source migration head is **0026**. To populate the optional owned demo in this new database, use `.\.venv\Scripts\python.exe -m backend.seed`. Create your own account through the product; there is no shared demo password. Do not seed a restored customer workspace as a substitute for its original data.

Start the existing managed local runtime:

```powershell
& .\scripts\start.ps1
```

It uses the clone's `.venv`, defaults to `JOB_MODE=local`, checks the API/UI, and preserves existing data. UI: http://127.0.0.1:5181; API: http://127.0.0.1:8011. Stop only these managed services with `& .\scripts\stop.ps1`. See [local login/import](LOCAL_LOGIN_AND_IMPORT.md).

For separate foreground terminals, the existing entry points are:

```powershell
$env:JOB_MODE = 'local'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

```powershell
Set-Location frontend
npm.cmd run dev
```

`frontend/vite.config.ts` proxies `/api` and `/health` to port 8011. Optional names `PROJECTTRACE_API_URL` and `PROJECTTRACE_UI_PORT` control the development endpoints.

## Environment and secrets

`.env.example` is a safe name/template reference, not a populated credential file and not a promise of automatic dotenv loading. Use process environment variables or the existing approved operator-owned `data/local-settings.json`/`scripts/start.ps1 -Config` mechanism. The loader rejects shell commands, raw config keys and unsupported names. Never commit actual `.env`, keys, credentials or local settings.

| Area | Names (no secret values) |
|---|---|
| Local runtime | `APP_ENV`, `DATABASE_URL`, `JOB_MODE`, `CORS_ORIGINS`, `OSV_ENABLED` |
| Encrypted inputs | `ANALYSIS_INPUT_KEY`, `ANALYSIS_INPUT_KEY_FILE`, `ANALYSIS_PREVIOUS_KEYS`, `ANALYSIS_PREVIOUS_KEYS_FILE`, `ANALYSIS_KEY_FILE` |
| Source storage | `SOURCE_BLOB_BACKEND`, `SOURCE_BLOB_DIR`, `SOURCE_UPLOAD_DIR`; optional `SOURCE_S3_*`, approved `AWS_*_FILE` credentials |
| Broker/deployment | `REDIS_URL`, `REDIS_URL_FILE`, `DATABASE_URL_FILE`, `POSTGRES_PASSWORD` |
| Optional SCM | `GITHUB_APP_ID`, `GITHUB_INSTALLATION_ID`, `GITHUB_PRIVATE_KEY_FILE`, `GITHUB_WEBHOOK_SECRET_FILE`; connection-specific approved `SCM_*_FILE` |
| Optional identity/audit | `OIDC_*`, `OIDC_CLIENT_SECRET_FILE`, `AUDIT_CHECKPOINT_KEY_FILE`, `AUDIT_CHECKPOINT_KEY_ID` |
| Parser/testing | `PROJECTTRACE_PARSER_ISOLATION`, `PROJECTTRACE_E2E_ISOLATED_API`, `PROJECTTRACE_PYTHON`, `PROJECTTRACE_E2E_RESULTS` |

See `.env.example`, `backend/settings.py`, and `scripts/dev_runtime.py` for the exact supported names. Public ZIP/GitHub source analysis needs no private GitHub App, cloud/LLM credential or arbitrary repository code execution. Optional provider features remain unqualified until separately configured and tested.

SQLite/local mode does not require Redis. Distributed deployment uses PostgreSQL, Redis, Celery workers and beat, a shared operator-managed encryption key and consistent blob storage. `compose.yaml` defines PostgreSQL 17 and Redis 7 with required operator secrets, migration/seed/API/worker/scheduler/frontend services. Do not run the stack against old volumes without its upgrade/backup procedure. Production configuration additionally requires verified PostgreSQL/Redis TLS, explicit HTTPS origins and Celery; local demo defaults are not production settings.

The existing Windows worker commands are in README (`python -m celery -A workers.tasks worker --pool=solo --loglevel=INFO` and its beat command). Solo mode is a local Windows option, not production worker qualification. See [broker acceptance](BROKER_RECOVERY_ACCEPTANCE.md) and [upgrade instructions](UPGRADE_ENTERPRISE_HARDENING.md).

## Verification commands and actual evidence

Initial fast checks after installation:

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend analyzers integrations workers scripts tests integration_tests
.\.venv\Scripts\ruff.exe check backend analyzers integrations workers tests scripts integration_tests
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m pytest -q tests/test_configuration_drift.py --basetemp .\data\new-laptop-configuration-tests
Push-Location frontend
npm.cmd test
npm.cmd run build
Pop-Location
git diff --check
git status --short
```

Pytest owns and may recreate `--basetemp`; use only a dedicated disposable directory, never an existing database/source directory. Windows testing does not exercise required Linux Landlock/seccomp denial guarantees. Browser tests need Chromium installed (`npx.cmd playwright install chromium` from `frontend/`) and Vite running. The existing isolated API fixture is enabled by `PROJECTTRACE_E2E_ISOLATED_API=1`; set `PROJECTTRACE_PYTHON` to the new clone's absolute `.venv\Scripts\python.exe`. It creates disposable databases, not a production workspace.

### Recorded before this backup (not rerun for the handoff)

- Latest native/quality continuity source: **59 backend passed, 0 failed/errors/skipped**, one deprecation warning, 665.75 seconds; **54 frontend tests**, **2 Chromium tests**, production build **42 routes**. The 101-pass wider selection was an earlier intermediate source. Read [the exact source hashes/commands/individual outcomes](evidence/COMMERCIAL_V1_NATIVE_QUALITY_CONTINUITY_20261031.json) and its compressed raw reports.
- Read-only checks covered **45 owned SQLite databases**, zero FK violations/invalid pointers, **82** matching published counter checks and **16** unchanged metric-direction checks. These are historical disposable fixture checks, not a backup of those databases.
- The browser native-history workflow uses real owned API analysis/history plus a deliberately controlled uncertainty-overview fixture. It is not live GitHub or historical-provider browser qualification.
- Earlier Windows full-suite result: **1,015 passed, 91 skipped**, on earlier source. Exact skip identifiers/reasons were not retained. This is not a full-suite result on the consolidated backup.
- Historical Ubuntu parser/worker selections: **81 passed**, plus **9 configuration-drift passed**. Docker SEC-002 build/restricted probe passed against source digest `e100b089ef6a5ddaa27327bed51097d94b81aa44d5cf2ff1484dfa27d857eb07`, image `sha256:1bc662ae93992f671f766f20c404f64e03c9277970e6d937c8241d127b497914`. These predate subsequent product changes. Selected original WSL receipts are preserved portably in [the historical evidence bundle](evidence/LINUX_PARSER_SEC002_HISTORICAL_20261030_PORTABLE.json.gz); earlier BLOCKED records are historical and superseded by the later same-source container PASS.

### Executed during this backup

Repository/remote/divergence and ignored-file inventory, source/evidence secret review including decompressed reports, Ruff over all owned Python directories, compilation over those directories, `alembic heads` (0026), whitespace/staged-content/completeness checks and remote commit verification. The migration receipt records exact outcomes. No long pytest suite, current-tree Linux/Docker gate, full pinned workload or live provider was rerun just to back up unchanged source.

### Open release gates

- Current consolidated source needs a new full manifest and actual Linux required-mode parser/worker + Docker SEC-002 execution. WSL alone is insufficient; use the exact existing `.github/workflows/ci.yml` commands and real worker IPC/denials. Historical passes do not certify this commit.
- Live public GitHub BASE/HEAD/native-history workflow, real PostgreSQL/Redis/Celery acceptance for this delta, complete rule/vendor corpus and cross-version in-flight receipt semantics remain open.
- SCALE-001 still requires cold/warm/incremental complete outputs, deterministic comparisons, cancellation, memory/disk exhaustion, worker termination/recovery, duplicate delivery, tenant and atomic publication gates under **768,000,000 bytes with zero swap** and the unchanged pinned **21,636-file** workload. Preserve the **64,000,000-byte checkpoint**, **256,000-node generation-map**, **1,000,000-node sanitizer**, time and other existing guards. No experiment or local fixture pass qualifies this track.
- Schema 0026 downgrade intentionally fails closed with retained v2 receipts/pages. Expiry is not permission to relabel history as v1. ADR/policy review and migration/rollback approval remain separate.

## What GitHub does not back up

Git preserves safe source, tests, migrations, configuration templates, CI and sanitized evidence. It deliberately excludes existing accounts, imported source, encrypted data, secret keys and runtime state.

Retained local-only locations on the old laptop:

- This checkout's `data/` (including `analysis-input.key`, `source-blobs/`, `source-uploads/`, any database/runtime/settings/logs); other old checkouts may hold their own data, including `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`.
- `.venv` environments; `frontend/node_modules`, `dist`, `test-results`, build caches; pytest/ruff/Python caches and ignored logs under `work/`.
- Windows raw profiling and original disposable databases under `C:\Users\sai krishna\Documents\Codex\2026-10-25\you-are-taking-over-projecttrace-development\work`, and temporary fixture directories named in receipts.
- WSL historical source copy `/home/sai_krishna/projecttrace-linux-qualification-20261030-2zdhvg3c` and raw evidence `/home/sai_krishna/projecttrace-linux-evidence-20261030-yqe4r2f8`. Portable receipts do not include the virtualenv, Docker image layers or complete original Linux source copy. Remaining raw build/install/image-inspection logs stay there.
- Local backup audit files in the Windows work root's `github-handoff-20261102` directory, including inventories and final local/remote-tip receipt. They contain no published application data.

No excluded file was deleted. If you need existing users/imported repositories on the new laptop, perform a separate consistent, encrypted transfer of database + source blobs + original key ring/operator secrets through a trusted channel. Stop/drain writers or use the database's supported consistent backup, retain originals, and restore to an isolated target before changing pointers. Never put that recovery set in GitHub. A fresh clone alone cannot decrypt or recreate old application history. Do not copy Git credential stores or secret values into this guide.

## Next engineering milestone

Create a complete manifest for the consolidated cloned source, verify an isolated Linux copy, and run the existing required parser/worker and SEC-002 container gates against that exact copy. Then validate the authorized real public-provider BASE/HEAD/native-history workflow and remaining distributed/service gates. Preserve unknown evidence semantics and all guards. No generic scanning framework, rejected graph-index adoption or release-readiness claim follows from this backup.

Backup audit and validation receipt: [GITHUB_HANDOFF_20261102.json](evidence/GITHUB_HANDOFF_20261102.json).
