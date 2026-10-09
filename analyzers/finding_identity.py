"""Conservative structural anchors. Hashes contain no source or secret values."""

import ast
import hashlib
import json
from collections import Counter

VERSION = "structural-v2"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def python_index(source):
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if len(nodes) > 40000:
        raise ValueError("Structural identity syntax budget exceeded")
    parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    bindings = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = {node.name}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {a.asname or a.name.split(".")[0] for a in node.names}
        else:
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        for name in names:
            bindings.setdefault(name, []).append(ast.dump(node, include_attributes=False))
    return tree, nodes, parents, bindings


def annotate(files, findings, metrics):
    indexes = {}
    file_hashes, contexts = {}, {}
    metric_index = {(m["path"], m.get("qualified_name", m.get("name"))): m for m in reversed(metrics)}
    for path in {
        f["path"]
        for f in findings
        if f["path"].endswith(".py") and not (f.get("structural_key") and f.get("identity_confidence") == "HIGH")
    }:
        try:
            indexes[path] = python_index(files[path])
        except (SyntaxError, ValueError, RecursionError, KeyError):
            pass
    for item in findings:
        if item.get("structural_key") and item.get("identity_confidence") == "HIGH":
            continue
        path, line = item["path"], item.get("line", 1)
        key, context, file_hash, confidence, method = None, None, None, "LOW", "LEGACY_FALLBACK"
        if path in indexes:
            tree, nodes, parents, bindings = indexes[path]
            candidates = [
                n
                for n in nodes
                if isinstance(n, ast.stmt) and getattr(n, "lineno", 0) <= line <= getattr(n, "end_lineno", 0)
            ]
            target = min(candidates, key=lambda n: (n.end_lineno - n.lineno, -n.col_offset), default=None)
            if target:
                owner, cursor, names = target, target, []
                owner_found = False
                while cursor:
                    if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        names.insert(0, cursor.name)
                        if not owner_found:
                            owner = cursor
                            owner_found = True
                    cursor = parents.get(cursor)
                symbol = ".".join(names) or "<module>"
                if item.get("metric") == "file_lines":
                    symbol, owner = "<file>", tree
                # Metric threshold concepts survive a changed measurement; context does not.
                symptom = (
                    item.get("metric")
                    if item.get("category") == "QUALITY" and item.get("measured") is not None
                    else ast.dump(target, include_attributes=False)
                )
                if isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.get("measured") is None:
                    symptom = [
                        target.name,
                        ast.dump(target.args, include_attributes=False),
                        [ast.dump(d, include_attributes=False) for d in target.decorator_list],
                    ]
                key = digest([item["rule"], symbol, symptom])
                owner_key = (path, owner)
                if owner_key not in contexts:
                    referenced = {n.id for n in ast.walk(owner) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                    contexts[owner_key] = digest([
                        ast.dump(owner, include_attributes=False),
                        {n: bindings[n] for n in sorted(referenced) if n in bindings},
                    ])
                context = contexts[owner_key]
                if path not in file_hashes:
                    file_hashes[path] = digest(ast.dump(tree, include_attributes=False))
                file_hash = file_hashes[path]
                confidence, method = "HIGH", "PYTHON_AST"
                item["structural_symbol"] = symbol
        elif item.get("resource_context_hash") and item.get("infrastructure_format") != "DOCKERFILE":
            key = digest(
                [item["rule"], item.get("resource_identity"), item.get("structural_symptom", item.get("explanation"))]
            )
            context = item["resource_context_hash"]
            confidence, method = "HIGH", "RESOURCE_STRUCTURE"
        elif item.get("category") == "QUALITY":
            # Maintained parser metrics support symbol identity; statement matching remains conservative.
            metric = metric_index.get((path, item.get("symbol")))
            if metric and item.get("measured") is not None:
                key = digest([item["rule"], item["symbol"], item.get("metric")])
                context = digest([metric.get("syntax_context_hash", metric["body_hash"]), item.get("observation_hash")])
                file_hash = metric.get("file_structure_hash")
                confidence, method = "HIGH", "PARSER_SYMBOL"
        if key:
            item.update(structural_key=key, structural_context_hash=context, file_structure_hash=file_hash)
        item.update(identity_version=VERSION, identity_confidence=confidence, identity_method=method)
    counts = Counter((f["path"], f.get("structural_key")) for f in findings if f.get("structural_key"))
    for item in findings:
        if counts[(item["path"], item.get("structural_key"))] > 1:
            item["identity_confidence"] = "AMBIGUOUS"
    return findings
