# ADR 0001 — modular monolith and scoped relational records

Accepted for the local MVP: React/FastAPI with a shared SQLAlchemy/Alembic database; tenant and repository columns on domain records; JSON domain payloads for early evolution; dedicated static-analysis modules and optional Celery provider workers. This minimizes service coordination while preserving explicit security boundaries.

PostgreSQL is the deployment target. SQLite is an explicit native test/demo adapter because Docker is unavailable. Evidence graph edges are relational documents rather than a separate graph service. Normalize high-query-volume entities and enforce richer compound tenant constraints before production; the full master entity schema is not complete.
