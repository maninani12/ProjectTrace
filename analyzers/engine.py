"""Bounded static analysis. Repository contents are data, never executable."""

import ast
import hashlib
import io
import json
import re
import stat
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version as package_version
from pathlib import PurePosixPath
from urllib.parse import quote

from analyzers.analysis_coverage import build as build_analysis_coverage
from analyzers.baseline import context_signals, implementation_claims, inventory
from analyzers.code_quality.classification import binary_input
from analyzers.code_quality.core import build as quality_build
from analyzers.code_quality.rules import RULES as QUALITY_RULES
from analyzers.finding_identity import annotate as annotate_finding_identity
from analyzers.flows import python_flows
from analyzers.infrastructure import structured_iac_batch
from analyzers.infrastructure_deep import config as infrastructure_config
from analyzers.infrastructure_deep import link_local_declarations
from analyzers.languages import LANGUAGES, analyze_languages
from analyzers.native_rules import NATIVE_RULES
from analyzers.quality import metrics as python_metrics
from analyzers.quality import structure as python_structure
from analyzers.source_input import SourceFiles
from analyzers.verifiers import claim_key, extract_documentation, verify_claim

VERSION = "1.6.0"
PARSER_SIGNATURE = hashlib.sha256(
    json.dumps(
        [
            sys.version,
            "native-observations-v10-partitioned-context",
            *[
                package_version(p)
                for p in [
                    "tree-sitter",
                    "tree-sitter-javascript",
                    "tree-sitter-typescript",
                    "tree-sitter-java",
                    "python-hcl2",
                    "PyYAML",
                ]
            ],
        ]
    ).encode()
).hexdigest()
MAX_FILES = 1000
MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 10_000_000
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".java",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".tf",
    ".txt",
    ".toml",
    ".xml",
    ".gradle",
    ".env",
    ".example",
    ".lock",
    ".kts",
    ".ini",
}
SKIP_PARTS = {"node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__"}
SECRET_RE = re.compile(
    r"(?i)(?:gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|(?:password|api[_-]?key|secret(?:_key)?|token)\s*[:=]\s*[\"\']([^\"\'\n]{12,})[\"\'])"
)
PRIVATE_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|$)", re.S
)
ENV_SECRET_RE = re.compile(
    r"(?im)^\s*(?:[\w-]*(?:password|token|secret|api[_-]?key)[\w-]*)\s*[:=]\s*([A-Za-z0-9_+/=-]{12,})\s*(?:#.*)?$"
)


def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def redact(text):
    text = PRIVATE_RE.sub("[REDACTED PRIVATE KEY]", text)
    text = re.sub(r"(?i)((?:postgres(?:ql)?|mysql|mongodb)(?:\+\w+)?://[^\s/:]+:)[^\s/@]+(@)", r"\1[REDACTED]\2", text)
    text = re.sub(
        r"(?m)^(?:[A-Z_]*(?:PASSWORD|TOKEN|SECRET|API_KEY))\s*=\s*[^\n]+$", "[REDACTED ENVIRONMENT SECRET]", text
    )
    text = ENV_SECRET_RE.sub("[REDACTED ENVIRONMENT SECRET]", text)
    return SECRET_RE.sub("[REDACTED SECRET]", text)


def is_iac_source(path, source):
    return (
        path.endswith((".yml", ".yaml", ".tf", ".tf.json"))
        or path.endswith(".json")
        and any(marker in source for marker in ('"Resources"', '"kind"', '"services"'))
        or PurePosixPath(path).name.startswith("Dockerfile")
    )


def redact_metadata(value):
    """Mask credential-shaped strings throughout persisted native metadata."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {redact(str(key)): redact_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_metadata(item) for item in value]
    return value


def safe_path(path):
    if not isinstance(path, str) or len(path) > 240 or "\\" in path or ":" in path or "\x00" in path:
        raise ValueError("Repository contains an invalid path.")
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or path.startswith("/") or not p.parts:
        raise ValueError("Repository path traversal is forbidden.")
    return p


def validate_files(files, *, keep_excluded=False):
    intake = getattr(files, "intake", [])
    if not (files or intake) or len(files) + len(intake) > MAX_FILES:
        raise ValueError(f"Repository must contain 1–{MAX_FILES} files.")
    size = sum(row["bytes"] for row in intake if row.get("state") != "SKIPPED_SIZE_LIMIT")
    clean = SourceFiles(intake=intake)
    seen_paths = {str(safe_path(row["path"])) for row in intake}
    if len(seen_paths) != len(intake):
        raise ValueError("Repository contains duplicate paths.")
    if size > MAX_TOTAL_BYTES:
        raise ValueError("Repository exceeds the configured total size limit.")
    for path, source in files.items():
        p = safe_path(path)
        if str(p) in seen_paths:
            raise ValueError("Repository contains duplicate paths.")
        seen_paths.add(str(p))
        if not keep_excluded and any(part in SKIP_PARTS for part in p.parts):
            continue
        if (
            not keep_excluded
            and p.suffix.lower() not in TEXT_SUFFIXES
            and p.name not in {"Dockerfile", "CODEOWNERS", "Makefile", ".env"}
            and not p.name.startswith("Dockerfile")
        ):
            continue
        if not isinstance(source, str):
            raise ValueError("File contents must be UTF-8 text.")
        n = len(source.encode())
        size += n
        if n > MAX_FILE_BYTES and keep_excluded and size <= MAX_TOTAL_BYTES:
            clean.intake.append(
                {
                    "path": str(p),
                    "bytes": n,
                    "hash": hash_text(source),
                    "physical_lines": None,
                    "state": "SKIPPED_SIZE_LIMIT",
                }
            )
            continue
        if n > MAX_FILE_BYTES or size > MAX_TOTAL_BYTES:
            raise ValueError("Repository exceeds the configured file or total size limit.")
        if keep_excluded and binary_input(str(p), source.encode()):
            clean.intake.append(
                {"path": str(p), "bytes": n, "hash": hash_text(source), "physical_lines": None, "state": "BINARY"}
            )
            continue
        clean[str(p)] = source
    if not clean and not (keep_excluded and clean.intake):
        raise ValueError("Repository contains no supported text files.")
    return clean


def read_zip(blob, *, keep_excluded=False):
    if len(blob) > MAX_TOTAL_BYTES:
        raise ValueError("Archive exceeds the 10 MB limit.")
    files = SourceFiles()
    seen_paths = set()
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            raise ValueError("Archive exceeds the configured file count limit.")
        total = 0
        for entry in entries:
            safe_path(entry.orig_filename)
            p = safe_path(entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Archive symbolic links are forbidden.")
            total += entry.file_size
            if (
                entry.file_size > MAX_FILE_BYTES
                and not keep_excluded
                or total > MAX_TOTAL_BYTES
                or entry.file_size > max(entry.compress_size, 1) * 200
            ):
                raise ValueError("Archive exceeds extraction limits or compression ratio.")
            if (
                entry.is_dir()
                or not keep_excluded
                and p.suffix.lower() not in TEXT_SUFFIXES
                and p.name not in {"Dockerfile", "CODEOWNERS", ".env"}
            ):
                continue
            canonical = str(p)
            if canonical in seen_paths:
                raise ValueError("Archive contains duplicate paths.")
            seen_paths.add(canonical)
            if entry.file_size > MAX_FILE_BYTES and keep_excluded:
                files.intake.append(
                    {
                        "path": canonical,
                        "bytes": entry.file_size,
                        "hash": None,
                        "physical_lines": None,
                        "state": "SKIPPED_SIZE_LIMIT",
                    }
                )
                continue
            raw = archive.read(entry)
            if keep_excluded and binary_input(canonical, raw):
                files.intake.append(
                    {
                        "path": canonical,
                        "bytes": len(raw),
                        "hash": hashlib.sha256(raw).hexdigest(),
                        "physical_lines": None,
                        "state": "BINARY",
                    }
                )
                continue
            try:
                files[canonical] = raw.decode("utf-8")
            except UnicodeDecodeError:
                if keep_excluded:
                    files.intake.append(
                        {
                            "path": canonical,
                            "bytes": len(raw),
                            "hash": hashlib.sha256(raw).hexdigest(),
                            "physical_lines": None,
                        }
                    )
                continue
    return validate_files(files, keep_excluded=keep_excluded)


RULES = {
    "PT-SAST-001": (
        "SAST",
        "HIGH",
        "Dynamic SQL reaches an execution sink",
        "Use parameterized queries; pass values separately from SQL.",
        "CWE-89",
    ),
    "PT-SAST-002": (
        "SAST",
        "HIGH",
        "Shell execution is enabled",
        "Pass an argument list with shell=False and validate external input.",
        "CWE-78",
    ),
    "PT-SAST-003": (
        "SAST",
        "HIGH",
        "Unsafe deserialization",
        "Use a safe data format; never deserialize untrusted objects.",
        "CWE-502",
    ),
    "PT-SAST-004": (
        "SAST",
        "MEDIUM",
        "Weak digest algorithm",
        "Use SHA-256 or a purpose-built password hashing algorithm.",
        "CWE-327",
    ),
    "PT-SECRET-001": (
        "SECRET",
        "CRITICAL",
        "Credential-shaped value in source",
        "Revoke if real, remove from source and use a secret manager.",
        "CWE-798",
    ),
    "PT-IAC-001": (
        "IAC",
        "HIGH",
        "Privileged container enabled",
        "Remove privileged mode and grant only required capabilities.",
        "CWE-250",
    ),
    "PT-IAC-002": ("IAC", "MEDIUM", "Container explicitly runs as root", "Use a dedicated non-root user.", "CWE-250"),
    "PT-IAC-003": (
        "IAC",
        "HIGH",
        "Public storage ACL",
        "Restrict the ACL and enforce public access blocking.",
        "CWE-732",
    ),
    "PT-QUALITY-001": (
        "QUALITY",
        "MEDIUM",
        "Function exceeds complexity budget",
        "Split independent branches into focused, tested functions.",
        None,
    ),
    "PT-SAST-006": (
        "SAST",
        "MEDIUM",
        "Dynamic HTML reaches a raw rendering sink",
        "Escape untrusted values or use a template engine with automatic escaping.",
        "CWE-79",
    ),
    "PT-SAST-007": (
        "SAST",
        "MEDIUM",
        "Dynamic path reaches a filesystem response",
        "Resolve paths under an allowlisted root and reject traversal before reading files.",
        "CWE-22",
    ),
    "PT-QUALITY-002": (
        "QUALITY",
        "LOW",
        "Function exceeds 80 lines",
        "Extract cohesive responsibilities into smaller functions.",
        None,
    ),
    "PT-QUALITY-003": (
        "QUALITY",
        "LOW",
        "Control flow is deeply nested",
        "Extract focused helpers or use guard clauses to reduce nesting.",
        None,
    ),
    "PT-QUALITY-004": (
        "QUALITY",
        "LOW",
        "Class exceeds 200 lines",
        "Split independent class responsibilities into focused collaborators.",
        None,
    ),
    "PT-QUALITY-005": (
        "QUALITY",
        "MEDIUM",
        "Bare exception handler swallows system exceptions",
        "Catch specific exceptions and retain a safe diagnostic or re-raise.",
        None,
    ),
    "PT-SAST-008": (
        "SAST",
        "MEDIUM",
        "Request-derived URL reaches an outbound HTTP sink",
        "Allowlist destinations, validate DNS/IP ranges and constrain redirects before making requests.",
        "CWE-918",
    ),
    "PT-SAST-009": (
        "SAST",
        "MEDIUM",
        "Insecure temporary filename generation",
        "Use NamedTemporaryFile or mkstemp to atomically create temporary files.",
        "CWE-377",
    ),
    "PT-SAST-010": (
        "SAST",
        "HIGH",
        "JWT signature verification explicitly disabled",
        "Verify the signature and restrict accepted algorithms before trusting JWT claims.",
        "CWE-347",
    ),
    "PT-PARSE-001": (
        "QUALITY",
        "LOW",
        "Source could not be parsed",
        "Fix syntax or check the supported language version; analysis is incomplete.",
        None,
    ),
}

RULES.update(NATIVE_RULES)
RULES.update(QUALITY_RULES)


def finding(rule, path, line, detail="", confidence="HIGH"):
    category, severity, title, remediation, cwe = RULES[rule]
    return {
        "rule": rule,
        "rule_id": rule,
        "rule_version": VERSION,
        "analyzer_version": VERSION,
        "category": category,
        "severity": severity,
        "title": title,
        "path": path,
        "line": line,
        "end_line": line,
        "language": {
            ".py": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".java": "Java",
            ".tf": "Terraform",
            ".yaml": "YAML",
            ".yml": "YAML",
        }.get(PurePosixPath(path).suffix.lower(), "Configuration"),
        "explanation": redact(detail or title),
        "remediation": remediation,
        "confidence": confidence,
        "cwe": cwe,
        "classification": "SECURITY_HOTSPOT" if category == "SAST" else "STATIC_FINDING",
        "review_status": "OPEN",
        "fingerprint": hash_text(f"{rule}:{path}:{line}:{detail}"),
    }


def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return call_name(node.value) + "." + node.attr
    return ""


def own_nodes(node):
    """Walk a definition without charging nested definitions to its metrics."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield from own_nodes(child)


def nesting_depth(node, depth=0):
    current = depth + isinstance(
        node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)
    )
    children = [
        child
        for child in ast.iter_child_nodes(node)
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda))
    ]
    return max([current] + [nesting_depth(child, current) for child in children])


def pattern_source(source):
    """Mask JS/Java comments and string bodies, preserving positions and quotes.

    This is lexical filtering for narrow patterns, not a language parser.
    """
    result, index = [], 0
    while index < len(source):
        if source.startswith("//", index):
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            result.append(" " * (end - index))
            index = end
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = len(source) if end < 0 else end + 2
            result.append("".join("\n" if c == "\n" else " " for c in source[index:end]))
            index = end
        elif source[index] in {"'", '"', "`"}:
            delimiter = source[index]
            result.append(delimiter)
            index += 1
            while index < len(source):
                current = source[index]
                if current == "\\" and index + 1 < len(source):
                    result.append("  ")
                    index += 2
                elif current == delimiter:
                    result.append(delimiter)
                    index += 1
                    break
                else:
                    result.append("\n" if current == "\n" else " ")
                    index += 1
        else:
            result.append(source[index])
            index += 1
    return "".join(result)


def secret_context(path, material):
    lowered = path.lower()
    if any(
        part in {"test", "tests", "fixtures", "fixture", "__tests__"} for part in PurePosixPath(lowered).parts
    ) or PurePosixPath(lowered).name.startswith("test_"):
        return "TEST_FIXTURE"
    if any(value in lowered for value in ("example", "sample", "demo")) or re.search(
        r"fake|dummy|fixture|example|not[_ -]?(?:a[_ -]?)?real|not[_ -]?live", material, re.I
    ):
        return "EXAMPLE_CREDENTIAL"
    if any(part in {"production", "prod"} for part in PurePosixPath(lowered).parts) and (
        re.search(r"gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN", material)
    ):
        return "LIKELY_PRODUCTION"
    return "UNKNOWN"


def python_analysis(path, source, tree=None):
    findings, signals = [], []
    try:
        tree = tree or ast.parse(source)
    except (SyntaxError, RecursionError) as error:
        return [finding("PT-PARSE-001", path, getattr(error, "lineno", 1) or 1)], []
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    aliases = {}
    for imported in ast.walk(tree):
        if isinstance(imported, ast.Import):
            aliases.update({part.asname or part.name.split(".")[0]: part.name for part in imported.names})
        elif isinstance(imported, ast.ImportFrom):
            aliases.update(
                {part.asname or part.name: (imported.module or "") + "." + part.name for part in imported.names}
            )

    def canonical(node):
        name = call_name(node)
        head, _, tail = name.partition(".")
        return aliases.get(head, head) + ("." + tail if tail else "")

    def scope(node):
        parent = parents.get(node)
        while parent and not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            parent = parents.get(parent)
        return parent

    assignments = {}
    builtin_bindings = {}
    for bound in ast.walk(tree):
        if isinstance(bound, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            builtin_bindings.setdefault(scope(bound), set()).add(bound.name)
            if isinstance(bound, (ast.FunctionDef, ast.AsyncFunctionDef)):
                builtin_bindings.setdefault(bound, set()).update(
                    a.arg for a in [*bound.args.posonlyargs, *bound.args.args, *bound.args.kwonlyargs]
                )
                builtin_bindings[bound].update(a.arg for a in (bound.args.vararg, bound.args.kwarg) if a)
        elif isinstance(bound, ast.Name) and isinstance(bound.ctx, ast.Store):
            builtin_bindings.setdefault(scope(bound), set()).add(bound.id)
        elif isinstance(bound, (ast.Import, ast.ImportFrom)):
            builtin_bindings.setdefault(scope(bound), set()).update(
                a.asname or a.name.split(".")[0] for a in bound.names if getattr(bound, "module", None) != "builtins"
            )

    def builtin_available(name, location):
        owner = scope(location)
        while owner:
            if name in builtin_bindings.get(owner, set()):
                return False
            owner = scope(owner)
        return True

    for assigned in ast.walk(tree):
        if isinstance(assigned, (ast.Assign, ast.AnnAssign)):
            for target in assigned.targets if isinstance(assigned, ast.Assign) else [assigned.target]:
                if isinstance(target, ast.Name):
                    assignments.setdefault((scope(assigned), target.id), []).append(assigned)

    def prior_value(node, location, visited=None):
        visited = visited or set()
        if isinstance(node, ast.Name) and node.id not in visited:
            values = [
                value for value in assignments.get((scope(location), node.id), []) if value.lineno < location.lineno
            ]
            if values:
                assigned = max(values, key=lambda value: value.lineno)
                return prior_value(assigned.value, assigned, visited | {node.id})
        return node

    def request_derived(node, location):
        resolved = prior_value(node, location)
        return any(
            call_name(value).startswith(("request.args", "request.query_params", "request.form", "request.json"))
            for value in ast.walk(resolved)
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                signals.append({"type": "import", "value": name, "path": path, "line": node.lineno})
        if isinstance(node, ast.Call):
            name = canonical(node.func)
            argument = node.args[0] if node.args else None
            if (
                name in {"eval", "exec", "builtins.eval", "builtins.exec"}
                and argument is not None
                and builtin_available(call_name(node.func).split(".")[0], node)
            ):
                if "." not in name or name.startswith("builtins.") and (call_name(node.func).split(".")[0] in aliases):
                    findings.append(
                        finding(
                            "PT-SAST-005",
                            path,
                            node.lineno,
                            "A builtin dynamic-code evaluation sink is called; source reachability and defenses require review.",
                            "MEDIUM",
                        )
                    )
            if isinstance(argument, ast.Call) and call_name(argument.func).split(".")[-1] == "text":
                argument = argument.args[0] if argument.args else None
            sql_argument = prior_value(argument, node) if argument is not None else argument
            dynamic_sql = isinstance(sql_argument, (ast.JoinedStr, ast.BinOp)) or (
                isinstance(sql_argument, ast.Call) and call_name(sql_argument.func).endswith(".format")
            )
            if name.endswith(".execute") and dynamic_sql:
                findings.append(
                    finding(
                        "PT-SAST-001",
                        path,
                        node.lineno,
                        "A dynamically constructed expression is passed to execute(). External input reachability is not proven.",
                        "MEDIUM",
                    )
                )
            if name in {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output"} and any(
                k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords
            ):
                findings.append(
                    finding("PT-SAST-002", path, node.lineno, "The subprocess call explicitly enables shell=True.")
                )
            if name == "os.system":
                findings.append(
                    finding(
                        "PT-SAST-002",
                        path,
                        node.lineno,
                        "os.system executes its command through a shell; input provenance requires review.",
                        "MEDIUM",
                    )
                )
            if name in {"pickle.loads", "pickle.load", "yaml.unsafe_load"}:
                findings.append(finding("PT-SAST-003", path, node.lineno))
            if name in {"hashlib.md5", "hashlib.sha1"}:
                findings.append(
                    finding(
                        "PT-SAST-004",
                        path,
                        node.lineno,
                        "Weak digest detected; security relevance requires human review.",
                        "MEDIUM",
                    )
                )
            if (
                name
                in {
                    "requests.get",
                    "requests.post",
                    "requests.request",
                    "httpx.get",
                    "httpx.post",
                    "urllib.request.urlopen",
                }
                and argument is not None
                and request_derived(argument, node)
            ):
                findings.append(
                    finding(
                        "PT-SAST-008",
                        path,
                        node.lineno,
                        "A request attribute or locally assigned request value reaches an HTTP URL argument. Redirect behavior and defenses require human review.",
                        "MEDIUM",
                    )
                )
            if name == "tempfile.mktemp":
                findings.append(finding("PT-SAST-009", path, node.lineno))
            if name in {"jwt.decode", "jose.jwt.decode"} and any(
                keyword.arg == "options"
                and isinstance(keyword.value, ast.Dict)
                and any(
                    isinstance(key, ast.Constant)
                    and key.value == "verify_signature"
                    and isinstance(value, ast.Constant)
                    and value.value is False
                    for key, value in zip(keyword.value.keys, keyword.value.values, strict=True)
                )
                for keyword in node.keywords
            ):
                findings.append(finding("PT-SAST-010", path, node.lineno))
            if name.endswith("add_middleware") and node.args and call_name(node.args[0]).endswith("SessionMiddleware"):
                signals.append({"type": "auth", "value": "session", "path": path, "line": node.lineno})
            if name in {"jwt.encode", "jwt.decode", "jose.jwt.encode", "jose.jwt.decode"}:
                signals.append({"type": "auth", "value": "jwt", "path": path, "line": node.lineno})
            if name.split(".")[-1] in {"FastAPI", "Flask"}:
                signals.append(
                    {"type": "technology", "value": name.split(".")[-1].lower(), "path": path, "line": node.lineno}
                )
            if name.split(".")[-1] in {"HTMLResponse", "FileResponse"} and isinstance(
                argument, (ast.JoinedStr, ast.BinOp)
            ):
                findings.append(
                    finding(
                        "PT-SAST-006" if name.endswith("HTMLResponse") else "PT-SAST-007",
                        path,
                        node.lineno,
                        "Dynamic construction reaches a sensitive sink. External-input flow and exploitability require human review.",
                        "MEDIUM",
                    )
                )
            if name.endswith("cookies.get") and node.args:
                signals.append({"type": "auth_hint", "value": "cookie session", "path": path, "line": node.lineno})
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = re.match(r"(postgres(?:ql)?|sqlite|mysql|mongodb)(?:\+\w+)?://", node.value)
            parent = parents.get(node)
            configured = isinstance(parent, (ast.Assign, ast.AnnAssign)) and any(
                re.search(r"database|db|dsn|url|sqlalchemy", call_name(target), re.I)
                for target in (parent.targets if isinstance(parent, ast.Assign) else [parent.target])
            )
            configured = (
                configured
                or isinstance(parent, ast.Call)
                and canonical(parent.func).split(".")[-1]
                in {"create_engine", "create_async_engine", "connect", "MongoClient"}
            )
            if match and configured:
                signals.append(
                    {
                        "type": "database",
                        "value": "postgresql" if match.group(1).startswith("postgres") else match.group(1),
                        "path": path,
                        "line": node.lineno,
                    }
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexity = 1 + sum(
                isinstance(x, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp)) for x in own_nodes(node)
            )
            if complexity > 10:
                findings.append(
                    finding(
                        "PT-QUALITY-001",
                        path,
                        node.lineno,
                        f"{node.name}: cyclomatic branch approximation {complexity}; threshold 10.",
                    )
                )
            if (node.end_lineno or node.lineno) - node.lineno > 80:
                findings.append(finding("PT-QUALITY-002", path, node.lineno, f"{node.name}: more than 80 lines."))
            depth = nesting_depth(node)
            if depth > 4:
                findings.append(
                    finding(
                        "PT-QUALITY-003", path, node.lineno, f"{node.name}: control-flow nesting {depth}; threshold 4."
                    )
                )
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                    method = call_name(decorator.func).split(".")[-1].upper()
                    if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                        signals.append(
                            {
                                "type": "route",
                                "value": f"{method} {decorator.args[0].value}",
                                "path": path,
                                "line": decorator.lineno,
                            }
                        )
                    elif method == "ROUTE":
                        methods = next(
                            (keyword.value for keyword in decorator.keywords if keyword.arg == "methods"), None
                        )
                        methods = (
                            methods.elts if isinstance(methods, (ast.List, ast.Tuple)) else [ast.Constant(value="GET")]
                        )
                        for item in methods:
                            if (
                                isinstance(item, ast.Constant)
                                and isinstance(item.value, str)
                                and item.value.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                            ):
                                signals.append(
                                    {
                                        "type": "route",
                                        "value": item.value.upper() + " " + str(decorator.args[0].value),
                                        "path": path,
                                        "line": decorator.lineno,
                                    }
                                )
        if isinstance(node, ast.ClassDef) and (node.end_lineno or node.lineno) - node.lineno > 200:
            findings.append(finding("PT-QUALITY-004", path, node.lineno, f"{node.name}: more than 200 lines."))
        if (
            isinstance(node, ast.ExceptHandler)
            and node.type is None
            and not any(isinstance(statement, ast.Raise) for statement in node.body)
        ):
            findings.append(finding("PT-QUALITY-005", path, node.lineno))
    for result in findings:
        result["end_line"] = max(
            result["line"],
            next(
                (
                    getattr(node, "end_lineno", result["line"]) or result["line"]
                    for node in ast.walk(tree)
                    if getattr(node, "lineno", None) == result["line"]
                ),
                result["line"],
            ),
        )
    for signal in signals:
        signal["value"] = redact(signal["value"])
    return findings, signals


def dependencies(files):
    """Compatibility inventory helper; callers needing coverage should use inventory."""
    return inventory(files)[0]


def extract_claims(files, diagnostics=None):
    return extract_documentation(files, diagnostics=diagnostics)


def verify(claim, signals, deps):
    result, _ = verify_claim(claim, signals, deps)
    return result["status"], result["reason"], result["signals"]


def native_observations(files, cached_analysis=None, infrastructure_settings=None, *, performance=None):
    # Only independent owned syntax/IaC helpers run concurrently; source and DB
    # work stay in the caller. Every submitted batch retains its existing caps.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="native-parser") as pool:
        return _native_observations(files, cached_analysis, infrastructure_settings, performance, pool)


def _native_observations(files, cached_analysis, infrastructure_settings, performance, pool):
    """File-local parser observations; callers may provide a bounded partition."""
    infrastructure_settings = infrastructure_settings or infrastructure_config(None)
    infrastructure_signature = hash_text(json.dumps(infrastructure_settings, sort_keys=True))
    findings, signals, warnings = [], [], []
    assets, quality_metrics = [], []
    failures = set()
    cache = {}
    reused = 0
    language_results, iac_results = None, None
    language_pending, iac_pending = {}, {}
    for path in files:
        prior = (cached_analysis or {}).get(path, {})
        meta = files.metadata_for(path) if hasattr(files, "metadata_for") else None
        content_hash = files.hash_for(path) if meta else hash_text(files[path])
        iac = meta.get("iac_candidate", bool(meta.get("infrastructure_format")) or path.endswith((".yaml", ".yml", ".json"))) if meta else is_iac_source(path, files[path])
        if (prior.get("hash") == content_hash and prior.get("version") == VERSION
            and prior.get("parser_signature") == PARSER_SIGNATURE and not prior.get("warnings")
            and not any(f.get("rule") == "PT-PARSE-001" for f in prior.get("findings", []))
            and (not iac or prior.get("infrastructure_signature", infrastructure_signature) == infrastructure_signature)):
            continue
        if PurePosixPath(path).suffix in LANGUAGES:
            language_pending[path] = files[path]
        if iac:
            source = files[path]
            if is_iac_source(path, source):
                iac_pending[path] = source
    language_future = pool.submit(analyze_languages, language_pending, performance=performance) if language_pending else None
    iac_future = pool.submit(structured_iac_batch, iac_pending, finding, infrastructure_settings, performance=performance) if iac_pending else None
    for path in files:
        file_started = time.perf_counter()
        metadata = files.metadata_for(path) if hasattr(files, "metadata_for") else None
        source = None if metadata else files[path]
        previous = (cached_analysis or {}).get(path)
        content_hash = files.hash_for(path) if metadata else hash_text(source)
        iac = (
            metadata.get(
                "iac_candidate",
                bool(metadata.get("infrastructure_format")) or path.endswith((".yaml", ".yml", ".json")),
            )
            if metadata
            else is_iac_source(path, source)
        )
        if (
            previous
            and previous.get("hash") == content_hash
            and previous.get("version") == VERSION
            and previous.get("parser_signature") == PARSER_SIGNATURE
            and (
                not iac
                or previous.get("infrastructure_signature", infrastructure_signature) == infrastructure_signature
            )
            and not previous.get("warnings")
            and not any(item.get("rule") == "PT-PARSE-001" for item in previous.get("findings", []))
        ):
            cached = json.loads(json.dumps(previous))
            findings.extend(cached["findings"])
            signals.extend(cached["signals"])
            assets.extend(cached.get("assets", []))
            quality_metrics.extend(cached.get("quality_metrics", []))
            cache[path] = cached
            reused += 1
            if performance:
                performance.record("CACHE_REUSE", time.perf_counter() - file_started, path, state="REUSED")
            continue
        if source is None:
            source = files[path]
        finding_start, signal_start = len(findings), len(signals)
        asset_start, metric_start = len(assets), len(quality_metrics)
        if path.endswith(".py"):
            python_started = time.perf_counter()
            try:
                parsed_tree = None
                try:
                    parsed_tree = ast.parse(source)
                except (SyntaxError, RecursionError):
                    pass
                f, s = python_analysis(path, source, parsed_tree)
                if not any(item["rule"] == "PT-PARSE-001" for item in f):
                    measured = python_metrics(path, source, parsed_tree)
                    s.append(python_structure(path, source, parsed_tree))
                    quality_metrics.extend(measured)
                    s.extend(
                        {
                            "type": "function",
                            "value": metric["name"],
                            "path": path,
                            "line": metric["line"],
                            "end_line": metric["end_line"],
                        }
                        for metric in measured
                    )
                    # Upgrade branch metrics while preserving the established rule IDs.
                    f = [item for item in f if item["rule"] != "PT-QUALITY-001"]
                    f.extend(
                        finding(
                            "PT-QUALITY-001",
                            path,
                            metric["line"],
                            f"{metric['name']}: cyclomatic approximation {metric['cyclomatic']}; threshold 10.",
                        )
                        for metric in measured
                        if metric["cyclomatic"] > 10
                    )
                    flows = python_flows(path, source, finding)
                    proven = {(item["rule"], item["line"]) for item in flows}
                    f = [item for item in f if (item["rule"], item["line"]) not in proven] + flows
                findings.extend(f)
                signals.extend(s)
            except Exception as error:
                failures.update({"PARSING", "QUALITY", "SAST"})
                warnings.append(
                    {
                        "analyzer": "PARSING",
                        "path": path,
                        "code": type(error).__name__,
                        "message": "Native Python analysis failed; source details are withheld.",
                        "state": "FAILED",
                    }
                )
            if performance:
                performance.record("PYTHON_NATIVE", time.perf_counter() - python_started, path)
        elif path.endswith((".js", ".ts", ".jsx", ".tsx", ".java", ".mjs", ".cjs")):
            parsed = None
            try:
                if language_results is None:
                    language_results = language_future.result()
                parsed = language_results[path]
                if isinstance(parsed, dict):
                    raise ValueError("Native syntax process failed or exceeded its budget")
                f, sig, metrics = parsed
                findings.extend(f)
                signals.extend(sig)
                quality_metrics.extend(metrics)
            except Exception as error:
                warnings.append(
                    {
                        "analyzer": "PARSING",
                        "path": path,
                        "code": parsed.get("code", type(error).__name__) if isinstance(parsed, dict) else type(error).__name__,
                        **({k: parsed[k] for k in ("budget", "actual", "maximum") if k in parsed} if isinstance(parsed, dict) else {}),
                        "state": "PARTIAL",
                        "message": "Native syntax parsing failed or exceeded its budget; this file has partial coverage.",
                    }
                )
        post_started = time.perf_counter()
        secret_lines = set()
        for match in (
            list(SECRET_RE.finditer(source)) + list(PRIVATE_RE.finditer(source)) + list(ENV_SECRET_RE.finditer(source))
        ):
            value = next((part for part in match.groups() if part is not None), match.group(0))
            if value.startswith(("${", "{{", "<")):
                continue
            line_no = source[: match.start()].count("\n") + 1
            if line_no in secret_lines:
                continue
            secret_lines.add(line_no)
            context = secret_context(path, match.group(0))
            result = finding(
                "PT-SECRET-001",
                path,
                line_no,
                "Secret-like material detected. The value is redacted; validity has not been tested.",
                "LOW" if context in {"TEST_FIXTURE", "EXAMPLE_CREDENTIAL"} else "MEDIUM",
            )
            result["secret_context"] = context
            if context in {"TEST_FIXTURE", "EXAMPLE_CREDENTIAL"}:
                result["severity"] = "MEDIUM"
            findings.append(result)
        if is_iac_source(path, source):
            if iac_results is None:
                iac_results = iac_future.result() if iac_future else {}
            if path not in iac_results:
                iac_results.update(structured_iac_batch({path: source}, finding, infrastructure_settings, performance=performance))
            f, resource_assets, messages = iac_results[path]
            findings.extend(f)
            assets.extend(resource_assets)
            warnings.extend(messages)
        native_occurrences = {}
        lines = source.splitlines()
        security_context_hash = None
        for item in findings[finding_start:]:
            if item.get("category") != "QUALITY":
                # Location is not identity. Hash a normalized statement and the
                # bounded surrounding security context; ambiguous repeats remain
                # separate occurrences and are not eligible for automatic carry.
                index = max(0, item["line"] - 1)
                statement = re.sub(r"\s+", " ", lines[index].strip()) if index < len(lines) else ""
                anchor = json.dumps(
                    [item["rule"], path, item.get("resource_identity"), statement, item.get("explanation")],
                    sort_keys=True,
                )
                count = native_occurrences.get(anchor, 0)
                native_occurrences[anchor] = count + 1
                item["fingerprint"] = hash_text(anchor + ":" + str(count))
                item["fingerprint_version"] = "native-statement-v1"
                if security_context_hash is None:
                    security_context_hash = hash_text("\n".join(
                        line.strip() for line in lines if line.strip() and not line.lstrip().startswith(("#", "//"))))
                item["security_context_hash"] = security_context_hash
                item["blocking_eligible"] = False
                item["precision_status"] = "UNMEASURED"
            if "resource_identity" in item:
                item["resource_identity"] = redact(item["resource_identity"])
            for step in item.get("flow", []):
                step["symbol"] = redact(step["symbol"])
        signals.extend(context_signals(path, source))
        for signal in signals[signal_start:]:
            signal["value"] = redact(signal["value"])
            for symbol in signal.get("symbols", []):
                for key in ["name", "qualified_name"]:
                    if key in symbol:
                        symbol[key] = redact(symbol[key])
        for metric in quality_metrics[metric_start:]:
            metric["name"] = redact(metric["name"])
            if "qualified_name" in metric:
                metric["qualified_name"] = redact(metric["qualified_name"])
            for token in metric.get("duplicate_tokens", []):
                token["value"] = redact(token["value"])
        for asset in assets[asset_start:]:
            masked = redact_metadata(asset)
            asset.clear()
            asset.update(masked)
        cache[path] = {
            "hash": content_hash,
            "version": VERSION,
            "parser_signature": PARSER_SIGNATURE,
            "findings": findings[finding_start:],
            "signals": signals[signal_start:],
            "assets": assets[asset_start:],
            "quality_metrics": quality_metrics[metric_start:],
            "warnings": [warning for warning in warnings if warning.get("path") == path],
            "infrastructure_signature": infrastructure_signature,
        }
        if performance:
            performance.record("FILE_POSTPROCESS", time.perf_counter() - post_started, path)
    identity_started = time.perf_counter()
    annotate_finding_identity(files, findings, quality_metrics)
    if performance:
        performance.record("PARTITION_IDENTITY", time.perf_counter() - identity_started)
    return findings, signals, warnings, assets, quality_metrics, failures, cache, reused


def analyze(
    files,
    cached_analysis=None,
    progress=None,
    verification_context=None,
    profile=None,
    *,
    observations=None,
    input_files=None,
):
    input_files = input_files if input_files is not None else validate_files(files, keep_excluded=True)
    infrastructure_settings = infrastructure_config((profile or {}).get("infrastructure"))
    try:
        if observations is None:
            files = validate_files(files)
    except ValueError as error:
        if str(error) != "Repository contains no supported text files.":
            raise
        files = {}
    if progress:
        progress("ANALYZING")
    observations = observations or native_observations(files, cached_analysis, infrastructure_settings)
    findings, signals, warnings, assets, quality_metrics, failures, cache, reused = observations
    performance = getattr(progress, "performance", None)
    component_started = time.perf_counter()
    try:
        deps, manifest_warnings = inventory(files)
        warnings.extend(manifest_warnings)
    except Exception as error:
        deps = []
        failures.add("DEPENDENCIES")
        warnings.append(
            {
                "analyzer": "DEPENDENCIES",
                "code": type(error).__name__,
                "message": "Dependency inventory failed; source details are withheld.",
                "state": "FAILED",
            }
        )
    for dependency in deps:
        for field in ("name", "version", "license"):
            if isinstance(dependency.get(field), str):
                dependency[field] = redact(dependency[field])
    if performance:
        performance.record("DEPENDENCIES", time.perf_counter() - component_started)
    warnings.extend(
        {
            "analyzer": "PARSING",
            "path": f["path"],
            "message": "Source could not be parsed; analysis coverage is partial.",
        }
        for f in findings
        if f["rule"] == "PT-PARSE-001"
    )
    claims = []
    if progress:
        progress("EXTRACTING_CLAIMS")
    component_started = time.perf_counter()
    try:
        candidates = extract_claims(files, warnings)
    except Exception as error:
        candidates = []
        failures.add("CLAIMS")
        warnings.append(
            {
                "analyzer": "CLAIMS",
                "code": type(error).__name__,
                "message": "Documentation claim extraction failed; source details are withheld.",
                "state": "FAILED",
            }
        )
    # JSON OpenAPI declarations enter the same evidence-grounded verifier pipeline.
    for path in files:
        if len(candidates) > 1500:
            warnings.append(
                {
                    "analyzer": "CLAIMS",
                    "state": "PARTIAL",
                    "message": "OpenAPI/documentation candidate limit reached; remaining declarations are unmeasured.",
                }
            )
            break
        if not path.endswith(".json"):
            continue
        source = files[path]
        try:
            contract = json.loads(source)
            if not isinstance(contract, dict) or "openapi" not in contract:
                continue
            for route, methods in contract.get("paths", {}).items():
                if len(candidates) > 1500:
                    break
                for method in methods:
                    if len(candidates) > 1500:
                        break
                    if method.upper() not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}:
                        continue
                    endpoint = method.upper() + " " + route
                    candidates.append(
                        {
                            "text": f"API contract includes {endpoint}.",
                            "origin": "DOCUMENTATION",
                            "category": "API",
                            "expected": endpoint,
                            "path": path,
                            "line": 1,
                            "assertion_family": "api_contract",
                        }
                    )
        except (ValueError, TypeError, AttributeError):
            if "openapi" in source.lower():
                warnings.append(
                    {
                        "analyzer": "API",
                        "path": path,
                        "message": "OpenAPI contract could not be parsed; coverage is partial.",
                    }
                )
    if progress:
        if performance:
            performance.record("CLAIM_EXTRACTION", time.perf_counter() - component_started)
        progress("VERIFYING")
    component_started = time.perf_counter()
    prior_verifications = (
        (verification_context or {}).get("claims", {}) if (verification_context or {}).get("version") == VERSION else {}
    )
    verification_cache = {}
    reused_verifications = 0
    for claim in candidates:
        claim["text"] = redact(claim["text"])
        claim["expected"] = redact(claim["expected"])
        key = claim_key(claim)
        try:
            verdict, reused_verification = verify_claim(claim, signals, deps, prior_verifications.get(key))
        except Exception as error:
            failures.add("CLAIMS")
            warnings.append(
                {
                    "analyzer": "CLAIMS",
                    "path": claim["path"],
                    "code": type(error).__name__,
                    "message": "A deterministic verifier failed; this statement remains unverified.",
                    "state": "FAILED",
                }
            )
            verdict = {
                "fingerprint": None,
                "status": "UNVERIFIED",
                "reason": "Verification failed; inspect the safe analysis diagnostic.",
                "signals": [],
                "verifier": "UNAVAILABLE",
            }
            reused_verification = False
        verification_cache[key] = verdict
        reused_verifications += reused_verification
        status, reason, evidence = verdict["status"], verdict["reason"], verdict["signals"]
        claims.append(
            {
                **claim,
                "origin": "DOCUMENTATION",
                "claim_key": key,
                "verifier": verdict["verifier"],
                "verification_reused": reused_verification,
                "status": status,
                "reason": reason,
                "signals": evidence,
                "severity": "HIGH" if claim["category"] == "AUTHENTICATION" else "MEDIUM",
                "confidence": "HIGH" if status == "VERIFIED" else "MEDIUM",
                "review_status": "OPEN",
            }
        )
    if performance:
        performance.record("CLAIM_VERIFICATION", time.perf_counter() - component_started)
    storage = [
        item
        for item in assets
        if item["kind"] in {"aws_s3_bucket", "AWS::S3::Bucket", "google_storage_bucket", "azurerm_storage_container"}
    ]
    for path in files:
        if not path.endswith(".md"):
            continue
        source = files[path]
        fenced = False
        for line, content in enumerate(source.splitlines(), 1):
            if content.strip().startswith("```"):
                fenced = not fenced
            if fenced or not re.search(r"^\s*(?:[-*]\s+)?(?:Production\s+)?storage is private[.!]?\s*$", content, re.I):
                continue
            scoped_storage = storage
            if content.strip().lower().startswith("production"):
                scoped_storage = [
                    item
                    for item in storage
                    if item.get("environment") in {"prod", "production"}
                    or re.search(r"(?:^|[._/-])(?:prod|production)(?:$|[._/-])", item["identity"].lower())
                ]
            public = [item for item in scoped_storage if item["public"] == "DECLARED_PUBLIC"]
            claims.append(
                {
                    "text": content.strip(),
                    "origin": "DOCUMENTATION",
                    "category": "CLOUD_SECURITY",
                    "expected": "private_storage",
                    "assertion_family": "storage_privacy",
                    "path": path,
                    "line": line,
                    "status": "CONTRADICTED" if public else "UNVERIFIED",
                    "reason": "A supported storage declaration explicitly permits public access. This contradicts the broad assertion within the declared configuration scope; live deployment is unobserved."
                    if public
                    else "The supported inventory does not establish storage privacy in the assertion's environment scope; complete policy and deployed access are unobserved.",
                    "signals": [
                        {
                            "path": item["path"],
                            "line": item["line"],
                            "type": "cloud_resource",
                            "value": item["identity"],
                        }
                        for item in public
                    ],
                    "severity": "HIGH",
                    "confidence": "HIGH" if public else "LOW",
                    "review_status": "OPEN",
                    "verifier": "NATIVE_STATIC_STORAGE_PRIVACY",
                    "verification_scope": "DECLARED_CONFIGURATION",
                }
            )
    duplicates = {}
    for metric in quality_metrics:
        if metric["token_count"] >= 30:
            duplicates.setdefault(metric["body_hash"], []).append(metric)
    for group in duplicates.values():
        if len(group) > 1:
            for metric in group[1:]:
                findings.append(
                    finding(
                        "PT-QUALITY-007",
                        metric["path"],
                        metric["line"],
                        "Exact normalized function body also occurs at "
                        + group[0]["path"]
                        + ":"
                        + str(group[0]["line"]),
                    )
                )
    findings.extend(link_local_declarations(files, assets, warnings, finding, infrastructure_settings))
    for resource in assets:
        resource["environment"] = (
            infrastructure_settings["environment"]
            if infrastructure_settings["environment"] != "UNKNOWN"
            else resource.get("environment", "UNKNOWN")
        )
    component_started = time.perf_counter()
    quality_findings, quality = quality_build(input_files, quality_metrics, signals, findings, warnings, profile)
    if performance:
        performance.record("QUALITY_AGGREGATION", time.perf_counter() - component_started)
    findings = [f for f in findings if f["category"] != "QUALITY"] + quality_findings
    component_started = time.perf_counter()
    annotate_finding_identity(files, findings, quality_metrics)
    if performance:
        performance.record("FINAL_IDENTITY", time.perf_counter() - component_started)
    quality["parser_signature"] = PARSER_SIGNATURE
    quality["parsers"] = [
        {k: v for k, v in s.items() if k not in {"symbols", "observations", "file_metrics"}}
        for s in signals
        if s.get("type") == "parser" or s.get("type") == "quality_file" and s.get("parser") == "Python ast"
    ]
    if quality["state"] == "PARTIAL":
        warnings.append(
            {
                "analyzer": "QUALITY",
                "state": "PARTIAL",
                "message": "Quality scope includes unsupported/partial source or exceeded duplication work limits; inspect file inventory.",
            }
        )
    claims.extend(sorted(implementation_claims(signals, deps), key=claim_key))
    if len(claims) > 1500:
        claims = claims[:1500]
        warnings.append({"analyzer": "CLAIMS", "message": "Claim limit reached; extraction coverage is partial."})
    for claim in claims:
        claim.setdefault("claim_key", claim_key(claim))
    py_files = sum(path.endswith(".py") for path in files)
    pattern_files = sum(path.endswith((".js", ".ts", ".jsx", ".tsx", ".java", ".mjs", ".cjs")) for path in files)
    iac_files = sum(
        files.metadata_for(path).get("iac_candidate", bool(files.metadata_for(path).get("infrastructure_format")))
        if hasattr(files, "metadata_for")
        else is_iac_source(path, files[path])
        for path in files
    )
    manifest_files = sum(
        PurePosixPath(path).name
        in {
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "pyproject.toml",
            "poetry.lock",
            "uv.lock",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
        }
        or PurePosixPath(path).name.startswith("requirements")
        for path in files
    )

    def engine(name, count, limitations, categories=(), declarations=0):
        messages = [
            warning["message"]
            for warning in warnings
            if warning["analyzer"] == name or name in {"QUALITY", "SAST"} and warning["analyzer"] == "PARSING"
        ]
        return {
            "state": "FAILED"
            if name in failures
            else "PARTIAL"
            if messages
            else "COMPLETED"
            if count
            else "SKIPPED_UNSUPPORTED",
            "supported_files": count,
            "findings": sum(f["category"] in categories for f in findings),
            "declarations": declarations,
            "warnings": messages,
            "limitations": limitations,
            "analyzer_version": VERSION,
        }

    engines = {
        "PARSING": engine(
            "PARSING",
            py_files + pattern_files,
            [
                "Python standard-library AST and versioned Tree-sitter JavaScript/TypeScript/TSX/Java grammars; syntax node budget 40,000."
            ],
        ),
        "QUALITY": engine(
            "QUALITY",
            py_files + pattern_files,
            [
                "Native syntax complexity, length, nesting, parameters, exception observations, bounded normalized duplicate blocks and Python structural reliability checks. Partial language maturity; no full CFG/type or unused-symbol resolution."
            ],
            {"QUALITY"},
        ),
        "SAST": engine(
            "SAST",
            py_files + pattern_files,
            [
                "Python bounded assignment and local-helper source/sink flow, contextual HTML sanitizer and SQL parameter models; JS/TS/Java syntax hotspots. No complete CFG, cross-file taint or runtime exploitability proof."
            ],
            {"SAST"},
        ),
        "SECRETS": engine(
            "SECRETS", len(files), ["Pattern/context checks only; credential validity is never tested."], {"SECRET"}
        ),
        "DEPENDENCIES": engine(
            "DEPENDENCIES",
            manifest_files,
            [
                "Manifest inventory; Yarn/pnpm resolved stanza subsets; lockfile directness may be unknown; no complete dependency resolution."
            ],
            declarations=len(deps),
        ),
        "IAC": engine(
            "IAC",
            iac_files,
            [
                "Structured Terraform HCL2, Kubernetes, Compose, CloudFormation and Dockerfile checks; aliases and unrendered Helm templates refused. No Terraform evaluation or live deployment proof."
            ],
            {"IAC"},
        ),
        "CLAIMS": engine(
            "CLAIMS",
            len(files),
            [
                "Recognized affirmative documentation and implementation statements; unsupported semantic statements are not extracted."
            ],
            declarations=len(claims),
        ),
        "API": engine(
            "API",
            sum("openapi" in files[path].lower() for path in files if path.endswith(".json")),
            [
                "JSON OpenAPI and supported Python route decorators; unsupported routers, prefixes and dynamic registration remain unverified."
            ],
        ),
    }
    profile = profile or {}
    configured = []
    for item in findings:
        override = {} if item["category"] == "QUALITY" else profile.get("rules", {}).get(item["rule"], {})
        if item["category"] == "IAC":
            infrastructure_override = infrastructure_settings["rules"].get(item["rule"], {})
            if (
                infrastructure_override.get("environments")
                and infrastructure_settings["environment"] not in infrastructure_override["environments"]
            ):
                continue
            override = {**override, **infrastructure_override}
        if override.get("enabled", True):
            configured.append(
                {
                    **item,
                    "severity": override.get("severity", item["severity"]),
                    "profile_version": profile.get("version", 0),
                }
            )
    findings = configured
    license_policy = profile.get("licenses", {})
    for dep in deps:
        license_id = dep.get("license")
        dep["license_status"] = (
            "UNKNOWN"
            if not license_id
            else "RESTRICTED"
            if license_id in license_policy.get("restricted", [])
            else "APPROVED"
            if license_id in license_policy.get("approved", [])
            else "REVIEW_REQUIRED"
        )
        if dep["license_status"] == "RESTRICTED" or license_policy and dep["license_status"] == "REVIEW_REQUIRED":
            findings.append(
                finding(
                    "PT-LICENSE-001",
                    dep["path"],
                    1,
                    "Observed manifest license "
                    + str(license_id)
                    + "; policy outcome "
                    + dep["license_status"]
                    + ". This is not a legal conclusion.",
                    "MEDIUM",
                )
            )
    return {
        "findings": findings,
        "cloud_assets": assets,
        "quality_metrics": quality["metrics"],
        "code_quality": quality,
        "analysis_coverage": build_analysis_coverage(input_files, files, quality, signals, warnings, VERSION),
        "signals": signals,
        "dependencies": deps,
        "claims": claims,
        "files": files,
        "analysis_cache": cache,
        "reused_files": reused,
        "verification_cache": {"version": VERSION, "claims": verification_cache},
        "reused_verifications": reused_verifications,
        "reverified_claims": len(candidates) - reused_verifications,
        "engines": engines,
        "warnings": warnings,
        "documentation_files": sum(path.endswith(".md") for path in files),
    }


def sbom(deps):
    """CycloneDX inventory, deduplicated across manifests; no resolved graph claim."""
    unique = {}
    for dependency in deps:
        key = (dependency["ecosystem"], dependency["name"], dependency["version"])
        entry = unique.setdefault(key, {**dependency, "manifests": set(), "direct_any": False})
        entry["manifests"].add(dependency["path"])
        entry["direct_any"] |= dependency.get("direct") is True
        if not entry.get("license") and dependency.get("license"):
            entry["license"] = dependency["license"]
    components = []
    for (ecosystem, name, version), dependency in sorted(unique.items()):
        package_type = {"PyPI": "pypi", "npm": "npm", "Maven": "maven"}.get(ecosystem, "generic")
        package_name = name.replace(":", "/", 1) if ecosystem == "Maven" else name
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "bom-ref": f"{ecosystem}:{name}@{version}",
            "purl": f"pkg:{package_type}/{quote(package_name, safe='/')}@{quote(version, safe='')}",
            "properties": [{"name": "projecttrace:version_kind", "value": dependency.get("version_kind", "UNKNOWN")}]
            + [{"name": "projecttrace:manifest", "value": manifest} for manifest in sorted(dependency["manifests"])],
        }
        if isinstance(dependency.get("license"), str):
            component["licenses"] = [{"license": {"name": dependency["license"]}}]
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": components,
        "metadata": {"component": {"type": "application", "name": "Imported snapshot", "bom-ref": "snapshot-root"}},
        "dependencies": [
            {
                "ref": "snapshot-root",
                "dependsOn": [
                    f"{ecosystem}:{name}@{version}"
                    for (ecosystem, name, version), value in sorted(unique.items())
                    if value["direct_any"]
                ],
            }
        ],
    }
