"""Bounded Tree-sitter adapters for JavaScript, TypeScript, TSX and Java."""

import hashlib
import json
import os
import subprocess
import sys
from bisect import bisect_right
from importlib import import_module
from importlib.metadata import version
from pathlib import Path, PurePosixPath

DEFINITIONS = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "method_declaration",
    "constructor_declaration",
}
BRANCHES = {
    "if_statement",
    "for_statement",
    "for_in_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "switch_case",
    "ternary_expression",
    "conditional_expression",
}
LANGUAGES = {
    ".js": ("JavaScript", "language", "tree-sitter-javascript"),
    ".jsx": ("JavaScript", "language", "tree-sitter-javascript"),
    ".ts": ("TypeScript", "language_typescript", "tree-sitter-typescript"),
    ".tsx": ("TypeScript", "language_tsx", "tree-sitter-typescript"),
    ".java": ("Java", "language", "tree-sitter-java"),
}


def analyze_languages(files):
    """One isolated native-parser process per uncached language batch.

    Only ProjectTrace's installed helper executes. Imported source stays JSON
    data in memory; credentials and user Python paths are not inherited.
    """
    if not files:
        return {}
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
        }
    }
    try:
        reply = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("native_parser_worker.py"))],
            input=json.dumps(files, ensure_ascii=False).encode(),
            capture_output=True,
            timeout=30,
            env=environment,
            cwd=Path(__file__).resolve().parents[1],
        )
        if reply.returncode or len(reply.stdout) > 16_000_000:
            raise ValueError("Native parser process failed or exceeded its result budget")
        result = json.loads(reply.stdout)
        if not isinstance(result, dict) or result.keys() != files.keys():
            raise ValueError("Native parser returned an invalid result")
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {path: {"error": "Native parser process failed or exceeded its budget"} for path in files}


def walk(node, own=False):
    todo = [node]
    count = 0
    while todo:
        current = todo.pop()
        count += 1
        if count > 40000:
            raise ValueError("Syntax node budget exceeded")
        yield current
        todo.extend(reversed([child for child in current.named_children if not own or child.type not in DEFINITIONS]))


def analyze_language(path, source, make_finding):
    result = analyze_languages({path: source})[path]
    if isinstance(result, dict):
        raise ValueError("Native syntax coverage is partial")
    return result


def _analyze_language(path, source, make_finding):
    # Native extensions are loaded only in the isolated parser helper.
    from tree_sitter import Language, Parser

    suffix = PurePosixPath(path).suffix
    name, factory, package = LANGUAGES[suffix]
    grammar = Language(getattr(import_module(package.replace("-", "_")), factory)())
    raw = source.encode()
    # Keep the parser/grammar alive while visiting its tree. Derive source
    # lines from byte offsets rather than native Point property accessors.
    parser = Parser(grammar)
    tree = parser.parse(raw)
    line_starts = [0] + [offset + 1 for offset, value in enumerate(raw) if value == 10]

    def line_at(offset):
        return bisect_right(line_starts, offset)

    findings, signals, metrics = [], [], []
    metadata = {
        "type": "parser",
        "value": name,
        "path": path,
        "line": 1,
        "parser": "Tree-sitter",
        "parser_version": version("tree-sitter"),
        "grammar_version": version(package),
        "state": "PARTIAL" if tree.root_node.has_error else "COMPLETED",
    }
    signals.append(metadata)
    if tree.root_node.has_error:
        error = next((node for node in walk(tree.root_node) if node.type == "ERROR" or node.is_missing), tree.root_node)
        findings.append(
            make_finding(
                "PT-PARSE-001",
                path,
                line_at(error.start_byte),
                "Tree-sitter found invalid or unsupported syntax; this file has partial coverage.",
            )
        )

    def text(node):
        return raw[node.start_byte : node.end_byte].decode() if node else ""

    def nesting(node):
        highest, todo = 0, [(node, 0)]
        while todo:
            current, depth = todo.pop()
            depth += current.type in BRANCHES
            highest = max(highest, depth)
            todo.extend((child, depth) for child in current.named_children if child.type not in DEFINITIONS)
        return highest

    def body_tokens(body):
        # Include operators and punctuation: named-child-only traversal can
        # mistake different arithmetic/control expressions for duplicates.
        tokens, todo, visited = [], [body], 0
        while todo:
            current = todo.pop()
            visited += 1
            if visited > 40000:
                raise ValueError("Syntax token budget exceeded")
            if current.type == "comment":
                continue
            children = current.children
            if children:
                todo.extend(reversed(children))
            else:
                tokens.append(current.type + ":" + text(current))
        return tokens

    for node in walk(tree.root_node):
        line = line_at(node.start_byte)
        if node.type in DEFINITIONS:
            body = node.child_by_field_name("body")
            if body is None:
                continue
            nodes = list(walk(body, own=True))
            complexity = 1 + sum(child.type in BRANCHES for child in nodes)
            complexity += sum(
                child.type == "binary_expression" and text(child.child_by_field_name("operator")) in {"&&", "||"}
                for child in nodes
            )
            length = line_at(node.end_byte) - line + 1
            depth = nesting(body)
            function_name = text(node.child_by_field_name("name")) or "anonymous"
            tokens = body_tokens(body)
            body_hash = hashlib.sha256("\x00".join(tokens).encode()).hexdigest()
            metric = {
                "path": path,
                "line": line,
                "end_line": line_at(node.end_byte),
                "name": function_name,
                "language": name,
                "cyclomatic": complexity,
                "length": length,
                "nesting": depth,
                "body_hash": body_hash,
                "token_count": len(tokens),
                "formula": "1 + if/loops/catch/switch cases/ternary/short-circuit operators; nested functions excluded",
                "cognitive_approximation": sum(1 + nesting(child) for child in nodes if child.type in BRANCHES),
            }
            metrics.append(metric)
            signals.append(
                {
                    "type": "function",
                    "value": function_name,
                    "path": path,
                    "line": line,
                    "end_line": metric["end_line"],
                    "language": name,
                }
            )
            for rule, actual, threshold in [
                ("PT-QUALITY-001", complexity, 10),
                ("PT-QUALITY-002", length, 80),
                ("PT-QUALITY-003", depth, 4),
            ]:
                if actual > threshold:
                    findings.append(
                        make_finding(rule, path, line, f"{function_name}: measured {actual}; threshold {threshold}.")
                    )
        if node.type in {"class_declaration", "class"} and line_at(node.end_byte) - line + 1 > 200:
            findings.append(make_finding("PT-QUALITY-004", path, line))
        if node.type == "catch_clause":
            body = node.child_by_field_name("body")
            if body and not [child for child in body.named_children if child.type != "comment"]:
                findings.append(make_finding("PT-QUALITY-006", path, line))
        if node.type in {"call_expression", "method_invocation"}:
            called = text(node.child_by_field_name("function") or node.child_by_field_name("name"))
            if called == "eval":
                findings.append(
                    make_finding(
                        "PT-SAST-005", path, line, "Parsed eval invocation. Input reachability is unproven.", "MEDIUM"
                    )
                )
        if node.type == "assignment_expression":
            left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
            if text(left).endswith(".innerHTML") and right and right.type not in {"string", "string_literal"}:
                # A sanitizer only applies to this modeled HTML sink.
                if right.type == "call_expression" and text(right.child_by_field_name("function")) in {
                    "DOMPurify.sanitize",
                    "escapeHtml",
                }:
                    continue
                findings.append(
                    make_finding(
                        "PT-SAST-006",
                        path,
                        line,
                        "Parsed non-literal innerHTML assignment. Input reachability is unproven.",
                        "MEDIUM",
                    )
                )
    return findings, signals, metrics
