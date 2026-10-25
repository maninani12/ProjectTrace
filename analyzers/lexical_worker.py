"""Untrusted lexical interpretation, invoked only after sandbox enforcement."""

import difflib
import fnmatch
import hashlib
import re
from pathlib import PurePosixPath

from analyzers import sandbox
from analyzers.lexical import POLICY


def changed_ranges(value):
    old, head = value["old"], value["head"]
    if any(not isinstance(s, str) or len(s) > 1_000_000 for s in (old, head)):
        raise sandbox.SandboxFailure("LEXICAL_DIFF_BUDGET")
    return {"path": value["path"], "signature": value["signature"], "ranges": [
        [j1 + 1, max(j1 + 1, j2)]
        for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, old.splitlines(), head.splitlines(), autojunk=False).get_opcodes()
        if tag != "equal"]}


def generated(source):
    return bool(re.search(r"(?im)^\s*(?:#|//|/\*|\*)\s*(?:@generated|generated (?:by|file|code)|auto-generated|do not edit)", source[:2000]))


def describe(rows):
    from analyzers.analysis_coverage import infrastructure_format
    from analyzers.code_quality.classification import BINARY_SUFFIXES, source_language
    from analyzers.engine import is_iac_source
    result = []
    for row in rows:
        source = row.get("source", row["prefix"])
        binary = PurePosixPath(row["path"]).suffix.lower() in BINARY_SUFFIXES or row["nul"] and row["utf8"]
        retained = row["utf8"] and not binary
        value = {"path": row["path"], "request_hash": row["request_hash"], "lexical_policy": POLICY,
                 "source_language": source_language(row["path"], row["prefix"] if retained else ""),
                 "infrastructure_format": infrastructure_format(row["path"], source if retained else ""),
                 "iac_candidate": is_iac_source(row["path"], source) if retained else False,
                 "generated_header": generated(row["prefix"]) if retained else False,
                 "text_retained": retained, "binary": binary, "bytes": row["bytes"],
                 "physical_lines": row["physical_lines"] if retained else None}
        if "historical" in row:
            old = row["historical"]
            for key in ("source_language", "infrastructure_format", "iac_candidate", "generated_header", "text_retained"):
                if old.get(key) is not None:
                    value[key] = old[key]
            value["physical_lines"] = old["physical_lines"]
        result.append(value)
    return result


def classify(value):
    from analyzers.code_quality.classification import classify as run
    class View(dict):
        def metadata_for(self, path):
            return self.metadata.get(path)
    files = View({r["path"]: "" for r in value["rows"] if r["metadata"] is not None})
    files.metadata = {r["path"]: r["metadata"] for r in value["rows"] if r["metadata"] is not None}
    files.intake = [r["diagnostic"] for r in value["rows"] if r["diagnostic"] is not None]
    return run(files, value["scope"])


def ownership(value):
    source, paths = value["source"], value["paths"]
    if len(source.encode()) > 512_000 or len(paths) > 100:
        raise sandbox.SandboxFailure("CODEOWNERS_INPUT_BUDGET")
    rules, diagnostics = [], []
    lines = source.splitlines()
    if len(lines) > 5000:
        diagnostics.append("CODEOWNERS_LINE_LIMIT")
    for line in lines[:5000]:
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if len(parts) < 2 or parts[0].startswith("!") or "\\" in parts[0] or ".." in PurePosixPath(parts[0]).parts:
            diagnostics.append("UNSUPPORTED_CODEOWNERS_SYNTAX")
            continue
        pattern = parts[0].lstrip("/")
        if len(pattern) > 4096:
            raise sandbox.SandboxFailure("CODEOWNERS_PATTERN_BUDGET")
        if pattern.endswith("/"):
            pattern += "**"
        variants = [pattern, "**/" + pattern]
        variants.extend(p[3:] for p in tuple(variants) if p.startswith("**/"))
        checks = tuple(re.compile(fnmatch.translate(p)).match for p in dict.fromkeys(variants))
        owner = " ".join(part for part in parts[1:] if not part.startswith("#"))[:200]
        if not owner:
            diagnostics.append("UNSUPPORTED_CODEOWNERS_SYNTAX")
            continue
        rules.append((checks, owner))
    if len(rules) * len(paths) > 500_000:
        raise sandbox.SandboxFailure("CODEOWNERS_MATCH_BUDGET")
    owners = {}
    for path in paths:
        selected = None
        for checks, owner in rules:
            if any(check(path) for check in checks):
                selected = owner
        owners[path] = {"selected": selected, "state": "PARTIAL_UNSUPPORTED_RULES" if diagnostics else "SUPPORTED_RULES",
                        "diagnostics": sorted(set(diagnostics))[:20]}
    return {"signature": value["signature"], "owners": owners}


def sections(value):
    from analyzers.engine import redact
    source = value["source"]
    if len(source.encode()) > 512_000 or hashlib.sha256(source.encode()).hexdigest() != value["hash"]:
        raise sandbox.SandboxFailure("SECTIONS_SOURCE_BUDGET")
    return {"path": value["path"], "hash": value["hash"], "sections": [
        {"title": redact(line.lstrip("# ")), "line": n}
        for n, line in enumerate(source.splitlines(), 1) if line.startswith("#")]}


def storage_claims(files, assets):
    claims = []
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
    return claims
