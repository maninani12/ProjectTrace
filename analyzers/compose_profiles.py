"""Bounded evidence for a documented, single-profile root Compose command."""

import re
from graphlib import CycleError, TopologicalSorter

PROFILE_FILE = "docker-compose.yml"
PROFILE_README = "README.md"
PROFILE_CONTEXT = "ROOT_COMPOSE_PROFILE"
PROFILE_FAMILY = "compose_profile_selection"
PROFILE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
COMMAND = re.compile(rf"^ {{0,3}}`(docker compose --profile ({PROFILE_PATTERN}) up)`(?=$|[.\s])")
COMPETING_PATHS = {
    ".env",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "compose.override.yml",
    "compose.override.yaml",
    "docker-compose.override.yml",
    "docker-compose.override.yaml",
}
POSITIONS = {"__line__", "__end_line__"}


def documented_profile(path, lines, line):
    if path == PROFILE_README and 2 <= line <= len(lines):
        previous, current = lines[line - 2 : line]
        if f"`{PROFILE_FILE}`" not in previous or "<!--" in previous or "-->" in previous:
            return None
        match = COMMAND.match(current)
        if match:
            command, name = match.groups()
            return (command, "INFRASTRUCTURE", name)
    return None


def required_services(value):
    if isinstance(value, list):
        names = value
    elif getattr(value, "plain", False):
        names = [name for name in value if name not in POSITIONS]
        for name in names:
            condition = value[name]
            if (
                not getattr(condition, "plain", False)
                or condition.get("condition")
                not in ("service_started", "service_healthy", "service_completed_successfully")
                or condition.get("required", True) is not True
            ):
                return None
    else:
        return None
    if all(isinstance(n, str) and NAME.fullmatch(n) for n in names) and len(set(names)) == len(names):
        return set(names)
    return None


def profile_anchors(services):
    """Compute the active service set and retain one real source anchor per profile."""
    if not services or len(services) > 64 + len(POSITIONS):
        return {}
    definitions, anchors = {}, {}
    for name, service in services.items():
        if name in POSITIONS:
            continue
        if (
            not isinstance(name, str)
            or not NAME.fullmatch(name)
            or not getattr(service, "plain", False)
            or not (service.get("image") or service.get("build"))
            or {"extends", "links", "volumes_from", "network_mode", "ipc", "pid"} & service.keys()
        ):
            return {}
        profiles = service.get("profiles", [])
        dependencies = required_services(service.get("depends_on", []))
        if (
            not isinstance(profiles, list)
            or dependencies is None
            or not all(isinstance(p, str) and re.fullmatch(PROFILE_PATTERN, p) for p in profiles)
            or len(set(profiles)) != len(profiles)
        ):
            return {}
        definitions[name] = (profiles, dependencies)
        for profile in profiles:
            anchors.setdefault(profile, name)
        if len(anchors) > 16:
            return {}
    result = {}
    for profile, anchor in anchors.items():
        active = {name: deps for name, (profiles, deps) in definitions.items() if not profiles or profile in profiles}
        if any(deps - active.keys() for deps in active.values()):
            continue
        try:
            tuple(TopologicalSorter(active).static_order())
        except CycleError:
            continue
        result.setdefault(anchor, {})[profile] = sorted(active)
    return result


def profile_signals(assets, inventory):
    """Withhold support when the implicit root file selection is ambiguous."""
    entries = getattr(inventory, "entries", inventory)
    paths = set(entries)
    paths.update(row["path"] for row in getattr(inventory, "intake", ()))
    blocked = COMPETING_PATHS | {PROFILE_FILE}
    if PROFILE_FILE not in inventory or any(path != PROFILE_FILE and path.casefold() in blocked for path in paths):
        return {}
    return {
        profile: [{"type": PROFILE_FAMILY, "value": ", ".join(services), "path": PROFILE_FILE, "line": a["line"]}]
        for a in assets
        if a.get("path") == PROFILE_FILE and a.get("provider") == "COMPOSE"
        for profile, services in a.get("profile_selections", {}).items()
        if re.fullmatch(PROFILE_PATTERN, profile)
        and isinstance(services, list)
        and services
        and all(isinstance(name, str) and NAME.fullmatch(name) for name in services)
    }
