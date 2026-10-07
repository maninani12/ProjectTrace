# Language support

| Language | Parser | Quality / security maturity | Main boundaries |
| --- | --- | --- | --- |
| Python | CPython ast | PARTIAL; selected syntax metrics, reliability and security rules; bounded local flows | No complete type/CFG/framework or cross-file taint model; AST still in-process |
| JavaScript / JSX | Maintained Tree-sitter grammar | PARTIAL; syntax metrics and selected hotspots | Lexical scope models are bounded; no complete cross-file flow |
| TypeScript / TSX | Maintained Tree-sitter grammar | PARTIAL; syntax metrics and selected hotspots | No TypeScript compiler/type resolution; framework models incomplete |
| Java | Maintained Tree-sitter grammar | PARTIAL; syntax metrics and selected hotspots | No complete overload/type or cross-file flow; arbitrary methods named eval are not treated as builtins |
| Go, Rust, C/C++, C#, Kotlin, Ruby and other source | No native semantic parser | UNSUPPORTED | Inventory preserves files and gaps; generic secret-like patterns may still run; zero findings never establishes safety |

Trust & Coverage distinguishes file inventory, parser completion and semantic maturity. Failed parsing, generated/vendor exclusions, policy exclusions, binary and size skips are visible. Unknown LOC remains unknown. Rules and parser versions are captured with the snapshot. Benchmark evidence and voluntary review feedback are separate; no rule has representative production precision or default blocking qualification from the present purposive corpus.

Analysis never runs customer tests, builds, dependency installations or scripts. IaC and maintained grammar parsing use bounded helper processes; a complete OS sandbox is not verified on Windows. No external LLM receives source. Imported coverage reports are supplied measurements, not tests executed by ProjectTrace.
