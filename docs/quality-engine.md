# Quality engine

Python AST rules approximate branch complexity and flag functions exceeding 80 lines. Rules include ID, version, category, severity/confidence, source location, rationale and remediation. Parse errors are explicitly reported as incomplete analysis instead of silently passing.

No maintainability or technical-debt score is invented. JS/Java coverage is currently conservative security-pattern scanning, not a complete quality AST adapter. Duplication, precise control flow, naming policy and broad language support remain future work. The fixture corpus is too small to establish general false-positive rates.
