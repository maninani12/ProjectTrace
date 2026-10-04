# Development conventions

Run backend tests, Ruff, TypeScript build, frontend tests and browser workflows before submitting changes. No commit or push was made automatically.

Every analyzer rule needs a stable ID/version, rationale, severity/confidence distinction, location and remediation. Add a positive fixture and a false-positive trap. Document unsupported coverage. Never treat absence as direct contradiction without conclusive scoped evidence.

Never execute, install or build imported repositories. Keep provider networking in connectors; keep parsers data-only. Every resource API needs organization and repository authorization tests. Never accept model-generated citations outside the retrieved authorized set.

Every schema change requires an Alembic migration and upgrade/rollback tests. User-visible metrics must be computed from stored data or actual measurements. No proprietary rules or provider APIs may be invented. Keep live verification distinct from mocked contract tests.
