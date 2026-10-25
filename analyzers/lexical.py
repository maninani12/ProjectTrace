"""Coordinator for bounded lexical operations; no source/glob grammar executes here."""

import hashlib
import json

from analyzers import sandbox

POLICY = "lexical-v1"
LANGUAGES = {None, "UNKNOWN", "Python", "JavaScript", "TypeScript", "Java", "Make", "Shell", "Ruby", "Perl",
             "Rust", "Go", "C#", "C", "C++", "C/C++", "PHP", "Kotlin", "Swift", "Scala", "Dart", "SQL",
             "R", "Vue", "Svelte", "PowerShell", "Lua"}
FORMATS = {None, "Dockerfile", "Terraform", "CloudFormation", "Kubernetes", "Compose"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def changed_ranges(path, old, head):
    from analyzers.engine import safe_path
    path = str(safe_path(path))
    if any(not isinstance(s, str) or len(s) > 1_000_000 for s in (old, head)):
        raise sandbox.SandboxFailure("LEXICAL_DIFF_BUDGET")
    signature = digest([path, old, head])
    result = sandbox.call("lexical_diff", {"path": path, "old": old, "head": head, "signature": signature})
    if (not isinstance(result, dict) or set(result) != {"path", "signature", "ranges"}
            or result["path"] != path or result["signature"] != signature or not isinstance(result["ranges"], list)):
        raise sandbox.SandboxFailure("DIFF_SCOPE")
    maximum, previous = len(head.splitlines()) + 1, 0
    for row in result["ranges"]:
        if (not isinstance(row, list) or len(row) != 2 or any(type(n) is not int for n in row)
                or not previous < row[0] <= row[1] <= maximum):
            raise sandbox.SandboxFailure("DIFF_SCHEMA")
        previous = row[1]
    return [tuple(row) for row in result["ranges"]]


def packet(path, source, *, raw=None):
    from analyzers.engine import safe_path
    path = str(safe_path(path))
    if source is not None and (not isinstance(source, str) or len(source.encode()) > 512_000):
        raise sandbox.SandboxFailure("LEXICAL_FILE_BUDGET")
    size = len(raw) if raw is not None else len(source.encode()) if source is not None else 0
    value = {"path": path, "prefix": source[:2000] if source is not None else "", "bytes": size,
             "physical_lines": len(source.splitlines()) if source is not None else None,
             "utf8": source is not None, "nul": b"\x00" in raw if raw is not None else "\x00" in source if source is not None else False}
    # Language recognition historically examines the complete first line.
    # Delimiter selection is a bounded primitive; shebang interpretation stays isolated.
    if source is not None and len(source) > 2000:
        value["first_line"] = source.split("\n", 1)[0]
    if source is not None and path.endswith((".json", ".yml", ".yaml")):
        value["source"] = source
    value["request_hash"] = digest(value)
    return value


def batches(rows, maximum=2_000_000):
    batch, size = [], 0
    for row in rows:
        length = len(json.dumps(row, ensure_ascii=False).encode())
        if batch and (len(batch) >= 100 or size + length > maximum):
            yield batch
            batch, size = [], 0
        batch.append(row)
        size += length
    if batch:
        yield batch


def validate_description(value, original):
    if (not isinstance(value, dict) or set(value) != {"path", "request_hash", "source_language", "infrastructure_format",
            "iac_candidate", "generated_header", "text_retained", "binary", "bytes", "physical_lines", "lexical_policy"}
            or value["path"] != original["path"] or value["request_hash"] != original["request_hash"]
            or value["source_language"] not in tuple(LANGUAGES) or value["infrastructure_format"] not in tuple(FORMATS)
            or any(type(value[k]) is not bool for k in ("iac_candidate", "generated_header", "text_retained", "binary"))
            or value["lexical_policy"] != POLICY or type(value["bytes"]) is not int or not 0 <= value["bytes"] <= 4_000_000_000
            or value["bytes"] != original["bytes"]
            or value["physical_lines"] != (original["physical_lines"] if value["text_retained"] else None)):
        raise sandbox.SandboxFailure("LEXICAL_OUTPUT_SCOPE")
    return {k: v for k, v in value.items() if k not in {"path", "request_hash"}}


def describe_packets(rows):
    result = {}
    for batch in batches(rows):
        values = sandbox.call("lexical_describe", {"rows": batch})
        if not isinstance(values, list) or len(values) != len(batch):
            raise sandbox.SandboxFailure("LEXICAL_OUTPUT_SCOPE")
        for row, value in zip(batch, values, strict=True):
            result[row["path"]] = validate_description(value, row)
    return result


def describe_one(path, source):
    row = packet(path, source)
    return describe_packets([row])[row["path"]]


def describe(files):
    """Saved immutable inventory metadata needs no source decryption on warm paths."""
    result, pending = {}, []
    for path in files:
        if hasattr(files, "metadata_for"):
            data = files.metadata_for(path)
            if data.get("lexical_policy") == POLICY:
                if (data.get("source_language") not in tuple(LANGUAGES) or data.get("infrastructure_format") not in tuple(FORMATS)
                        or any(type(data.get(k)) is not bool for k in ("iac_candidate", "generated_header", "text_retained"))
                        or type(data.get("bytes")) is not int or data["bytes"] < 0
                        or (data.get("physical_lines") is not None and (type(data["physical_lines"]) is not int or data["physical_lines"] < 0))):
                    raise sandbox.SandboxFailure("LEXICAL_STORED_METADATA")
                result[path] = {k: data[k] for k in ("source_language", "infrastructure_format", "iac_candidate",
                                                     "generated_header", "text_retained", "bytes", "physical_lines", "lexical_policy")}
                continue
            # Historical metadata is typed input to contained classification;
            # do not rewrite historical records or decode excluded source.
            row = packet(path, "")
            row["historical"] = {k: data.get(k) for k in ("source_language", "infrastructure_format", "iac_candidate",
                                                         "generated_header", "text_retained", "bytes", "physical_lines")}
            row["bytes"], row["physical_lines"] = data["bytes"], data.get("physical_lines")
            row["request_hash"] = digest({k: v for k, v in row.items() if k != "request_hash"})
            pending.append(row)
        else:
            pending.append(packet(path, files[path]))
    for data in getattr(files, "intake", []):
        row = packet(data["path"], None)
        row["bytes"] = data["bytes"]
        row["request_hash"] = digest({k: v for k, v in row.items() if k != "request_hash"})
        pending.append(row)
    cache = getattr(files, "_lexical_descriptions", None)
    signature = digest(pending)
    if cache and cache[0] == signature:
        result.update(cache[1])
    else:
        measured = describe_packets(pending)
        result.update(measured)
        if hasattr(files, "__dict__"):
            files._lexical_descriptions = (signature, measured)
    return result


def classify(files, scope):
    from analyzers.engine import safe_path
    metadata = describe(files)
    if not hasattr(files, "metadata_for"):
        metadata = {p: {**row, **({"physical_lines": len(files[p].splitlines()), "bytes": len(files[p].encode())}
                                if p in files else {})} for p, row in metadata.items()}
    diagnostics = {r["path"]: r for r in getattr(files, "intake", [])}
    result = []
    rows = ({"path": p, "metadata": metadata.get(p), "diagnostic": diagnostics.get(p)}
            for p in sorted(set(metadata) | set(diagnostics)))
    for batch in batches(rows):
        values = sandbox.call("lexical_classify", {"rows": batch, "scope": scope or {}})
        if not isinstance(values, list) or [r.get("path") for r in values if isinstance(r, dict)] != [r["path"] for r in batch]:
            raise sandbox.SandboxFailure("CLASSIFICATION_SCOPE")
        for original, value in zip(batch, values, strict=True):
            if (set(value) - {"path", "language", "kind", "reason", "physical_lines", "bytes", "intake_hash"}
                    or str(safe_path(value["path"])) != value["path"] or value.get("language") not in tuple(LANGUAGES)
                    or not isinstance(value.get("kind"), str)
                    or value.get("kind") not in {"SOURCE", "TEST", "EXAMPLE", "NON_SOURCE", "UNSUPPORTED",
                        "UNSUPPORTED_ENCODING", "EXCLUDED_BINARY", "EXCLUDED_CONFIG", "EXCLUDED_GENERATED", "EXCLUDED_VENDOR", "SKIPPED_SIZE_LIMIT"}
                    or not isinstance(value.get("reason"), str) or len(value["reason"]) > 500):
                raise sandbox.SandboxFailure("CLASSIFICATION_SCHEMA")
            counts = original["diagnostic"] or original["metadata"]
            if (type(value.get("bytes")) is not int or type(value.get("physical_lines")) not in {int, type(None)}
                    or value.get("bytes") != counts["bytes"] or value.get("physical_lines") != counts["physical_lines"]):
                raise sandbox.SandboxFailure("CLASSIFICATION_COUNTS")
        result.extend(values)
    return result


class Ownership:
    def __init__(self, source):
        if not isinstance(source, str) or len(source.encode()) > 512_000:
            raise sandbox.SandboxFailure("CODEOWNERS_SOURCE_BUDGET")
        self.source, self.signature, self.values = source, digest(source), {}

    def resolve(self, paths):
        from analyzers.engine import safe_path
        paths = list(dict.fromkeys(str(safe_path(p)) for p in paths))
        if not self.source:
            self.values.update({path: {"selected": None, "state": "NO_DECLARATION", "diagnostics": []} for path in paths})
            return
        for batch in batches({"path": path} for path in paths if path not in self.values):
            expected = [row["path"] for row in batch]
            result = sandbox.call("lexical_ownership", {"source": self.source, "signature": self.signature, "paths": expected})
            if (not isinstance(result, dict) or set(result) != {"signature", "owners"}
                    or result["signature"] != self.signature or not isinstance(result["owners"], dict)
                    or set(result["owners"]) != set(expected)):
                raise sandbox.SandboxFailure("OWNERSHIP_SCOPE")
            for path, row in result["owners"].items():
                if (not isinstance(row, dict) or set(row) != {"selected", "state", "diagnostics"}
                        or (row["selected"] is not None and (not isinstance(row["selected"], str) or len(row["selected"]) > 200))
                        or row["state"] not in ("SUPPORTED_RULES", "PARTIAL_UNSUPPORTED_RULES", "NO_DECLARATION")
                        or not isinstance(row["diagnostics"], list) or len(row["diagnostics"]) > 20
                        or any(code not in {"UNSUPPORTED_CODEOWNERS_SYNTAX", "CODEOWNERS_LINE_LIMIT"} for code in row["diagnostics"])):
                    raise sandbox.SandboxFailure("OWNERSHIP_SCHEMA")
            self.values.update(result["owners"])


def ownership_rules(files):
    cached = getattr(files, "_contained_ownership", None)
    declared = set(files) | {row["path"] for row in getattr(files, "intake", [])}
    candidates = sorted(p for p in declared if p in {"CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"}
                        or p.endswith("/.github/CODEOWNERS"))
    # Excluded/binary/oversized declarations are not evidence of absent ownership.
    # Check before cache reuse, including a formerly readable declaration.
    if candidates and candidates[0] not in files:
        raise sandbox.SandboxFailure("CODEOWNERS_UNREADABLE")
    source = files[candidates[0]] if candidates else ""
    signature = digest(source)
    if cached is not None and cached.signature == signature:
        return cached
    rules = Ownership(source)
    rules.resolve(list(files) + [r["path"] for r in getattr(files, "intake", [])])
    if hasattr(files, "__dict__"):
        files._contained_ownership = rules
    return rules


def sections(path, source):
    request = {"path": path, "source": source, "hash": hashlib.sha256(source.encode()).hexdigest()}
    result = sandbox.call("lexical_sections", request)
    if (not isinstance(result, dict) or set(result) != {"path", "hash", "sections"}
            or result["path"] != path or result["hash"] != request["hash"] or not isinstance(result["sections"], list)):
        raise sandbox.SandboxFailure("SECTIONS_SCOPE")
    previous = 0
    maximum = len(source.splitlines())
    for row in result["sections"]:
        if (not isinstance(row, dict) or set(row) != {"title", "line"} or not isinstance(row["title"], str)
                or type(row["line"]) is not int or not previous < row["line"] <= maximum):
            raise sandbox.SandboxFailure("SECTIONS_SCHEMA")
        previous = row["line"]
    return result["sections"]


def section_map(files, selected=None):
    from analyzers.isolated_analysis import partitions
    output = {}
    for batch in partitions(files, selected=(p for p in (selected if selected is not None else files) if p.endswith(".md"))):
        hashes = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in batch.items()}
        result = sandbox.call("lexical_sections", {"files": batch})
        if not isinstance(result, dict) or set(result) != set(batch):
            raise sandbox.SandboxFailure("SECTIONS_SCOPE")
        for path, value in result.items():
            if not isinstance(value, dict) or set(value) != {"hash", "sections"} or value["hash"] != hashes[path] or not isinstance(value["sections"], list):
                raise sandbox.SandboxFailure("SECTIONS_SCOPE")
            previous = 0
            for row in value["sections"]:
                if (not isinstance(row, dict) or set(row) != {"title", "line"} or not isinstance(row["title"], str)
                        or type(row["line"]) is not int or not previous < row["line"] <= len(batch[path].splitlines())):
                    raise sandbox.SandboxFailure("SECTIONS_SCHEMA")
                previous = row["line"]
            output[path] = value["sections"]
    return output


def storage_claims(files, assets):
    from analyzers.isolated_analysis import partitions
    result = []
    minimal = [{k: a.get(k) for k in ("kind", "identity", "path", "line", "environment", "public")}
               for a in assets if a["kind"] in {"aws_s3_bucket", "AWS::S3::Bucket", "google_storage_bucket", "azurerm_storage_container"}]
    for batch in partitions(files, selected=(p for p in files if p.endswith(".md"))):
        hashes = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in batch.items()}
        value = sandbox.call("lexical_storage", {"files": batch, "assets": minimal})
        if not isinstance(value, dict) or set(value) != {"hashes", "claims"} or value["hashes"] != hashes or not isinstance(value["claims"], list):
            raise sandbox.SandboxFailure("STORAGE_CLAIM_SCOPE")
        for row in value["claims"]:
            if (not isinstance(row, dict) or row.get("path") not in batch or type(row.get("line")) is not int
                    or not 1 <= row["line"] <= len(batch[row["path"]].splitlines())
                    or row.get("category") != "CLOUD_SECURITY" or row.get("expected") != "private_storage"
                    or row.get("status") not in {"CONTRADICTED", "UNVERIFIED"}):
                raise sandbox.SandboxFailure("STORAGE_CLAIM_SCHEMA")
        result.extend(value["claims"])
    return result
