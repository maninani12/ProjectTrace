"""Bounded Python source-to-sink flow evidence, including local helper calls.

This is conservative static data flow, not a complete CFG or exploitability proof.
Repository functions are inspected as syntax; they are never executed.
"""

import ast

SOURCE_PREFIXES = (
    "request.args",
    "request.query_params",
    "request.path_params",
    "request.form",
    "request.json",
    "request.get_json",
    "request.data",
    "request.body",
    "req.query",
    "req.body",
)


def name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return name(node.value) + "." + node.attr
    return ""


def python_flows(path, source, make_finding):
    tree = ast.parse(source)
    helpers = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    results = {}
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update({part.asname or part.name.split(".")[0]: part.name for part in node.names})
        elif isinstance(node, ast.ImportFrom):
            aliases.update({part.asname or part.name: (node.module or "") + "." + part.name for part in node.names})

    def canonical(node):
        value = name(node)
        head, _, tail = value.partition(".")
        return aliases.get(head, head) + ("." + tail if tail else "")

    def step(kind, node, symbol):
        return {"kind": kind, "path": path, "line": getattr(node, "lineno", 1), "symbol": symbol[:160]}

    def expression(node, env, rule, depth=0):
        if node is None or depth > 24:
            return []
        if isinstance(node, ast.Name):
            trail = env.get(node.id, [])
            return [] if rule == "PT-SAST-006" and any(item.get("context") == "HTML" for item in trail) else trail
        value = name(node)
        if value.startswith(SOURCE_PREFIXES):
            return [step("SOURCE", node, value)]
        if isinstance(node, ast.Call):
            called = canonical(node.func)
            if called.startswith(SOURCE_PREFIXES) or called == "input":
                return [step("SOURCE", node, called)]
            if rule == "PT-SAST-006" and called in {"html.escape", "markupsafe.escape"}:
                return []
            # Calls with unknown transformations retain taint but do not invent sanitization.
            parts = node.args + [keyword.value for keyword in node.keywords]
        else:
            parts = list(ast.iter_child_nodes(node))
        for part in parts:
            trail = expression(part, env, rule, depth + 1)
            if trail:
                if isinstance(node, ast.Call) and canonical(node.func) in {"html.escape", "markupsafe.escape"}:
                    return trail + [{**step("SANITIZER", node, canonical(node.func)), "context": "HTML"}]
                if (
                    isinstance(node, ast.Call)
                    and canonical(node.func) not in {"str", "bytes", "sqlalchemy.text"}
                    and not canonical(node.func).endswith((".format", ".join", ".encode", ".decode"))
                ):
                    return trail + [step("UNKNOWN_PROPAGATION", node, canonical(node.func))]
                return trail
        return []

    def inspect_call(node, env, stack):
        called = canonical(node.func)
        index, rule = 0, None
        if called.endswith(".execute") and len(node.args) == 1:
            rule = "PT-SAST-001"
        elif (
            called == "os.system"
            or called.startswith("subprocess.")
            and any(
                keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                for keyword in node.keywords
            )
        ):
            rule = "PT-SAST-002"
        elif called in {"pickle.loads", "pickle.load", "yaml.unsafe_load"}:
            rule = "PT-SAST-003"
        elif called.split(".")[-1] in {"HTMLResponse", "render_template_string"}:
            rule = "PT-SAST-006"
        elif called.split(".")[-1] in {"FileResponse", "send_file"}:
            rule = "PT-SAST-007"
        elif called in {
            "requests.get",
            "requests.post",
            "httpx.get",
            "httpx.post",
            "urllib.request.urlopen",
            "requests.request",
        }:
            rule = "PT-SAST-008"
            index = 1 if called == "requests.request" else 0
        if rule and len(node.args) > index:
            trail = expression(node.args[index], env, rule)
            if trail:
                item = make_finding(
                    rule,
                    path,
                    node.lineno,
                    "Observed static source-to-sink flow. Runtime reachability and exploitability are unobserved.",
                    "HIGH",
                )
                item.update(
                    classification="CONFIRMED_STATIC_FINDING",
                    flow=trail + [step("SINK", node, called)],
                    flow_scope="LOCAL_HELPERS" if stack else "INTRAPROCEDURAL",
                    sanitizer_model="HTML escaping for HTML sinks; SQL separate-parameter calls excluded",
                    path_feasibility="CONSERVATIVE_POSSIBLE_PATH",
                )
                if any(part["kind"] == "UNKNOWN_PROPAGATION" for part in trail):
                    item.update(classification="SECURITY_HOTSPOT", confidence="MEDIUM")
                results[(rule, node.lineno)] = item
        if called in helpers and called not in stack and len(stack) < 3:
            helper = helpers[called]
            local = {}
            for parameter, argument in zip(helper.args.posonlyargs + helper.args.args, node.args):
                trail = expression(argument, env, "ANY")
                if trail:
                    local[parameter.arg] = trail + [step("PROPAGATION", node, called + "(" + parameter.arg + ")")]
            if local:
                block(helper.body, local, stack + [called])

    def block(statements, env, stack):
        for node in statements:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            # Inspect calls in statement expressions, excluding nested statement bodies.
            todo = [node]
            while todo:
                current = todo.pop()
                if isinstance(current, ast.Call):
                    inspect_call(current, env, stack)
                todo.extend(child for child in ast.iter_child_nodes(current) if not isinstance(child, ast.stmt))
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                trail = expression(node.value, env, "ANY")
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        env[target.id] = trail + [step("PROPAGATION", node, target.id)] if trail else []
            elif isinstance(node, ast.If):
                left, right = dict(env), dict(env)
                block(node.body, left, stack)
                block(node.orelse, right, stack)
                for key in left.keys() | right.keys():
                    env[key] = left.get(key) or right.get(key) or []
            else:
                for field in ("body", "orelse", "finalbody"):
                    nested = getattr(node, field, None)
                    if isinstance(nested, list):
                        block(nested, env, stack)
                for handler in getattr(node, "handlers", []):
                    block(handler.body, dict(env), stack)

    block(tree.body, {}, [])
    for function in helpers.values():
        block(function.body, {}, [function.name])
    return list(results.values())
