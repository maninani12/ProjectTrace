"""Deterministic manifest inventory and implementation claims; no provider or execution."""

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath


def inventory(files):
    rows, warnings = {}, []

    def put(path, ecosystem, name, version, direct=None, license=None):
        if not isinstance(name, str) or not isinstance(version, str) or len(name) > 200 or len(version) > 100:
            return
        exact = bool(re.fullmatch(r"\d+(?:\.\d+)+(?:[.+-][\w.-]+)?", version))
        row = dict(
            name=name,
            version=version,
            ecosystem=ecosystem,
            path=path,
            direct=direct,
            version_kind="EXACT" if exact else "CONSTRAINT",
            license=license,
        )
        rows[(path, ecosystem, name, version)] = row

    def requirement(path, line):
        match = re.match(r"\s*([A-Za-z0-9_.-]+)(?:\[[^]]+\])?\s*([^;#]*)(?:[;#].*)?$", line)
        if match:
            name, constraint = match.groups()
            constraint = constraint.strip() or "unspecified"
            put(path, "PyPI", name, constraint[2:] if constraint.startswith("==") else constraint, True)

    for path, source in files.items():
        name = PurePosixPath(path).name
        try:
            if name.startswith("requirements") and name.endswith((".txt", ".lock")):
                for line in source.splitlines():
                    requirement(path, line)
            elif name == "package.json":
                manifest = json.loads(source)
                for group in ["dependencies", "devDependencies", "optionalDependencies"]:
                    for package, version in manifest.get(group, {}).items():
                        put(path, "npm", package, version, True)
            elif name == "package-lock.json":
                manifest = json.loads(source)
                root = manifest.get("packages", {}).get("", {})
                direct = {
                    **root.get("dependencies", {}),
                    **root.get("devDependencies", {}),
                    **root.get("optionalDependencies", {}),
                }
                for key, value in manifest.get("packages", {}).items():
                    if key and "node_modules/" in key and value.get("version"):
                        package = key.rsplit("node_modules/", 1)[1]
                        put(path, "npm", package, value["version"], package in direct, value.get("license"))
                if not manifest.get("packages"):
                    for package, value in manifest.get("dependencies", {}).items():
                        if value.get("version"):
                            put(path, "npm", package, value["version"], None)
            elif name in {"pyproject.toml", "poetry.lock"}:
                manifest = tomllib.loads(source)
                for line in manifest.get("project", {}).get("dependencies", []):
                    requirement(path, line)
                poetry = manifest.get("tool", {}).get("poetry", {})
                for package, version in poetry.get("dependencies", {}).items():
                    if package != "python":
                        put(
                            path,
                            "PyPI",
                            package,
                            version if isinstance(version, str) else version.get("version", "unspecified"),
                            True,
                        )
                for package in manifest.get("package", []):
                    put(path, "PyPI", package["name"], package["version"], None)
            elif name == "pom.xml":
                if "<!DOCTYPE" in source or "<!ENTITY" in source:
                    raise ValueError("XML entity declarations are not supported")
                root = ET.fromstring(source)
                for element in root.iter():
                    if element.tag.split("}")[-1] == "dependency":
                        fields = {e.tag.split("}")[-1]: e.text for e in element}
                        if fields.get("groupId") and fields.get("artifactId"):
                            put(
                                path,
                                "Maven",
                                fields["groupId"] + ":" + fields["artifactId"],
                                fields.get("version") or "managed",
                                True,
                            )
            elif name in {"build.gradle", "build.gradle.kts"}:
                for group, artifact, version in re.findall(r"[\"']([\w.-]+):([\w.-]+):([^\"']+)[\"']", source):
                    put(path, "Maven", group + ":" + artifact, version, True)
        except ValueError, TypeError, AttributeError, KeyError, ET.ParseError:
            warnings.append(
                dict(
                    analyzer="DEPENDENCIES",
                    path=path,
                    message="Manifest could not be parsed; inventory coverage is partial.",
                )
            )
    return list(rows.values()), warnings


def context_signals(path, source):
    signals = []
    name = PurePosixPath(path).name
    if name.startswith("test_") and path.endswith(".py") or "/tests/" in "/" + path:
        signals.append(dict(type="testing", value="test files", path=path, line=1))
    if ".github/workflows/" in path and path.endswith((".yml", ".yaml")):
        signals.append(dict(type="ci", value="GitHub Actions", path=path, line=1))
    if name == "Dockerfile":
        for line_no, line in enumerate(source.splitlines(), 1):
            if re.match(r"\s*FROM\s+", line, re.I):
                signals.append(dict(type="infrastructure", value="Docker", path=path, line=line_no))
                break
    if path.endswith((".tf", ".yaml", ".yml")):
        for line_no, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for provider in re.findall(r'\bprovider\s+"(aws|azurerm|google)"', line):
                signals.append(dict(type="infrastructure", value=provider, path=path, line=line_no))
            if re.match(r"\s*kind:\s*\w+", line):
                signals.append(dict(type="infrastructure", value="Kubernetes", path=path, line=line_no))
    return signals


def implementation_claims(signals, dependencies):
    claims, seen = [], set()
    aliases = {
        "fastapi",
        "flask",
        "django",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "sqlalchemy",
        "redis",
        "kafka",
        "pytest",
        "argon2",
    }
    for signal in signals:
        kind, value = signal["type"], signal["value"]
        if kind == "import" and value.split(".")[0] not in aliases:
            continue
        key = (signal["path"], kind, value)
        if key in seen:
            continue
        seen.add(key)
        text, category, status = {
            "import": (f"Source imports {value}.", "TECHNOLOGY", "INFERRED"),
            "technology": (f"Source configures {value}.", "TECHNOLOGY", "VERIFIED"),
            "database": (f"Database configuration selects {value}.", "TECHNOLOGY", "VERIFIED"),
            "auth": (f"Source configures {value} authentication.", "AUTHENTICATION", "VERIFIED"),
            "auth_hint": (f"Source contains {value} authentication signals.", "AUTHENTICATION", "INFERRED"),
            "route": (f"Source registers {value}.", "API", "VERIFIED"),
            "infrastructure": (f"Infrastructure declares {value}.", "INFRASTRUCTURE", "VERIFIED"),
            "testing": ("Repository contains test source files.", "TESTING", "VERIFIED"),
            "ci": (f"Repository declares {value} configuration.", "CI", "VERIFIED"),
        }.get(kind, (None, None, None))
        if text:
            claims.append(
                dict(
                    text=text,
                    category=category,
                    expected=value,
                    path=signal["path"],
                    line=signal["line"],
                    origin="IMPLEMENTATION",
                    status=status,
                    reason="Current static syntax or configuration evidence supports this statement; execution is unobserved.",
                    signals=[signal],
                    severity="MEDIUM",
                    confidence="HIGH" if status == "VERIFIED" else "MEDIUM",
                    review_status="OPEN",
                )
            )
    for dependency in dependencies:
        if dependency["name"].split("[")[0].lower() not in aliases | {"react", "react-dom", "express", "leaflet"}:
            continue
        claims.append(
            dict(
                text=f"Manifest declares {dependency['name']} {dependency['version']}.",
                category="TECHNOLOGY",
                expected=dependency["name"].lower(),
                path=dependency["path"],
                line=1,
                origin="IMPLEMENTATION",
                status="INFERRED",
                reason="A dependency declaration supports availability, not runtime use.",
                signals=[],
                severity="LOW",
                confidence="MEDIUM",
                review_status="OPEN",
            )
        )
    return claims
