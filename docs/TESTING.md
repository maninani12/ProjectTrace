# Validation and test scope

Backend pytest fixtures create isolated temporary SQLite databases. Deployment uses Alembic; test-only metadata creation is not a production startup dependency. Migration tests separately run a fresh upgrade, rollback and re-upgrade, including provider uniqueness.

Tests cover demo evidence provenance and status transitions, imports vs runtime proof, compound claims, safe SQL, static security rules, no code execution, ZIP traversal/symlinks/limits, prompt injection, tenant/ACL/RBAC/CSRF/IDOR, session logout, secret redaction, review concurrency/audit, idempotent analyses, webhook signature/replay, exception expiry, grounded/unsupported questions, fake citations and incremental content reuse. GitHub tests use mocks and do not count as live provider verification.

Vitest/React Testing Library cover status text, login semantics and actionable login errors. Playwright covers the desktop CEO/developer flow, confirmation review and audit, claim filtering, source inspection, PR gate, all major pages, console exceptions, width overflow, mobile navigation and unsupported investigation. These are critical smoke workflows, not exhaustive frontend coverage.

`scripts/benchmark.py` records repeated static-analysis timings. `scripts/api_benchmark.py` performs a bounded four-client localhost workload. Real PostgreSQL migration/query behavior, Redis outage/retry, non-root Linux prefork and forced-crash lease recovery now have validation evidence. Sustained production load, saturation/fairness, provider outages, large unique monorepos and production restore remain unverified. The native benchmark command is `python -m scripts.benchmark_analyzers --output <absolute-output.json>`; its synthetic labels do not estimate real-world precision.

The selected dependency lockfiles are audited with pip-audit/npm audit. Audits are time-specific and do not certify future vulnerability status. `benchmarks/expected-findings.md` documents the safe corpus.

Current test counts, failures resolved during development, browser screenshots, benchmark confusion labels and real-runtime results are recorded in [FINAL_PRODUCT_VALIDATION.md](../FINAL_PRODUCT_VALIDATION.md).
