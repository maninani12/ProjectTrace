"""Static infrastructure semantics; expressions and commands are never evaluated."""

import re

from analyzers.infrastructure_deep import RULES as DEEP_RULES

RULES = {
    "PT-IAC-010": (
        "IAC",
        "LOW",
        "Container image is not digest pinned",
        "Pin the reviewed image digest; verify provenance separately.",
        None,
    ),
    "PT-IAC-011": (
        "IAC",
        "MEDIUM",
        "Read-only root filesystem is not declared",
        "Declare a read-only root filesystem and explicit writable mounts.",
        "CWE-732",
    ),
    "PT-IAC-012": (
        "IAC",
        "MEDIUM",
        "Broad Kubernetes RBAC permissions",
        "Limit verbs, resources and subjects to the required workload.",
        "CWE-250",
    ),
    "PT-IAC-013": (
        "IAC",
        "LOW",
        "Automatic service account token enabled",
        "Disable automountServiceAccountToken when API access is unnecessary.",
        None,
    ),
    "PT-IAC-014": (
        "IAC",
        "MEDIUM",
        "Ingress TLS configuration missing",
        "Declare TLS termination; validate runtime routing separately.",
        "CWE-319",
    ),
    "PT-IAC-015": (
        "IAC",
        "MEDIUM",
        "Dockerfile downloads executable material",
        "Verify content digests and avoid piping network responses into a shell.",
        "CWE-494",
    ),
    "PT-IAC-016": (
        "IAC",
        "MEDIUM",
        "Dockerfile secret-bearing declaration",
        "Use ephemeral build secret mounts rather than ARG/ENV or secret files.",
        "CWE-798",
    ),
    "PT-IAC-017": (
        "IAC",
        "MEDIUM",
        "Final Dockerfile user is undeclared",
        "Declare a non-root final user; base-image defaults are unobserved.",
        "CWE-250",
    ),
    "PT-IAC-018": (
        "IAC",
        "HIGH",
        "Public database access declared",
        "Disable public database access and restrict network attachments.",
        "CWE-284",
    ),
    "PT-IAC-019": (
        "IAC",
        "MEDIUM",
        "Storage encryption explicitly disabled",
        "Enable encryption and review deployed key policy separately.",
        "CWE-311",
    ),
    "PT-IAC-020": (
        "IAC",
        "MEDIUM",
        "Container seccomp is explicitly unconfined",
        "Use a runtime-default or reviewed seccomp profile.",
        "CWE-250",
    ),
}
RULES.update(DEEP_RULES)

KUBERNETES_KINDS = {
    "Pod",
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "ReplicationController",
    "Job",
    "CronJob",
    "Service",
    "Ingress",
    "ServiceAccount",
    "Role",
    "ClusterRole",
    "RoleBinding",
    "ClusterRoleBinding",
    "NetworkPolicy",
    "ConfigMap",
    "Secret",
    "PersistentVolume",
    "PersistentVolumeClaim",
}


def dockerfile(path, source, asset, report):
    """Bounded instruction parser with continuations, stage inheritance and ranges."""
    instructions, buffer, start = [], "", 0
    escape = "`" if re.search(r"(?im)^#\s*escape\s*=\s*`\s*$", source) else "\\"
    for line, raw in enumerate(source.splitlines(), 1):
        if not buffer and (not raw.strip() or raw.lstrip().startswith("#")):
            continue
        if not buffer:
            start = line
        piece = raw.rstrip()
        continuation = piece.endswith(escape)
        buffer += (piece[:-1] if continuation else piece) + (" " if continuation else "")
        if continuation:
            continue
        parts = buffer.strip().split(maxsplit=1)
        opcode, operand = parts[0].upper(), parts[1] if len(parts) == 2 else ""
        if opcode not in {
            "FROM",
            "ARG",
            "ENV",
            "USER",
            "RUN",
            "COPY",
            "ADD",
            "EXPOSE",
            "HEALTHCHECK",
            "WORKDIR",
            "ENTRYPOINT",
            "CMD",
            "LABEL",
            "SHELL",
            "VOLUME",
            "STOPSIGNAL",
            "ONBUILD",
            "MAINTAINER",
        }:
            raise ValueError("Unsupported Dockerfile instruction")
        if "<<" in operand:
            raise ValueError("Dockerfile heredoc has partial coverage")
        instructions.append((opcode, operand, start, line))
        buffer = ""
    if buffer:
        raise ValueError("Incomplete Dockerfile continuation")
    stages, names, current = [], {}, None
    for opcode, operand, first, last in instructions:
        if opcode == "FROM":
            parts = operand.split()
            parts = [p for p in parts if not p.startswith("--platform=")]
            if not parts:
                raise ValueError("FROM image missing")
            image = parts[0]
            name = parts[2] if len(parts) == 3 and parts[1].upper() == "AS" else str(len(stages))
            inherited = names.get(image)
            current = asset(f"dockerfile:{path}:stage:{len(stages)}", "ContainerImage", {}, first)
            current.update(
                format="DOCKERFILE",
                stage=name,
                final_stage=False,
                end_line=last,
                effective_user=inherited.get("effective_user") if inherited else None,
                effective_user_line=inherited.get("effective_user_line") if inherited else None,
                instructions=[],
            )
            current["relations"].append(
                {
                    "type": "BASED_ON",
                    "target": inherited["identity"] if inherited else image,
                    "target_path": path if inherited else None,
                    "authority": "DECLARED",
                }
            )
            names[name] = current
            names[str(len(stages))] = current
            stages.append(current)
            if image != "scratch" and not inherited and "@sha256:" not in image:
                report(
                    "PT-IAC-010",
                    current,
                    "The base image is not pinned by digest; its contents and vulnerabilities are unobserved.",
                    first,
                )
        elif opcode == "ARG" and current is None:
            continue  # Global build arguments are symbolic, not evaluated.
        elif current is None:
            raise ValueError("Instruction before FROM")
        if current is None:
            continue
        current["end_line"] = last
        current["instructions"].append({"opcode": opcode, "line": first, "end_line": last})
        if opcode == "USER":
            current["effective_user"] = "SYMBOLIC" if "$" in operand else operand.split(":")[0]
            current["effective_user_line"] = first
        if opcode in {"ARG", "ENV"} and re.search(
            r"(?i)(?:^|\s)(?:\w*password\w*|\w*secret\w*|\w*token\w*|\w*private_key\w*)\s*(?:=|\s)", operand
        ):
            report(
                "PT-IAC-016",
                current,
                "A credential-named ARG/ENV declaration is present; values are not persisted as resource metadata.",
                first,
            )
        if opcode == "COPY":
            match = re.search(r"--from=(\S+)", operand)
            if match and match[1] in names:
                current["relations"].append(
                    {
                        "type": "COPIES_FROM",
                        "target": names[match[1]]["identity"],
                        "target_path": path,
                        "authority": "DECLARED",
                    }
                )
            if re.search(r"(?i)(?:^|\s)(?:\S*/)?(?:\.env(?:\.\w+)?|id_rsa|\S*\.pem)(?:\s|$)", operand):
                report(
                    "PT-IAC-016",
                    current,
                    "COPY explicitly names a potential secret file; file contents are not evaluated.",
                    first,
                )
        if (
            opcode == "ADD"
            and re.search(r"https?://|git@", operand)
            or opcode == "RUN"
            and re.search(r"(?i)\b(curl|wget)\b.*\|\s*(?:bash|sh)\b", operand)
        ):
            report(
                "PT-IAC-015",
                current,
                "Remote ADD or a download-to-shell pipeline is declared; the command is never executed.",
                first,
            )
        if opcode == "RUN" and re.search(r"\bchmod\s+(?:-[A-Za-z]+\s+)?(?:0?777|a\+rwx)\b", operand):
            report(
                "PT-IAC-029",
                current,
                "The instruction declares world-writable file permissions; commands are not executed.",
                first,
            )
    if not stages:
        raise ValueError("Dockerfile has no FROM")
    stages[-1]["final_stage"] = True
    final = stages[-1]
    if final["effective_user"] in {"root", "0"}:
        report(
            "PT-IAC-002",
            final,
            "The final stage explicitly selects root; intermediate build users do not determine the final user.",
            final["effective_user_line"],
        )
    elif final["effective_user"] is None:
        report("PT-IAC-017", final, "No USER is declared for the final stage; the base image default is unknown.")


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not key.startswith("__"):
                yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)
    elif isinstance(value, str):
        yield value


def terraform(parsed, assets, asset, report, warnings, path):
    current = [a for a in assets if a["path"] == path]
    for category in ("variable", "locals", "output", "module", "data", "provider"):
        for block in parsed.get(category, []):
            for name, properties in block.items():
                if name.startswith("__"):
                    continue
                target = asset(
                    f"{category}.{name}",
                    f"Terraform{category.title()}",
                    properties,
                    properties.get("__start_line__", 1) if isinstance(properties, dict) else 1,
                )
                target["format"] = "TERRAFORM"
                target["symbolic"] = True
                target["declaration_category"] = category
                if category == "provider" and isinstance(properties, dict) and isinstance(properties.get("alias"), str):
                    target["provider_alias"] = properties["alias"]
                if category == "module":
                    source = properties.get("source", "") if isinstance(properties, dict) else ""
                    target["module_resolution"] = (
                        "LOCAL_DECLARATION_NOT_EXPANDED"
                        if isinstance(source, str) and source.startswith(("./", "../"))
                        else "REMOTE_UNRESOLVED"
                    )
                    if isinstance(source, str) and source.startswith(("./", "../")) and len(source) <= 240:
                        target["local_module_source"] = source
                    warnings.append(
                        {
                            "analyzer": "IAC",
                            "path": path,
                            "code": "LOCAL_MODULE_SYMBOLIC"
                            if target.get("local_module_source")
                            else "EXTERNAL_MODULE_UNRESOLVED",
                            "state": "PARTIAL",
                            "message": "Terraform module declaration retained; module evaluation/fetching is disabled.",
                        }
                    )
    targets = {a["identity"]: a for a in current}
    for block in parsed.get("resource", []):
        for kind, names in block.items():
            if not isinstance(names, dict):
                continue
            for name, props in names.items():
                target = targets.get(kind + "." + name)
                if not target or not isinstance(props, dict):
                    continue
                target.update(
                    format="TERRAFORM",
                    end_line=props.get("__end_line__", target["line"]),
                    instance_expansion="SYMBOLIC" if "count" in props or "for_each" in props else "SINGLE_DECLARATION",
                )
                if (
                    props.get("publicly_accessible") is True
                    or kind == "azurerm_mssql_server"
                    and props.get("public_network_access_enabled") is True
                ):
                    target["public"] = "DECLARED_PUBLIC"
                    report(
                        "PT-IAC-018",
                        target,
                        "Public database/network access is explicitly enabled; deployment is unobserved.",
                    )
                if props.get("storage_encrypted") is False:
                    target["encryption"] = "DECLARED_DISABLED"
                    report("PT-IAC-019", target, "Storage encryption is explicitly disabled.")
                elif props.get("storage_encrypted") is True:
                    target["encryption"] = "DECLARED_ENABLED"
                if kind in {"aws_lb", "aws_alb", "aws_elb"} and props.get("internal") is False:
                    target["public"] = "DECLARED_PUBLIC"
                    report(
                        "PT-IAC-023",
                        target,
                        "The load balancer explicitly sets internal=false; runtime attachments are unobserved.",
                    )
                if (
                    kind == "azurerm_storage_account"
                    and props.get("allow_nested_items_to_be_public") is True
                    or kind == "google_storage_bucket"
                    and props.get("public_access_prevention") == "inherited"
                ):
                    report(
                        "PT-IAC-009",
                        target,
                        "Restrictive public-access prevention is not enforced by this explicit declaration; inherited policy is unobserved.",
                    )
                for expression in walk(props):
                    for ref in re.findall(r"(?<![\w.])((?:aws_|azurerm_|google_)[\w]+\.[\w-]+)\.[\w]+", expression):
                        relation = {
                            "type": "REFERENCES",
                            "target": ref,
                            "authority": "DECLARED",
                            "resolution": "SYMBOLIC",
                        }
                        if relation not in target["relations"]:
                            target["relations"].append(relation)
                    for ref in re.findall(r"(?<![\w.])((?:var|local|module)\.[\w-]+)", expression):
                        target["relations"].append(
                            {
                                "type": "REFERENCES",
                                "target": ref.replace("var.", "variable.").replace("local.", "locals."),
                                "authority": "DECLARED",
                                "resolution": "SYMBOLIC",
                            }
                        )


def enrich_document(doc, assets, asset, report, path):
    if not isinstance(doc, dict):
        return
    if "Resources" in doc:
        targets = {a["identity"]: a for a in assets if a["path"] == path}
        for identity, resource in doc.get("Resources", {}).items():
            target = targets.get(identity)
            if not target or not isinstance(resource, dict):
                continue
            props = resource.get("Properties", {})
            target.update(
                format="CLOUDFORMATION",
                condition="SYMBOLIC" if resource.get("Condition") else "UNCONDITIONAL",
                end_line=resource.get("__end_line__", target["line"]),
            )
            if props.get("PubliclyAccessible") is True:
                target["public"] = "DECLARED_PUBLIC"
                report(
                    "PT-IAC-018",
                    target,
                    "CloudFormation PubliclyAccessible is true; effective reachability is unobserved.",
                )
            if props.get("StorageEncrypted") is False:
                target["encryption"] = "DECLARED_DISABLED"
                report("PT-IAC-019", target, "CloudFormation StorageEncrypted is explicitly false.")
            for reference in cfn_references(props):
                target["relations"].append(
                    {
                        "type": "REFERENCES",
                        "target": reference,
                        "target_path": path,
                        "authority": "DECLARED",
                        "resolution": "SYMBOLIC",
                    }
                )
        return
    kind, meta = doc.get("kind"), doc.get("metadata", {})
    if kind in KUBERNETES_KINDS:
        namespace = meta.get("namespace", "default")
        identity = f"{kind}/{namespace}/{meta.get('name', 'unnamed')}"
        target = next((a for a in assets if a["identity"] == identity and a["path"] == path), None)
        target = target or asset(identity, kind, doc, doc.get("__line__", 1), "KUBERNETES")
        target.update(format="KUBERNETES", namespace=namespace, end_line=doc.get("__end_line__", target["line"]))
        spec = doc.get("spec", {})
        if kind in {"Secret", "ConfigMap"}:
            target["data_values_retained"] = False
            target["entry_count"] = sum(
                len(v) for k in ("data", "stringData", "binaryData") if isinstance((v := doc.get(k)), dict)
            )
        if kind in {"Role", "ClusterRole"}:
            for rule in doc.get("rules", []):
                if isinstance(rule, dict) and any(
                    "*" in rule.get(key, []) for key in ("verbs", "resources", "apiGroups")
                ):
                    report(
                        "PT-IAC-012",
                        target,
                        "RBAC uses a wildcard verb/resource/API group; effective permissions require binding review.",
                        rule.get("__line__"),
                    )
        if kind in {"RoleBinding", "ClusterRoleBinding"}:
            ref = doc.get("roleRef", {})
            if ref.get("name") and ref.get("kind") in {"Role", "ClusterRole"}:
                target["relations"].append(
                    {
                        "type": "BINDS_ROLE",
                        "target": f"{ref['kind']}/{namespace if ref['kind'] == 'Role' else 'default'}/{ref['name']}",
                        "authority": "DECLARED",
                    }
                )
            for subject in doc.get("subjects", []):
                if isinstance(subject, dict) and subject.get("kind") == "ServiceAccount" and subject.get("name"):
                    target["relations"].append(
                        {
                            "type": "BINDS_IDENTITY",
                            "target": f"ServiceAccount/{subject.get('namespace', namespace)}/{subject['name']}",
                            "authority": "DECLARED",
                        }
                    )
        if kind == "Ingress" and not spec.get("tls"):
            report("PT-IAC-014", target, "Ingress has no declared TLS block; upstream termination is unknown.")
        if kind == "ServiceAccount" and doc.get("automountServiceAccountToken") is True:
            report("PT-IAC-013", target, "The service account explicitly enables automatic API token mounting.")
        workload = (
            spec
            if kind == "Pod"
            else spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
            if kind == "CronJob"
            else spec.get("template", {}).get("spec", {})
        )
        for container in workload.get("containers", []) + workload.get("initContainers", []):
            if not isinstance(container, dict):
                continue
            image = container.get("image", "")
            security = {**workload.get("securityContext", {}), **container.get("securityContext", {})}
            line = container.get("__line__", target["line"])
            if isinstance(image, str) and image and "@sha256:" not in image:
                report(
                    "PT-IAC-010",
                    target,
                    "Container image is not digest pinned; no image vulnerability assertion is made.",
                    line,
                )
            if security.get("readOnlyRootFilesystem") is not True:
                report(
                    "PT-IAC-011",
                    target,
                    "readOnlyRootFilesystem is not explicitly true; admission defaults are unknown.",
                    line,
                )
            if security.get("seccompProfile", {}).get("type") == "Unconfined":
                report("PT-IAC-020", target, "The container explicitly declares an unconfined seccomp profile.", line)
        return
    if isinstance(doc.get("services"), dict):
        for name, props in doc["services"].items():
            if not isinstance(props, dict):
                continue
            target = next((a for a in assets if a["identity"] == "compose:" + name and a["path"] == path), None)
            if target is None:
                continue
            target.update(format="COMPOSE", end_line=props.get("__end_line__", target["line"]))
            image = props.get("image")
            if isinstance(image, str):
                target["relations"].append({"type": "USES_IMAGE", "target": image, "authority": "DECLARED"})
                if "@sha256:" not in image:
                    report(
                        "PT-IAC-010", target, "Compose image is not digest pinned; resolved image contents are unknown."
                    )
            if props.get("read_only") is not True:
                report("PT-IAC-011", target, "Compose read_only is not explicitly true.")
            if "ALL" in props.get("cap_add", []):
                report("PT-IAC-007", target, "Compose explicitly adds all Linux capabilities.")
            for dependency in props.get("depends_on", []):
                if dependency != "__line__" and dependency != "__end_line__":
                    target["relations"].append(
                        {
                            "type": "DEPENDS_ON",
                            "target": "compose:" + dependency,
                            "target_path": path,
                            "authority": "DECLARED",
                        }
                    )


def cfn_references(value):
    if isinstance(value, dict):
        if isinstance(value.get("Ref"), str):
            yield value["Ref"]
        if value.get("intrinsic") in {"Ref", "GetAtt"}:
            raw = value.get("value")
            if isinstance(raw, str):
                yield raw.split(".")[0]
            elif isinstance(raw, list) and raw and isinstance(raw[0], str):
                yield raw[0]
        getatt = value.get("Fn::GetAtt")
        if isinstance(getatt, str):
            yield getatt.split(".")[0]
        elif isinstance(getatt, list) and getatt and isinstance(getatt[0], str):
            yield getatt[0]
        for item in value.values():
            yield from cfn_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from cfn_references(item)
