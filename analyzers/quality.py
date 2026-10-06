"""Transparent Python syntax metrics; no arbitrary quality score."""

import ast
import hashlib


def metrics(path, source):
    tree = ast.parse(source)
    result = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        complexity, cognitive, nesting, count = 1, 0, 0, 0
        todo = [(statement, 0) for statement in function.body]
        nodes = []
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
            complexity += branches
            cognitive += branches * (1 + depth)
            next_depth = depth + isinstance(
                node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)
            )
            nesting = max(nesting, next_depth)
            todo.extend((child, next_depth) for child in ast.iter_child_nodes(node))
        body = "\0".join(ast.dump(statement, include_attributes=False) for statement in function.body)
        result.append(
            {
                "path": path,
                "line": function.lineno,
                "end_line": function.end_lineno,
                "name": function.name,
                "language": "Python",
                "cyclomatic": complexity,
                "length": function.end_lineno - function.lineno + 1,
                "nesting": nesting,
                "cognitive_approximation": cognitive,
                "body_hash": hashlib.sha256(body.encode()).hexdigest(),
                "token_count": len(nodes),
                "formula": "1 + if/loops/catch/ternary + boolean operands minus one + match alternatives minus one; nested definitions excluded",
                "cognitive_formula": "sum(branch contributions * (1 + syntax control nesting)); ProjectTrace approximation",
            }
        )
    return result
