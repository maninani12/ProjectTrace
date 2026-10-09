"""Explainable first-party source scope; no executable repository configuration."""

import fnmatch
import re
from pathlib import PurePosixPath

LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
}
OTHER_LANGUAGES = {
    ".rs": "Rust",
    ".go": "Go",
    ".cs": "C#",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".h": "C/C++",
    ".rb": "Ruby",
    ".php": "PHP",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".scala": "Scala",
    ".dart": "Dart",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".r": "R",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".kts": "Kotlin",
    ".hpp": "C++",
    ".cxx": "C++",
    ".hxx": "C++",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".lua": "Lua",
    ".pl": "Perl",
}
NON_SOURCE_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".tf",
    ".toml",
    ".xml",
    ".ini",
    ".env",
    ".example",
    ".lock",
    ".csv",
    ".svg",
    ".css",
    ".html",
}
NON_SOURCE_NAMES = {"CODEOWNERS", ".env", ".gitignore", ".dockerignore", "LICENSE", "NOTICE"}
BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".woff",
    ".woff2",
    ".exe",
    ".dll",
    ".bin",
}


def binary_input(path, raw):
    if PurePosixPath(path).suffix.lower() in BINARY_SUFFIXES:
        return True
    if b"\x00" in raw:
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            # Non-UTF-8 source (including UTF-16) remains an explicit encoding gap.
            return False
        return True
    return False


def source_language(path, source=""):
    """Explicit extensions/filenames and a bounded shebang; never semantic detection."""
    p = PurePosixPath(path)
    language = LANGUAGES.get(p.suffix.lower()) or OTHER_LANGUAGES.get(p.suffix.lower())
    if language:
        return language
    if p.name == "Makefile":
        return "Make"
    first = source[:200].split("\n", 1)[0]
    if first.startswith("#!"):
        for pattern, name in (
            (r"\bpython(?:[23](?:\.\d+)?)?\b", "Python"),
            (r"\b(?:ba|z|k)?sh\b", "Shell"),
            (r"\bnode\b", "JavaScript"),
            (r"\bruby\b", "Ruby"),
            (r"\bperl\b", "Perl"),
        ):
            if re.search(pattern, first):
                return name
        return "UNKNOWN"
    if (
        p.suffix.lower() in NON_SOURCE_SUFFIXES | BINARY_SUFFIXES
        or p.name in NON_SOURCE_NAMES
        or p.name.startswith("Dockerfile")
        or path.endswith(".tf.json")
    ):
        return None
    return "UNKNOWN"


def coverage_source(row):
    return row["kind"] in {
        "SOURCE",
        "TEST",
        "EXAMPLE",
        "UNSUPPORTED",
        "UNSUPPORTED_ENCODING",
        "SKIPPED_SIZE_LIMIT",
    } and bool(row.get("language"))


VENDOR = {"node_modules", "vendor", ".venv", "venv", "third_party", "third-party"}
GENERATED = {"dist", "build", "target", "generated", "__pycache__", ".next", "coverage", "htmlcov"}


def matches(path, patterns):
    return any(
        fnmatch.fnmatchcase(path, pattern) or pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:])
        for pattern in patterns
    )


def classify(files, scope=None):
    scope = scope or {}
    rows = []
    diagnostics = {r["path"]: r for r in getattr(files, "intake", [])}
    for path in sorted(set(files) | set(diagnostics)):
        metadata = files.metadata_for(path) if hasattr(files, "metadata_for") else None
        source = "" if metadata else files.get(path, "")
        p = PurePosixPath(path)
        language = (
            scope.get("language_overrides", {}).get(path)
            or (metadata or {}).get("source_language")
            or source_language(path, source)
        )
        kind, reason = "SOURCE", "Recognized source extension."
        parts = set(p.parts)
        if diagnostics.get(path, {}).get("state") == "UNSUPPORTED":
            kind = "UNSUPPORTED"
            source_kind = diagnostics[path].get("source_kind")
            reason = {
                "SYMLINK": "Git symbolic link is inventoried without fetching or following its target.",
                "SUBMODULE": "Git submodule is inventoried without fetching the separate repository.",
            }.get(source_kind, "Entry has no supported source representation; no source parser was run.")
        elif parts & VENDOR or matches(path, scope.get("vendor_patterns", [])):
            kind, reason = "EXCLUDED_VENDOR", "Vendored dependency/environment path."
        elif (
            parts & GENERATED
            or p.name.endswith((".min.js", ".min.css", ".generated.ts", ".g.java"))
            or matches(path, scope.get("generated_patterns", []))
        ):
            kind, reason = "EXCLUDED_GENERATED", "Generated/build/coverage output path or filename."
        elif (metadata or {}).get("generated_header") or re.search(
            r"(?im)^\s*(?:#|//|/\*|\*)\s*(?:@generated|generated (?:by|file|code)|auto-generated|do not edit)",
            source[:2000],
        ):
            kind, reason = "EXCLUDED_GENERATED", "Explicit generated-code header."
        elif ".git" in parts or matches(path, scope.get("exclude", [])):
            kind, reason = "EXCLUDED_CONFIG", "Repository scope exclusion."
        elif scope.get("include") and not matches(path, scope["include"]):
            kind, reason = "EXCLUDED_CONFIG", "Outside configured include paths."
        elif path in diagnostics:
            kind, reason = (
                ("UNSUPPORTED_ENCODING", "Source is not UTF-8 text; no source parser was run.")
                if language
                else ("EXCLUDED_BINARY", "Non-UTF-8 binary/non-source entry; no source parser was run.")
            )
            if diagnostics[path].get("state") == "BINARY":
                kind, reason = "EXCLUDED_BINARY", "Binary format or NUL bytes; no source parser was run."
            if diagnostics[path].get("state") == "SKIPPED_SIZE_LIMIT":
                kind, reason = "SKIPPED_SIZE_LIMIT", "File exceeds the parser byte budget; no source parser was run."
        elif language not in set(LANGUAGES.values()) or p.suffix.lower() not in LANGUAGES:
            kind, reason = (
                ("UNSUPPORTED", "No native quality parser selected for this filename/language.")
                if language
                else ("NON_SOURCE", "Documentation/configuration/report or unrecognized non-source file.")
            )
        elif (
            "tests" in parts
            or "test" in parts
            or p.name.startswith("test_")
            or re.search(r"\.(?:test|spec)\.[^.]+$", p.name)
            or matches(path, scope.get("test_paths", []))
        ):
            kind, reason = "TEST", "Recognized test path/filename; separate quality treatment."
        elif parts & {"examples", "samples", "fixtures"}:
            kind, reason = "EXAMPLE", "Example/fixture source; separately reported."
        rows.append(
            {
                "path": path,
                "language": language,
                "kind": kind,
                "reason": reason,
                "physical_lines": diagnostics[path]["physical_lines"]
                if path in diagnostics
                else metadata["physical_lines"]
                if metadata
                else len(source.splitlines()),
                "bytes": diagnostics[path]["bytes"]
                if path in diagnostics
                else metadata["bytes"]
                if metadata
                else len(source.encode()),
                **({"intake_hash": diagnostics[path].get("hash")} if path in diagnostics else {}),
            }
        )
    return rows


def ownership_rules(files):
    cached_rules = getattr(files, "_ownership_rules", None)
    if cached_rules is not None:
        return cached_rules
    cached_lines = getattr(files, "_ownership_lines", None)
    if cached_lines is None:
        candidates = [
            key
            for key in files
            if key in {"CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"} or key.endswith("/.github/CODEOWNERS")
        ]
        cached_lines = files[sorted(candidates)[0]].splitlines()[:5000] if candidates else []
        if hasattr(files, "inventory_id"):
            files._ownership_lines = cached_lines
    rules = []
    for line in cached_lines:
        parts = line.split("#", 1)[0].split()
        if not parts or parts[0].startswith("#") or len(parts) < 2 or parts[0].startswith("!"):
            continue
        pattern = parts[0].lstrip("/")
        if pattern.endswith("/"):
            pattern += "**"
        variants = [pattern, "**/" + pattern]
        variants.extend(value[3:] for value in tuple(variants) if value.startswith("**/"))
        checks = tuple(re.compile(fnmatch.translate(value)).match for value in dict.fromkeys(variants))
        rules.append((checks, " ".join(part for part in parts[1:] if not part.startswith("#"))[:200]))
    if hasattr(files, "inventory_id"):
        files._ownership_rules = rules
    return rules


def ownership(path, files, fallback, *, rules=None):
    """Last matching supported CODEOWNERS glob; owners are not inferred authors."""
    selected = fallback
    provenance = "ProjectTrace repository assignment"
    for checks, owner in ownership_rules(files) if rules is None else rules:
        if any(check(path) for check in checks):
            selected = owner
            provenance = "CODEOWNERS supported glob (last match)"
    return {"owner": selected, "owner_source": provenance}
