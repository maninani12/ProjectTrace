"""Structured, non-executing infrastructure inventory and ProjectTrace rules."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

import hcl2
import yaml

from analyzers.infrastructure_deep import checks as deep_checks
from analyzers.infrastructure_deep import config as infrastructure_config
from analyzers.infrastructure_extra import KUBERNETES_KINDS, dockerfile, enrich_document, terraform


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
    result["__end_line__"] = max(result["__line__"], node.end_mark.line + (1 if node.end_mark.column else 0))
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


def structured_iac(path, source, make_finding, settings=None):
    """Dedicated process and bounded I/O; complete OS sandbox remains unverified."""
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    try:
        if len(source.encode()) > 512000:
            raise ValueError("Input budget exceeded")
        with tempfile.TemporaryDirectory(prefix="projecttrace-iac-") as directory:
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(Path(__file__).with_name("iac_worker.py"))],
                input=json.dumps({"path": path, "source": source, "settings": settings or {}}).encode(),
                capture_output=True,
                timeout=15,
                cwd=directory,
                env=environment,
            )
        if result.returncode or len(result.stdout) > 8 * 1024 * 1024:
            raise ValueError("Parser process failed or exceeded its output budget")
        findings, assets, warnings = json.loads(result.stdout)
        return (
            [{**make_finding(item["rule"], path, item["line"], item["explanation"]), **item} for item in findings],
            assets,
            warnings,
        )
    except Exception as error:
        return (
            [],
            [],
            [
                {
                    "analyzer": "IAC",
                    "path": path,
                    "code": type(error).__name__,
                    "state": "PARTIAL",
                    "message": "Isolated infrastructure parser failed or exceeded its budget; this file is not fully analyzed.",
                }
            ],
        )


def _structured_iac(path, source, make_finding, settings=None):
    findings, assets, warnings = [], [], []
    settings = infrastructure_config(settings)
    suffix = PurePosixPath(path).suffix.lower()

    def asset(identity, kind, properties, line=1, provider="STATIC"):
        def canonical(value):
            if isinstance(value, dict):
                return {
                    k: canonical(v) for k, v in value.items() if k not in {"__line__", "__start_line__", "__end_line__"}
                }
            if isinstance(value, list):
                return [canonical(v) for v in value]
            return value

        result = {
            "identity": identity,
            "kind": kind,
            "provider": provider,
            "path": path,
            "line": line,
            "end_line": line,
            "format": "TERRAFORM"
            if path.endswith((".tf", ".tf.json"))
            else "DOCKERFILE"
            if PurePosixPath(path).name.startswith("Dockerfile")
            else "CLOUDFORMATION"
            if provider == "AWS"
            else provider,
            "authority": "STATIC",
            "verification_scope": "DECLARED_CONFIGURATION",
            "public": "UNKNOWN",
            "encryption": "UNKNOWN",
            "runtime_observed": False,
            "relations": [],
            "rule_ids": [],
            "resource_context_hash": hashlib.sha256(
                json.dumps(canonical(properties), sort_keys=True).encode()
            ).hexdigest(),
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
        item["resource_context_hash"] = target["resource_context_hash"]
        item["classification"] = "SECURITY_HOTSPOT"
        item["infrastructure_format"] = target["format"]
        item["authority"] = "STATIC"
        item["verification_scope"] = "DECLARED_CONFIGURATION"
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
        if suffix == ".tf" or path.endswith(".tf.json"):
            if path.endswith(".tf.json"):
                document = json.loads(source)
                parsed = {
                    key: [{name: value} for name, value in values.items()]
                    for key, values in document.items()
                    if isinstance(values, dict)
                }
            else:
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
            terraform(parsed, assets, asset, report, warnings, path)
        elif PurePosixPath(path).name.startswith("Dockerfile"):
            dockerfile(path, source, asset, report)
            final = next(a for a in assets if a.get("final_stage"))
            if settings["require_healthcheck"] and not any(
                i["opcode"] == "HEALTHCHECK" for i in final.get("instructions", [])
            ):
                report("PT-IAC-030", final, "The configured final-image healthcheck requirement is not declared.")
            from analyzers.finding_identity import digest

            normalized = []
            for a in assets:
                for instruction in a.get("instructions", []):
                    first, last = instruction["line"], instruction["end_line"]
                    normalized.append(
                        (
                            a["stage"],
                            instruction["opcode"],
                            " ".join(s.strip() for s in source.splitlines()[first - 1 : last]),
                        )
                    )
            for item in findings:
                item.update(
                    structural_key=digest(
                        [item["rule"], item["resource_identity"].replace(path, "<file>"), item["explanation"]]
                    ),
                    structural_context_hash=digest(normalized),
                    file_structure_hash=digest(normalized),
                    identity_version="structural-v2",
                    identity_confidence="HIGH",
                    identity_method="DOCKER_INSTRUCTIONS",
                )
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
                elif doc.get("kind") in KUBERNETES_KINDS:
                    meta, kind = doc.get("metadata", {}), doc["kind"]
                    target = asset(
                        f"{kind}/{meta.get('namespace', 'default')}/{meta.get('name', 'unnamed')}",
                        kind,
                        doc,
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
                        target = asset(
                            "compose:" + name, "ContainerWorkload", props, props.get("__line__", 1), "COMPOSE"
                        )
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
                enrich_document(doc, assets, asset, report, path)
                deep_checks(doc, assets, asset, report, path, settings)
                if doc.get("Transform") or any(
                    isinstance(r, dict) and r.get("Type") == "AWS::CloudFormation::Stack"
                    for r in doc.get("Resources", {}).values()
                ):
                    warnings.append(
                        {
                            "analyzer": "IAC",
                            "path": path,
                            "code": "TRANSFORM_UNRESOLVED" if doc.get("Transform") else "EXTERNAL_TEMPLATE_UNRESOLVED",
                            "state": "PARTIAL",
                            "message": "CloudFormation transforms/nested stacks are retained as declarations; expansion or remote template fetching is not performed.",
                        }
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
        if "*" in resources:
            report(
                "PT-IAC-022",
                target,
                "An Allow statement uses wildcard resources; whether individual actions support narrower scope requires review.",
            )
        if statement.get("Principal") == "*" and "*" in resources:
            target["public"] = "POTENTIAL_EXPOSURE" if statement.get("Condition") else "DECLARED_PUBLIC"
            report(
                "PT-IAC-004",
                target,
                "An Allow statement grants wildcard principal and resource access; policy conditions require review.",
            )
