# Getting started

Follow the separate PowerShell or CMD instructions in the repository README. Python 3.14, Node 24 and the two lockfiles reproduce the tested native environment. Run Alembic before seeding; no automatic table creation occurs at app startup. Open http://127.0.0.1:5181 and enter the labeled demo.

The demo login exists only in APP_ENV=demo. For a separate local workspace, use `python -m scripts.admin` to create an operator with an interactive password, set APP_ENV=development and restart the API. This does not configure production identity. Organization creation via the CLI is implemented; self-service invitation and organization UI creation are deferred.

Import a ZIP with the repository action. Limits and unsupported-file behavior are explained before upload. The local importer is synchronous and bounded; large or private production imports require the future isolated worker/object-storage deployment.
