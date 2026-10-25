"""Host coordinator: bounded source packets, no in-process repository syntax parsing."""

import copy
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

from analyzers import sandbox
from analyzers.parser_protocol import completed_packets, expand_native_artifact


def source_reply(operation, files, **options):
    value = sandbox.call(operation, {"files": files, **options})
    if not isinstance(value, list) or len(value) != 2:
        raise sandbox.SandboxFailure("HELPER_RESULT_SCHEMA")
    rows, warnings = value
    validate_source_rows(rows, warnings, files, documentation=operation == "documentation")
    return rows, warnings


def validate_source_rows(rows, warnings, files, *, documentation=False):
    """Parent identity/schema gate, independent of helper implementation correctness."""
    if not isinstance(rows, list) or not isinstance(warnings, list):
        raise sandbox.SandboxFailure("HELPER_RESULT_SCHEMA")
    line_counts = {path: len(source.splitlines()) for path, source in files.items()} if documentation else {}
    allowed = set(files)
    for warning in warnings:
        if not isinstance(warning, dict):
            raise sandbox.SandboxFailure("HELPER_WARNING_SCOPE")
        path = warning.get("path")
        if path is not None and (not isinstance(path, str) or path not in allowed):
            raise sandbox.SandboxFailure("HELPER_WARNING_SCOPE")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) or row["path"] not in files:
            raise sandbox.SandboxFailure("HELPER_RESULT_SCOPE")
        if documentation:
            if (set(row) != {"text", "category", "expected", "path", "line", "assertion_family"}
                    or any(not isinstance(row[key], str) for key in ("text", "category", "expected"))
                    or row["assertion_family"] != "declaration" or type(row["line"]) is not int
                    or not 1 <= row["line"] <= line_counts[row["path"]]):
                raise sandbox.SandboxFailure("HELPER_DOCUMENT_SCHEMA")
        elif (set(row) != {"name", "version", "ecosystem", "path", "direct", "dependency_kind", "manifest", "version_kind", "license"}
                or row["manifest"] != row["path"] or any(not isinstance(row[key], str) for key in ("name", "version", "ecosystem"))
                or len(row["name"]) > 200 or len(row["version"]) > 100
                or type(row["direct"]) not in {bool, type(None)}
                or row["dependency_kind"] not in ("DIRECT", "TRANSITIVE", "UNKNOWN")
                or row["version_kind"] not in ("EXACT", "CONSTRAINT")):
            raise sandbox.SandboxFailure("HELPER_MANIFEST_SCHEMA")


def partitions(files, *, selected=None, maximum=2_000_000):
    batch, size = {}, 0
    for path in selected if selected is not None else files:
        source = files[path]
        length = len(source.encode())
        if length > 512_000:
            raise sandbox.SandboxFailure("SOURCE_FILE_BUDGET")
        if batch and (len(batch) >= 100 or size + length > maximum):
            yield batch
            batch, size = {}, 0
        batch[path] = source
        size += length
    if batch:
        yield batch


class OpenAPIContracts:
    """Bounded sequential contract reads; unrelated JSON never leaves the helper."""
    def __init__(self, files, *, performance=None, checkpoint=None):
        self.files, self.performance, self.checkpoint = files, performance, checkpoint
        self.contained = sandbox.required()
        self.batches = partitions(files, selected=(p for p in files if p.endswith(".json")), maximum=512_000)
        self.pending = {}

    def close(self):
        self.pending.clear()
        self.batches.close()

    def read(self, path):
        if not self.contained:
            source = self.files[path]
            mentions = "openapi" in source.lower()
            try:
                return sandbox.parse_json(source), mentions, False
            except sandbox.SandboxFailure:
                raise
            except ValueError:
                return None, mentions, True
        if path not in self.pending:
            if self.pending:
                raise sandbox.SandboxFailure("HELPER_OPENAPI_ORDER")
            read_started = time.perf_counter()
            batch = next(self.batches, None)
            if self.performance:
                self.performance.record("OPENAPI_SOURCE_READ", time.perf_counter() - read_started)
            if batch is None or path not in batch:
                raise sandbox.SandboxFailure("HELPER_OPENAPI_SCOPE")
            started = time.perf_counter()
            try:
                try:
                    value = sandbox.call("openapi_batch", {"files": batch})
                except sandbox.SandboxFailure as error:
                    if error.code != "HELPER_PROTOCOL_DEPTH":
                        raise
                    # The batch wrapper adds nesting. Retain the original
                    # per-source IPC guard for contracts near that boundary.
                    value = {}
                    for name, source in batch.items():
                        contract, invalid = None, False
                        try:
                            parsed = sandbox.parse_json(source)
                            if isinstance(parsed, dict) and "openapi" in parsed:
                                contract = parsed
                        except sandbox.SandboxFailure:
                            raise
                        except ValueError:
                            invalid = True
                        value[name] = {"source_hash": hashlib.sha256(source.encode()).hexdigest(),
                                       "contract": contract, "invalid": invalid,
                                       "mentions_openapi": "openapi" in source.lower()}
                        if self.performance:
                            self.performance.count("openapi_single_file_fallbacks")
                        if self.checkpoint:
                            self.checkpoint()
                if not isinstance(value, dict) or set(value) != set(batch):
                    raise sandbox.SandboxFailure("HELPER_OPENAPI_SCOPE")
                for name, row in value.items():
                    if (not isinstance(row, dict)
                            or set(row) != {"source_hash", "contract", "mentions_openapi", "invalid"}
                            or row["source_hash"] != hashlib.sha256(batch[name].encode()).hexdigest()
                            or type(row["invalid"]) is not bool or type(row["mentions_openapi"]) is not bool
                            or row["mentions_openapi"] != ("openapi" in batch[name].lower())
                            or row["contract"] is not None and (
                                not isinstance(row["contract"], dict) or "openapi" not in row["contract"]
                                or row["invalid"])):
                        raise sandbox.SandboxFailure("HELPER_OPENAPI_SCHEMA")
                self.pending = value
            finally:
                if self.performance:
                    self.performance.record("OPENAPI_CONTRACT_BATCH", time.perf_counter() - started)
            if self.performance:
                self.performance.count("openapi_helper_batches")
                self.performance.count("openapi_submitted_files", len(batch))
                self.performance.count("openapi_submitted_bytes", sum(len(source.encode()) for source in batch.values()))
            if self.checkpoint:
                self.checkpoint()
        row = self.pending.pop(path)
        if self.performance:
            self.performance.count("openapi_consumed_files")
            self.performance.count("openapi_invalid_files", int(row["invalid"]))
            self.performance.count("openapi_contract_files", int(row["contract"] is not None))
        return row["contract"], row["mentions_openapi"], row["invalid"]


def native(files, cache, settings, *, performance=None):
    from analyzers.engine import PARSER_SIGNATURE, RULES, VERSION, finding, hash_text
    from analyzers.infrastructure import structured_iac_batch
    from analyzers.infrastructure_deep import config
    from analyzers.languages import LANGUAGES, analyze_languages

    sandbox.require_runtime()
    from analyzers.lexical import describe
    lexical = describe(files)
    settings = settings or config(None)
    signature = hash_text(json.dumps(settings, sort_keys=True))
    records, pending = {}, []
    for path in files:
        old = (cache or {}).get(path, {})
        metadata = files.metadata_for(path) if hasattr(files, "metadata_for") else None
        content_hash = files.hash_for(path) if metadata else hash_text(files[path])
        iac = lexical[path]["iac_candidate"]
        reusable = (old.get("hash") == content_hash and old.get("version") == VERSION
                    and old.get("parser_signature") == PARSER_SIGNATURE and not old.get("warnings")
                    and not any(row.get("rule") == "PT-PARSE-001" for row in old.get("findings", []))
                    and (not iac or old.get("infrastructure_signature", signature) == signature))
        if not reusable:
            pending.append(path)
            continue
        started = time.perf_counter()
        from analyzers.sanitization import metadata as sanitize
        previous = sanitize(copy.deepcopy(old))
        records[path] = [previous["findings"], previous["signals"], [], previous.get("assets", []),
                         previous.get("quality_metrics", []), [], {path: previous}, 1]
        if any(path.endswith(".py") and row.get("identity_confidence") != "HIGH" for row in previous["findings"]):
            identity(files, previous["findings"], previous.get("quality_metrics", []))
        if performance:
            performance.record("CACHE_REUSE", time.perf_counter() - started, path, state="REUSED")
    cold = {path: files[path] for path in pending}
    if len(cold) > 1000 or sum(len(source.encode()) for source in cold.values()) > 10_000_000:
        raise sandbox.SandboxFailure("NATIVE_INPUT_BUDGET")
    parsed = {"languages": {}, "iac": {}}
    if cold:
        languages = {p: s for p, s in cold.items() if any(p.endswith(suffix) for suffix in LANGUAGES)}
        iac = {p: s for p, s in cold.items() if lexical[p]["iac_candidate"]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            syntax = pool.submit(analyze_languages, languages, performance=performance)
            infrastructure = pool.submit(structured_iac_batch, iac, finding, settings, performance=performance)
            parsed = {"languages": syntax.result(), "iac": infrastructure.result()}
    for batch in partitions(cold):
        started = time.perf_counter()
        raw, failure = sandbox.invoke("native", {"files": batch, "cache": {},
                                                "settings": settings, "parsed": {name: {p: rows[p] for p in batch if p in rows}
                                                                                  for name, rows in parsed.items()}})
        if performance:
            performance.record("NATIVE_HELPER_TRANSPORT", time.perf_counter() - started)
        decode_started = time.perf_counter()
        rows = completed_packets(raw, batch, 16_000_000, expand=expand_native_artifact)
        if performance:
            performance.record("NATIVE_PACKET_VALIDATION", time.perf_counter() - decode_started)
        if failure and set(rows) == set(batch):
            rows.pop(next(reversed(rows)))
        for path in batch:
            if path not in rows:
                # This worker performs secrets/context as well as syntax.
                # Losing its packet must not advertise a clean scan in those
                # consumers, including IaC when its parsed input was prepared
                # successfully but the combined observation never completed.
                affected = {"PARSING", "QUALITY", "SAST", "SECRETS", "CLAIMS"}
                if lexical[path]["iac_candidate"]:
                    affected.add("IAC")
                if path.endswith((".py", ".json")):
                    affected.add("API")
                records[path] = [[], [], [{"analyzer": "PARSING", "path": path, "state": "PARTIAL",
                    "code": failure or "HELPER_PROTOCOL", "message": "Isolated parser did not complete this file."}],
                    [], [], sorted(affected), {}, 0]
                continue
            row = rows[path]
            if (not isinstance(row, list) or len(row) != 9 or not isinstance(row[6], dict) or set(row[6]) != {path}
                    or any(not isinstance(values, list) for values in row[:6]) or type(row[7]) is not int or row[7] != 0):
                raise sandbox.SandboxFailure("HELPER_SCOPE")
            artifact = row[6][path]
            if (not isinstance(artifact, dict) or set(artifact) != {"hash", "version", "parser_signature", "findings",
                    "signals", "assets", "quality_metrics", "warnings", "infrastructure_signature"}
                    or artifact["version"] != VERSION or artifact["parser_signature"] != PARSER_SIGNATURE
                    or artifact["infrastructure_signature"] != signature
                    or artifact["warnings"] != [w for w in row[2] if w.get("path") == path]
                    or any(artifact[key] != row[index] for key, index in (("findings", 0), ("signals", 1), ("assets", 3), ("quality_metrics", 4)))):
                raise sandbox.SandboxFailure("HELPER_CACHE_SCHEMA")
            if artifact.get("hash") != hashlib.sha256(batch[path].encode()).hexdigest():
                raise sandbox.SandboxFailure("HELPER_SOURCE_HASH")
            for values in row[:5]:
                if any(not isinstance(item, dict) or item.get("path") not in {path, None} for item in values):
                    raise sandbox.SandboxFailure("HELPER_SCOPE")
            maximum_line = len(batch[path].splitlines()) + 1
            for item in row[0]:
                if item.get("rule") not in RULES or type(item.get("line")) is not int or not 1 <= item["line"] <= maximum_line:
                    raise sandbox.SandboxFailure("HELPER_FINDING_SCHEMA")
            records[path] = row[:8]
            if performance:
                performance.merge(row[8])
        if performance:
            performance.record("CONTAINED_NATIVE", time.perf_counter() - started)
    combined = [[], [], [], [], [], set(), {}, 0]
    for path in files:
        row = records[path]
        for index in range(5):
            combined[index].extend(row[index])
        combined[5].update(row[5])
        combined[6].update(row[6])
        combined[7] += row[7]
    return tuple(combined)


def identity(files, findings, metrics):
    """Final quality findings also need Python AST identity; never reparse in the host."""
    grouped = {}
    for position, item in enumerate(findings):
        grouped.setdefault(item["path"], []).append(position)
    sources, positions, size = {}, [], 0

    def flush():
        selected = [findings[index] for index in positions]
        measured = [{k: v for k, v in row.items() if k != "duplicate_tokens"} for row in metrics if row["path"] in sources]
        result = sandbox.call("identity", {"files": sources, "findings": selected, "metrics": measured})
        if len(result) != len(selected):
            raise sandbox.SandboxFailure("HELPER_SCOPE")
        for index, row in zip(positions, result, strict=True):
            if row.get("rule") != findings[index]["rule"] or row.get("path") != findings[index]["path"]:
                raise sandbox.SandboxFailure("HELPER_SCOPE")
            findings[index].clear()
            findings[index].update(row)
    for path, indexes in grouped.items():
        source = files[path] if path.endswith(".py") else ""
        if sources and (len(sources) >= 100 or size + len(source.encode()) > 2_000_000):
            flush()
            sources, positions, size = {}, [], 0
        sources[path] = source
        size += len(source.encode())
        positions.extend(indexes)
    if sources:
        flush()
    return findings


def documentation(files, *, diagnostics=None, limit=1501):
    messages = diagnostics if diagnostics is not None else []
    result, batch, size, scanned, count = [], {}, 0, 0, 0

    def flush():
        rows, warnings = source_reply("documentation", batch, limit=max(1, limit - len(result)))
        if len(rows) > max(1, limit - len(result)):
            raise sandbox.SandboxFailure("HELPER_DOCUMENT_BUDGET")
        result.extend(rows)
        messages.extend(warnings)
    for path in files:
        if not path.endswith(".md"):
            continue
        source = files[path]
        length = len(source.encode())
        if scanned + length > 32_000_000 or count + 1 > 2000:
            if batch:
                flush()
                batch = {}
            messages.append({"analyzer": "CLAIMS", "code": "DOCUMENTATION_WORK_BUDGET", "state": "PARTIAL",
                             "message": "Documentation scanning reached its 32 MB / 2,000-file work budget."})
            break
        scanned += length
        count += 1
        if batch and (len(batch) >= 100 or size + length > 2_000_000):
            flush()
            batch, size = {}, 0
            if len(result) >= limit:
                break
        batch[path] = source
        size += length
    if batch and len(result) < limit:
        flush()
    return result
