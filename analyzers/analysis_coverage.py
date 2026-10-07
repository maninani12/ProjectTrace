"""All-file coverage inventory. Parse success and semantic maturity are separate."""

from collections import Counter, defaultdict
from pathlib import PurePosixPath

from analyzers.capabilities import registry
from analyzers.code_quality.classification import coverage_source


def infrastructure_format(path, source):
    name = PurePosixPath(path).name
    if name.startswith("Dockerfile"):
        return "Dockerfile"
    if path.endswith((".tf", ".tf.json")):
        return "Terraform"
    if path.endswith((".yaml", ".yml", ".json")):
        if "Resources" in source or "AWSTemplateFormatVersion" in source:
            return "CloudFormation"
        if "apiVersion" in source and "kind" in source:
            return "Kubernetes"
        if "services:" in source or name in {
            "compose.yaml",
            "compose.yml",
            "docker-compose.yml",
            "docker-compose.yaml",
        }:
            return "Compose"
    return None


def build(files, analyzed_files, quality, signals, warnings, version):
    capabilities = {r["language"]: r for r in registry(version)["languages"]}
    parsers = {s["path"]: s for s in signals if s.get("type") in {"parser", "quality_file"}}
    diagnostics = defaultdict(list)
    for warning in warnings:
        if warning.get("path"):
            diagnostics[warning["path"]].append({k: warning.get(k) for k in ("analyzer", "code", "state", "message")})
    rows = []
    for entry in quality["inventory"]:
        path, kind = entry["path"], entry["kind"]
        metadata = files.metadata_for(path) if hasattr(files, "metadata_for") else None
        language = (
            (
                (metadata or {}).get("infrastructure_format") or infrastructure_format(path, "")
                if metadata
                else infrastructure_format(path, files.get(path, ""))
            )
            or entry.get("language")
            or "Other text / binary"
        )
        cap = capabilities.get(language)
        parsed = entry.get("parser_state") == "COMPLETED"
        iac = language in {"Terraform", "CloudFormation", "Kubernetes", "Compose", "Dockerfile"}
        iac_parse_failed = any(
            d["analyzer"] == "IAC"
            and d.get("code")
            in {"ValueError", "ParserError", "ScannerError", "JSONDecodeError", "UnexpectedToken", "TimeoutExpired"}
            for d in diagnostics[path]
        )
        if iac:
            parsed = path in analyzed_files and not iac_parse_failed
        state = "PARTIAL" if cap and parsed else "UNSUPPORTED"
        if kind in {"EXCLUDED_GENERATED", "EXCLUDED_VENDOR", "SKIPPED_SIZE_LIMIT"}:
            state = kind
        elif kind == "EXCLUDED_BINARY":
            state = "BINARY"
        elif kind == "EXCLUDED_CONFIG":
            state = "IGNORED_BY_POLICY"
        elif kind == "UNSUPPORTED_ENCODING":
            state = "UNSUPPORTED"
        elif cap and not parsed and (entry.get("parser_state") == "PARTIAL" or diagnostics[path]):
            state = (
                "PARSE_FAILED"
                if any(d.get("state") in {"FAILED", "PARTIAL"} for d in diagnostics[path]) and not iac
                else "PARTIAL"
            )
            if not iac and entry.get("parser_state") == "PARTIAL":
                state = "PARSE_FAILED"
        excluded = kind in {
            "EXCLUDED_GENERATED",
            "EXCLUDED_VENDOR",
            "SKIPPED_SIZE_LIMIT",
            "EXCLUDED_BINARY",
            "EXCLUDED_CONFIG",
            "UNSUPPORTED_ENCODING",
        }
        if iac_parse_failed and not excluded:
            state = "PARSE_FAILED"
        elif iac and diagnostics[path] and not excluded:
            state = "PARTIAL"
        if state in {
            "EXCLUDED_GENERATED",
            "EXCLUDED_VENDOR",
            "SKIPPED_SIZE_LIMIT",
            "BINARY",
            "IGNORED_BY_POLICY",
            "UNSUPPORTED",
        }:
            parsed = False
        # Configuration/docs still receive declared inventory; no invented source-language coverage.
        if kind == "NON_SOURCE" and not iac:
            state = "PARTIAL" if path in analyzed_files else "IGNORED_BY_POLICY"
        rows.append(
            {
                "path": path,
                **({"component": files.component_for(path)} if hasattr(files, "component_for") else {}),
                "language": language,
                "kind": kind,
                "coverage_source": coverage_source(entry),
                "analysis_state": state,
                "bytes": entry["bytes"],
                "loc": entry["physical_lines"],
                "reason": entry["reason"],
                "parser": parsers.get(path, {}).get("parser") or (cap or {}).get("parser", "NOT_AVAILABLE"),
                "parser_state": "COMPLETED" if parsed else entry.get("parser_state", "NOT_ANALYZED"),
                "analyzer_support": (cap or {}).get("maturity", "UNSUPPORTED"),
                "quality_support": (cap or {}).get("quality", "NOT_AVAILABLE"),
                "security_support": (cap or {}).get(
                    "sast", "PATTERN_ONLY" if path in analyzed_files else "NOT_AVAILABLE"
                ),
                "source_parser_completed": parsed,
                "native_scan_performed": path in analyzed_files,
                "authority": "STATIC" if cap else "DECLARED",
                "runtime_observed": False,
                "diagnostics": diagnostics[path],
                "precision": "UNMEASURED",
            }
        )
    languages = []
    for language in sorted({r["language"] for r in rows}):
        selected = [r for r in rows if r["language"] == language]
        languages.append(
            {
                "language": language,
                "files": len(selected),
                "loc": sum(r["loc"] or 0 for r in selected),
                "loc_unknown_files": sum(r["loc"] is None for r in selected),
                "parsed_files": sum(r["source_parser_completed"] for r in selected),
                "states": dict(Counter(r["analysis_state"] for r in selected)),
                "maturity": capabilities.get(language, {}).get("maturity", "UNSUPPORTED"),
            }
        )
    source = [r for r in rows if r["coverage_source"]]
    complete = sum(r["source_parser_completed"] for r in source)
    return {
        "schema": "projecttrace-analysis-coverage-v1",
        "inventory": rows,
        "languages": languages,
        "summary": {
            "files_discovered": len(rows),
            "files_with_native_scan": sum(r["native_scan_performed"] for r in rows),
            "source_files": len(source),
            "source_files_parsed": complete,
            "source_analysis_percent": round(100 * complete / len(source), 6) if source else None,
            "states": dict(Counter(r["analysis_state"] for r in rows)),
        },
        "authority": "STATIC / DECLARED",
        "runtime_evidence": "UNOBSERVED",
        "customer_code_executed": False,
        "external_llm_used": False,
        "source_sent_to_external_ai": False,
        "limitations": [
            "A completed parser is not complete semantic, framework or security coverage.",
            "State exclusions describe quality scope; native_scan_performed exposes other static scans when applicable.",
            "Unknown LOC remains unknown. Unsupported files are inventoried, not declared safe.",
        ],
    }
