# CEO demo — 3–5 minutes

1. Open http://127.0.0.1:5181 and select **Explore Northstar demo**. Explain that the labeled fixture workspace is deterministic demo data, not a connected customer environment.
2. Overview: engineering systems, current claims and material findings are computed from analyzed fixture records. Say: “We connect engineering intent, implementation evidence and the decision to act.”
3. Select **Inspect the evidence** on the authentication story. README says JWT. Current `auth/session.py` configures SessionMiddleware. The conclusion is CONTRADICTED within that snapshot, with runtime limitations shown.
4. Select **History**: VERIFIED → STALE → CONTRADICTED. Explain that a new change triggers reverification instead of silently reusing the previous conclusion.
5. Open **Pull Requests**. PR #1842 shows changed files, claim impact, SAST/IaC review and one advisory gate. No live GitHub check is claimed.
6. Open **Findings** and inspect dynamic SQL or privileged-container evidence. The source file, line, rule, confidence and remediation are visible. Open **Dependencies** to distinguish known OSV advisories from NOT CHECKED dependencies.
7. Open **Drift**: authentication documentation and architecture statements require review. Kafka becoming unverified is not presented as proof that Kafka is absent.
8. Open **Evidence Graph**. Start with the JWT claim and follow DOCUMENTED BY and CONTRADICTED BY edges to current source.
9. Open **Ask Engineering**, ask “How is authentication implemented?”, and inspect source-backed results. Ask an unrelated question to show insufficient evidence. No language model is called in this demo.
10. Record a **CONFIRM** review with a reason, then open **Audit Trail**. The human decision is separate from the analyzer's truth status.

Key statement: ProjectTrace shows what we say, what the current evidence supports, what changed, who owns it and what needs review. It is not presented as a replacement for mature security products.

Re-run `python -m backend.seed` for idempotent initialization. It preserves existing records and reviews for matching snapshots. For a pristine disposable demo, select a **new database filename**, run migrations and seed, then restart the API against that database. Never delete a customer database to reset a demonstration.
