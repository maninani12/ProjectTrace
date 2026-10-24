# PR #1 browser CI recovery

Original run: [40116254951](https://github.com/maninani12/ProjectTrace/actions/runs/40116254951), head `b3a423d`. Backend 607 passed / 2 platform skips; browser 12 passed / 4 failed / 10 fixture-dependent skips. No artifacts were uploaded by the old workflow, so its screenshots/traces cannot be recovered from GitHub.

## Reproduction and evidence

[40118834658](https://github.com/maninani12/ProjectTrace/actions/runs/40118834658) repeated the same sources on Python 3.14 with Chromium, adding HTTP diagnostics and retained artifacts. Browser result: 13 passed / 3 failed / the same 10 skips. The native test passed on this repetition; the admission failure moved to Phase 2. Artifact `browser-evidence-40118834658` preserves network traces, page snapshots and service logs.

| Original failure | Evidence and diagnosis | Correction |
| --- | --- | --- |
| Native Platform polling | The original helper discarded status/body, so its exact failed response is unrecoverable. The unchanged native profile/reanalysis scenario passes in the instrumented repeat. This is consistent with the order/timing-dependent shared admission window: the identical job-reader helper fails with 429 in Phase 2, and controlled API/browser regressions demonstrate that an otherwise authorized job returns 429 after the shared general budget is consumed. No reproducible native authorization, publication or profile defect was found. | Fresh owned backend/admission state for every acceptance test; retain exact HTTP diagnostics. Preserve native assertions. |
| Phase 2 polling | Trace and error context record `GET /api/record/{job_id}` → **429**, `Retry-After: 60`, body “Rate limit reached.” All tests shared one API process and loopback IP. The 240/min general budget was consumed by preceding UI/graph reads and job polling. | Isolate test application state; do not increase or bypass production limits. |
| Public ZIP dialog | Page snapshot shows **Workspace access unavailable** and a rate-limit alert; trace records `/api/auth/me` → **429**. Registration was not proof that the later workspace identity read succeeded. The accessible dialog name/CTA were not the defect. | The same owned application isolation. Keep the actual signup/dialog/archive assertions. |
| Real import Drift | Trace shows the second archive POST returning **202**, then Drift requesting the **old snapshot ID**. Failure snapshot says **Correlating evidence**. The generic “Analysis completed” assertion could match the prior capture before the new job entered its active state. | Await the specific returned job, assert a different HEAD and the expected BASE, then require the Drift request to contain that exact HEAD and return real drift records. Keep the non-empty table and impact assertions. |

An earlier diagnostic push run was superseded by its PR event and canceled. Its 502 proxy failures coincide with the API shutdown and are excluded as product/root-cause evidence. Expected PostgreSQL tenant-FK rejection messages belong to passing isolation-negative tests; no database boundary was relaxed.

The first isolated focused run (`40119778641`) passed Native, Phase 2 and public ZIP import. Real-import then exposed Chromium response-body cache eviction while reading the streamed-upload receipt. Reading immediately at response time also failed in `40120169267`. The test now forwards the unchanged browser upload through `route.fetch()` to the real API, retains that API response, and fulfills the browser with the same real response. No receipt, status or finding is mocked. Exact job/snapshot and visible Drift assertions remain mandatory. Both intermediate failures remain in Actions rather than being counted as passes.

## Implementation boundaries

`frontend/e2e/fixtures.ts` starts the real migrated/seeded application in a unique OS-temp database with separate encrypted source/key/upload paths. Only CI sets `PROJECTTRACE_E2E_ISOLATED_API=1`. The fixture refuses external/private QA targets and an already occupied API port. It stops only its own child, retains temporary databases for recovery, and uploads logs rather than databases, keys or session data. Browser contexts remain Playwright's normal fresh contexts. Existing test bodies only switch their `test` import to this fixture.

Two controlled browser regressions exhaust the actual admission window, verify the 429/fail-closed UI, then verify that the next owned application has fresh data/admission. A backend regression checks authorized job visibility before exhaustion and 429 for both job and identity reads afterward. The production 240/min ceiling, authentication, tenant authorization and Redis policy are unchanged.

The workflow runs browser acceptance independently from backend/frontend/image validation. It runs the four original cases first, then the complete suite; focused and full JSON results and artifacts are retained separately. Duplicate push/PR events share a concurrency group; superseded attempts remain visible as canceled. No test is deleted, disabled, loosened or given a longer outcome timeout.

## Validation and retained gates

Local checks: frontend build and 49 unit tests passed; E2E TypeScript is checked separately; the rate/isolation/auth/determinism/generation selection passed 50 tests before the added quota regression, which independently passed with the other three admission tests. Chromium installation remains unavailable in this coding environment (download returns an invalid archive), so browser acceptance is evaluated in the real GitHub runner. Do not label local browser, PostgreSQL or Docker runs as passed.

Final acceptance is the complete green Actions run on the current PR head, including PostgreSQL backend tests, benchmarks, migration round-trip/seed, dependency audits, frontend build/unit tests, focused/full browser suites and both Docker image builds. The PR description and current check links record the final measured results.

The ten existing browser skips require explicit preserved fixtures: three Administration and two Learning cases need `PROJECTTRACE_ADMIN_QA`; one large-workspace and three repository-reliability cases need `PROJECTTRACE_LARGE_ACCOUNT`; the prerender/offline case needs `PROJECTTRACE_STATIC_BASE_URL`. These conditions and assertions remain unchanged. New quota tests run in owned CI and refuse destructive pressure against external/private QA targets.

Real Redis/Celery recovery, large-repository global-memory limits, full parser filesystem/network isolation, representative accuracy and production/DR qualification remain independent release gates. No migrations, production records, existing product modules or main-branch state are modified by this recovery.
