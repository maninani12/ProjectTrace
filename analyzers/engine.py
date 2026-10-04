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

VERSION = "1.1.0"
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
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.S
)


def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def redact(text):
    text = PRIVATE_RE.sub("[REDACTED PRIVATE KEY]", text)
    text = re.sub(r"(?i)((?:postgres(?:ql)?|mysql|mongodb)(?:\+\w+)?://[^\s/:]+:)[^\s/@]+(@)", r"\1[REDACTED]\2", text)
    text = re.sub(
        r"(?m)^(?:[A-Z_]*(?:PASSWORD|TOKEN|SECRET|API_KEY))\s*=\s*[^\n]+$", "[REDACTED ENVIRONMENT SECRET]", text
    )
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
        "rule_version": VERSION,
        "analyzer_version": VERSION,
        "category": category,
        "severity": severity,
        "title": title,
        "path": path,
        "line": line,
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


def python_analysis(path, source):
    findings, signals = [], []
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError) as error:
        return [finding("PT-PARSE-001", path, getattr(error, "lineno", 1) or 1)], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                signals.append({"type": "import", "value": name, "path": path, "line": node.lineno})
        if isinstance(node, ast.Call):
            name = call_name(node.func)
            argument = node.args[0] if node.args else None
            if isinstance(argument, ast.Call) and call_name(argument.func).split(".")[-1] == "text":
                argument = argument.args[0] if argument.args else None
            dynamic_sql = isinstance(argument, (ast.JoinedStr, ast.BinOp)) or (
                isinstance(argument, ast.Call) and call_name(argument.func).endswith(".format")
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
            if name.endswith("add_middleware") and node.args and call_name(node.args[0]).endswith("SessionMiddleware"):
                signals.append({"type": "auth", "value": "session", "path": path, "line": node.lineno})
            if name in {"jwt.encode", "jwt.decode"}:
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
            match = re.match(r"(postgres(?:ql)?|sqlite)(?:\+\w+)?://", node.value)
            if match:
                signals.append(
                    {
                        "type": "database",
                        "value": "postgresql" if match.group(1).startswith("postgres") else "sqlite",
                        "path": path,
                        "line": node.lineno,
                    }
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexity = 1 + sum(
                isinstance(x, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp)) for x in ast.walk(node)
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
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                    method = call_name(decorator.func).split(".")[-1].upper()
                    if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                        signals.append(
                            {
                                "type": "route",
                                "value": f"{method} {decorator.args[0].value}",
                                "path": path,
                                "line": decorator.lineno,
                            }
                        )
    return findings, signals


def dependencies(files):
    result = {}
    for path, source in files.items():
        if path.endswith("requirements.txt"):
            for line in source.splitlines():
                match = re.match(r"^\s*([\w.-]+)==([\w.+-]+)\s*(?:#.*)?$", line)
                if match:
                    name, version = match.groups()
                    result[("PyPI", name.lower(), version)] = {
                        "name": name,
                        "version": version,
                        "ecosystem": "PyPI",
                        "path": path,
                        "direct": True,
                    }
        if path.endswith("package-lock.json"):
            try:
                lock = json.loads(source)
                direct = lock.get("packages", {}).get("", {}).get("dependencies", {})
                for key, value in lock.get("packages", {}).items():
                    if key and "node_modules/" in key and value.get("version"):
                        name = key.rsplit("node_modules/", 1)[1]
                        result[("npm", name, value["version"])] = {
                            "name": name,
                            "version": value["version"],
                            "ecosystem": "npm",
                            "path": path,
                            "direct": name in direct,
                            "license": value.get("license"),
                        }
            except ValueError, TypeError, AttributeError:
                pass
    return list(result.values())


def extract_claims(files):
    claims = []
    patterns = [
        (
            "AUTHENTICATION",
            r"Authentication uses (JWT|session(?:s)?|OAuth)\b",
            lambda m: m.group(1).lower().rstrip("s"),
        ),
        (
            "TECHNOLOGY",
            r"(?:Backend|The service|Database) uses (FastAPI|PostgreSQL|Kafka|Redis)\b",
            lambda m: m.group(1).lower(),
        ),
        ("API", r"The API exposes (/(?:[\w/-]+))", lambda m: "GET " + m.group(1)),
        ("ARCHITECTURE", r"Orders publishes events through (Kafka|Redis)\b", lambda m: m.group(1).lower()),
    ]
    for path, text in files.items():
        if not path.endswith(".md"):
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for category, pattern, value in patterns:
                for match in re.finditer(pattern, line, re.I):
                    claims.append(
                        {
                            "text": match.group(0) + ".",
                            "category": category,
                            "expected": value(match),
                            "path": path,
                            "line": line_no,
                        }
                    )
            compound = re.search(r"Backend uses (.+)[.]", line)
            if compound and ("," in compound.group(1) or " and " in compound.group(1)):
                for technology in ["FastAPI", "PostgreSQL", "JWT", "Redis", "Kafka"]:
                    if technology.lower() in compound.group(1).lower() and not any(
                        c["path"] == path and c["line"] == line_no and c["expected"] == technology.lower()
                        for c in claims
                    ):
                        claims.append(
                            {
                                "text": ("Authentication" if technology == "JWT" else "Backend")
                                + f" uses {technology}.",
                                "category": "AUTHENTICATION" if technology == "JWT" else "TECHNOLOGY",
                                "expected": technology.lower(),
                                "path": path,
                                "line": line_no,
                            }
                        )
    return claims


def verify(claim, signals, deps):
    expected, category = claim["expected"], claim["category"]
    relevant = []
    status, explanation = (
        "UNVERIFIED",
        "No conclusive static evidence was found. Absence does not prove a contradiction.",
    )
    if category == "AUTHENTICATION":
        current = [s for s in signals if s["type"] == "auth"]
        relevant = current
        modes = {s["value"] for s in current}
        if expected in modes:
            status, explanation = (
                "VERIFIED",
                f"An executable syntax node configures {expected} authentication. Runtime behavior has not been observed.",
            )
        elif modes and expected in {"jwt", "session"} and modes <= {"jwt", "session"}:
            status, explanation = (
                "CONTRADICTED",
                f"The scanned implementation configures {', '.join(sorted(modes))} authentication; the document claims {expected}. Other files or services may implement additional methods.",
            )
    elif category == "API":
        relevant = [s for s in signals if s["type"] == "route" and s["value"] == expected]
        if relevant:
            status, explanation = "VERIFIED", "A matching route decorator exists in the current source snapshot."
    else:
        relevant = [s for s in signals if s["type"] in {"database", "technology"} and s["value"] == expected]
        if relevant:
            return (
                "VERIFIED",
                f"Current syntax/configuration explicitly selects {expected}; runtime is unobserved.",
                relevant,
            )
        aliases = {
            "postgresql": ["psycopg", "asyncpg", "psycopg2"],
            "fastapi": ["fastapi"],
            "kafka": ["kafka", "confluent_kafka"],
            "redis": ["redis"],
        }.get(expected, [expected])
        relevant = [s for s in signals if s["type"] == "import" and any(s["value"].split(".")[0] == a for a in aliases)]
        if relevant:
            status, explanation = (
                "INFERRED",
                f"Source imports {expected}-related modules. Imports alone do not prove runtime use.",
            )
        elif any(d["name"].lower() in aliases for d in deps):
            status, explanation = (
                "INFERRED",
                "A pinned dependency supports this technology claim; execution is unobserved.",
            )
    return status, explanation, relevant


def analyze(files, cached_analysis=None, progress=None):
    files = validate_files(files)
    if progress:
        progress("ANALYZING")
    findings, signals = [], []
    cache = {}
    reused = 0
    for path, source in files.items():
        previous = (cached_analysis or {}).get(path)
        content_hash = hash_text(source)
        if previous and previous.get("hash") == content_hash and previous.get("version") == VERSION:
            cached = json.loads(json.dumps(previous))
            findings.extend(cached["findings"])
            signals.extend(cached["signals"])
            cache[path] = cached
            reused += 1
            continue
        finding_start, signal_start = len(findings), len(signals)
        if path.endswith(".py"):
            f, s = python_analysis(path, source)
            findings.extend(f)
            signals.extend(s)
        elif path.endswith((".js", ".ts", ".jsx", ".tsx", ".java")):
            for line_no, line in enumerate(source.splitlines(), 1):
                # Conservative syntax-pattern adapters, not full taint analysis.
                if re.search(r"\beval\s*\(", line) and not line.lstrip().startswith(("//", "*")):
                    findings.append(
                        {
                            "rule": "PT-SAST-005",
                            "rule_version": VERSION,
                            "analyzer_version": VERSION,
                            "category": "SAST",
                            "severity": "HIGH",
                            "confidence": "MEDIUM",
                            "title": "Dynamic code evaluation",
                            "path": path,
                            "line": line_no,
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
        for match in list(SECRET_RE.finditer(source)) + list(PRIVATE_RE.finditer(source)):
            findings.append(
                finding(
                    "PT-SECRET-001",
                    path,
                    source[: match.start()].count("\n") + 1,
                    "Secret-like material detected. The value is redacted; validity has not been tested.",
                    "MEDIUM",
                )
            )
        if path.endswith((".yml", ".yaml", ".tf")) or PurePosixPath(path).name == "Dockerfile":
            for line_no, line in enumerate(source.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"privileged\s*:\s*true\b", line, re.I):
                    findings.append(finding("PT-IAC-001", path, line_no))
                if re.match(r"\s*USER\s+(root|0)\s*$", line, re.I):
                    findings.append(finding("PT-IAC-002", path, line_no))
                if re.search(r"acl\s*=\s*[\"\']public-(read|read-write)[\"\']", line):
                    findings.append(finding("PT-IAC-003", path, line_no))
        cache[path] = {
            "hash": content_hash,
            "version": VERSION,
            "findings": findings[finding_start:],
            "signals": signals[signal_start:],
        }
    deps, warnings = inventory(files)
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
    candidates = extract_claims(files)
    if progress:
        progress("VERIFYING")
    for claim in candidates:
        status, reason, evidence = verify(claim, signals, deps)
        claims.append(
            {
                **claim,
                "origin": "DOCUMENTATION",
                "status": status,
                "reason": reason,
                "signals": evidence,
                "severity": "HIGH" if claim["category"] == "AUTHENTICATION" else "MEDIUM",
                "confidence": "HIGH" if status == "VERIFIED" else "MEDIUM",
                "review_status": "OPEN",
            }
        )
    claims.extend(implementation_claims(signals, deps))
    # JSON OpenAPI paths are compared with extracted Python route decorators.
    for path, source in files.items():
        if path.endswith(".json"):
            try:
                contract = json.loads(source)
                if "openapi" not in contract:
                    continue
                routes = {s["value"] for s in signals if s["type"] == "route"}
                for route, methods in contract.get("paths", {}).items():
                    for method in methods:
                        endpoint = method.upper() + " " + route
                        if method.upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"} and endpoint not in routes:
                            claims.append(
                                {
                                    "text": f"API contract includes {endpoint}.",
                                    "origin": "DOCUMENTATION",
                                    "category": "API",
                                    "expected": endpoint,
                                    "path": path,
                                    "line": 1,
                                    "status": "UNVERIFIED",
                                    "reason": "No matching supported route decorator was found. Unsupported routing frameworks may exist.",
                                    "signals": [],
                                    "severity": "MEDIUM",
                                    "confidence": "MEDIUM",
                                    "review_status": "OPEN",
                                }
                            )
            except ValueError, TypeError, AttributeError:
                if "openapi" in source.lower():
                    warnings.append(
                        {
                            "analyzer": "API",
                            "path": path,
                            "message": "OpenAPI contract could not be parsed; coverage is partial.",
                        }
                    )
    if len(claims) > 1500:
        claims = claims[:1500]
        warnings.append({"analyzer": "CLAIMS", "message": "Claim limit reached; extraction coverage is partial."})
    return {
        "findings": findings,
        "signals": signals,
        "dependencies": deps,
        "claims": claims,
        "files": files,
        "analysis_cache": cache,
        "reused_files": reused,
        "warnings": warnings,
        "documentation_files": sum(path.endswith(".md") for path in files),
    }


def sbom(deps):
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": d["name"],
                "version": d["version"],
                "bom-ref": f"{d['ecosystem']}:{d['name']}@{d['version']}",
                "purl": f"pkg:{'pypi' if d['ecosystem'] == 'PyPI' else 'npm'}/{quote(d['name'], safe='/')}@{quote(d['version'], safe='')}",
                **({"licenses": [{"license": {"name": d["license"]}}]} if d.get("license") else {}),
            }
            for d in deps
        ],
        "metadata": {"component": {"type": "application", "name": "Imported snapshot", "bom-ref": "snapshot-root"}},
        "dependencies": [
            {
                "ref": "snapshot-root",
                "dependsOn": [f"{d['ecosystem']}:{d['name']}@{d['version']}" for d in deps if d.get("direct")],
            }
        ],
    }
