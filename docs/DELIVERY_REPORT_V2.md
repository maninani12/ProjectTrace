# ProjectTrace version 1.2 delivery report

4 October2026. This delivery extends the existing `ProjectTrace` folder and preserves the real workspace, both smart-waste repository records, previous snapshots, reviews and demo separation. No commit or push was made. The release is a tested local engineering-integrity/static-analysis product with a queued deployment path; production readiness is not established.

## Problems found and repaired

The updated input ZIP matched the working checkout, so a rebuild or repository replacement would have lost context without solving the problem. Seven exception lists were valid only on newer Python; tuples and a compatible Ruff syntax target now compile on3.14 and3.11. Installed dependencies still target3.14.

Core issues were shallow documentation wording, unstable snapshot claim identities, changed-file-only impact, hidden first-import queued/failed repositories, hash-only navigation, hardcoded analyzer coverage, and synchronous-only source import despite existing Celery infrastructure. Dependency coverage conflated checked/unchecked results and SBOM components could duplicate IDs or use the wrong Maven purl.

Additional review caught asynchronous advisory findings without their source evidence, duplicate package/advisory issues across manifests and native/live results, stale policy graph results after enrichment, and analyzer rule upgrades mislabeled as source drift. These now have targeted regression tests. This run's six rule-only changes in the two real repositories were retained as analysis-change records, with an audit correction; prior source/history was not deleted.

## Preserved and expanded behavior

The no-AI native pipeline remains the core: engineering source → native analysis → scoped evidence/graph → deterministic claims → drift/impact/policy → human review → audit. Native quality/security/dependency/IaC work independently of SonarQube, Wiz and live cloud connections. Northstar is labeled DEMO DATA and remains a separate organization; real source imports into it are rejected.

Claims now normalize recognized affirmative wording and aliases into atomic statements. Verifier classes cover technology/database/authentication/API/dependency/testing/CI/infrastructure/configuration with explicit limitations; unsupported meanings remain unverified or unextracted. Equivalent wording can retain a stable tenant/repository claim identity while every snapshot keeps its own version record and evidence. Cache reuse fingerprints relevant verifier input, including newly added/removed evidence. Review state carries only when evidence is unchanged; changed evidence invalidates an old exception epoch.

The graph adds supported system/component metadata, snapshots, artifacts, document sections, route/configuration/CI declarations and policy evaluations. Reverse dependency traversal includes removed base evidence and reports affected claims, docs, API/architecture nodes, findings and policies through stored edge IDs. Runtime topology, calls and cloud reachability are not invented. PR analyses include this impact plus advisory gates; live GitHub PR/check behavior still requires credentials and deployment validation.

Each analyzer reports COMPLETED, PARTIAL, FAILED or SKIPPED_UNSUPPORTED with supported files, safe diagnostics and limitations. Job lifecycle includes READY/VALIDATING/FINALIZING alongside queued/running/terminal states. Snapshot output remains atomic; native pre-output stages are durable. A completed advisory subjob cannot erase a partial native snapshot in the UI/workspace status.

## Native coverage and limitations

| Engine | Current tested capability | Material unsupported areas |
|---|---|---|
| Quality | Python AST branch approximation, function length, depth, class size, bare exceptions | Mature JS/TS/Java quality AST adapters, duplication, complete unreachable-code analysis |
| SAST | Conservative Python dynamic/assigned SQL, aliases, shell calls, unsafe deserialization, weak digest, raw HTML/file sinks, request-derived URL sinks, unsafe temp names, disabled JWT verification; limited JS/Java patterns | Complete CFG/interprocedural taint, exploitability, general authorization/randomness/framework coverage |
| Secrets | Detected token/key/assignment patterns; private keys; URL/env masking; test/example/unknown context; redaction in source, findings, claims/cache/SBOM metadata | All possible secret formats, credential validity, broad precision/recall |
| Dependencies | npm/package-lock, requirements, pyproject/Poetry, uv, Maven/Gradle, pnpm/yarn resolved-stanza subsets; exact/constraint/directness/license metadata | Complete resolution/runtime use, every lockfile dialect, complete licenses/transitive graph |
| IaC | Privileged containers, root Docker user, public ACL patterns, conservative anchored configuration checks | Most host namespaces/capabilities/IAM/ingress/encryption/securityContext/Helm semantics |
| API/architecture | Supported Python route facts, JSON OpenAPI declarations, static configuration and metadata graph | Dynamic routing/prefix resolution, complete service/call architecture, runtime validation |

CycloneDX export deduplicates component IDs, uses correct Maven purls and retains declaration/coverage metadata. It does not claim full runtime SBOM or license completeness; SPDX is deferred.

## Advisory coverage and connections

Coverage is explicit: VULNERABLE, CHECKED_NO_KNOWN_ADVISORY, NOT_CHECKED, CHECK_FAILED and UNKNOWN_VERSION. Optional OSV workers check exact versions only, cache per tenant for24hours with provider timestamps, and bound network work to32 unique queries/75seconds per job. Repeated jobs can continue remaining packages. Issues merge manifest observations, dependency/evidence links and native/live provider provenance; gates and policy graph nodes use current reviews and active exceptions. Withdrawn/reappearing advisories retain history and trigger appropriate re-review.

The fixed OSV transport was live-tested for two public package identities: lodash4.17.20 returned5 advisories and fastapi0.142.2 returned0 at the recorded time. Whole-repository live refresh and Redis/Celery transport were not executed. API behavior follows the [official OSV query contract](https://google.github.io/osv.dev/api/); no repository source is sent.

GitHub App connection/fetch/webhook/check adapters remain credential-gated and mocked in tests. AWS/Azure/GCP live inventory and SonarQube/Wiz/CodeQL/Snyk/Semgrep/Trivy evidence adapters remain unconfigured/deferred. Native static cloud evidence comes from IaC; the Cloud page distinguishes it from live context. No connection was fabricated and no external AI was called.

## User ZIP reanalysis

Both preserved real repositories were analyzed from `smart-waste-management-system-main.zip` with native1.2.0. The uploaded application was not executed.

| Result | Observed value per repository |
|---|---|
| Supported source artifacts |40 |
| Claims |74:73 implementation,1 documentation |
| Verdicts |30 static VERIFIED,43 INFERRED,1 UNVERIFIED |
| Findings |3 quality findings and1 masked test-fixture credential pattern |
| Dependency declarations |297 |
| Vulnerability coverage |268 NOT_CHECKED;29 UNKNOWN_VERSION |
| Structural graph nodes / persisted edges |117 /600, plus scoped claim/finding/dependency/evidence nodes |
| Source changes on upgrade |0 |
| Software drift |0; analyzer interpretation changes recorded separately |

The documentation claim “Database uses SQLite.” in `docs/testing.md` remains UNVERIFIED because supported static configuration evidence is inconclusive. That does not prove a contradiction. The secret finding is TEST_FIXTURE with low confidence/medium severity; its validity is untested. The other findings are branch-budget exceedances in `backend/main.py:472` and `backend/seed.py:15`, plus an80-line function limit in the initial migration atline12. No source findings imply a full clean security assessment.

## Database and queued architecture

Migration0004 adds `analysis_inputs` with job/organization/repository foreign keys, encrypted ciphertext and expiry. Existing generic snapshot/claim/finding/graph records remain intact; gradual normalized-domain evolution is still needed. Migration upgrade/downgrade/re-upgrade passes on fresh SQLite. The user's migrated database reports integrity `ok` with no foreign-key violations. A private pre-migration backup remains outside the source bundle.

`JOB_MODE=celery` queues source imports and responds202 with job ID. Broker messages contain IDs; input is encrypted with a key outside source control, expires after72hours, and is deleted on completion/cancellation. Celery beat schedules hourly cleanup. Dispatch outages retain `PENDING_RETRY` jobs. Retry/cancel, scoped actor/grant checks, bounded retries, quotas, stale-lease recovery controls and input expiry are tested by direct worker invocation. See the [Celery task guidance](https://docs.celeryq.dev/en/stable/userguide/tasks.html) for the broker delivery semantics behind this design; this release does not claim real restart/concurrency validation.

Production startup requires PostgreSQL, Redis, Celery, exact origins and an encryption key. PostgreSQL tenant locks serialize queue admission. Redis atomic limits separate login/import/analysis/Ask/webhook/provider/general policies and fail closed on outage. Safe structured logs carry IDs/stages/durations; authorized metrics expose observed job percentiles. Local tests validate contracts, not multiple replicas or deployed fairness.

## Fresh validation

| Check | Fresh result |
|---|---|
| Python compilation |3.14.3 and3.11.0 passed |
| Ruff |Passed |
| Backend |108 tests passed,98.50seconds |
| Frontend unit tests |15 passed |
| TypeScript/Vite |Build passed; main JS410.87KB/123.65KB gzip; graph180KB/58.16KB gzip, lazy loaded |
| Playwright |3 workflows passed,56.8seconds, zero page errors |
| Migration |Fresh upgrade →base downgrade →head upgrade; current user DB0004, integrity/FKs pass |
| Locked dependency audits |pip-audit no known vulnerabilities; npm audit0 |
| Synthetic safe native corpus |22/22 expected fixtures;4 false-positive traps with0 forbidden findings |

One upstream Starlette TestClient/httpx deprecation warning remains; it did not fail tests. Browser validation covers password login, fresh workspace/ZIP job/snapshot, claims/review, quality/security/masked secrets/dependencies/SBOM/IaC/evidence/graph/Ask, second snapshot/drift/impact/policy/audit, canonical URL/back/reload/hash redirects, tenant isolation, demo and mobile navigation. The first expanded real workflow ran before demo seeding. Saved images were visually inspected for evidence visibility and layout; this is not an exhaustive accessibility audit.

Security tests cover tenant/grant/RBAC/session/CSRF boundaries, malicious archives, prompt injection as data, nonexecution, secondary secret masking, review concurrency/expiry, webhook replay, queue encrypted input/retry/cancel/expiry and scoped advisory cache/graph/metrics. No claim of complete SAST/security certification or zero real-world false positives is made.

## Measured performance

Local Windows/Python3.14/SQLite or synthetic static measurements only. They are not production throughput/capacity. Nearest-rank percentiles use small samples; tail estimates require larger load studies.

| Measurement | Median | Scope / samples |
|---|---:|---|
| Real ZIP import |3625.23ms |ASGI TestClient + migrated SQLite,3 |
| Repeated snapshot cache hit |223.20ms |Same API/persistence adapter,3 |
| Incremental snapshot |2075.21ms |One synthetic Markdown change,3 |
| Workspace API |157.86ms |Authorized repo;15; p95/p99=271.12ms |
| Ask Engineering |30.94ms |Deterministic retrieval;15; p95/p99=105.26ms |
| Synthetic5-file full ZIP/static scan |0.977ms |12; no database/network |
| Synthetic5-file cached / incremental scan |0.801 /0.508ms |12 each |
| Python quality + SAST combined |0.400ms |Tiny fixture,12 |
| Single claim verification |0.01875ms |Tiny fixture,12; cache fingerprint overhead can exceed this |
| Synthetic500-file monorepo full / cached |48.57 /24.08ms |12 each; artificial fixture, not representative capacity |

The monorepo cached p95 includes a103.34ms outlier. Unchanged fixture reuse was5/5 files and3/3 claim verifications; incremental reuse4/5 and2/3. Pure graph construction, live queue delay, independent SCA refresh performance, PostgreSQL concurrency and traffic P99 are unmeasured. API import timings include persistence/graph output and should not be relabeled as pure graph timing. General false-positive rate is unmeasured despite the four passing synthetic traps.

## CEO and developer review

The overview shows analyzed scope, verified/inferred/unverified/contradicted claims, material findings, owners and the reason/evidence for a documentation conflict. The graph/impact/inspector expose file, line, rule/version, snapshot, scope, provider, secret context and review history. A queued or failed first import remains visible; absent analysis is not PASS. Static clean/unchecked results are distinguishable from runtime/cloud assurance. Canonical routes include `/claims`, `/quality`, `/graph`, `/ask`, `/audit`, and `/settings/connections`, with old-hash redirects and history/reload tests.

## Startup and production requirements

The preserved local app is available at **http://127.0.0.1:5181**; API8011. Existing `admin@projecttrace.local` credentials are unchanged. Account passwords, database/session files and encryption keys are excluded from the source bundle.

Existing local installation, separate PowerShell terminals:

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

```powershell
Set-Location 'C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace\frontend'
npm.cmd run dev
```

Use Repositories → Import repository for a new ZIP; Upload new snapshot compares against an existing repository. Keep demo and real login separate. For a fresh installation follow README to create the3.14 venv, install `requirements.lock`, migrate, optionally seed Northstar, and run `npm ci`. Seeding creates demo records only; it does not create/share the current user's credentials or import source.

Before production, run real PostgreSQL/Redis/Celery and scheduler; validate migrations, grants/cache isolation, concurrent admission, worker loss, stale lease retry, broker failure, process restart, input expiry/key rotation, restore and load. Docker/native PostgreSQL/native Redis and installed WSL were absent here, so these are genuine unverified deployment gates. Configure TLS/reverse proxy, explicit origins, private key management, monitoring/backup/retention and least-privilege authorized provider connections.

Hybrid FTS/pgvector retrieval, semantic LLM extraction, full JS/Java quality parsers/taint, comprehensive IaC/cloud risk paths, live optional security providers, advanced tenant fairness/telemetry, OIDC/SSO/SCIM, enterprise policy/retention and tamper-evident audit remain deferred. No production-ready or enterprise-ready claim is made.
