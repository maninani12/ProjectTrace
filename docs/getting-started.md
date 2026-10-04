# Getting started

Follow the separate PowerShell or CMD instructions in the repository README. Python 3.14, Node 24 and the two lockfiles reproduce the tested native environment. Run Alembic before seeding; no automatic table creation occurs at app startup. Open http://127.0.0.1:5181 and enter the labeled demo.

The demo login exists only in APP_ENV=demo. For a separate local workspace, use `python -m scripts.admin` to create an operator with an interactive password, set APP_ENV=development and restart the API. This does not configure production identity. Organization creation via the CLI is implemented; self-service invitation and organization UI creation are deferred.

Import a ZIP with the repository action. Limits and unsupported-file behavior are explained before upload. The local importer is synchronous and bounded; large or private production imports require the future isolated worker/object-storage deployment.

In local/demo environments, POST /api/auth/register can create an empty organization and owner with a 16+ character password. It is disabled in production. Sign in to that organization using the email/password fields; the Northstar demo login remains a separate workspace. ZIP imports are rejected in the demo organization to prevent mixing data. On Repositories, choose Import repository for a first ZIP and Upload new snapshot for subsequent versions of that repository. The global selector scopes native module pages.
