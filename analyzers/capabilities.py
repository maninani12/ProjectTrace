"""Versioned capability declarations: syntax support is not full semantic coverage."""

import importlib.metadata


def installed(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def registry(version):
    rows = []
    for name, parser in (
        ("Python", "CPython ast"),
        ("JavaScript", "Tree-sitter"),
        ("JSX", "Tree-sitter"),
        ("TypeScript", "Tree-sitter"),
        ("TSX", "Tree-sitter"),
        ("Java", "Tree-sitter"),
    ):
        rows.append(
            {
                "language": name,
                "parser": parser,
                "parser_version": installed("tree-sitter")
                if parser == "Tree-sitter"
                else __import__("platform").python_version(),
                "grammar_version": installed(
                    "tree-sitter-java"
                    if name == "Java"
                    else "tree-sitter-typescript"
                    if name in {"TypeScript", "TSX"}
                    else "tree-sitter-javascript"
                )
                if parser == "Tree-sitter"
                else None,
                "maturity": "PARTIAL",
                "quality": "SELECTED_RULES",
                "reliability": "SELECTED_RULES",
                "sast": "SELECTED_RULES",
                "flow": "LOCAL_FUNCTION_ONLY" if name == "Python" else "LIMITED",
                "frameworks": "SELECTED_PATTERNS_NO_COMPLETE_FRAMEWORK_MODEL",
                "duplication": "NORMALIZED_FUNCTION_BODY",
                "symbols": "STATIC_DECLARATIONS",
                "coverage_import": "LCOV_COBERTURA_JACOCO" if name == "Java" else "LCOV_COBERTURA",
                "runtime_execution": False,
                "precision": "UNMEASURED",
                "version": version,
            }
        )
    for name, parser in (
        ("Terraform", "python-hcl2"),
        ("CloudFormation", "PyYAML / JSON"),
        ("Kubernetes", "PyYAML / JSON"),
        ("Compose", "PyYAML / JSON"),
        ("Dockerfile", "Native instruction parser"),
    ):
        rows.append(
            {
                "language": name,
                "parser": parser,
                "parser_version": installed("python-hcl2")
                if name == "Terraform"
                else installed("PyYAML")
                if name != "Dockerfile"
                else version,
                "maturity": "PARTIAL",
                "quality": "NOT_APPLICABLE",
                "sast": "STATIC_CONFIGURATION_HOTSPOTS",
                "flow": "DECLARED_REFERENCES_ONLY",
                "runtime_execution": False,
                "precision": "UNMEASURED",
                "version": version,
            }
        )
    return {
        "schema": "projecttrace-capabilities-v1",
        "version": version,
        "languages": rows,
        "unsupported": "Inventoried as a coverage gap; absence of findings does not prove safety.",
        "parser_isolation": "PARTIAL: bounded parsing and IaC/grammar subprocess limits; Python AST remains in-process; full OS sandbox is unverified.",
        "rule_blocking": "Disabled by default: representative rule precision is unmeasured.",
        "scale": {"three_million_lines": "UNMEASURED_PARTITIONED_INTAKE", "hundred_concurrent_prs": "UNMEASURED"},
    }
