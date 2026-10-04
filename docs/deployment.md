# Deployment

The supplied Compose stack defines PostgreSQL 17, Redis 7, migration/seed jobs, FastAPI, Celery and an unprivileged nginx frontend. Only the frontend is published to 127.0.0.1:5181. Set a locally generated URL-safe POSTGRES_PASSWORD before `docker compose up --build`. Do not expose this demo Compose configuration publicly.

Docker is unavailable in the execution environment, so Compose, container builds and PostgreSQL/Redis behavior are unverified. The API migration runs before seeding/startup. No deploy, remote repository push or cloud resource creation was performed.

Production requires TLS, APP_ENV=production, explicit CORS origins, tested PostgreSQL migrations/restores, secure identity, repository permission inheritance, secret injection, object storage/retention, isolated parsing, distributed limits, queue monitoring, pinned/scanned images, staging smoke/load/security gates and incident ownership. Providing a container file does not meet those release gates. Infrastructure should be managed declaratively when a production environment is selected.
