"""Additional conservative configuration checks and local declaration links."""

import posixpath
import re
from pathlib import PurePosixPath

RULES = {
    "PT-IAC-021": (
        "IAC",
        "HIGH",
        "Broad identity trust declared",
        "Restrict trusted principals and add reviewed conditions.",
        "CWE-284",
    ),
    "PT-IAC-022": (
        "IAC",
        "MEDIUM",
        "Wildcard policy resources declared",
        "Review whether actions support narrower resource scope.",
        "CWE-732",
    ),
    "PT-IAC-023": (
        "IAC",
        "MEDIUM",
        "Internet-facing network exposure declared",
        "Restrict ingress and review deployed attachments separately.",
        "CWE-284",
    ),
    "PT-IAC-024": (
        "IAC",
        "LOW",
        "Required logging is disabled or undeclared",
        "Configure the required log destinations and retention.",
        None,
    ),
    "PT-IAC-025": (
        "IAC",
        "MEDIUM",
        "Default workload identity declared",
        "Assign a reviewed service account and disable unnecessary token mounting.",
        "CWE-250",
    ),
    "PT-IAC-026": (
        "IAC",
        "MEDIUM",
        "Required namespace network policy absent",
        "Include a restrictive NetworkPolicy and validate selectors.",
        "CWE-284",
    ),
    "PT-IAC-027": (
        "IAC",
        "MEDIUM",
        "Public Compose port binding declared",
        "Bind to an approved interface and review host/network exposure.",
        "CWE-284",
    ),
    "PT-IAC-028": (
        "IAC",
        "MEDIUM",
        "Sensitive device or host IPC access declared",
        "Remove unnecessary devices and host IPC access.",
        "CWE-250",
    ),
    "PT-IAC-029": (
        "IAC",
        "MEDIUM",
        "World-writable Dockerfile permissions declared",
        "Grant only the file permissions required by the workload.",
        "CWE-732",
    ),
    "PT-IAC-030": (
        "IAC",
        "LOW",
        "Required final-image healthcheck missing",
        "Declare a healthcheck appropriate to the running service.",
        None,
    ),
    "PT-IAC-031": (
        "IAC",
        "LOW",
        "Required resource requests undeclared",
        "Declare CPU and memory requests for workload containers.",
        None,
    ),
    "PT-IAC-032": (
        "IAC",
        "MEDIUM",
        "Container image registry outside configured policy",
        "Use an explicitly approved registry and reviewed digest.",
        "CWE-494",
    ),
}
DEFAULT = {
    "environment": "UNKNOWN",
    "require_network_policy": False,
    "require_healthcheck": False,
    "require_logging": False,
    "require_resource_requests": False,
    "allowed_image_registries": [],
    "rules": {},
}


def config(value=None):
    value = value or {}
    if not isinstance(value, dict) or value.keys() - DEFAULT.keys():
        raise ValueError("Unknown infrastructure policy field.")
    result = {**DEFAULT, **value}
    if result["environment"] not in {"UNKNOWN", "DEVELOPMENT", "TEST", "STAGING", "PRODUCTION"}:
        raise ValueError("Environment must be explicitly selected.")
    for key in ("require_network_policy", "require_healthcheck", "require_logging", "require_resource_requests"):
        if type(result[key]) is not bool:
            raise ValueError("Infrastructure requirements must be boolean.")
    registries = result["allowed_image_registries"]
    if (
        not isinstance(registries, list)
        or len(registries) > 50
        or any(not isinstance(r, str) or not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", r) for r in registries)
    ):
        raise ValueError("Use bounded image registry hostnames.")
    if not isinstance(result["rules"], dict) or len(result["rules"]) > 100:
        raise ValueError("Invalid infrastructure rule policy.")
    for rule, setting in result["rules"].items():
        if (
            rule not in {f"PT-IAC-{index:03}" for index in range(1, 33)}
            or not isinstance(setting, dict)
            or setting.keys() - {"enabled", "severity", "environments"}
        ):
            raise ValueError("Invalid infrastructure rule override.")
        if (
            "enabled" in setting
            and type(setting["enabled"]) is not bool
            or "severity" in setting
            and setting["severity"] not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
        ):
            raise ValueError("Invalid infrastructure enabled/severity setting.")
        if "environments" in setting and (
            not isinstance(setting["environments"], list)
            or any(
                e not in {"UNKNOWN", "DEVELOPMENT", "TEST", "STAGING", "PRODUCTION"} for e in setting["environments"]
            )
        ):
            raise ValueError("Invalid infrastructure environment applicability.")
    return result


def image_policy(image, target, report, settings, line=None):
    if not isinstance(image, str) or not settings["allowed_image_registries"]:
        return
    first = image.split("/")[0]
    registry = first if "." in first or ":" in first or first == "localhost" else "docker.io"
    if registry not in settings["allowed_image_registries"]:
        report(
            "PT-IAC-032",
            target,
            "The declared image registry is outside the explicitly configured allowlist; runtime image state is unobserved.",
            line,
        )


def checks(document, assets, asset, report, path, settings):
    if "Resources" in document:
        for section in ("Parameters", "Mappings", "Conditions", "Outputs"):
            for identity, declaration in document.get(section, {}).items():
                if str(identity).startswith("__"):
                    continue
                target = asset(section + "." + identity, "CloudFormation" + section, declaration, 1, "AWS")
                target.update(format="CLOUDFORMATION", symbolic=True, section=section)
        for identity, resource in document.get("Resources", {}).items():
            target = next((a for a in assets if a["identity"] == identity and a["path"] == path), None)
            if not target or not isinstance(resource, dict):
                continue
            props, kind = resource.get("Properties", {}), resource.get("Type", "")
            for ingress in props.get(
                "SecurityGroupIngress", [props] if kind == "AWS::EC2::SecurityGroupIngress" else []
            ):
                if isinstance(ingress, dict) and (
                    ingress.get("CidrIp") == "0.0.0.0/0" or ingress.get("CidrIpv6") == "::/0"
                ):
                    report(
                        "PT-IAC-023",
                        target,
                        "CloudFormation declares Internet-wide ingress; effective attachments are unobserved.",
                        ingress.get("__line__"),
                    )
                    target["public"] = "DECLARED_PUBLIC"
            if kind == "AWS::ElasticLoadBalancingV2::LoadBalancer" and props.get("Scheme") == "internet-facing":
                report("PT-IAC-023", target, "An Internet-facing load balancer is explicitly declared.")
                target["public"] = "DECLARED_PUBLIC"
            if settings["require_logging"] and kind == "AWS::EC2::FlowLog" and props.get("LogDestinationType") is None:
                report("PT-IAC-024", target, "Required flow-log destination is undeclared.")
            policy = props.get("AssumeRolePolicyDocument", {})
            statements = policy.get("Statement", []) if isinstance(policy, dict) else []
            for statement in statements if isinstance(statements, list) else [statements]:
                if (
                    isinstance(statement, dict)
                    and statement.get("Effect") == "Allow"
                    and (
                        statement.get("Principal") == "*"
                        or isinstance(statement.get("Principal"), dict)
                        and "*" in statement["Principal"].values()
                    )
                ):
                    report(
                        "PT-IAC-021",
                        target,
                        "The trust document allows a wildcard principal; conditions and effective assumption are not evaluated.",
                    )
    kind = document.get("kind")
    if kind:
        target = next(
            (
                a
                for a in assets
                if a["path"] == path and a["kind"] == kind and a.get("line") == document.get("__line__", 1)
            ),
            None,
        )
        if not target:
            return
        spec = document.get("spec", {})
        workload = (
            spec
            if kind == "Pod"
            else spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
            if kind == "CronJob"
            else spec.get("template", {}).get("spec", {})
        )
        if kind in {"RoleBinding", "ClusterRoleBinding"} and document.get("roleRef", {}).get("name") == "cluster-admin":
            report(
                "PT-IAC-012",
                target,
                "The binding explicitly names cluster-admin; installed role contents are unobserved.",
            )
        if workload.get("containers"):
            target["workload_identity"] = workload.get("serviceAccountName", "default")
            target["workload_namespace"] = document.get("metadata", {}).get("namespace", "default")
            if workload.get("serviceAccountName") in {None, "default"}:
                report(
                    "PT-IAC-025",
                    target,
                    "This workload declares or defaults to the namespace default service account; effective privileges are unobserved.",
                )
            if workload.get("automountServiceAccountToken") is True:
                report("PT-IAC-013", target, "The workload explicitly enables service-account token mounting.")
            for container in workload.get("containers", []) + workload.get("initContainers", []):
                if not isinstance(container, dict):
                    continue
                image_policy(container.get("image"), target, report, settings, container.get("__line__"))
                if settings["require_resource_requests"] and not container.get("resources", {}).get("requests"):
                    report(
                        "PT-IAC-031",
                        target,
                        "Required resource requests are undeclared; admission defaults are unknown.",
                        container.get("__line__"),
                    )
                for field in ("env", "envFrom"):
                    for entry in container.get(field, []):
                        if not isinstance(entry, dict):
                            continue
                        for reference, typ in (
                            (
                                entry.get("valueFrom", {}).get("secretKeyRef", {}) or entry.get("secretRef", {}),
                                "Secret",
                            ),
                            (
                                entry.get("valueFrom", {}).get("configMapKeyRef", {}) or entry.get("configMapRef", {}),
                                "ConfigMap",
                            ),
                        ):
                            if isinstance(reference, dict) and isinstance(reference.get("name"), str):
                                target["relations"].append(
                                    {
                                        "type": "REFERENCES",
                                        "target": f"{typ}/{target['workload_namespace']}/{reference['name']}",
                                        "authority": "DECLARED",
                                    }
                                )
    if isinstance(document.get("services"), dict):
        for name, props in document["services"].items():
            if not isinstance(props, dict):
                continue
            target = next((a for a in assets if a["identity"] == "compose:" + name and a["path"] == path), None)
            if not target:
                continue
            image_policy(props.get("image"), target, report, settings)
            if props.get("ipc") == "host" or props.get("devices"):
                report("PT-IAC-028", target, "Host IPC or device access is explicitly declared.")
            for port in props.get("ports", []):
                host = (
                    port.get("host_ip")
                    if isinstance(port, dict)
                    else str(port).split(":")[0]
                    if str(port).count(":") >= 2
                    else None
                )
                if host not in {"127.0.0.1", "::1", "[::1]"}:
                    report(
                        "PT-IAC-027",
                        target,
                        "A port is published without an explicit loopback binding; actual host/firewall reachability is unobserved.",
                    )
            for category, relation in (("networks", "ATTACHED_TO"), ("secrets", "REFERENCES")):
                for declaration in props.get(category, []):
                    identity = declaration.get("source") if isinstance(declaration, dict) else declaration
                    if isinstance(identity, str) and not identity.startswith("__"):
                        target["relations"].append(
                            {
                                "type": relation,
                                "target": f"compose:{category}:{identity}",
                                "target_path": path,
                                "authority": "DECLARED",
                            }
                        )
        for category in ("networks", "volumes", "secrets", "configs"):
            for name, declaration in document.get(category, {}).items():
                if str(name).startswith("__"):
                    continue
                target = asset(f"compose:{category}:{name}", "Compose" + category.title(), declaration, 1, "COMPOSE")
                target.update(format="COMPOSE", values_retained=False)


def link_local_declarations(files, assets, warnings, make_finding, settings):
    additions = []
    namespaces_with_network_policy = {a.get("namespace", "default") for a in assets if a["kind"] == "NetworkPolicy"}
    for target in assets:
        source = target.get("local_module_source")
        if source:
            directory = posixpath.normpath(posixpath.join(str(PurePosixPath(target["path"]).parent), source))
            included = [
                p
                for p in files
                if (directory == "." or p.startswith(directory + "/"))
                and p.endswith((".tf", ".tf.json"))
                and ".." not in PurePosixPath(directory).parts
            ]
            target["module_resolution"] = (
                "LOCAL_DECLARATIONS_LINKED_SYMBOLIC" if included else "LOCAL_MODULE_UNRESOLVED"
            )
            target["local_module_files"] = included[:100]
            for child in assets:
                if child["path"] in included and child is not target and not child.get("local_module_source"):
                    target["relations"].append(
                        {
                            "type": "REFERENCES",
                            "target": child["identity"],
                            "target_path": child["path"],
                            "authority": "DECLARED",
                            "resolution": "LOCAL_SOURCE_NOT_EVALUATED",
                        }
                    )
        if (
            settings["require_network_policy"]
            and target.get("workload_namespace")
            and target["workload_namespace"] not in namespaces_with_network_policy
        ):
            item = make_finding(
                "PT-IAC-026",
                target["path"],
                target["line"],
                "No NetworkPolicy declaration for this workload namespace exists in the captured repository scope; deployed policy is unobserved.",
            )
            item.update(
                resource_identity=target["identity"],
                resource_context_hash=target.get("resource_context_hash"),
                infrastructure_format="KUBERNETES",
                authority="STATIC",
                verification_scope="DECLARED_CONFIGURATION",
                classification="SECURITY_HOTSPOT",
            )
            additions.append(item)
    return additions
