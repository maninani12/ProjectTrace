"""Structured, non-executing infrastructure inventory and ProjectTrace rules."""

import json
from pathlib import PurePosixPath

import hcl2
import yaml


class InfrastructureLoader(yaml.SafeLoader):
    pass


def intrinsic(loader, tag, node):
    # CloudFormation references are retained as symbolic data, never resolved.
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {"intrinsic": tag, "value": value}


InfrastructureLoader.add_multi_constructor("!", intrinsic)


def mapping(loader, node):
    result = yaml.SafeLoader.construct_mapping(loader, node)
    result["__line__"] = node.start_mark.line + 1
    return result


InfrastructureLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def bounded_yaml(source):
    if "{{" in source or "{%" in source:
        raise ValueError("Unrendered Helm templates are unsupported; templates are never executed")
    # Refuse aliases, recursive graphs and excessive nesting before constructing data.
    count, depth = 0, 0
    for token in yaml.scan(source):
        count += 1
        if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
            raise ValueError("YAML aliases are outside the bounded parser profile")
        depth += isinstance(
            token,
            (
                yaml.tokens.BlockMappingStartToken,
                yaml.tokens.BlockSequenceStartToken,
                yaml.tokens.FlowMappingStartToken,
                yaml.tokens.FlowSequenceStartToken,
            ),
        )
        depth -= isinstance(
            token, (yaml.tokens.BlockEndToken, yaml.tokens.FlowMappingEndToken, yaml.tokens.FlowSequenceEndToken)
        )
        if count > 40000 or depth > 64:
            raise ValueError("YAML syntax budget exceeded")
    return list(yaml.load_all(source, Loader=InfrastructureLoader))


def structured_iac(path, source, make_finding):
    findings, assets, warnings = [], [], []
    suffix = PurePosixPath(path).suffix.lower()

    def asset(identity, kind, properties, line=1, provider="STATIC"):
        result = {
            "identity": identity,
            "kind": kind,
            "provider": provider,
            "path": path,
            "line": line,
            "authority": "STATIC",
            "verification_scope": "DECLARED_CONFIGURATION",
            "public": "UNKNOWN",
            "encryption": "UNKNOWN",
            "runtime_observed": False,
            "relations": [],
            "rule_ids": [],
        }
        tags = properties.get("tags", {}) if isinstance(properties, dict) else {}
        result["environment"] = next(
            (
                str(tags[key]).lower()
                for key in ("Environment", "environment", "env")
                if isinstance(tags, dict) and isinstance(tags.get(key), str)
            ),
            "UNKNOWN",
        )
        assets.append(result)
        return result

    def report(rule, target, explanation, line=None):
        item = make_finding(rule, path, line or target["line"], explanation)
        item["resource_identity"] = target["identity"]
        item["classification"] = "SECURITY_HOTSPOT"
        findings.append(item)
        target["rule_ids"].append(rule)

    def containers(target, spec):
        if not isinstance(spec, dict):
            return
        for key in ("hostNetwork", "hostPID", "hostIPC"):
            if spec.get(key) is True:
                report("PT-IAC-006", target, f"{key} is explicitly enabled.", spec.get("__line__"))
        for volume in spec.get("volumes", []):
            if isinstance(volume, dict) and "hostPath" in volume:
                report("PT-IAC-006", target, "A hostPath volume is declared.", volume.get("__line__"))
        for container in spec.get("containers", []) + spec.get("initContainers", []):
            if not isinstance(container, dict):
                continue
            security = {**spec.get("securityContext", {}), **container.get("securityContext", {})}
            line = container.get("__line__", target["line"])
            image = container.get("image")
            if isinstance(image, str):
                target["relations"].append({"type": "USES_IMAGE", "target": image, "authority": "DECLARED"})
            if security.get("privileged") is True:
                report("PT-IAC-001", target, "Container securityContext.privileged is true.", line)
            if security.get("runAsUser") == 0:
                report("PT-IAC-002", target, "Container securityContext.runAsUser is zero.", line)
            if security.get("allowPrivilegeEscalation") is True or "ALL" in security.get("capabilities", {}).get(
                "add", []
            ):
                report("PT-IAC-007", target, "Privilege escalation or all capabilities are explicitly permitted.", line)
            if not container.get("resources", {}).get("limits"):
                report(
                    "PT-IAC-008",
                    target,
                    "This container has no declared resource limits; runtime defaults are unknown.",
                    line,
                )

    try:
        if suffix == ".tf":
            parsed = hcl2.loads(
                source, serialization_options=hcl2.SerializationOptions(strip_string_quotes=True, with_meta=True)
            )
            for block in parsed.get("resource", []):
                for kind, names in block.items():
                    if kind.startswith("__") or not isinstance(names, dict):
                        continue
                    for name, props in names.items():
                        if not isinstance(props, dict):
                            continue
                        target = asset(
                            kind + "." + name,
                            kind,
                            props,
                            props.get("__start_line__", 1),
                            "AWS"
                            if kind.startswith("aws_")
                            else "AZURE"
                            if kind.startswith("azurerm_")
                            else "GCP"
                            if kind.startswith("google_")
                            else "STATIC",
                        )
                        if props.get("acl") in {"public-read", "public-read-write"}:
                            target["public"] = "DECLARED_PUBLIC"
                            report(
                                "PT-IAC-003",
                                target,
                                "The storage ACL explicitly allows public access. Deployment is unobserved.",
                            )
                        if kind == "aws_s3_bucket_public_access_block":
                            disabled = [
                                key
                                for key in (
                                    "block_public_acls",
                                    "block_public_policy",
                                    "ignore_public_acls",
                                    "restrict_public_buckets",
                                )
                                if props.get(key) is False
                            ]
                            if disabled:
                                report("PT-IAC-009", target, "Explicitly disabled: " + ", ".join(disabled))
                        if kind in {
                            "aws_security_group",
                            "aws_security_group_rule",
                            "aws_vpc_security_group_ingress_rule",
                        }:
                            ingresses = props.get(
                                "ingress",
                                [props]
                                if props.get("type", "ingress") == "ingress" and kind != "aws_security_group"
                                else [],
                            )
                            for ingress in ingresses:
                                ranges = (
                                    ingress.get("cidr_blocks", [])
                                    + ingress.get("ipv6_cidr_blocks", [])
                                    + [ingress.get("cidr_ipv4"), ingress.get("cidr_ipv6")]
                                )
                                if any(value in {"0.0.0.0/0", "::/0"} for value in ranges):
                                    target["public"] = "DECLARED_PUBLIC"
                                    report(
                                        "PT-IAC-004",
                                        target,
                                        "Ingress admits 0.0.0.0/0 or ::/0; attachment and runtime reachability are unobserved.",
                                    )
                        policy = props.get("policy")
                        if isinstance(policy, str) and policy.startswith("${jsonencode(") and policy.endswith(")}"):
                            # Parse the literal argument as HCL data. jsonencode is
                            # never evaluated, and references remain symbolic.
                            argument = policy.removeprefix("${jsonencode(").removesuffix(")}")
                            if argument.startswith("{") and argument.endswith("}"):
                                literal = hcl2.loads(
                                    "locals { policy_object = " + argument + " }",
                                    serialization_options=hcl2.SerializationOptions(strip_string_quotes=True),
                                )
                                policy = literal["locals"][0]["policy_object"]
                        if isinstance(policy, dict):
                            check_policy(policy, target, report)
                        if isinstance(policy, str) and not policy.startswith("${"):
                            try:
                                check_policy(json.loads(policy), target, report)
                            except ValueError:
                                pass
                        if kind in {"google_storage_bucket", "azurerm_storage_container"} and props.get(
                            "container_access_type"
                        ) in {"blob", "container"}:
                            target["public"] = "DECLARED_PUBLIC"
                            report("PT-IAC-003", target, "The storage container explicitly declares anonymous access.")
        elif PurePosixPath(path).name == "Dockerfile":
            target = asset("dockerfile:" + path, "ContainerImage", {})
            for line, content in enumerate(source.splitlines(), 1):
                parts = content.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0].upper() == "USER" and parts[1].split(":")[0] in {"root", "0"}:
                    report("PT-IAC-002", target, "Dockerfile USER explicitly selects root.", line)
        elif suffix in {".yaml", ".yml", ".json"}:
            docs = [json.loads(source)] if suffix == ".json" else bounded_yaml(source)
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                if "Resources" in doc:  # CloudFormation
                    for identity, resource in doc["Resources"].items():
                        if not isinstance(resource, dict) or "Type" not in resource:
                            continue
                        props = resource.get("Properties", {})
                        target = asset(identity, resource["Type"], props, resource.get("__line__", 1), "AWS")
                        if props.get("AccessControl") in {"PublicRead", "PublicReadWrite"}:
                            target["public"] = "DECLARED_PUBLIC"
                            report("PT-IAC-003", target, "CloudFormation AccessControl permits public access.")
                        if isinstance(props.get("PolicyDocument"), dict):
                            check_policy(props["PolicyDocument"], target, report)
                        if props.get("BucketEncryption"):
                            target["encryption"] = "DECLARED_ENABLED"
                elif doc.get("kind") in {
                    "Pod",
                    "Deployment",
                    "StatefulSet",
                    "DaemonSet",
                    "Job",
                    "CronJob",
                    "Service",
                    "ServiceAccount",
                }:
                    meta, kind = doc.get("metadata", {}), doc["kind"]
                    target = asset(
                        f"{kind}/{meta.get('namespace', 'default')}/{meta.get('name', 'unnamed')}",
                        kind,
                        {},
                        doc.get("__line__", 1),
                        "KUBERNETES",
                    )
                    spec = doc.get("spec", {})
                    if kind == "Service" and spec.get("type") == "LoadBalancer":
                        # LB type alone does not prove Internet exposure.
                        target["public"] = "POTENTIAL_EXPOSURE"
                    workload = (
                        spec
                        if kind == "Pod"
                        else spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
                        if kind == "CronJob"
                        else spec.get("template", {}).get("spec", {})
                    )
                    containers(target, workload)
                    if isinstance(workload.get("serviceAccountName"), str):
                        target["relations"].append(
                            {
                                "type": "USES_IDENTITY",
                                "target": "ServiceAccount/"
                                + meta.get("namespace", "default")
                                + "/"
                                + workload["serviceAccountName"],
                                "authority": "DECLARED",
                            }
                        )
                elif isinstance(doc.get("services"), dict):
                    for name, props in doc["services"].items():
                        if not isinstance(props, dict):
                            continue
                        target = asset("compose:" + name, "ContainerWorkload", {}, props.get("__line__", 1), "COMPOSE")
                        if props.get("privileged") is True:
                            report("PT-IAC-001", target, "Compose service explicitly enables privileged mode.")
                        if str(props.get("user", "")).split(":")[0] in {"root", "0"}:
                            report("PT-IAC-002", target, "Compose service explicitly selects root.")
                        if props.get("network_mode") == "host" or props.get("pid") == "host":
                            report("PT-IAC-006", target, "Compose service shares a host namespace.")
                        for volume in props.get("volumes", []):
                            source_mount = (
                                volume.split(":")[0]
                                if isinstance(volume, str)
                                else volume.get("source", "")
                                if isinstance(volume, dict) and volume.get("type") == "bind"
                                else ""
                            )
                            if source_mount in {"/", "/proc", "/sys", "/var/run/docker.sock"}:
                                report(
                                    "PT-IAC-006",
                                    target,
                                    "A sensitive host filesystem or container control socket is mounted.",
                                )
    except Exception as error:
        # No source, templates or credential values enter diagnostics.
        warnings.append(
            {
                "analyzer": "IAC",
                "path": path,
                "code": type(error).__name__,
                "state": "PARTIAL",
                "message": "Structured infrastructure parsing failed or exceeded its supported syntax/budget; this file has partial coverage.",
            }
        )
    return findings, assets, warnings


def check_policy(policy, target, report):
    statements = policy.get("Statement", [])
    statements = [statements] if isinstance(statements, dict) else statements
    for statement in statements if isinstance(statements, list) else []:
        if not isinstance(statement, dict) or statement.get("Effect") != "Allow":
            continue
        actions, resources = statement.get("Action", []), statement.get("Resource", [])
        actions = [actions] if isinstance(actions, str) else actions
        resources = [resources] if isinstance(resources, str) else resources
        if "*" in actions or any(isinstance(action, str) and action.endswith(":*") for action in actions):
            report(
                "PT-IAC-005",
                target,
                "An Allow statement grants wildcard actions; effective permissions and escalation are unproven.",
            )
        if statement.get("Principal") == "*" and "*" in resources:
            target["public"] = "POTENTIAL_EXPOSURE" if statement.get("Condition") else "DECLARED_PUBLIC"
            report(
                "PT-IAC-004",
                target,
                "An Allow statement grants wildcard principal and resource access; policy conditions require review.",
            )
