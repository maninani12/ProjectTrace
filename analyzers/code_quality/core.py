"""Quality observations, explainable summary, baseline comparison and advisory gate."""

import hashlib
import json
import time
from collections import Counter

from analyzers.code_quality import FINGERPRINT_VERSION, VERSION
from analyzers.code_quality.classification import LANGUAGES, classify
from analyzers.code_quality.coverage import absent, percent
from analyzers.code_quality.duplication import detect
from analyzers.code_quality.rules import DEFINITIONS, config


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def build(files, metrics, signals, raw_findings, warnings, profile=None):
    started = time.perf_counter()
    settings = config((profile or {}).get("quality"))
    # Existing native quality toggles remain effective unless specifically overridden.
    settings["rules"] = {
        **{k: v for k, v in (profile or {}).get("rules", {}).items() if k in DEFINITIONS},
        **settings["rules"],
    }
    inventory = classify(files, settings["scope"])
    paths = {r["path"]: r for r in inventory}
    failed = {w.get("path") for w in warnings if w.get("analyzer") == "PARSING"}
    failed.update(s["path"] for s in signals if s.get("type") == "parser" and s.get("state") != "COMPLETED")
    failed.intersection_update(p for p, row in paths.items() if row["kind"] in {"SOURCE", "TEST", "EXAMPLE"})
    observed = {s["path"] for s in signals if s.get("type") in {"parser", "quality_file"}}
    file_metrics = {s["path"]: s.get("file_metrics", {}) for s in signals if s.get("type") == "quality_file"}
    selected = {p for p, r in paths.items() if r["kind"] in {"SOURCE", "TEST", "EXAMPLE"} and p in observed}
    for row in inventory:
        row["hash"] = (
            row.get("intake_hash")
            if "intake_hash" in row
            else files.hash_for(row["path"])
            if hasattr(files, "hash_for")
            else hashlib.sha256(files[row["path"]].encode()).hexdigest()
        )
        row["parser_state"] = (
            "PARTIAL" if row["path"] in failed else "COMPLETED" if row["path"] in selected else "NOT_ANALYZED"
        )
        override = settings["scope"]["language_overrides"].get(row["path"])
        actual = LANGUAGES.get(__import__("pathlib").PurePosixPath(row["path"]).suffix.lower())
        if override and override != actual:
            row.update(
                parser_state="UNSUPPORTED_OVERRIDE",
                reason="Override differs from the parser selected by the extension; not analyzed as the requested language.",
            )
            selected.discard(row["path"])
        if row["path"] in selected:
            row.update(file_metrics.get(row["path"], {}))
    measured = [{k: v for k, v in m.items() if k not in {"duplicate_tokens"}} for m in metrics if m["path"] in selected]
    production = [m for m in metrics if m["path"] in selected and paths[m["path"]]["kind"] == "SOURCE"]
    dup = detect(production, settings["rules"].get("PT-QUALITY-007", {}).get("threshold", 50))
    symbols = [
        sym
        for s in signals
        if s.get("type") == "quality_file" and s["path"] in selected
        for sym in s.get("symbols", [])
    ]
    symbols.extend(
        {
            "path": m["path"],
            "name": m["name"],
            "qualified_name": m.get("qualified_name", m["name"]),
            "kind": m.get("kind", "FUNCTION"),
            "line": m["line"],
            "end_line": m["end_line"],
            "hash": m["body_hash"],
        }
        for m in measured
    )
    findings = []

    def emit(
        rule,
        path,
        line,
        *,
        metric=None,
        actual=None,
        threshold=None,
        anchor=None,
        detail=None,
        end_line=None,
        context=None,
    ):
        definition = DEFINITIONS[rule]
        setting = settings["rules"].get(rule, {})
        if not setting.get("enabled", True) or path not in selected:
            return
        containing = metric or next(
            (
                m
                for m in sorted(measured, key=lambda m: m["end_line"] - m["line"])
                if m["path"] == path and m["line"] <= line <= m["end_line"]
            ),
            None,
        )
        symbol = (containing or {}).get("qualified_name", (containing or {}).get("name", "<module>"))
        # Symbol identity is independent of offsets; observation hash controls review carry.
        fingerprint = digest([FINGERPRINT_VERSION, rule, path, symbol, anchor or "threshold"])
        context_hash = digest([rule, actual, threshold, anchor, context, (containing or {}).get("body_hash")])
        findings.append(
            {
                "rule": rule,
                "title": definition[0],
                "category": "QUALITY",
                "dimension": definition[1],
                "severity": setting.get("severity", definition[2]),
                "confidence": "HIGH" if definition[5] == "STABLE" else "MEDIUM",
                "rule_status": definition[5],
                "path": path,
                "line": line,
                "end_line": end_line or (containing or {}).get("end_line", line),
                "symbol": symbol,
                "language": paths[path]["language"],
                "source_kind": paths[path]["kind"],
                "measured": actual,
                "threshold": threshold,
                "metric": definition[3],
                "explanation": detail
                or f"Measured {actual}; configured threshold {threshold}. Inspect the recorded metric contributors.",
                "remediation": definition[7],
                "fingerprint": fingerprint,
                "fingerprint_version": FINGERPRINT_VERSION,
                "observation_hash": context_hash,
                "rule_version": VERSION,
                "analyzer_version": VERSION,
                "classification": "RELIABILITY_OBSERVATION"
                if definition[1] == "RELIABILITY"
                else "MAINTAINABILITY_OBSERVATION",
                "review_status": "OPEN",
                "authority": "STATIC",
            }
        )

    for metric in measured:
        if paths[metric["path"]]["kind"] != "SOURCE":
            continue
        for rule in ["PT-QUALITY-001", "PT-QUALITY-002", "PT-QUALITY-003", "PT-QUALITY-008", "PT-QUALITY-009"]:
            key, default = DEFINITIONS[rule][3:5]
            threshold = settings["rules"].get(rule, {}).get("threshold", default)
            if metric.get(key, 0) > threshold:
                emit(rule, metric["path"], metric["line"], metric=metric, actual=metric[key], threshold=threshold)
    for symbol in symbols:
        if symbol["kind"] == "CLASS" and paths[symbol["path"]]["kind"] == "SOURCE":
            actual = symbol["end_line"] - symbol["line"] + 1
            threshold = settings["rules"].get("PT-QUALITY-004", {}).get("threshold", 200)
            if actual > threshold:
                emit(
                    "PT-QUALITY-004", symbol["path"], symbol["line"], metric=symbol, actual=actual, threshold=threshold
                )
    file_threshold = settings["rules"].get("PT-QUALITY-013", {}).get("threshold", DEFINITIONS["PT-QUALITY-013"][4])
    for path in selected:
        row = paths[path]
        if row["kind"] == "SOURCE" and row["physical_lines"] > file_threshold:
            emit(
                "PT-QUALITY-013",
                path,
                1,
                metric={"qualified_name": "<file>", "end_line": row["physical_lines"], "body_hash": row["hash"]},
                actual=row["physical_lines"],
                threshold=file_threshold,
            )
    for signal in signals:
        if signal.get("type") == "quality_file" and signal["path"] in selected:
            for observation in signal.get("observations", []):
                emit(
                    observation["rule"],
                    signal["path"],
                    observation["line"],
                    anchor=observation.get("anchor", observation.get("detail")),
                    detail=observation.get("detail"),
                    context=observation.get("context"),
                )
    # Existing parser-backed exception observations; re-anchor to owning symbol.
    for item in raw_findings:
        if item["rule"] in {"PT-QUALITY-005", "PT-QUALITY-006"}:
            lines = files[item["path"]].splitlines()
            anchor = lines[item["line"] - 1].strip() if item["line"] <= len(lines) else item["rule"]
            before = len(findings)
            emit(item["rule"], item["path"], item["line"], anchor=anchor, detail=item["explanation"])
            if len(findings) > before:
                findings[-1].update(
                    {
                        k: v
                        for k, v in item.items()
                        if k.startswith("structural_") or k.startswith("identity_") or k == "file_structure_hash"
                    }
                )
    for group in dup["groups"]:
        for occurrence in group["occurrences"]:
            emit(
                "PT-QUALITY-007",
                occurrence["path"],
                occurrence["line"],
                anchor=group["id"],
                actual=group["tokens"],
                threshold=dup["minimum_tokens"],
                end_line=occurrence["end_line"],
                detail=f"Native normalized block in {len(group['occurrences'])} occurrences; {group['tokens']} tokens. Group {group['id'][:12]}.",
            )
    # Multiple identical symptom anchors in one symbol are explicitly distinguished by order.
    counts = Counter()
    for finding in findings:
        base = finding["fingerprint"]
        counts[base] += 1
        if counts[base] > 1:
            finding["fingerprint"] = digest([base, counts[base]])
    source_lines = sum(r["physical_lines"] for r in inventory if r["path"] in selected and r["kind"] == "SOURCE")
    dup["density_percent"] = percent(dup["duplicated_lines"], source_lines)
    languages = []
    for language in sorted({r["language"] for r in inventory if r["language"]}):
        rows = [r for r in inventory if r["language"] == language]
        languages.append(
            {
                "language": language,
                "maturity": "PARTIAL" if language in LANGUAGES.values() else "UNSUPPORTED",
                "analyzed": sum(r["parser_state"] == "COMPLETED" for r in rows),
                "partial": sum(r["parser_state"] == "PARTIAL" for r in rows),
                "total": len(rows),
                "reason": "Bounded syntax metrics; no complete control flow, type resolution or framework semantics.",
            }
        )
    result = {
        "version": VERSION,
        "fingerprint_version": FINGERPRINT_VERSION,
        "configuration": settings,
        "profile_version": (profile or {}).get("version", 0),
        "profile_lineage": (profile or {}).get("profile_lineage", []),
        "gate_version": digest(settings["gate"]),
        "profile_hash": digest(settings),
        "detection_hash": digest({"rules": settings["rules"], "scope": settings["scope"]}),
        "state": "PARTIAL"
        if failed
        or any(
            r["kind"] in {"UNSUPPORTED", "UNSUPPORTED_ENCODING", "SKIPPED_SIZE_LIMIT"}
            or r["parser_state"] == "UNSUPPORTED_OVERRIDE"
            or r["kind"] in {"SOURCE", "TEST", "EXAMPLE"}
            and r["path"] not in selected
            for r in inventory
        )
        or dup["state"] == "PARTIAL"
        else "COMPLETED"
        if selected
        else "NOT_AVAILABLE",
        "inventory": inventory,
        "languages": languages,
        "scope_counts": dict(Counter(r["kind"] for r in inventory)),
        "metrics": measured,
        "symbols": symbols,
        "duplication": dup,
        "coverage": absent(),
        "performance": {"quality_ms": round((time.perf_counter() - started) * 1000, 2)},
        "limitations": [
            (
                "Partitioned encrypted inventory with configured quotas; per-file parser budget remains 512 KB. Large-scale performance requires measured benchmark evidence."
                if hasattr(files, "inventory_id")
                else "Native source intake: 1,000 entries / 10 MB / 512 KB per file. No 10k/50k repository scale claim."
            ),
            "Metric thresholds apply to production source; tests/examples are separately measured. Reliability observations still include them.",
            "Structural concept identity with conservative unique full-file rename reconciliation. Ambiguous repeated anchors do not inherit reviews.",
            "No automatic unused-symbol, resource leak, full-CFG or live Git authorship conclusions.",
        ],
    }
    return findings, result


def compare(quality, findings, previous, changed_lines, *, base_id=None, model_changed=False):
    old = {f.get("fingerprint"): f for f in previous if f.get("category") == "QUALITY"}
    resolved, current = [], set()
    for item in findings:
        if item.get("category") != "QUALITY":
            continue
        fp = item["fingerprint"]
        current.add(fp)
        item["delta"] = (
            "EXISTING" if fp in old else "ANALYZER_BASELINE" if model_changed else "NEW" if base_id else "INITIAL"
        )
        previous = old.get(fp, {})
        worsened = (
            type(item.get("measured")) in {int, float}
            and type(previous.get("measured")) in {int, float}
            and item["measured"] > previous["measured"]
        )
        item["new_code"] = (
            bool(base_id)
            and (fp not in old or worsened)
            and not model_changed
            and any(
                lo <= item.get("end_line", item["line"]) and hi >= item["line"]
                for lo, hi in changed_lines.get(item["path"], [])
            )
        )
        item["machine_status"] = "OPEN"
    for fp, item in old.items():
        if fp not in current and not model_changed:
            resolved.append(
                {
                    "fingerprint": fp,
                    "id": item.get("id"),
                    "title": item["title"],
                    "path": item["path"],
                    "rule": item["rule"],
                    "delta": "RESOLVED",
                    "machine_status": "RESOLVED",
                }
            )
    production = {r["path"]: r for r in quality["inventory"] if r["kind"] == "SOURCE"}
    changed = {
        p: {line for lo, hi in spans for line in range(max(1, lo), min(hi, production[p]["physical_lines"]) + 1)}
        for p, spans in changed_lines.items()
        if p in production
    }
    total = sum(len(lines) for lines in changed.values())
    duplicated = sum(
        len(set(quality["duplication"]["lines_by_path"].get(p, [])) & lines) for p, lines in changed.items()
    )
    quality["duplication"].update(
        changed_duplicated_lines=duplicated,
        changed_line_total=total,
        new_density_percent=percent(duplicated, total) if base_id else None,
    )
    quality["changed_lines"] = changed_lines
    quality.update(
        base_id=base_id,
        baseline_state="SELECTED" if base_id else "NOT_CONFIGURED",
        resolved=resolved,
        deltas=dict(Counter(f["delta"] for f in findings if f.get("category") == "QUALITY")),
    )
    return quality


def gate(quality, findings, coverage=None):
    if quality["state"] == "NOT_AVAILABLE" and not any(
        r["kind"] in {"SOURCE", "TEST", "EXAMPLE", "UNSUPPORTED", "UNSUPPORTED_ENCODING", "SKIPPED_SIZE_LIMIT"}
        for r in quality["inventory"]
    ):
        return {
            "status": "PASS",
            "mode": "ADVISORY",
            "scope": quality["configuration"]["gate"]["scope"],
            "base_id": quality.get("base_id"),
            "results": [
                {
                    "policy": "Quality: source applicability",
                    "version": VERSION,
                    "result": "PASS",
                    "reason": "No first-party source in this captured quality scope; quality conditions are not applicable.",
                    "remediation": "Inspect the captured file exclusions.",
                }
            ],
        }
    settings = quality["configuration"]["gate"]
    all_quality = [f for f in findings if f.get("category") == "QUALITY"]
    selected = [
        f
        for f in all_quality
        if (settings["scope"] == "OVERALL" or f.get("new_code"))
        and f.get("review_status") not in {"FALSE_POSITIVE", "RESOLVED"}
    ]
    stable = [f for f in selected if f.get("rule_status") == "STABLE"]
    results = []

    def condition(
        name, measured, threshold, failed, ids=(), remedy="Inspect the linked source evidence.", missing=False
    ):
        results.append(
            {
                "policy": name,
                "version": VERSION,
                "measured": measured,
                "threshold": threshold,
                "result": "REVIEW_REQUIRED"
                if missing
                or failed
                and name in {"Quality: high severity", "Quality: reliability", "Quality: function complexity"}
                else "FAIL"
                if failed
                else "PASS",
                "blocking_eligible": name
                in {"Quality: changed-line coverage", "Quality: parsed-file analysis coverage"},
                "precision_status": "NOT_APPLICABLE"
                if name in {"Quality: changed-line coverage", "Quality: parsed-file analysis coverage"}
                else "UNMEASURED",
                "finding_ids": list(ids),
                "reason": "Required evidence is unavailable."
                if missing
                else f"Measured {measured}; threshold {threshold}."
                + (
                    " Representative rule precision is unmeasured; review is required instead of blocking."
                    if failed
                    and name in {"Quality: high severity", "Quality: reliability", "Quality: function complexity"}
                    else ""
                ),
                "remediation": remedy,
            }
        )

    for name, items, threshold in [
        (
            "Quality: high severity",
            [f for f in stable if f["severity"] in {"HIGH", "CRITICAL"}],
            settings["max_new_high"],
        ),
        (
            "Quality: reliability",
            [f for f in stable if f["dimension"] == "RELIABILITY"],
            settings["max_new_reliability"],
        ),
    ]:
        condition(name, len(items), threshold, len(items) > threshold, [f.get("id", f["fingerprint"]) for f in items])
    eligible_metrics = [m for m in quality["metrics"] if settings["scope"] == "OVERALL" or m.get("new_code", False)]
    maximum = max((m["cyclomatic"] for m in eligible_metrics), default=0)
    condition(
        "Quality: function complexity",
        maximum,
        settings["max_new_complexity"],
        maximum > settings["max_new_complexity"],
    )
    duplicate = [f for f in selected if f["rule"] == "PT-QUALITY-007"]
    density = (
        quality["duplication"].get("new_density_percent")
        if settings["scope"] == "NEW_CODE"
        else quality["duplication"].get("density_percent")
    )
    threshold = settings["max_new_duplication_percent"]
    if duplicate and threshold is not None:
        results.append(
            {
                "policy": "Quality: normalized duplication",
                "version": VERSION,
                "result": "REVIEW_REQUIRED" if density is None or density > threshold else "PASS",
                "measured": density,
                "threshold": threshold,
                "finding_ids": [f.get("id", f["fingerprint"]) for f in duplicate],
                "reason": "Beta normalized blocks need context review when exceeding the configured density. Denominator: selected production physical lines (changed lines for New Code).",
                "remediation": "Inspect side-by-side occurrences before extracting shared code.",
            }
        )
    report = coverage or quality["coverage"]
    if settings.get("min_analysis_coverage_percent") is not None:
        eligible = [
            row
            for row in quality["inventory"]
            if row["kind"] in {"SOURCE", "TEST", "EXAMPLE", "UNSUPPORTED", "UNSUPPORTED_ENCODING", "SKIPPED_SIZE_LIMIT"}
        ]
        parsed = sum(row.get("parser_state") == "COMPLETED" for row in eligible)
        actual = round(100 * parsed / len(eligible), 2) if eligible else None
        condition(
            "Quality: parsed-file analysis coverage",
            actual,
            settings["min_analysis_coverage_percent"],
            actual is not None and actual < settings["min_analysis_coverage_percent"],
            missing=actual is None,
            remedy="Inspect unsupported files and parser diagnostics. Denominator: included first-party source/test/example and unsupported files; excludes vendor/generated/binary/configuration.",
        )
    if settings.get("max_new_nesting") is not None:
        condition(
            "Quality: maximum nesting",
            max((m["nesting"] for m in eligible_metrics), default=0),
            settings["max_new_nesting"],
            any(m["nesting"] > settings["max_new_nesting"] for m in eligible_metrics),
            remedy="Review the recorded nesting contributors and use guard clauses where appropriate.",
        )
    required = settings.get("required_languages", [])
    failures = [
        r
        for r in quality["inventory"]
        if r.get("language") in required
        and r["kind"] in {"SOURCE", "TEST", "EXAMPLE", "SKIPPED_SIZE_LIMIT", "UNSUPPORTED_ENCODING"}
        and r.get("parser_state") != "COMPLETED"
    ]
    if required:
        condition(
            "Quality: required language parsers",
            len(failures),
            0,
            bool(failures),
            remedy="Repair parser failures or explicitly adjust required language policy.",
        )
        results[-1].update(
            result="FAIL" if failures else "PASS",
            file_paths=[r["path"] for r in failures],
            blocking_eligible=True,
            precision_status="NOT_APPLICABLE",
        )
    eligible_inventory = [
        r
        for r in quality["inventory"]
        if r["kind"] in {"SOURCE", "TEST", "EXAMPLE", "UNSUPPORTED", "UNSUPPORTED_ENCODING", "SKIPPED_SIZE_LIMIT"}
    ]
    parsed_percent = (
        round(100 * sum(r.get("parser_state") == "COMPLETED" for r in eligible_inventory) / len(eligible_inventory), 2)
        if eligible_inventory
        else None
    )
    operators = {
        "EQ": lambda a, b: a == b,
        "LT": lambda a, b: a < b,
        "LTE": lambda a, b: a <= b,
        "GT": lambda a, b: a > b,
        "GTE": lambda a, b: a >= b,
    }
    for configured in settings.get("conditions", []):
        new_code = configured.get("scope", settings["scope"]) == "NEW_CODE"
        scoped = [
            f
            for f in all_quality
            if (not new_code or f.get("new_code"))
            and f.get("review_status") not in {"FALSE_POSITIVE", "RESOLVED"}
            and (not configured.get("dimension") or f["dimension"] == configured["dimension"])
            and (not configured.get("severities") or f["severity"] in configured["severities"])
            and (not configured.get("rule_ids") or f["rule"] in configured["rule_ids"])
        ]
        measured_metrics = [m for m in quality["metrics"] if not new_code or m.get("new_code")]
        metric = configured["metric"]
        affected_files = [f["path"] for f in scoped]
        if metric == "finding_count":
            observed = len(scoped)
        elif metric in {"cyclomatic", "nesting", "parameters", "length", "cognitive_approximation"}:
            observed = max((m[metric] for m in measured_metrics), default=0)
            affected_files = [
                m["path"]
                for m in measured_metrics
                if not operators[configured["operator"]](m[metric], configured["threshold"])
            ]
        elif metric == "changed_coverage":
            observed = report.get("changed_line_percent") if report.get("state") == "VALID" else None
        elif metric == "analysis_coverage":
            observed = parsed_percent
            affected_files = [r["path"] for r in eligible_inventory if r.get("parser_state") != "COMPLETED"]
        elif metric == "parser_failures":
            affected_files = [r["path"] for r in eligible_inventory if r.get("parser_state") != "COMPLETED"]
            observed = len(affected_files)
        else:
            observed = quality["duplication"].get("new_density_percent" if new_code else "density_percent")
        failed = observed is None or not operators[configured["operator"]](observed, configured["threshold"])
        blocking = metric in {"analysis_coverage", "changed_coverage", "parser_failures"} or configured.get(
            "allow_unvalidated_blocking", False
        )
        outcome = configured.get("failure", "REVIEW_REQUIRED")
        if outcome == "FAIL" and not blocking:
            outcome = "REVIEW_REQUIRED"
        results.append(
            {
                "policy": "Quality: " + configured["id"],
                "condition": configured,
                "version": quality.get("profile_version", 0),
                "result": "REVIEW_REQUIRED" if observed is None else outcome if failed else "PASS",
                "measured": observed,
                "threshold": configured["threshold"],
                "operator": configured["operator"],
                "finding_ids": [f.get("id", f["fingerprint"]) for f in scoped] if metric == "finding_count" else [],
                "file_paths": sorted(set(affected_files)),
                "blocking_eligible": blocking,
                "precision_status": "NOT_APPLICABLE"
                if metric in {"analysis_coverage", "changed_coverage", "parser_failures"}
                else "UNMEASURED",
                "reason": "Required measurement unavailable."
                if observed is None
                else f"Measured {observed}; requires {configured['operator']} {configured['threshold']}."
                + (" Explicit organization blocking override." if configured.get("allow_unvalidated_blocking") else ""),
                "remediation": "Inspect the affected source, metrics and evidence; amend the captured profile only through an authorized versioned change.",
            }
        )
    if settings["min_changed_coverage"] is not None:
        actual = report.get("changed_line_percent")
        condition(
            "Quality: changed-line coverage",
            actual,
            settings["min_changed_coverage"],
            actual is not None and actual < settings["min_changed_coverage"],
            missing=report["state"] != "VALID" or actual is None,
        )
    if settings["scope"] == "NEW_CODE" and not quality.get("base_id"):
        results.append(
            {
                "policy": "Quality: baseline",
                "version": VERSION,
                "result": "REVIEW_REQUIRED",
                "reason": "Select a BASE snapshot before enforcing New Code conditions.",
                "remediation": "Choose an accepted snapshot in Rules & Profiles, then analyze HEAD.",
            }
        )
    if quality.get("comparison_model_changed"):
        results.append(
            {
                "policy": "Quality: comparable baseline",
                "version": VERSION,
                "result": "REVIEW_REQUIRED",
                "reason": "Analyzer/rule/scope changed. Establish an accepted baseline under this model before enforcing New Code.",
                "remediation": "Inspect model-change annotations and select the newly accepted snapshot as BASE.",
            }
        )
    if quality["state"] != "COMPLETED":
        results.append(
            {
                "policy": "Quality: analysis coverage",
                "version": VERSION,
                "result": "REVIEW_REQUIRED",
                "reason": "Quality coverage is partial/unavailable; inspect language and file diagnostics.",
                "remediation": "Repair parsing or explicitly scope unsupported source.",
            }
        )
    if any(f.get("rule_status") != "STABLE" for f in selected) and not duplicate:
        results.append(
            {
                "policy": "Quality: beta observations",
                "version": VERSION,
                "result": "WARNING",
                "reason": "Beta observations require human context; they do not automatically block.",
                "remediation": "Review the matching rules and source context.",
            }
        )
    rank = {"PASS": 0, "WARNING": 1, "REVIEW_REQUIRED": 2, "FAIL": 3}
    return {
        "status": max((r["result"] for r in results), key=rank.get, default="PASS"),
        "mode": "ADVISORY",
        "scope": settings["scope"],
        "base_id": quality.get("base_id"),
        "results": results,
    }


def summary(quality, findings):
    items = [f for f in findings if f.get("category") == "QUALITY"]
    return {
        "total": len(items),
        "dimensions": dict(Counter(f["dimension"] for f in items)),
        "severity": dict(Counter(f["severity"] for f in items)),
        "review": dict(Counter(f.get("review_status", "OPEN") for f in items)),
        "new": sum(f.get("new_code", False) for f in items),
        "resolved": len(quality.get("resolved", [])),
        "functions": len(quality["metrics"]),
        "max_cyclomatic": max((m["cyclomatic"] for m in quality["metrics"]), default=None),
    }


def hotspot_rows(quality, findings, history=()):
    rows = []
    for path in sorted({m["path"] for m in quality["metrics"]}):
        metrics = [m for m in quality["metrics"] if m["path"] == path]
        active = [
            f
            for f in findings
            if f.get("category") == "QUALITY"
            and f["path"] == path
            and f.get("review_status") not in {"FALSE_POSITIVE", "RESOLVED"}
        ]
        complexity = max((m["cyclomatic"] for m in metrics), default=0)
        changes = sum(path in h.get("changed_files", []) for h in history)
        duplicate = len(quality["duplication"]["lines_by_path"].get(path, []))
        material = sum(f["severity"] in {"HIGH", "CRITICAL"} for f in active)
        score = complexity + len(active) * 3 + material * 5 + min(duplicate, 100) / 10 + changes * 2
        rows.append(
            {
                "path": path,
                "owner": next((r.get("owner") for r in quality["inventory"] if r["path"] == path), None),
                "score": round(score, 1),
                "classification": "MAINTENANCE_HOTSPOT",
                "factors": {
                    "max_cyclomatic": complexity,
                    "active_quality_findings": len(active),
                    "material_findings": material,
                    "duplicated_lines": duplicate,
                    "observed_snapshot_changes": changes,
                },
                "formula": "max cyclomatic + 3*active quality findings + 5*high/critical + min(duplicate lines,100)/10 + 2*observed snapshot changes",
                "git_authors": None,
                "git_change_frequency": None,
                "history_scope": "Observed ProjectTrace snapshots only; not Git commit history",
            }
        )
    return sorted(rows, key=lambda r: (-r["score"], r["path"]))
