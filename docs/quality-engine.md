# Native quality engine

ProjectTrace 1.3.3 uses Python AST and maintained Tree-sitter grammars for JavaScript/JSX, TypeScript/TSX and Java. Function metrics and source locations appear in Code Quality; findings have versioned IDs, severity, explanation and remediation. Parse failures/budgets are explicit PARTIAL coverage.

See [Native platform](NATIVE_PLATFORM.md) for exact complexity/length/nesting formulas, the cognitive approximation, duplicate-body rules and language limits. Quality gates support organization/repository profiles and new-findings scope. Full control-flow, naming/style policies, near-duplicate detection and standardized maintainability/debt ratings are deferred. The small synthetic corpus cannot establish a real-world false-positive rate.
