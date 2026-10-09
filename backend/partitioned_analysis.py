"""Bounded file parsing with tenant-private typed observation reuse and global correlation."""

import hashlib
import json
import time
from pathlib import PurePosixPath

from sqlalchemy import select, text

from analyzers.compact_tokens import CompactTokens
from analyzers.engine import PARSER_SIGNATURE, VERSION, analyze, native_observations
from analyzers.infrastructure_deep import config
from analyzers.performance import Performance
from backend.db import ParserArtifact
from backend.domain import add
from backend.repository_store import RepositoryFiles, limits


def artifact_key(files, path, settings):
    metadata = files.metadata_for(path)
    # Path affects test/secret context, imports, owner identity and configuration semantics.
    inputs = [files.organization_id, files.hash_for(path), path, PARSER_SIGNATURE, VERSION]
    if metadata.get(
        "iac_candidate", bool(metadata.get("infrastructure_format")) or path.endswith((".yaml", ".yml", ".json"))
    ):
        inputs.append(settings)
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def analyze_inventory(db, files, *, progress=None, verification_context=None, profile=None):
    if not isinstance(files, RepositoryFiles) or files.native_only:
        raise ValueError("Analysis requires an authorized complete inventory.")
    started = time.perf_counter()
    performance = getattr(progress, "performance", None) or Performance()
    native = files.view(native_only=True)
    quota, settings = limits(), config((profile or {}).get("infrastructure"))
    # Source is bounded by a partition. Aggregate collections contain observations only.
    findings, signals, warnings, assets, metrics, failures, cache, reused = [], [], [], [], [], set(), {}, 0
    batch, size, partitions, max_files, max_bytes, hits, misses = [], 0, 0, 0, 0, 0, 0

    def parse_partition():
        nonlocal reused, partitions, max_files, max_bytes, hits, misses
        if not batch:
            return
        identifiers = {p: artifact_key(files, p, settings) for p in batch}
        lookup_started = time.perf_counter()
        stored = dict(
            db.execute(
                select(ParserArtifact.id, ParserArtifact.data).where(
                    ParserArtifact.organization_id == files.organization_id,
                    ParserArtifact.id.in_(list(identifiers.values())),
                )
            ).all()
        )
        previous = {p: stored[k] for p, k in identifiers.items() if k in stored}
        performance.record("CACHE_LOOKUP", time.perf_counter() - lookup_started)
        if progress:
            db.commit()  # No read snapshot spans parser CPU/provider I/O.
        partition = native.view(native_only=True, paths=batch, cache_sources=True)
        parse_started = time.perf_counter()
        observed = native_observations(partition, previous, settings, performance=performance)
        performance.record("PARTITION_PARSE", time.perf_counter() - parse_started)
        performance.count("source_blob_reads", partition._source_reads)
        performance.count("source_cache_hits", partition._source_hits)
        f, s, w, a, m, failed, parsed, count = observed
        findings.extend(f)
        signals.extend(s)
        warnings.extend(w)
        assets.extend(a)
        # Avoid retaining millions of per-token dictionaries across the full
        # repository. Cache rows keep their original lossless JSON format.
        metrics.extend({**item, "duplicate_tokens": CompactTokens(item.get("duplicate_tokens", []))} for item in m)
        failures.update(failed)
        reused += count
        hits += count
        misses += len(batch) - count
        performance.count("parser_cache_hits", count)
        performance.count("parser_cache_misses", len(batch) - count)
        if progress and db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        write_started, rows = time.perf_counter(), []
        for path, data in parsed.items():
            key = identifiers[path]
            if (
                key in stored
                or data.get("warnings")
                or any(item.get("rule") == "PT-PARSE-001" for item in data.get("findings", []))
            ):
                continue
            dialect = db.get_bind().dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            elif dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                raise ValueError("Parser cache requires a supported SQL adapter.")
            rows.append(dict(id=key, organization_id=files.organization_id, content_hash=files.hash_for(path),
                             language=PurePosixPath(path).suffix or PurePosixPath(path).name,
                             parser_version=PARSER_SIGNATURE, rule_version=VERSION, data=data))
        if rows:
            db.execute(insert(ParserArtifact).on_conflict_do_nothing(index_elements=["id"]), rows)
        job_id = getattr(progress, "job_id", None)
        if job_id:
            # Diagnostics survive a later timeout without publishing incomplete
            # findings/evidence as a successful snapshot.
            from analyzers.engine import redact_metadata
            for path in batch:
                messages = [warning for warning in w if warning.get("path") == path]
                if any(issue.get("rule") == "PT-PARSE-001" and issue.get("path") == path for issue in f):
                    messages.append({"analyzer": "PARSING", "path": path, "code": "SOURCE_SYNTAX_FAILED", "state": "PARTIAL",
                                     "message": "Source syntax parsing failed; full semantic coverage is unavailable."})
                if messages:
                    add(db, files.organization_id, files.repository_id, "parser_diagnostic",
                        redact_metadata({"job_id": job_id, "inventory_id": files.inventory_id,
                                         "path": path, "warnings": messages,
                                         "result_scope": "FILE_LOCAL_DIAGNOSTIC_ONLY"}))
                    performance.count("persisted_parser_diagnostic_files")
        performance.record("CACHE_WRITE", time.perf_counter() - write_started)
        if progress:
            # Completed bounded file results are independently valid even if
            # the subsequent deadline/lease check fails. Commit cache and
            # diagnostics before that check; unfinished snapshot output has
            # not started and remains atomic in the later transaction.
            db.commit()
            progress("ANALYZING")
        partitions += 1
        max_files = max(max_files, len(batch))
        max_bytes = max(max_bytes, size)

    if progress:
        progress("ANALYZING")
    for path in sorted(native):
        raw_size = files.metadata_for(path)["bytes"]
        boundary_changed = bool(batch) and (
            files.component_for(path),
            files.metadata_for(path).get("component_root", "."),
        ) != (files.component_for(batch[0]), files.metadata_for(batch[0]).get("component_root", "."))
        if batch and (
            boundary_changed or len(batch) >= quota["partition_files"] or size + raw_size > quota["partition_bytes"]
        ):
            parse_partition()
            batch.clear()
            size = 0
        batch.append(path)
        size += raw_size
    parse_partition()
    batch.clear()
    observations = findings, signals, warnings, assets, metrics, failures, cache, reused
    result = analyze(
        native,
        progress=progress,
        verification_context=verification_context,
        profile=profile,
        observations=observations,
        input_files=files,
    )
    result["source_storage"] = {
        "kind": "TENANT_ENCRYPTED_CONTENT_ADDRESSED",
        "inventory_id": files.inventory_id,
        "partitions": partitions,
        "partition_model": "DECLARED_COMPONENT_THEN_FILE_AND_BYTE_BUDGET",
        "max_partition_files": max_files,
        "max_partition_bytes": max_bytes,
        "parser_cache_hits": hits,
        "parser_cache_misses": misses,
        "parser_cache_scope": "TENANT_CONTENT_PATH_PARSER_RULE_VERSION",
        "quality_thresholds_recomputed": True,
        "global_correlations_recomputed": True,
        "analysis_ms": round(1000 * (time.perf_counter() - started), 2),
        "large_repository_performance": "UNMEASURED",
        "performance": performance.snapshot(),
    }
    return result
