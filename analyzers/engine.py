"""Bounded static analysis. Repository contents are data, never executable."""

import ast
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import PurePosixPath
from urllib.parse import quote

from analyzers.baseline import context_signals, implementation_claims, inventory
from analyzers.verifiers import claim_key, extract_documentation, verify_claim

VERSION = "1.2.0"
MAX_FILES = 1000
MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 10_000_000
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
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


def safe_path(path):
    if not isinstance(path, str) or len(path) > 240 or "\\" in path or ":" in path or "\x00" in path:
        raise ValueError("Repository contains an invalid path.")
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or path.startswith("/") or not p.parts:
        raise ValueError("Repository path traversal is forbidden.")
    return p


def validate_files(files):
    if not files or len(files) > MAX_FILES:
        raise ValueError(f"Repository must contain 1–{MAX_FILES} files.")
    size = 0
    clean = {}
    for path, source in files.items():
        p = safe_path(path)
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in {"Dockerfile", "CODEOWNERS", "Makefile"}:
            continue
        if not isinstance(source, str):
            raise ValueError("File contents must be UTF-8 text.")
        n = len(source.encode())
        size += n
        if n > MAX_FILE_BYTES or size > MAX_TOTAL_BYTES:
            raise ValueError("Repository exceeds the configured file or total size limit.")
        clean[str(p)] = source
    if not clean:
        raise ValueError("Repository contains no supported text files.")
    return clean


def read_zip(blob):
    if len(blob) > MAX_TOTAL_BYTES:
        raise ValueError("Archive exceeds the 10 MB limit.")
    files = {}
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
                or total > MAX_TOTAL_BYTES
                or entry.file_size > max(entry.compress_size, 1) * 200
            ):
                raise ValueError("Archive exceeds extraction limits or compression ratio.")
            if entry.is_dir() or p.suffix.lower() not in TEXT_SUFFIXES and p.name not in {"Dockerfile", "CODEOWNERS"}:
                continue
            canonical = str(p)
            if canonical in files:
                raise ValueError("Archive contains duplicate paths.")
            try:
                files[canonical] = archive.read(entry).decode("utf-8")
            except UnicodeDecodeError:
                continue
    return validate_files(files)


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


def python_analysis(path, source):
    findings, signals = [], []
    try:
        tree = ast.parse(source)
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


def extract_claims(files):
    return extract_documentation(files)


def verify(claim, signals, deps):
    result, _ = verify_claim(claim, signals, deps)
    return result["status"], result["reason"], result["signals"]


def analyze(files, cached_analysis=None, progress=None, verification_context=None):
    files = validate_files(files)
    if progress:
        progress("ANALYZING")
    findings, signals, warnings = [], [], []
    failures = set()
    cache = {}
    reused = 0
    for path, source in files.items():
        previous = (cached_analysis or {}).get(path)
        content_hash = hash_text(source)
        if (
            previous
            and previous.get("hash") == content_hash
            and previous.get("version") == VERSION
            and not previous.get("warnings")
        ):
            cached = json.loads(json.dumps(previous))
            findings.extend(cached["findings"])
            signals.extend(cached["signals"])
            cache[path] = cached
            reused += 1
            continue
        finding_start, signal_start = len(findings), len(signals)
        if path.endswith(".py"):
            try:
                f, s = python_analysis(path, source)
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
        elif path.endswith((".js", ".ts", ".jsx", ".tsx", ".java")):
            for line_no, line in enumerate(pattern_source(source).splitlines(), 1):
                # Conservative syntax-pattern adapters, not full taint analysis.
                if re.search(r"\beval\s*\(", line) and not line.lstrip().startswith(("//", "*")):
                    findings.append(
                        {
                            "rule": "PT-SAST-005",
                            "rule_id": "PT-SAST-005",
                            "rule_version": VERSION,
                            "analyzer_version": VERSION,
                            "category": "SAST",
                            "severity": "HIGH",
                            "confidence": "MEDIUM",
                            "title": "Dynamic code evaluation",
                            "path": path,
                            "line": line_no,
                            "end_line": line_no,
                            "language": "Java"
                            if path.endswith(".java")
                            else "TypeScript"
                            if path.endswith((".ts", ".tsx"))
                            else "JavaScript",
                            "explanation": "An eval call pattern was found. Data flow and reachability are unproven.",
                            "remediation": "Replace dynamic evaluation with structured data handling.",
                            "cwe": "CWE-95",
                            "review_status": "OPEN",
                            "fingerprint": hash_text(path + str(line_no)),
                        }
                    )
                if re.search(r"\.innerHTML\s*=\s*(?![\"'`\s])", line) and not line.lstrip().startswith("//"):
                    findings.append(
                        finding(
                            "PT-SAST-006",
                            path,
                            line_no,
                            "A non-literal expression is assigned to innerHTML. Data flow is unproven.",
                            "MEDIUM",
                        )
                    )
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
        if path.endswith((".yml", ".yaml", ".tf")) or PurePosixPath(path).name == "Dockerfile":
            for line_no, line in enumerate(source.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.match(r"\s*privileged\s*:\s*true\s*(?:#.*)?$", line, re.I):
                    findings.append(finding("PT-IAC-001", path, line_no))
                if re.match(r"\s*USER\s+(root|0)\s*$", line, re.I):
                    findings.append(finding("PT-IAC-002", path, line_no))
                if re.match(r"\s*acl\s*=\s*[\"\']public-(read|read-write)[\"\']\s*(?:#.*)?$", line):
                    findings.append(finding("PT-IAC-003", path, line_no))
        cache[path] = {
            "hash": content_hash,
            "version": VERSION,
            "findings": findings[finding_start:],
            "signals": signals[signal_start:],
            "warnings": [warning for warning in warnings if warning.get("path") == path],
        }
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
    signals.extend(s for path, source in files.items() for s in context_signals(path, source))
    warnings.extend(
        {
            "analyzer": "PARSING",
            "path": f["path"],
            "message": "Python source could not be parsed; analysis coverage is partial.",
        }
        for f in findings
        if f["rule"] == "PT-PARSE-001"
    )
    claims = []
    if progress:
        progress("EXTRACTING_CLAIMS")
    try:
        candidates = extract_claims(files)
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
    for path, source in files.items():
        if not path.endswith(".json"):
            continue
        try:
            contract = json.loads(source)
            if not isinstance(contract, dict) or "openapi" not in contract:
                continue
            for route, methods in contract.get("paths", {}).items():
                for method in methods:
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
        progress("VERIFYING")
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
    claims.extend(implementation_claims(signals, deps))
    if len(claims) > 1500:
        claims = claims[:1500]
        warnings.append({"analyzer": "CLAIMS", "message": "Claim limit reached; extraction coverage is partial."})
    for claim in claims:
        claim.setdefault("claim_key", claim_key(claim))
    py_files = sum(path.endswith(".py") for path in files)
    pattern_files = sum(path.endswith((".js", ".ts", ".jsx", ".tsx", ".java")) for path in files)
    iac_files = sum(
        path.endswith((".tf", ".yml", ".yaml")) or PurePosixPath(path).name == "Dockerfile" for path in files
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
            "PARSING", py_files, ["Python standard-library AST; JS/TS/Java use limited lexical patterns."]
        ),
        "QUALITY": engine(
            "QUALITY",
            py_files,
            [
                "Python branch approximation, length, nesting, class size and bare exceptions; JS/TS/Java quality parsers deferred."
            ],
            {"QUALITY"},
        ),
        "SAST": engine(
            "SAST",
            py_files + pattern_files,
            [
                "Narrow static source/sink rules; no complete control-flow, interprocedural taint or exploitability proof."
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
                "Static privileged/root/public-ACL patterns; no live cloud, Terraform evaluation or complete YAML semantics."
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
            sum(path.endswith(".json") and "openapi" in source.lower() for path, source in files.items()),
            [
                "JSON OpenAPI and supported Python route decorators; unsupported routers, prefixes and dynamic registration remain unverified."
            ],
        ),
    }
    return {
        "findings": findings,
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
