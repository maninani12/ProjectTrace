# ProjectTrace 1.3.3 release status

Native quality/security/secrets/dependency/SBOM/IaC/static-cloud/claim analysis is independent of competitor products. The current release preserves version 1.2 and adds versioned rule profiles, syntax metrics, bounded flow traces, typed cloud assets, static risk paths and scoped PostgreSQL full-text/graph retrieval.

Passed: baseline and fresh backend/frontend/browser checks; locked dependency audits; SQLite and real PostgreSQL migration upgrade/rollback/re-upgrade; real Redis/Celery duplicate delivery, broker outage/retry, cancellation/expiry, non-root Linux prefork and forced-crash natural lease recovery. Clean packaging excludes credentials, data, caches and build artifacts while retaining intentional inert browser ZIP fixtures.

Not passed: Docker/Compose/image scan and exact shipped image versions; production restore; real AWS/GitHub account end-to-end verification; Azure/GCP live adapters; complete multi-language taint/control-flow, IAM effective permission/escalation and deployed runtime attack paths; enterprise identity/member lifecycle; parser OS sandbox; managed object storage/key lifecycle; semantic vector retrieval; sustained capacity/fairness and population precision/recall.

The release is usable locally and has real service validation. It does not satisfy the entire enterprise master specification or all production release gates. [FINAL_PRODUCT_VALIDATION.md](../FINAL_PRODUCT_VALIDATION.md) is the authoritative current evidence report; earlier repair/delivery reports are historical.
