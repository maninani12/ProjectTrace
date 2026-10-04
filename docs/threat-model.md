# Threat model

| Asset / boundary | Threat | Current mitigation | Residual gap |
|---|---|---|---|
| Private source / browser API | Tenant leak, IDOR | Tenant filters and explicit repository grants; tests on reads/investigation/exports/audit | Live source permission inheritance and revocation synchronization |
| Browser session | CSRF, fixation, theft | Exact Origin, session CSRF, opaque rotated HttpOnly cookies, Argon2 | OIDC, distributed brute-force controls and user lifecycle |
| Repository intake / parser | Code execution, ZIP Slip, bombs | No execution; no filesystem extraction; path/symlink/ratio/size/count limits | OS sandbox and adversarial resource-exhaustion evaluation |
| SCM / webhook / worker | Forgery, replay, SSRF, unauthorized fetch | HMAC, unique delivery, provider allowlist, validated repo/SHA, source grants | Live integration, outbox dispatch, fork handling and recovery |
| Secret/source persistence | Credential exposure | Pattern detection and redaction; no external AI | Missed formats, stronger DLP, storage encryption policy, deletion/retention |
| AI boundary | Prompt injection, fake citations | Disabled external calls; bounded redacted context and citation validation contract | Provider evaluations, prompt/version quotas, semantic retrieval |
| Database/audit | Modification, loss | Transactions, uniqueness, versions, no audit-write API, local backup validation | DBA tamper resistance, PostgreSQL restore, immutable archival |
| Cloud/external tools | Overprivileged access, false attribution | Unconfigured states; normalization distinguishes external evidence | Authorized read-only adapters and live permissions tests |

Actors include legitimate engineers/reviewers, malicious repository authors, unauthenticated clients, compromised provider accounts and privileged operators. Fixtures are not trusted instructions. The local demo threat envelope is narrower than a production multi-tenant deployment.
