"""Static evidence for the two documented local RDF Compose selections."""

import re

GUIDE = "docs/rdf-local-development.md"
BASE = "docker/development/docker-compose-postgres.yml"
DEFAULT_BASE = "docker/development/docker-compose.yml"
OVERLAY = "docker/development/docker-compose-fuseki.yml"
OPTION_PREFIX = "If your local backend uses PostgreSQL,"
OPTION = OPTION_PREFIX + " swap `docker-compose.yml` for `docker-compose-postgres.yml`."
CONTEXT = "RDF_COMPOSE_POSTGRES_OPTION"
COMMAND = f"docker compose -f {DEFAULT_BASE} -f {OVERLAY} up -d fuseki"
STANDALONE = "RDF_COMPOSE_FUSEKI_STANDALONE"
LAYERED = "RDF_COMPOSE_FUSEKI_LAYERED"
FUSEKI_STANDALONE = "Start the Fuseki triple store using Docker Compose:"
FUSEKI_LAYERED = (
    "If you want to run the OpenMetadata server directly from IntelliJ while keeping Fuseki in Docker, "
    "start Fuseki separately:"
)
STANDALONE_COMMAND = f"docker compose -f {OVERLAY} up -d"
SOURCE_PATHS = {BASE, DEFAULT_BASE, OVERLAY}
BACKEND_SERVICES = ("openmetadata-server", "execute-migrate-all")
DB_DEFAULTS = {"DB_DRIVER_CLASS": "org.postgresql.Driver", "DB_SCHEME": "postgresql", "DB_HOST": "postgresql"}
RDF_DEFAULTS = {
    "RDF_ENABLED": "true",
    "RDF_STORAGE_TYPE": "FUSEKI",
    "RDF_ENDPOINT": "http://fuseki:3030/openmetadata",
}


def documentation_context(lines, line):
    if line >= 5 and lines[line - 5 : line] == ["```bash", COMMAND, "```", "", OPTION]:
        return CONTEXT
    if lines[line - 1 : line + 4] == [FUSEKI_LAYERED, "", "```bash", COMMAND, "```"]:
        return LAYERED
    if lines[line - 1 : line + 5] == [
        FUSEKI_STANDALONE,
        "",
        "```bash",
        "cd /path/to/OpenMetadata",
        STANDALONE_COMMAND,
        "```",
    ]:
        return STANDALONE
    return None


CONTEXT_CLAIMS = {
    CONTEXT: (OPTION, "TECHNOLOGY", "postgresql"),
    STANDALONE: (FUSEKI_STANDALONE, "INFRASTRUCTURE", "fuseki"),
    LAYERED: (FUSEKI_LAYERED, "INFRASTRUCTURE", "fuseki"),
}


def declared_defaults(service, expected):
    environment = service.get("environment")
    return getattr(environment, "plain", False) and all(
        environment.get(key) in (value, "${" + key + ":-" + value + "}") for key, value in expected.items()
    )


def depends_on(service, name):
    dependencies = service.get("depends_on")
    if not getattr(dependencies, "plain", False):
        return False
    dependency = dependencies.get(name)
    return (
        getattr(dependency, "plain", False)
        and dependency.get("condition") == "service_healthy"
        and dependency.get("required", True) is True
    )


def compose_services(documents):
    if len(documents) != 1:
        return None
    document = documents[0]
    if not getattr(document, "plain", False) or "include" in document:
        return None
    services = document.get("services")
    if getattr(services, "plain", False):
        return services
    return None


def plain_service(service):
    return getattr(service, "plain", False) and not {"profiles", "extends", "env_file"} & service.keys()


def fuseki_image(service):
    image = service.get("image")
    return isinstance(image, str) and re.fullmatch(r"stain/jena-fuseki:[0-9]+\.[0-9]+\.[0-9]+", image)


def fuseki_overlay(services):
    return all(
        plain_service(service := services.get(name))
        and declared_defaults(service, RDF_DEFAULTS)
        and depends_on(service, "fuseki")
        and not DB_DEFAULTS.keys() & service["environment"].keys()
        for name in BACKEND_SERVICES
    )


def option_service(path, services):
    """PostgreSQL configuration markers for the existing conditional declaration."""
    if not services:
        return None
    selected = "postgresql" if path == BASE else "fuseki"
    other = "fuseki" if path == BASE else "postgresql"
    if other in services or any(not plain_service(services.get(name)) for name in (*BACKEND_SERVICES, selected)):
        return None
    service = services[selected]
    if path == BASE:
        build = service.get("build")
        if (
            getattr(build, "plain", False)
            and build.get("context") == "../../."
            and build.get("dockerfile") == "docker/postgresql/Dockerfile_postgres"
            and "image" not in service
            and all(
                declared_defaults(services[n], DB_DEFAULTS) and depends_on(services[n], selected)
                for n in BACKEND_SERVICES
            )
        ):
            return "openmetadata-server"
    else:
        if fuseki_image(service) and not {"build", "depends_on"} & service.keys() and fuseki_overlay(services):
            return "fuseki"
    return None


def fuseki_startup(path, services):
    if not services:
        return None
    if path == DEFAULT_BASE:
        if "fuseki" not in services and all(
            plain_service(service := services.get(name))
            and getattr(build := service.get("build"), "plain", False)
            and build.get("context") == "../../."
            and build.get("dockerfile") == "docker/development/Dockerfile"
            and "image" not in service
            for name in BACKEND_SERVICES
        ):
            return LAYERED
    if path == OVERLAY:
        service = services.get("fuseki")
        if not plain_service(service) or not fuseki_image(service):
            return None
        if {"build", "depends_on", "links", "volumes_from", "network_mode", "ipc", "pid"} & service.keys():
            return None
        environment = service.get("environment")
        if service.get("ports") != ["3030:3030"] or not isinstance(environment, list):
            return None
        if [
            entry
            for entry in environment
            if isinstance(entry, str) and (entry == "FUSEKI_BASE" or entry.startswith("FUSEKI_BASE="))
        ] != ["FUSEKI_BASE=/fuseki"]:
            return None
        if set(services) == {"__line__", "__end_line__", "fuseki"}:
            return STANDALONE
        if fuseki_overlay(services):
            return LAYERED
    return None


def option_signals(assets, files, context):
    """Join only selected typed records within the current source inventory."""
    if context == CONTEXT:
        paths = {BASE: "compose:openmetadata-server", OVERLAY: "compose:fuseki"}
        field, value, signal_type, expected = "postgres_option", True, "compose_postgres_option", "postgresql"
    elif context in (LAYERED, STANDALONE):
        paths = {OVERLAY: "compose:fuseki"}
        if context == LAYERED:
            paths[DEFAULT_BASE] = "compose:openmetadata-server"
        field, value, signal_type, expected = "fuseki_startup", context, "compose_fuseki_startup", "fuseki"
    else:
        return []
    matches = [
        a
        for a in assets
        if a.get("path") in paths and a.get("identity") == paths[a["path"]] and a.get("provider") == "COMPOSE"
    ]
    if len(matches) != len(paths) or {a["path"] for a in matches} != paths.keys():
        return []
    if any(a["path"] not in files or a.get(field) != value for a in matches):
        return []
    return [{"type": signal_type, "value": expected, "path": a["path"], "line": a["line"]} for a in matches]
