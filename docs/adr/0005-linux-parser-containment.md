# ADR 0005 — Attested Linux source parser containment

Status: implemented for qualification; overall SEC-002 is not yet closed.

Start from exact verified PR #2 head `6d937e3c25384aecc508d17943f530f8c22dc6fc`. Stack `codex/linux-parser-isolation` on `codex/broker-recovery-hardening`; do not merge, rewrite or retarget PRs #1/#2.

## Decision

Use short-lived owned processes with Landlock ABI 3+ read-only runtime access and a seccomp syscall allowlist, empty ambient capability sets, no-new-privileges, no dumpability, bounded resources and controlled IPC. This avoids requiring privileged namespaces/SYS_ADMIN in application containers. Namespace-only flags, RLIMIT and Windows Job Objects are not accepted as equivalent controls.

Bootstrap trusted installed code before the boundary, then install and test actual denials before input. Default Linux/production processing is required mode; explicit development mode is unqualified and prohibited in production parsing. Old helper entry points are development-only; required routing cannot silently fall back.

Move Python AST/metrics/flows/identity as well as language/IaC parsing, manifests, documentation/OpenAPI and coverage parsing across the boundary. Keep database/source authorization, encrypted storage, generation publication and job fencing in the coordinator. Preserve the evidence contract and include the isolation policy in cache signatures. Pure-Python bounded IPC decoding avoids exposing the native JSON scanner to helper packets; IPC and Python/kernel primitives remain trusted.

Do not place HCL's default pickle cache inside the trusted bootstrap: construct the same installed grammar with cache disabled. Do not pass application credentials, source object paths or writable application mounts to parsers. No new database migration or UI redesign is required.

## Trade-offs and open scope

Process startup/serialization overhead is measured against an owned baseline, not excused by larger outcome timeouts. Whole global computation is not made memory bounded; that remains SCALE-001. Runtime code/resources must be immutable and secret free. Kernel/outer-container Landlock availability and real image enforcement are mandatory acceptance prerequisites.

The call-graph inventory found archive ZIP/zlib ingestion still in the coordinator. Relabeling it as a resource limit would not close its exploit boundary. The guide records it as an explicit remaining SEC-002 gate; the overall verdict stays partial until that streaming archive boundary is implemented and qualified. See `SEC002_PARSER_ISOLATION.md` for exact reviewed scope, controls, tests and residual trust assumptions.
