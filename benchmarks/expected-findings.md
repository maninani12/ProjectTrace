# Static benchmark corpus

The source text in `samples/demo.json` is data and must never be imported, installed, or executed.

| Fixture | Expected evidence |
|---|---|
| Identity base | JWT call, health route, FastAPI import; JWT claim VERIFIED |
| Identity head | SessionMiddleware configuration; JWT claim CONTRADICTED; VERIFIED → STALE → CONTRADICTED history |
| Identity SQL | PT-SAST-001 at users/search.py:3; dynamic expression, medium confidence; taint reachability unproven |
| Identity pod | PT-IAC-001 at deploy/pod.yaml:11 |
| Identity OpenAPI | GET /users/export contract UNVERIFIED; absence is not a contradiction |
| Payments | PostgreSQL INFERRED; synthetic credential masked; exact-version cached OSV advisories |
| Commerce base/head | Kafka INFERRED → UNVERIFIED; architecture review drift; Redis is not conclusive disproof of Kafka |
| Platform status | No supported findings; health route VERIFIED; FastAPI INFERRED |

Tests add command execution, unsafe deserialization, weak hashes, compound claims, parameterized SQL false-positive trap, malformed archives, path traversal, symlinks, oversized files, nested archives, nonexecution, prompt injection and unsupported questions.

Rule count is not a coverage or maturity measure. This small corpus does not establish population-level precision/recall or zero false positives. JS/Java adapters are lexical patterns, not complete parsers or taint engines. The 500-file workload measures local incremental reuse, not enterprise capacity.
