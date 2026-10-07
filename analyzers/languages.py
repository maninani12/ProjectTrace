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
    ".mjs": ("JavaScript", "language", "tree-sitter-javascript"),
    ".cjs": ("JavaScript", "language", "tree-sitter-javascript"),
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

    symbols = [
        {
            "path": path,
            "name": path,
            "qualified_name": path,
            "kind": "MODULE",
            "line": 1,
            "end_line": line_at(len(raw)),
            "language": name,
            "hash": hashlib.sha256(raw).hexdigest(),
        }
    ]
    lexical_scopes = DEFINITIONS | {"statement_block", "program"}

    def lexical_owner(node, function_only=False):
        current = node
        accepted = DEFINITIONS | {"program"} if function_only else lexical_scopes
        while current.parent and current.type not in accepted:
            current = current.parent
        return current

    eval_bindings = set()
    for declaration in walk(tree.root_node):
        if declaration.type == "function_declaration" and text(declaration.child_by_field_name("name")) == "eval":
            eval_bindings.add(lexical_owner(declaration.parent).id)
        elif declaration.type == "variable_declarator" and text(declaration.child_by_field_name("name")) == "eval":
            parent = declaration.parent
            function_only = bool(parent and parent.type == "variable_declaration")
            eval_bindings.add(lexical_owner(parent, function_only).id)
        elif declaration.type in DEFINITIONS:
            params = declaration.child_by_field_name("parameters") or declaration.child_by_field_name("parameter")
            if params and any(
                text(p.child_by_field_name("pattern") or p.child_by_field_name("name") or p) == "eval"
                for p in (params.named_children if params.type in {"formal_parameters", "parameters"} else [params])
            ):
                eval_bindings.add(declaration.id)
        elif declaration.type == "import_statement" and any(
            n.type == "identifier" and text(n) == "eval" for n in walk(declaration)
        ):
            eval_bindings.add(tree.root_node.id)

    def unshadowed_eval(node):
        parent = node.parent
        while parent:
            if parent.id in eval_bindings:
                return False
            parent = parent.parent
        return True

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
            function_name = text(node.child_by_field_name("name"))
            if (
                not function_name
                and node.parent
                and node.parent.type in {"variable_declarator", "pair", "assignment_expression"}
            ):
                function_name = text(
                    node.parent.child_by_field_name("name")
                    or node.parent.child_by_field_name("key")
                    or node.parent.child_by_field_name("left")
                )
            function_name = function_name or "anonymous"
            qualified = [function_name]
            parent = node.parent
            while parent:
                if parent.type in DEFINITIONS | {"class_declaration", "class", "interface_declaration"}:
                    ancestor_name = text(parent.child_by_field_name("name"))
                    if ancestor_name:
                        qualified.insert(0, ancestor_name)
                parent = parent.parent
            params = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
            parameter_nodes = (
                list(params.named_children)
                if params and params.type in {"formal_parameters", "parameters"}
                else [params]
                if params
                else []
            )
            parameter_nodes = [c for c in parameter_nodes if c.type != "comment"]
            bindings = set()
            for parameter in parameter_nodes:
                identifier = (
                    parameter.child_by_field_name("name") or parameter.child_by_field_name("pattern") or parameter
                )
                if identifier.type in {"identifier", "shorthand_property_identifier_pattern"}:
                    bindings.add(text(identifier))
            for child in nodes:
                if child.type == "variable_declarator":
                    identifier = child.child_by_field_name("name")
                    if identifier and identifier.type == "identifier":
                        bindings.add(text(identifier))
            normalized, names, leaves, todo = [], {}, [], [body]
            while todo:
                child = todo.pop()
                if child.type == "comment" or child.type in DEFINITIONS:
                    continue
                if child.children:
                    todo.extend(reversed(child.children))
                else:
                    leaves.append(child)
            for child in leaves:
                value = text(child)
                if child.type == "identifier" and value in bindings:
                    value = names.setdefault(value, "local" + str(len(names)))
                if any(part in child.type for part in {"string", "number", "decimal", "integer", "character", "float"}):
                    value = hashlib.sha256(value.encode()).hexdigest()
                normalized.append({"value": child.type + ":" + value, "line": line_at(child.start_byte)})
            cognitive, contributors, todo = 0, [], [(body, 0)]
            while todo:
                child, level = todo.pop()
                branches = int(child.type in BRANCHES) + int(
                    child.type == "binary_expression" and text(child.child_by_field_name("operator")) in {"&&", "||"}
                )
                contribution = branches * (1 + level)
                cognitive += contribution
                if branches:
                    contributors.append(
                        {
                            "line": line_at(child.start_byte),
                            "kind": child.type,
                            "cyclomatic": branches,
                            "cognitive": contribution,
                            "depth": level,
                        }
                    )
                todo.extend(
                    (c, level + int(child.type in BRANCHES)) for c in child.named_children if c.type not in DEFINITIONS
                )
            tokens = body_tokens(body)
            body_hash = hashlib.sha256("\x00".join(tokens).encode()).hexdigest()
            metric = {
                "path": path,
                "line": line,
                "end_line": line_at(node.end_byte),
                "name": function_name,
                "language": name,
                "qualified_name": ".".join(qualified),
                "kind": "CONSTRUCTOR"
                if node.type == "constructor_declaration"
                else "METHOD"
                if node.type.startswith("method")
                else "FUNCTION",
                "parameters": len(parameter_nodes),
                "statements": sum(c.type.endswith("statement") for c in nodes),
                "duplicate_tokens": normalized,
                "contributors": contributors,
                "cognitive_formula": "sum(decision contributions * (1 + enclosing syntax-control depth)); nested definitions excluded; ProjectTrace model",
                "cyclomatic": complexity,
                "length": length,
                "nesting": depth,
                "body_hash": body_hash,
                "syntax_context_hash": hashlib.sha256("\x00".join(body_tokens(node)).encode()).hexdigest(),
                "token_count": len(tokens),
                "formula": "1 + if/loops/catch/switch cases/ternary/short-circuit operators; nested functions excluded",
                "cognitive_approximation": cognitive,
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
        if node.type in {
            "class_declaration",
            "class",
            "interface_declaration",
            "field_declaration",
            "public_field_definition",
        }:
            symbols.append(
                {
                    "path": path,
                    "name": text(node.child_by_field_name("name")) or node.type,
                    "qualified_name": text(node.child_by_field_name("name")) or node.type,
                    "kind": "INTERFACE"
                    if node.type == "interface_declaration"
                    else "CLASS"
                    if node.type in {"class_declaration", "class"}
                    else "FIELD",
                    "line": line,
                    "end_line": line_at(node.end_byte),
                    "language": name,
                }
            )
        if node.type in {"class_declaration", "class"} and line_at(node.end_byte) - line + 1 > 200:
            findings.append(make_finding("PT-QUALITY-004", path, line))
        if node.type == "catch_clause":
            body = node.child_by_field_name("body")
            if body and not [child for child in body.named_children if child.type != "comment"]:
                findings.append(make_finding("PT-QUALITY-006", path, line))
        if node.type in {"call_expression", "method_invocation"}:
            called = text(node.child_by_field_name("function") or node.child_by_field_name("name"))
            if called == "eval" and name != "Java" and unshadowed_eval(node):
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
    file_nodes = list(walk(tree.root_node))
    if not tree.root_node.has_error:
        from analyzers.finding_identity import digest

        file_hash = digest(body_tokens(tree.root_node))
        for metric in metrics:
            metric["file_structure_hash"] = file_hash
        for item in findings:
            candidates = [
                n
                for n in file_nodes
                if line_at(n.start_byte) <= item["line"] <= line_at(n.end_byte)
                and (
                    n.type.endswith("statement")
                    or n.type in {"call_expression", "method_invocation", "assignment_expression", "catch_clause"}
                )
            ]
            target = min(candidates, key=lambda n: n.end_byte - n.start_byte, default=None)
            if target is None:
                continue
            owning = min(
                (m for m in metrics if m["line"] <= item["line"] <= m["end_line"]),
                key=lambda m: m["end_line"] - m["line"],
                default=None,
            )
            owner, cursor = target, target
            while cursor:
                if cursor.type in DEFINITIONS:
                    owner = cursor
                    break
                cursor = cursor.parent
            referenced = {text(n) for n in walk(owner) if n.type == "identifier"}
            bindings = [
                body_tokens(n)
                for n in tree.root_node.named_children
                if n.type in {"import_statement", "import_declaration", "lexical_declaration", "variable_declaration"}
                and any(text(i) in referenced for i in walk(n) if i.type == "identifier")
                and not (n.start_byte <= owner.start_byte and owner.end_byte <= n.end_byte)
            ]
            symbol = owning["qualified_name"] if owning else "<module>"
            item.update(
                structural_key=digest([item["rule"], symbol, body_tokens(target)]),
                structural_context_hash=digest([body_tokens(owner), bindings]),
                file_structure_hash=file_hash,
                structural_symbol=symbol,
                identity_version="structural-v2",
                identity_confidence="HIGH",
                identity_method="TREE_SITTER_NODE",
            )
    comment_lines = set()
    for item in file_nodes:
        if item.type in {"comment", "line_comment", "block_comment"}:
            comment_lines.update(range(line_at(item.start_byte), line_at(item.end_byte) + 1))
    signals.append(
        {
            **metadata,
            "type": "quality_file",
            "symbols": symbols,
            "observations": [],
            "file_metrics": {
                "logical_statements": sum(
                    n.type.endswith("statement") or n.type in {"lexical_declaration", "local_variable_declaration"}
                    for n in file_nodes
                ),
                "classes": sum(n.type in {"class_declaration", "class"} for n in file_nodes),
                "comment_lines": len(comment_lines),
                "logical_definition": "Count of named statement/declaration nodes; not cross-language-equivalent logical LOC.",
            },
        }
    )
    return findings, signals, metrics
