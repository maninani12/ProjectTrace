"""Shared Python structural metrics and conservative reliability observations."""

import ast
import bisect
import hashlib
import io
import sys
import tokenize


def metrics(path, source, tree=None):
    tree = tree or ast.parse(source)
    all_nodes = list(ast.walk(tree))
    if len(all_nodes) > 40000:
        raise ValueError("Python syntax budget exceeded")
    parents = {child: parent for parent in all_nodes for child in ast.iter_child_nodes(parent)}
    lexical = [
        t
        for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type
        not in {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    ]
    starts = [t.start[0] for t in lexical]
    result = []
    for function in all_nodes:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        ancestor = parents.get(function)
        qualified = [function.name]
        method = isinstance(ancestor, ast.ClassDef)
        while ancestor:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualified.insert(0, ancestor.name)
            ancestor = parents.get(ancestor)
        complexity, cognitive, nesting, count = 1, 0, 0, 0
        todo = [(statement, 0) for statement in reversed(function.body)]
        nodes, contributors = [], []
        while todo:
            node, depth = todo.pop()
            count += 1
            if count > 40000:
                raise ValueError("Python syntax budget exceeded")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            nodes.append(node)
            branches = int(isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)))
            if isinstance(node, ast.BoolOp):
                branches += len(node.values) - 1
            if isinstance(node, ast.Match):
                branches += max(0, len(node.cases) - 1)
            recursion = isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == function.name
            complexity += branches
            cognitive += branches * (1 + depth) + int(recursion)
            if branches or recursion:
                contributors.append(
                    {
                        "line": getattr(node, "lineno", function.lineno),
                        "kind": type(node).__name__,
                        "cyclomatic": branches,
                        "cognitive": branches * (1 + depth) + int(recursion),
                        "depth": depth,
                    }
                )
            next_depth = depth + isinstance(
                node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)
            )
            nesting = max(nesting, next_depth)
            todo.extend((child, next_depth) for child in reversed(list(ast.iter_child_nodes(node))))
        body = "\0".join(ast.dump(statement, include_attributes=False) for statement in function.body)
        params = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
        bindings = {arg.arg for arg in params}
        bindings.update(node.id for node in nodes if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store))
        names, tokens, original = {}, [], []
        first = function.body[0].lineno
        previous_token = None
        for token in lexical[bisect.bisect_left(starts, first) : bisect.bisect_right(starts, function.end_lineno)]:
            literal = token.type in {tokenize.STRING, tokenize.NUMBER}
            value = hashlib.sha256(token.string.encode()).hexdigest() if literal else token.string
            original.append(value)
            if token.type == tokenize.NAME and token.string in bindings and previous_token != ".":
                value = names.setdefault(token.string, "local" + str(len(names)))
            tokens.append({"value": str(token.type) + ":" + value, "line": token.start[0]})
            previous_token = token.string
        parameter_count = len(params) + int(function.args.vararg is not None) + int(function.args.kwarg is not None)
        if method and params and params[0].arg in {"self", "cls"}:
            parameter_count -= 1
        result.append(
            {
                "path": path,
                "line": function.lineno,
                "end_line": function.end_lineno,
                "name": function.name,
                "qualified_name": ".".join(qualified),
                "kind": "METHOD" if method else "FUNCTION",
                "language": "Python",
                "cyclomatic": complexity,
                "length": function.end_lineno - function.lineno + 1,
                "nesting": nesting,
                "parameters": parameter_count,
                "statements": sum(isinstance(node, ast.stmt) for node in nodes),
                "cognitive_approximation": cognitive,
                "contributors": contributors,
                "body_hash": hashlib.sha256(body.encode()).hexdigest(),
                "token_count": len(nodes),
                "duplicate_tokens": tokens,
                "original_token_hash": hashlib.sha256("\0".join(original).encode()).hexdigest(),
                "formula": "1 + if/loops/catch/ternary + boolean operands minus one + match alternatives minus one; nested definitions excluded",
                "cognitive_formula": "sum(decision contributions * (1 + enclosing syntax-control depth)) + direct same-name recursion; nested definitions excluded; ProjectTrace model, not proprietary compatibility",
            }
        )
    return result


def structure(path, source, tree):
    nodes = list(ast.walk(tree))
    parents = {child: parent for parent in nodes for child in ast.iter_child_nodes(parent)}

    def qualified(node):
        names = [node.name]
        ancestor = parents.get(node)
        while ancestor:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.insert(0, ancestor.name)
            ancestor = parents.get(ancestor)
        return ".".join(names)

    symbols = [
        {
            "path": path,
            "name": path,
            "qualified_name": path,
            "kind": "MODULE",
            "language": "Python",
            "line": 1,
            "end_line": max(1, len(source.splitlines())),
            "hash": hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest(),
        }
    ]
    observations = []
    for node in nodes:
        if isinstance(node, ast.ClassDef):
            symbols.append(
                {
                    "path": path,
                    "name": node.name,
                    "qualified_name": qualified(node),
                    "kind": "CLASS",
                    "language": "Python",
                    "line": node.lineno,
                    "end_line": node.end_lineno,
                    "class_lines": node.end_lineno - node.lineno + 1,
                    "method_count": sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in node.body),
                    "hash": hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(),
                }
            )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = [*node.args.posonlyargs, *node.args.args]
            defaults = list(zip(positional[-len(node.args.defaults) :], node.args.defaults)) + list(
                zip(node.args.kwonlyargs, node.args.kw_defaults)
            )
            for parameter, default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    observations.append(
                        {
                            "rule": "PT-QUALITY-011",
                            "line": default.lineno,
                            "symbol_line": node.lineno,
                            "anchor": "default-" + parameter.arg,
                            "context": hashlib.sha256(ast.dump(default, include_attributes=False).encode()).hexdigest(),
                            "detail": "Mutable literal defaults are constructed once and shared between calls.",
                        }
                    )
        if isinstance(node, ast.Compare) and any(isinstance(op, (ast.Is, ast.IsNot)) for op in node.ops):
            for op, left, right in zip(node.ops, [node.left, *node.comparators], node.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and any(
                    isinstance(x, ast.Constant) and x.value is not None and type(x.value) is not bool
                    for x in [left, right]
                ):
                    observations.append(
                        {
                            "rule": "PT-QUALITY-012",
                            "line": node.lineno,
                            "anchor": hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(),
                            "detail": "Identity is compared with a value literal; equality semantics are usually intended.",
                        }
                    )
        for field in ["body", "orelse", "finalbody"]:
            statements = getattr(node, field, None)
            if not isinstance(statements, list):
                continue
            stopped = False
            for statement in statements:
                if stopped and isinstance(statement, ast.stmt):
                    observations.append(
                        {
                            "rule": "PT-QUALITY-010",
                            "line": statement.lineno,
                            "anchor": hashlib.sha256(
                                ast.dump(statement, include_attributes=False).encode()
                            ).hexdigest(),
                            "detail": "This statement follows an unconditional return/raise/break/continue in the same syntax block.",
                        }
                    )
                    break
                stopped = isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue))
    return {
        "type": "quality_file",
        "value": "Python",
        "path": path,
        "line": 1,
        "symbols": symbols,
        "observations": observations,
        "parser": "Python ast",
        "parser_version": sys.version.split()[0],
        "state": "COMPLETED",
        "file_metrics": {
            "logical_statements": sum(isinstance(n, ast.stmt) for n in nodes),
            "classes": sum(isinstance(n, ast.ClassDef) for n in nodes),
            "comment_lines": len(
                {
                    t.start[0]
                    for t in tokenize.generate_tokens(io.StringIO(source).readline)
                    if t.type == tokenize.COMMENT
                }
            ),
            "logical_definition": "Count of AST statement nodes, including nested definitions; comment lines count tokenizer COMMENT start lines.",
        },
    }
