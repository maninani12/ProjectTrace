"""Versioned quality-only rule metadata and typed configuration."""

import copy

from analyzers.code_quality import VERSION

# key, dimension, severity, metric, threshold, status, bad example, good example
DEFINITIONS = {
    "PT-QUALITY-001": (
        "Cyclomatic complexity exceeds threshold",
        "MAINTAINABILITY",
        "HIGH",
        "cyclomatic",
        10,
        "STABLE",
        "Many independent decisions in one function.",
        "Extract coherent decisions into focused helpers.",
    ),
    "PT-QUALITY-002": (
        "Function source span exceeds threshold",
        "MAINTAINABILITY",
        "MEDIUM",
        "length",
        80,
        "STABLE",
        "An 81-line production function.",
        "Split responsibilities while preserving behavior.",
    ),
    "PT-QUALITY-003": (
        "Control nesting exceeds threshold",
        "MAINTAINABILITY",
        "MEDIUM",
        "nesting",
        4,
        "STABLE",
        "Five nested control structures.",
        "Use guard clauses and cohesive helpers.",
    ),
    "PT-QUALITY-004": (
        "Class source span exceeds threshold",
        "MAINTAINABILITY",
        "MEDIUM",
        "class_lines",
        200,
        "BETA",
        "A class spanning more than 200 lines.",
        "Review responsibilities; avoid splitting cohesive domain types blindly.",
    ),
    "PT-QUALITY-005": (
        "Bare exception handler",
        "RELIABILITY",
        "LOW",
        None,
        None,
        "BETA",
        "try: work()\nexcept: pass",
        "Catch an explicit expected exception or propagate failure.",
    ),
    "PT-QUALITY-006": (
        "Empty exception handler",
        "RELIABILITY",
        "MEDIUM",
        None,
        None,
        "BETA",
        "try { work(); } catch (error) {}",
        "Handle the expected error or rethrow with context.",
    ),
    "PT-QUALITY-007": (
        "Meaningful normalized duplicate block",
        "MAINTAINABILITY",
        "LOW",
        "duplicate_tokens",
        50,
        "BETA",
        "The same substantial sequence appears in two functions.",
        "Review shared behavior before extracting an abstraction.",
    ),
    "PT-QUALITY-008": (
        "ProjectTrace cognitive complexity exceeds threshold",
        "MAINTAINABILITY",
        "MEDIUM",
        "cognitive_approximation",
        15,
        "BETA",
        "Many nested decisions and logical branches.",
        "Reduce nested decisions; inspect the recorded contributors.",
    ),
    "PT-QUALITY-009": (
        "Parameter count exceeds threshold",
        "MAINTAINABILITY",
        "MEDIUM",
        "parameters",
        7,
        "BETA",
        "A production function with eight explicit parameters.",
        "Group a cohesive data concept; retain framework-required signatures.",
    ),
    "PT-QUALITY-010": (
        "Statement after unconditional transfer",
        "RELIABILITY",
        "MEDIUM",
        None,
        None,
        "STABLE",
        "return value\nwork()",
        "Remove unreachable statements or repair the preceding transfer.",
    ),
    "PT-QUALITY-011": (
        "Mutable literal default parameter",
        "RELIABILITY",
        "HIGH",
        None,
        None,
        "STABLE",
        "def append(value, items=[]): items.append(value)",
        "Use None and construct a fresh container inside the function.",
    ),
    "PT-QUALITY-012": (
        "Identity comparison with a value literal",
        "RELIABILITY",
        "MEDIUM",
        None,
        None,
        "STABLE",
        "if result is 1000: ...",
        "Use == for value comparison; retain is for None/boolean sentinels.",
    ),
    "PT-QUALITY-013": (
        "File source span exceeds threshold",
        "MAINTAINABILITY",
        "LOW",
        "file_lines",
        1000,
        "BETA",
        "A first-party source file exceeds the configured physical-line budget.",
        "Review cohesive modules and generated-code scope before splitting the file.",
    ),
}

RULES = {key: ("QUALITY", row[2], row[0], row[7], None) for key, row in DEFINITIONS.items()}
DEFAULT = {
    "name": "ProjectTrace Recommended",
    "rules": {},
    "scope": {
        "include": [],
        "exclude": [],
        "test_paths": [],
        "generated_patterns": [],
        "vendor_patterns": [],
        "language_overrides": {},
    },
    "gate": {
        "scope": "NEW_CODE",
        "max_new_high": 0,
        "max_new_reliability": 0,
        "max_new_complexity": 20,
        "max_new_duplication_percent": 3,
        "min_changed_coverage": None,
        "min_analysis_coverage_percent": None,
        "max_new_nesting": None,
        "required_languages": [],
        "conditions": [],
    },
    "baseline_id": None,
}


def config(value=None):
    value = value or {}
    if not isinstance(value, dict) or value.keys() - DEFAULT.keys():
        raise ValueError("Unknown quality configuration field.")
    result = copy.deepcopy(DEFAULT)
    for key, setting in value.items():
        if key in {"scope", "gate"}:
            if not isinstance(setting, dict) or setting.keys() - result[key].keys():
                raise ValueError("Unknown quality scope/gate setting.")
            result[key].update(setting)
        else:
            result[key] = setting
    if not isinstance(result["name"], str) or not 1 <= len(result["name"]) <= 120:
        raise ValueError("Quality profile name is required.")
    if result["baseline_id"] is not None and (
        not isinstance(result["baseline_id"], str) or len(result["baseline_id"]) > 80
    ):
        raise ValueError("Invalid baseline snapshot ID.")
    if not isinstance(result["rules"], dict) or len(result["rules"]) > len(DEFINITIONS):
        raise ValueError("Invalid quality rules.")
    for key, setting in result["rules"].items():
        if (
            key not in DEFINITIONS
            or not isinstance(setting, dict)
            or setting.keys() - {"enabled", "severity", "threshold"}
        ):
            raise ValueError("Unknown quality rule/parameter.")
        if "enabled" in setting and type(setting["enabled"]) is not bool:
            raise ValueError("Rule enabled must be boolean.")
        if "severity" in setting and setting["severity"] not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("Invalid rule severity.")
        if "threshold" in setting and (
            DEFINITIONS[key][3] is None
            or type(setting["threshold"]) is not int
            or not (30 if key == "PT-QUALITY-007" else 1) <= setting["threshold"] <= 10000
        ):
            raise ValueError("Invalid rule threshold.")
    for key, patterns in result["scope"].items():
        if key == "language_overrides":
            if (
                not isinstance(patterns, dict)
                or len(patterns) > 100
                or any(
                    not isinstance(path, str)
                    or not 1 <= len(path) <= 240
                    or ".." in path
                    or "\\" in path
                    or ":" in path
                    or path.startswith("/")
                    or not isinstance(lang, str)
                    or lang not in {"Python", "JavaScript", "TypeScript", "Java"}
                    for path, lang in patterns.items()
                )
            ):
                raise ValueError("Invalid language overrides.")
        elif (
            not isinstance(patterns, list)
            or len(patterns) > 100
            or any(
                not isinstance(pattern, str) or not 1 <= len(pattern) <= 240 or ".." in pattern or "\\" in pattern
                for pattern in patterns
            )
        ):
            raise ValueError("Invalid source glob.")
    gate = result["gate"]
    if gate["scope"] == "ALL_CODE":
        gate["scope"] = "OVERALL"
    if gate["scope"] not in {"NEW_CODE", "OVERALL"}:
        raise ValueError("Invalid quality gate scope.")
    for key in ["max_new_high", "max_new_reliability", "max_new_complexity"]:
        if type(gate[key]) is not int or not 0 <= gate[key] <= 10000:
            raise ValueError("Invalid gate threshold.")
    for key in ["max_new_duplication_percent", "min_changed_coverage", "min_analysis_coverage_percent"]:
        if gate[key] is not None and (type(gate[key]) not in {int, float} or not 0 <= gate[key] <= 100):
            raise ValueError("Invalid gate percentage.")
    if gate["max_new_nesting"] is not None and (
        type(gate["max_new_nesting"]) is not int or not 0 <= gate["max_new_nesting"] <= 100
    ):
        raise ValueError("Invalid nesting gate threshold.")
    if not isinstance(gate["required_languages"], list) or any(
        lang not in {"Python", "JavaScript", "TypeScript", "Java"} for lang in gate["required_languages"]
    ):
        raise ValueError("Invalid required parser language.")
    conditions = gate["conditions"]
    if not isinstance(conditions, list) or len(conditions) > 30:
        raise ValueError("At most 30 quality gate conditions are allowed.")
    seen = set()
    for condition in conditions:
        if not isinstance(condition, dict) or condition.keys() - {
            "id",
            "metric",
            "operator",
            "threshold",
            "scope",
            "dimension",
            "severities",
            "rule_ids",
            "failure",
            "allow_unvalidated_blocking",
        }:
            raise ValueError("Unknown quality gate condition field.")
        key = condition.get("id")
        if not isinstance(key, str) or not 1 <= len(key) <= 100 or key in seen:
            raise ValueError("Condition IDs must be unique.")
        seen.add(key)
        if condition.get("metric") not in {
            "finding_count",
            "cyclomatic",
            "nesting",
            "parameters",
            "length",
            "cognitive_approximation",
            "changed_coverage",
            "analysis_coverage",
            "duplication_percent",
            "parser_failures",
        } or condition.get("operator") not in {"EQ", "LT", "LTE", "GT", "GTE"}:
            raise ValueError("Invalid gate metric/operator.")
        threshold = condition.get("threshold")
        if type(threshold) not in {int, float} or not 0 <= threshold <= 10000:
            raise ValueError("Invalid condition threshold.")
        if condition.get("scope", gate["scope"]) not in {"NEW_CODE", "OVERALL", "ALL_CODE"} or condition.get(
            "failure", "REVIEW_REQUIRED"
        ) not in {"WARNING", "REVIEW_REQUIRED", "FAIL"}:
            raise ValueError("Invalid condition scope/result.")
        if "allow_unvalidated_blocking" in condition and type(condition["allow_unvalidated_blocking"]) is not bool:
            raise ValueError("Blocking override must be explicit boolean.")
        if condition.get("dimension") not in {None, "RELIABILITY", "MAINTAINABILITY"}:
            raise ValueError("Invalid condition dimension.")
        for field, allowed in (
            ("severities", {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}),
            ("rule_ids", set(DEFINITIONS)),
        ):
            values = condition.get(field, [])
            if not isinstance(values, list) or len(values) > len(allowed) or any(v not in allowed for v in values):
                raise ValueError("Invalid condition finding filters.")
    return result


def registry():
    return [
        {
            "id": key,
            "version": VERSION,
            "title": row[0],
            "dimension": row[1],
            "default_severity": row[2],
            "metric": row[3],
            "default_threshold": row[4],
            "threshold_min": 30 if key == "PT-QUALITY-007" else 1 if row[3] else None,
            "status": row[5],
            "precision_status": "UNMEASURED",
            "blocking_eligible": False,
            "bad_example": row[6],
            "good_example": row[7],
            "remediation": row[7],
            "enabled_by_default": True,
            "languages": ["Python"]
            if key in {"PT-QUALITY-005", "PT-QUALITY-010", "PT-QUALITY-011", "PT-QUALITY-012"}
            else ["JavaScript", "TypeScript", "Java"]
            if key == "PT-QUALITY-006"
            else ["Python", "JavaScript", "TypeScript", "Java"],
            "detection": "Bounded syntax/AST observation; not complete CFG/type/framework analysis.",
            "introduced_analyzer": VERSION if key >= "PT-QUALITY-008" else "1.3.3",
            "supported_versions": "Syntax accepted by the recorded installed parser; language-version compatibility matrix is unverified.",
            "references": [],
            "tags": [row[1].lower(), "native"],
            "why": "Review a concrete source structure or measured threshold while retaining repository context.",
        }
        for key, row in DEFINITIONS.items()
    ]
