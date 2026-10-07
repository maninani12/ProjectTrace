# Language support

| Language | Parser | Quality / security maturity | Main boundaries |
| --- | --- | --- | --- |
| Python | CPython ast | PARTIAL; selected syntax metrics, reliability and security rules; bounded local flows | No complete type/CFG/framework or cross-file taint model; AST still in-process |
| JavaScript / JSX | Maintained Tree-sitter grammar | PARTIAL; syntax metrics and selected hotspots | Lexical scope models are bounded; no complete cross-file flow |
| TypeScript / TSX | Maintained Tree-sitter grammar | PARTIAL; syntax metrics and selected hotspots | No TypeScript compiler/type resolution; framework models incomplete |
| Java | Maintained Tree-sitter grammar | PARTIAL; syntax metrics and selected hotspots | No complete overload/type or cross-file flow; arbitrary methods named eval are not treated as builtins |
| Go, Rust, C/C++, C#, Kotlin/Kotlin scripts, Ruby, PHP, Shell, PowerShell, SQL, Vue, Svelte, Swift, Scala, Dart, R, Lua, Perl and Make | No native semantic parser | UNSUPPORTED | Explicit extensions/filenames preserve inventory and gaps; zero findings never establishes safety |
| Terraform, CloudFormation, Kubernetes, Compose, Dockerfile | Bounded HCL2, safe YAML/JSON, native Dockerfile instruction parser | PARTIAL; selected configuration checks | STATIC declared configuration, runtime UNOBSERVED; no template execution, module fetching or deployment assurance |

Trust & Coverage distinguishes file inventory, parser completion and semantic maturity. Failed parsing, generated/vendor exclusions, policy exclusions, binary and size skips are visible. Unknown LOC remains unknown. Rules and parser versions are captured with the snapshot. Benchmark evidence and voluntary review feedback are separate; no rule has representative production precision or default blocking qualification from the present purposive corpus.

Analysis never runs customer tests, builds, dependency installations or scripts. IaC and maintained grammar parsing use bounded helper processes; a complete OS sandbox is not verified on Windows. No external LLM receives source. Imported coverage reports are supplied measurements, not tests executed by ProjectTrace.

Unknown text extensions and ambiguous filenames are `UNKNOWN` / `UNSUPPORTED`, not silently non-source. A bounded first-line shebang can label a language, but does not select a new parser: extensionless Python/Node scripts remain unsupported. Known documentation/configuration names and extensions remain non-source. Binary formats/NUL-containing UTF-8 payloads are `BINARY`; non-UTF-8 programming source, including UTF-16, is an explicit unsupported encoding gap. Unsupported encoding, binary and oversized files have unknown LOC.

The source denominator includes first-party programming source, tests/examples, unsupported/unknown source, unsupported source encoding and oversized source. It excludes vendor/generated/policy exclusions, binary and known documentation/configuration/IaC. IaC parsing is reported separately by format. `source_analysis_percent = 100 × source_files_parsed / source_files`, captured to six decimal places; no source denominator yields null (not measured). Gates compare the unrounded ratio. A 100% syntax-parser measurement can pass that specific condition while every current analyzer retains PARTIAL semantic maturity.

Active file states are PARTIAL, UNSUPPORTED, PARSE_FAILED, EXCLUDED_GENERATED, EXCLUDED_VENDOR, SKIPPED_SIZE_LIMIT, BINARY and IGNORED_BY_POLICY. SUPPORTED is reserved for a future qualified mature analyzer; no current analyzer emits it, so the UI does not offer that filter. Legacy snapshots without captured coverage show LEGACY_NOT_MEASURED and remain unchanged. New analyses use the current classification; historical measurements are not retroactively recalculated. Closure evidence: [PHASE_2_CLOSURE.md](PHASE_2_CLOSURE.md).
