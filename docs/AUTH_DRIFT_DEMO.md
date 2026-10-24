# Authentication drift: senior architect demonstration

## What this proves

ProjectTrace compares a documentation claim against captured source syntax, retains the old verdict, and explains why a later implementation contradicts the unchanged document. This is static engineering evidence; it does not prove deployed authentication behavior. No imported source, dependency installer or build is executed.

| Capture | README contract | Captured implementation | Expected verdict |
| --- | --- | --- | --- |
| BASE | Authentication uses JWT. | `jwt.encode(...)` in `app.py` | VERIFIED |
| HEAD | Same unchanged contract | `app.add_middleware(SessionMiddleware, ...)` in `app.py` | CONTRADICTED |

The canonical input is `samples/auth-drift.json`. These are deliberately small static inputs, not a deployable authentication service. Settings are unresolved, and signing/session keys are never supplied. The existing Northstar identity fixture remains available and unchanged.

## Five-minute review

1. In a freshly seeded private evaluation instance, choose **Explore Northstar demo**, then **Engineering Changes**. Select the Identity change (PR 1842). Existing seeded databases are not rewritten: use a new disposable instance to obtain the added comparison references.
2. Select **Inspect engineering change**. Read the explicit BASE and HEAD snapshot IDs, the original JWT claim and the VERIFIED / CONTRADICTED verdicts. Each side has its own captured explanation.
3. Select **Inspect original documentation**. The unchanged claim is visible in its original source artifact. Close the inspector.
4. Select **Inspect BASE source**, then **Inspect HEAD source**. Inspect the actual captured JWT call and session middleware configuration, and compare their SHA-256 hashes. These buttons use the existing authorized evidence reader.
5. Select **Inspect HEAD claim**, then **History**. Confirm VERIFIED → STALE → CONTRADICTED. The old snapshot and claim have not been edited. Continue through the existing Claim Ledger, Evidence Graph, Code Quality, Security, Administration and Learning navigation as usual.

For a clean automated demonstration, start the existing API with `JOB_MODE=local` against a **new disposable database upgraded to migration 0025**. Do not downgrade or replace a populated database. Then, from the repository root:

```bash
python -m scripts.auth_drift_demo > auth-drift-proof.json
```

The script accepts only an HTTP loopback API origin (`--url http://127.0.0.1:8011` by default). It creates a fresh synthetic organization, captures BASE and HEAD through the real API, waits for durable queued jobs, retrieves both authorized source records, checks the verdicts and logs out. It leaves all captures in place. Generated account credentials, cookies and CSRF tokens are never printed. Output contains only synthetic fixture source, captured IDs, hashes and verdicts. Use the UI flow or browser test for visual presentation; the script's temporary account is not intended for interactive login.

With the API and Vite running on their existing private loopback ports and Chromium installed:

```bash
cd frontend
npx playwright test e2e/auth-drift.spec.ts
```

This browser test creates its own organization, accepts synchronous or queued analysis, inspects both source versions and claim history, and records comparison/BASE/HEAD screenshots under its Playwright output directory. It must actually pass before its screenshots can be treated as acceptance evidence.

## Accuracy checks and limits

- JWT call syntax is VERIFIED; only an import is INFERRED. Missing source, comments, strings and unparsable source without supported signals are UNVERIFIED, not automatically contradicted.
- Session configuration contradicts JWT only within the scanned static scope. If affirmative JWT and session syntax both exist, the JWT claim remains supported. This is not proof of exclusive authentication across omitted services.
- Discovery order does not affect evidence ordering or verdict fingerprints. Removal of evidence invalidates a cached affirmative result.
- Historical drift requires an explicit BASE. A first capture with a contradiction is a consistency finding, not a historical change.
- Comparison references are bounded to 50 changed documentation claims and eight source references per side, with truncation flags. The original claim/evidence records remain authoritative. Old projections without this optional field still render normally.
- Interrupted unpublished comparisons stay private. Recovery resumes the existing generation and publishes one comparison; cross-tenant requests for the comparison, snapshots, claims and source return 404.

See `AUTONOMOUS_AUDIT_2026_10_24.md` for executed checks and unresolved release gates. Passing synthetic fixtures cannot establish representative real-world accuracy or production readiness.
