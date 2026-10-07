# Controlled 100-PR measurement

Evidence: `benchmarks/pr-load-100.json`, produced by `python -m scripts.benchmark_pr_load --work-dir <fresh-private-directory> --output <report.json>`. Only owned inert fixture text is parsed. No customer program, build, test or IaC is executed.

The measured run sent 100 signed PR events to the actual per-connection FastAPI webhook. It added ten identical delivery replays and five distinct deliveries repeating an already current SHA: 115 HTTP requests, 105 distinct durable receipts and 100 jobs. Twenty queued heads were superseded. Four controlled threads invoked the production GHES worker and database scheduler; 80 native snapshots completed, 40 in each organization, with no observed scope mismatch or worker failure. An owned subprocess claimed work and exited with code 73; after deliberately advancing its lease expiry, recovery requeued one job. Old attempt tokens cannot release or publish a replacement attempt.

| Measured quantity | Result |
| --- | ---: |
| Webhook p50 / p95 / p99 | 46.317 / 75.997 / 82.640 ms |
| Queue wait p50 / p95 | 26,135.814 / 45,843.272 ms |
| Worker attempt p50 / p95 | 1,423.642 / 3,674.150 ms |
| Complete test wall time | 54.837 s |
| Deferred worker attempts | 6 |
| Observed worker failures | 0 |

The final controlled adapter implements `iter_snapshot`, entering the production streaming capture path: 80 tenant-encrypted inventories and 80 inventory-backed snapshots completed. It exercises final source-I/O reuse, syntax-failure cache admission, deferred full snapshot serialization, scoped comparison reads, batched capture and initial snapshot job linkage. The report records current implementation hashes. Owned files, keys and ciphertext stay in its isolated private directory. The Windows Job Object bounds this run to 768 MiB committed memory and 600 user CPU seconds; it does not supply filesystem/network isolation.

Quantiles use the lower observed order statistic at floor((n - 1) * p), as implemented by the helper. The report retains sample counts; these local observations are not production percentile guarantees.

The earlier bounded-mapping adapter measurement is retained in `benchmarks/pr-load-100-before-finalization-release.json`; the pre-batching result is retained in `benchmarks/pr-load-100-before-graph-batching.json`. The final run overlapped the 50,000-file benchmark on the shared desktop in a separate database. This measures host contention, not a single mixed production queue. These are local TestClient/SQLite measurements, not a network SLA. Attempt timings include claim races and deferred deliveries. Four busy threads do not prove four saturated CPUs. The test accepts the event burst before draining it; it does not establish sustained concurrent network ingestion while a large analysis runs. Real Redis transport, Celery prefork crash timing, PostgreSQL contention, TLS ingress, sustained arrival rates and representative customer repository throughput remain **UNMEASURED** in this environment.

The scheduler uses short serialized database admission/claim transactions, tenant round robin, FIFO eligible work, and global/tenant/repository running ceilings (defaults 4/2/1). Pending admission is separately bounded (10,000/1,000/200); limits are operator-configurable within enforced ranges. Native, large, SCM and advisory tasks have separate Celery routes. Queue claims, latest PR heads and cancellation flags are indexed projections of existing authoritative job Records. Per-connection SHA suppression preserves every distinct delivery receipt. Returning to an older SHA creates a new head generation rather than reviving a cancelled attempt.

Running cancellation is cooperative at bounded pipeline stages; a slow parser/provider call may finish its timeout before stopping. Stage heartbeats renew leases. Recovery and periodic queued-job redispatch tolerate broker dispatch failures; duplicate delivery does not bypass the fenced claim. Check publication rechecks connection version, installation/repository access, actor authorization, tenant egress and latest head immediately before the provider request. A concurrent head arriving after that final check cannot undo an HTTP request already in flight; checks are addressed to their immutable SHA and must remain advisory.

Tests: `tests/test_fair_scheduling.py`, `tests/test_queue.py`, `tests/test_ghes.py`, `tests/test_advisory_worker.py`. Local SQLite serializes writers and is not the production concurrency qualification adapter.
