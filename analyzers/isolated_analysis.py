"""Host coordinator: bounded source packets, no in-process repository syntax parsing."""

import copy
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

from analyzers import sandbox
from analyzers.parser_protocol import completed_packets


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


def native(files, cache, settings, *, performance=None):
    from analyzers.engine import PARSER_SIGNATURE, VERSION, finding, hash_text, is_iac_source
    from analyzers.infrastructure import structured_iac_batch
    from analyzers.infrastructure_deep import config
    from analyzers.languages import LANGUAGES, analyze_languages

    sandbox.require_runtime()
    settings = settings or config(None)
    signature = hash_text(json.dumps(settings, sort_keys=True))
    records, pending = {}, []
    for path in files:
        old = (cache or {}).get(path, {})
        metadata = files.metadata_for(path) if hasattr(files, "metadata_for") else None
        content_hash = files.hash_for(path) if metadata else hash_text(files[path])
        iac = metadata.get("iac_candidate", bool(metadata.get("infrastructure_format"))) if metadata else is_iac_source(path, files[path])
        reusable = (old.get("hash") == content_hash and old.get("version") == VERSION
                    and old.get("parser_signature") == PARSER_SIGNATURE and not old.get("warnings")
                    and not any(row.get("rule") == "PT-PARSE-001" for row in old.get("findings", []))
                    and (not iac or old.get("infrastructure_signature", signature) == signature))
        if not reusable:
            pending.append(path)
            continue
        started = time.perf_counter()
        previous = copy.deepcopy(old)
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
        iac = {p: s for p, s in cold.items() if is_iac_source(p, s)}
        with ThreadPoolExecutor(max_workers=2) as pool:
            syntax = pool.submit(analyze_languages, languages, performance=performance)
            infrastructure = pool.submit(structured_iac_batch, iac, finding, settings, performance=performance)
            parsed = {"languages": syntax.result(), "iac": infrastructure.result()}
    for batch in partitions(cold):
        started = time.perf_counter()
        raw, failure = sandbox.invoke("native", {"files": batch, "cache": {},
                                                "settings": settings, "parsed": {name: {p: rows[p] for p in batch if p in rows}
                                                                                  for name, rows in parsed.items()}})
        rows = completed_packets(raw, batch, 16_000_000)
        if failure and set(rows) == set(batch):
            rows.pop(next(reversed(rows)))
        for path in batch:
            if path not in rows:
                records[path] = [[], [], [{"analyzer": "PARSING", "path": path, "state": "PARTIAL",
                    "code": failure or "HELPER_PROTOCOL", "message": "Isolated parser did not complete this file."}],
                    [], [], ["PARSING", "QUALITY", "SAST"], {}, 0]
                continue
            row = rows[path]
            if not isinstance(row, list) or len(row) != 9 or set(row[6]) != {path}:
                raise sandbox.SandboxFailure("HELPER_SCOPE")
            if row[6][path].get("hash") != hashlib.sha256(batch[path].encode()).hexdigest():
                raise sandbox.SandboxFailure("HELPER_SOURCE_HASH")
            for values in row[:5]:
                if any(item.get("path") not in {path, None} for item in values):
                    raise sandbox.SandboxFailure("HELPER_SCOPE")
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
        rows, warnings = sandbox.call("documentation", {"files": batch, "limit": max(1, limit - len(result))})
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
