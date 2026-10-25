# ADR 0006 — contain repository lexical interpretation; retain independent privacy enforcement

Status: implemented for current-head executable qualification. Baseline: PR #3 head 6406745b; no merge/deployment authorized.

The original ADR 0005 source/report/archive boundary left source classification, repository globs, CODEOWNERS and small Markdown interpreters in the coordinator. These are parsers even when implemented with Python standard-library functions. Move them to the existing attested Linux worker, using prefix/metadata batches where semantics permit; preserve full bounded YAML/JSON input when later markers matter.

Keep byte/encoding admission, canonical path/count/hash/schema/tenant checks, encryption and publication in the trusted coordinator. Reusing immutable typed inventory metadata is not executing repository grammar. Never pass application credentials, database objects, keys, storage locations or bootstrap selectors into lexical work.

CODEOWNERS retains the installed supported subset and last-supported-match precedence. Unsupported rules/line truncation expose uncertainty. Runtime/budget/protocol failures stop publication rather than inventing a clean negative. Cache identity binds the source hash and policy, not a caller's fallback assignment.

A parser's own redaction is not a security control. Add a separate bounded coordinator scanner/schema guard with no regex or user patterns, including sensitive containers, invalid scalars, cycles and redacted-key collisions. Apply it to helper metadata and creation/update of published records. Supported-form compatibility is tested; preserve newlines where the previous regex damaged evidence offsets. Raw source remains authorized encrypted data, not unsanitized published evidence.

Bump the sandbox policy/cache signature for the new boundary; preserve published history, queue leases, source identity and atomic generation promotion. Do not solve global memory in this PR. Qualification requires actual kernel denials, lexical compatibility/adversarial tests, recovery/tenant/cache/privacy regressions and a green current-head workflow. See SEC002_PARSER_ISOLATION.md and PR #3 for the final evidence/verdict. Application/runtime/kernel integrity and malicious semantic output remain explicit TCB/residual assumptions.
