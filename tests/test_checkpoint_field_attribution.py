"""Privacy-preserving comparison of published v1 and dirty paged checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import types
from pathlib import Path

from sqlalchemy import func, select

from analyzers.observation_store import MetricRows
from backend.analysis_checkpoints import load as candidate_load
from backend.analysis_checkpoints import save as candidate_save
from backend.db import AnalysisCheckpoint, AnalysisCheckpointPart
from backend.domain import add
from tests.test_repository_store import storage  # noqa: F401

PUBLISHED_HEAD = "9e21509591bfa5457cc829ebd5637f95be68d573"
V1_SOURCE_SHA256 = "52d6bf8ac730a25103c0d9b727319d5671a505141e662f2ba6f2806578bafdaf"
V1_SCHEMA = "projecttrace-analysis-checkpoint-v1"
MAXIMUM = 64_000_000
CONTROLLED_FIELDS = {
    "findings",
    "cloud_assets",
    "quality_metrics",
    "code_quality",
    "analysis_coverage",
    "signals",
    "dependencies",
    "claims",
    "files",
    "analysis_cache",
    "reused_files",
    "verification_cache",
    "reused_verifications",
    "reverified_claims",
    "engines",
    "warnings",
    "documentation_files",
}


def _v1_module():
    """Execute the published serializer source in-memory; never overwrite worktree code."""
    source = subprocess.run(
        ["git", "show", f"{PUBLISHED_HEAD}:backend/analysis_checkpoints.py"],
        check=True,
        capture_output=True,
    ).stdout
    if hashlib.sha256(source).hexdigest() != V1_SOURCE_SHA256:
        raise AssertionError("Published v1 checkpoint source hash changed.")
    module = types.ModuleType("_projecttrace_published_v1_checkpoint")
    exec(compile(source, "<published-v1-analysis-checkpoints>", "exec"), module.__dict__)
    return module


def _encoder():
    # Match the published call: JSONEncoder(sort_keys=True), all defaults intact.
    return json.JSONEncoder(sort_keys=True)


def _json_utf8_bytes(value):
    return sum(len(chunk.encode()) for chunk in _encoder().iterencode(value))


def _member_bytes(key, value):
    # JSONEncoder's default key/value separator is ": ".
    return _json_utf8_bytes(key) + 2 + _json_utf8_bytes(value)


def _normalize_v1_result(result):
    # Exact v1 save behavior: shallow-copy and materialize files as a list only
    # when the files member exists.
    return {**result, "files": list(result["files"])} if "files" in result else result


def _coarse_type(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float):
        return "number"
    if isinstance(value, (list, tuple)):
        return "list"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, str):
        return "string"
    return "other"


def _entry_count(value):
    return len(value) if isinstance(value, (dict, list, tuple)) else None


def _measure(
    result,
    *,
    job_id="fixture-job",
    organization_id="fixture-tenant",
    repository_id="fixture-repository",
    signature="a" * 64,
):
    normalized = _normalize_v1_result(result)
    result_bytes = _json_utf8_bytes(normalized)
    maximum = int(os.getenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "64000000"))
    members = []
    other_bytes = 0
    other_count = 0
    for key in sorted(normalized):
        value = normalized[key]
        contribution = _member_bytes(key, value)
        if key in CONTROLLED_FIELDS:
            members.append(
                {
                    "field": key,
                    "member_bytes": contribution,
                    "value_bytes": _json_utf8_bytes(value),
                    "value_type": _coarse_type(value),
                    "collection_entries": _entry_count(value),
                    "nested_fields": (
                        [
                            {
                                "field": child_key if child_key in {"metrics", "inventory", "summary"} else "other",
                                "member_bytes": _member_bytes(child_key, child_value),
                                "value_bytes": _json_utf8_bytes(child_value),
                                "value_type": _coarse_type(child_value),
                                "collection_entries": _entry_count(child_value),
                            }
                            for child_key, child_value in sorted(value.items())
                        ]
                        if key == "code_quality" and isinstance(value, dict)
                        else None
                    ),
                }
            )
        else:
            # Do not retain or emit unknown/dynamic keys.
            other_bytes += contribution
            other_count += 1
    if other_count:
        members.append(
            {
                "field": "other",
                "member_bytes": other_bytes,
                "value_bytes": None,
                "value_type": "mixed",
                "collection_entries": other_count,
            }
        )
    result_punctuation = 2 + 2 * max(0, len(normalized) - 1)
    result_reconciled = result_punctuation + sum(item["member_bytes"] for item in members)

    envelope = {
        "schema": V1_SCHEMA,
        "job_id": job_id,
        "organization_id": organization_id,
        "repository_id": repository_id,
        "signature": signature,
        "result": normalized,
    }
    envelope_bytes = _json_utf8_bytes(envelope)
    envelope_members = {
        key: _member_bytes(key, value)
        for key, value in envelope.items()
        if key != "result"
    }
    result_envelope_member = _json_utf8_bytes("result") + 2 + result_bytes
    envelope_punctuation = 2 + 2 * (len(envelope) - 1)
    envelope_reconciled = envelope_punctuation + result_envelope_member + sum(envelope_members.values())
    return {
        "raw_json_bytes": envelope_bytes,
        "configured_maximum_bytes": maximum,
        "remaining_budget_bytes": maximum - envelope_bytes,
        "budget_outcome": "WITHIN" if envelope_bytes <= maximum else "OVER",
        "result_object_bytes": result_bytes,
        "result_object_punctuation_bytes": result_punctuation,
        "result_member_bytes_sum": sum(item["member_bytes"] for item in members),
        "result_reconciled_bytes": result_reconciled,
        "result_reconciled": result_reconciled == result_bytes,
        "result_fields": [
            {
                **item,
                "percent_of_result_bytes": round(100 * item["member_bytes"] / result_bytes, 6)
                if result_bytes
                else 0.0,
            }
            for item in members
        ],
        "fixed_envelope_member_bytes": envelope_members,
        "result_envelope_member_bytes": result_envelope_member,
        "envelope_punctuation_bytes": envelope_punctuation,
        "envelope_reconciled_bytes": envelope_reconciled,
        "envelope_reconciled": envelope_reconciled == envelope_bytes,
        "files_materialized_count": len(normalized["files"]) if "files" in normalized else None,
    }


def _result(metrics=None, *, warning_values=None, file_values=None):
    metrics = [] if metrics is None else metrics
    inventory = []
    return {
        "findings": [],
        "cloud_assets": [],
        "quality_metrics": metrics,
        # This intentionally shares the metric list in memory, as analyzer
        # output does. V1 JSON duplicates the values and loses object identity.
        "code_quality": {
            "metrics": metrics,
            "inventory": inventory,
            "summary": {"complete": True, "score": 0.5, "nullable": None},
        },
        "analysis_coverage": {"summary": {"complete": True, "files": 0}, "languages": []},
        "signals": [],
        "dependencies": [],
        "claims": [],
        "files": () if file_values is None else file_values,
        "analysis_cache": {},
        "reused_files": 0,
        "verification_cache": {"version": "fixture", "claims": {}},
        "reused_verifications": 0,
        "reverified_claims": 0,
        "engines": {"fixture": "COMPLETED"},
        "warnings": [] if warning_values is None else warning_values,
        "documentation_files": 0,
    }


def _representative_result():
    metrics = [
        {
            "path": f"fixture/module-{index % 120:03d}.py",
            "line": index + 1,
            "name": "synthetic_metric",
            "value": index / 10,
            "enabled": index % 2 == 0,
            "note": 'synthetic-λ; quote="; newline=\n',
        }
        for index in range(800)
    ]
    value = _result(metrics, file_values=tuple(f"fixture-file-{i:04d}" for i in range(512)))
    value["findings"] = [{"id": f"finding-{i}", "evidence_ids": [f"evidence-{i % 40}"]} for i in range(160)]
    value["cloud_assets"] = [{"id": f"asset-{i}", "kind": "SERVICE"} for i in range(64)]
    value["signals"] = [{"kind": "FUNCTION", "line": i + 1} for i in range(240)]
    value["dependencies"] = [{"name": f"package-{i}", "version": "1.2.3"} for i in range(100)]
    value["claims"] = [{"id": f"claim-{i}", "status": "VERIFIED"} for i in range(240)]
    value["analysis_cache"] = {f"entry-{i}": {"findings": [], "quality_metrics": []} for i in range(24)}
    value["verification_cache"] = {
        "version": "fixture",
        "claims": {f"claim-{i}": {"verified": i % 2 == 0} for i in range(80)},
    }
    value["warnings"] = ["synthetic-λ", 'quoted="value"'] * 8
    value["code_quality"]["inventory"] = [
        {"path": f"fixture/inventory-{i:04d}", "owner": None, "line_count": i}
        for i in range(256)
    ]
    return value


def _materialize(value):
    if isinstance(value, MetricRows):
        return [_materialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _materialize(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_materialize(child) for child in value]
    return value


def _new_job(db, user, repository):
    job = add(db, user.organization_id, repository.id, "job", {"state": "VERIFYING"})
    db.commit()
    return job


def _write_safe_measurement(value):
    output = os.getenv("PROJECTTRACE_CHECKPOINT_ATTRIBUTION_PATH")
    if not output:
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def test_v1_field_attribution_reconciles_and_candidate_comparison(storage, monkeypatch):  # noqa: F811
    db, user, repository = storage
    legacy = _v1_module()
    signature = "b" * 64
    small = _result(file_values=("fixture-file-0", "fixture-file-1"))
    representative = _representative_result()
    measurements = {
        "small_synthetic": _measure(small),
        "representative_synthetic": _measure(representative),
    }
    assert all(item["result_reconciled"] and item["envelope_reconciled"] for item in measurements.values())
    assert measurements["small_synthetic"]["files_materialized_count"] == 2
    assert representative["quality_metrics"] is representative["code_quality"]["metrics"]
    measurements["representative_synthetic"]["shared_metric_projection"] = {
        "same_input_object": True,
        "quality_metrics_value_bytes": _json_utf8_bytes(representative["quality_metrics"]),
        "code_quality_metrics_value_bytes": _json_utf8_bytes(representative["code_quality"]["metrics"]),
        "v1_serializes_both_values": True,
    }
    assert (
        measurements["representative_synthetic"]["shared_metric_projection"]["quality_metrics_value_bytes"]
        == measurements["representative_synthetic"]["shared_metric_projection"]["code_quality_metrics_value_bytes"]
    )

    # Compare the historical writer/reader and current dirty candidate on the
    # same representative logical result, using separate disposable jobs.
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", str(MAXIMUM))
    v1_job = _new_job(db, user, repository)
    assert legacy.save(db, v1_job.id, user.organization_id, repository.id, signature, representative, lambda: None)
    v1_row = db.get(AnalysisCheckpoint, v1_job.id)
    v1_measurement = _measure(
        representative,
        job_id=v1_job.id,
        organization_id=user.organization_id,
        repository_id=repository.id,
        signature=signature,
    )
    assert v1_measurement["result_object_bytes"] == measurements["representative_synthetic"]["result_object_bytes"]
    v1_bytes = v1_measurement["raw_json_bytes"]
    v1_ciphertext_bytes = len(v1_row.ciphertext.encode())
    v1_result = legacy.load(db, v1_job.id, user.organization_id, repository.id, signature)

    candidate_job = _new_job(db, user, repository)
    assert candidate_save(db, candidate_job.id, user.organization_id, repository.id,
                          signature, representative, lambda: None)
    candidate_row = db.get(AnalysisCheckpoint, candidate_job.id)
    candidate_page_bytes = db.scalar(
        select(func.coalesce(func.sum(func.length(AnalysisCheckpointPart.ciphertext)), 0)).where(
            AnalysisCheckpointPart.job_id == candidate_job.id
        )
    )
    candidate_pages = db.scalar(
        select(func.count()).select_from(AnalysisCheckpointPart).where(
            AnalysisCheckpointPart.job_id == candidate_job.id
        )
    )
    owners = []
    candidate_result = candidate_load(
        db,
        candidate_job.id,
        user.organization_id,
        repository.id,
        signature,
        checkpoint=lambda: None,
        own=owners.append,
    )
    try:
        assert _materialize(candidate_result) == v1_result
        assert type(v1_result["files"]) is list
        assert type(candidate_result["files"]).__name__ == "ReplayRows"
        assert v1_result["quality_metrics"] is not v1_result["code_quality"]["metrics"]
        assert candidate_result["quality_metrics"] is candidate_result["code_quality"]["metrics"]
        v1_nested_length = len(v1_result["code_quality"]["metrics"])
        candidate_nested_length = len(candidate_result["code_quality"]["metrics"])
        v1_result["quality_metrics"].append({"path": "fixture/mutation.py", "line": 1})
        candidate_result["quality_metrics"].append({"path": "fixture/mutation.py", "line": 1})
        assert len(v1_result["code_quality"]["metrics"]) == v1_nested_length
        assert len(candidate_result["code_quality"]["metrics"]) == candidate_nested_length + 1
        measurements["same_fixture_v1_vs_candidate"] = {
            "logical_values_equal_after_materialization": True,
            "v1_raw_json_bytes": v1_bytes,
            "v1_ciphertext_bytes": v1_ciphertext_bytes,
            "candidate_logical_v1_json_bytes": v1_bytes,
            "candidate_manifest_ciphertext_bytes": len(candidate_row.ciphertext.encode()),
            "candidate_page_ciphertext_bytes": candidate_page_bytes,
            "candidate_aggregate_ciphertext_bytes": candidate_page_bytes + len(candidate_row.ciphertext.encode()),
            "candidate_page_count": candidate_pages,
            "v1_files_container_type": type(v1_result["files"]).__name__,
            "candidate_files_container_type": type(candidate_result["files"]).__name__,
            "v1_metric_projection_alias": v1_result["quality_metrics"] is v1_result["code_quality"]["metrics"],
            "candidate_metric_projection_alias": candidate_result["quality_metrics"] is candidate_result["code_quality"]["metrics"],
            "mutation_semantics": {
                "v1_mutating_quality_metrics_changes_code_quality_metrics": (
                    len(v1_result["code_quality"]["metrics"]) != v1_nested_length
                ),
                "candidate_mutating_quality_metrics_changes_code_quality_metrics": (
                    len(candidate_result["code_quality"]["metrics"]) != candidate_nested_length
                ),
            },
            "semantic_note": "Values compare equal after materialization; v1 JSON decode returns independent lists while candidate replay preserves shared collection aliases and lazy container types, changing identity and mutation propagation.",
        }
    finally:
        for owner in owners:
            owner.close()

    # Prove exact inclusive/exclusive v1 byte boundaries at the smallest
    # supported configured limit. This avoids allocating a 64 MB raw buffer.
    monkeypatch.setenv("ANALYSIS_CHECKPOINT_MAX_BYTES", "1000000")
    boundary = {}
    for target in (999_999, 1_000_000, 1_000_001):
        job = _new_job(db, user, repository)
        base = _result(file_values=())
        base_bytes = _measure(
            base,
            job_id=job.id,
            organization_id=user.organization_id,
            repository_id=repository.id,
            signature=signature,
        )["raw_json_bytes"]
        warning_length = target - base_bytes - 2
        assert warning_length >= 0
        value = _result(warning_values=["x" * warning_length], file_values=())
        measured = _measure(
            value,
            job_id=job.id,
            organization_id=user.organization_id,
            repository_id=repository.id,
            signature=signature,
        )
        assert measured["raw_json_bytes"] == target
        assert measured["result_reconciled"] and measured["envelope_reconciled"]
        saved = legacy.save(db, job.id, user.organization_id, repository.id,
                            signature, value, lambda: None)
        row = db.get(AnalysisCheckpoint, job.id)
        boundary[str(target)] = {
            "raw_json_bytes": measured["raw_json_bytes"],
            "save_result": saved,
            "ciphertext_bytes": len(row.ciphertext.encode()) if row else 0,
            "field_contributions": measured["result_fields"],
            "result_reconciled": measured["result_reconciled"],
            "envelope_reconciled": measured["envelope_reconciled"],
        }
        assert saved is (target <= 1_000_000)
        assert (row is not None) is (target <= 1_000_000)

    integrity = db.connection().exec_driver_sql("PRAGMA integrity_check").scalar_one()
    fk_violations = db.connection().exec_driver_sql("PRAGMA foreign_key_check").all()
    assert integrity == "ok" and not fk_violations
    output = {
        "schema": "projecttrace-scale001-checkpoint-field-attribution-v1",
        "fixture_scope": "synthetic schema-shaped values only; no repository payloads",
        "base_head": PUBLISHED_HEAD,
        "v1_source_sha256": V1_SOURCE_SHA256,
        "encoder": {
            "class": "json.JSONEncoder",
            "sort_keys": True,
            "ensure_ascii": "default true",
            "separators": "default Python JSONEncoder separators",
            "chunk_encoding": "chunk.encode() UTF-8",
            "files_normalization": "list(result['files']) when the field exists",
            "payload_values_or_hashes_recorded": False,
        },
        "measurements": measurements,
        "v1_boundary_at_1mb": {
            "configured_maximum_bytes": 1_000_000,
            "cases": boundary,
            "limit_increased": False,
        },
        "candidate_storage_integrity": {"sqlite_integrity": integrity, "foreign_key_violations": len(fk_violations)},
    }
    _write_safe_measurement(output)
    print("CHECKPOINT_ATTRIBUTION_SAFE_SUMMARY " + json.dumps({
        "small_raw_json_bytes": measurements["small_synthetic"]["raw_json_bytes"],
        "representative_raw_json_bytes": measurements["representative_synthetic"]["raw_json_bytes"],
        "representative_largest_fields": sorted(
            ((item["field"], item["member_bytes"]) for item in measurements["representative_synthetic"]["result_fields"]),
            key=lambda item: item[1], reverse=True,
        )[:5],
        "v1_candidate_values_equal": measurements["same_fixture_v1_vs_candidate"]["logical_values_equal_after_materialization"],
        "v1_candidate_container_or_alias_difference": (
            measurements["same_fixture_v1_vs_candidate"]["v1_files_container_type"]
            != measurements["same_fixture_v1_vs_candidate"]["candidate_files_container_type"]
            or measurements["same_fixture_v1_vs_candidate"]["v1_metric_projection_alias"]
            != measurements["same_fixture_v1_vs_candidate"]["candidate_metric_projection_alias"]
        ),
        "boundary_results": {key: value["save_result"] for key, value in boundary.items()},
    }, separators=(",", ":")))
