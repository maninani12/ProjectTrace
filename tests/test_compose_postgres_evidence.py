import pytest

from analyzers.compose_evidence import BASE, COMMAND, GUIDE, OPTION, OVERLAY
from analyzers.engine import analyze
from analyzers.verifiers import extract_documentation, verify_claim
from backend import main
from backend.db import Record
from tests.test_code_quality import import_repo
from tests.test_engineering_changes import advance


def service(name, dependency, environment):
    return f"  {name}:\n    environment:\n{environment}\n    depends_on:\n      {dependency}:\n        condition: service_healthy\n"


@pytest.fixture
def sources():
    db = (
        "      DB_DRIVER_CLASS: ${DB_DRIVER_CLASS:-org.postgresql.Driver}\n"
        "      DB_SCHEME: ${DB_SCHEME:-postgresql}\n"
        "      DB_HOST: ${DB_HOST:-postgresql}"
    )
    rdf = (
        "      RDF_ENABLED: ${RDF_ENABLED:-true}\n"
        "      RDF_STORAGE_TYPE: ${RDF_STORAGE_TYPE:-FUSEKI}\n"
        "      RDF_ENDPOINT: http://fuseki:3030/openmetadata"
    )
    return {
        GUIDE: f"```bash\n{COMMAND}\n```\n\n{OPTION}\n",
        BASE: "services:\n  postgresql:\n    build:\n      context: ../../.\n"
        "      dockerfile: docker/postgresql/Dockerfile_postgres\n"
        + service("openmetadata-server", "postgresql", db)
        + service("execute-migrate-all", "postgresql", db),
        OVERLAY: "services:\n  fuseki:\n    image: stain/jena-fuseki:5.0.0\n"
        + service("openmetadata-server", "fuseki", rdf)
        + service("execute-migrate-all", "fuseki", rdf),
        "tests/test_connection.py": 'URI = "postgresql://localhost/synthetic"\n',
    }


def postgres(files, **kwargs):
    result = analyze(files, **kwargs)
    claim = next(c for c in result["claims"] if c.get("expected") == "postgresql" and c["origin"] == "DOCUMENTATION")
    assert claim["text"] == OPTION
    assert claim["confidence"] == "MEDIUM"
    assert not any(f["rule"] == "PT-CONSISTENCY-001" for f in result["findings"])
    return claim, result


def test_selected_compose_supports_declared_option_and_preserves_cache(sources):
    claim, result = postgres(sources)
    assert claim["status"] == "INFERRED"
    assert "targets Fuseki only" in claim["reason"]
    assert {s["path"] for s in claim["signals"]} == {BASE, OVERLAY}
    anchors = {BASE: "environment:", OVERLAY: "image: stain/jena-fuseki:5.0.0"}
    for signal in claim["signals"]:
        path = signal["path"]
        assert sources[path].splitlines()[signal["line"] - 1].strip() == anchors[path]
    replay, _ = postgres(dict(reversed(list(sources.items()))), verification_context=result["verification_cache"])
    assert replay["claim_key"] == claim["claim_key"]
    assert replay["signals"] == claim["signals"]
    assert replay["verification_reused"]


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (GUIDE, "up -d fuseki", "--profile tools up -d fuseki"),
        (GUIDE, "up -d fuseki", "up -d unrelated"),
        (GUIDE, "docker/development/docker-compose.yml", "other/docker-compose.yml"),
        (BASE, "  postgresql:\n", "  unrelated:\n"),
        (BASE, "      DB_HOST: ${DB_HOST:-postgresql}\n", ""),
        (BASE, "  openmetadata-server:\n", "  unrelated-app:\n"),
        (BASE, "      DB_SCHEME: ${DB_SCHEME:-postgresql}", "      DB_SCHEME: mysql"),
        (BASE, "      DB_HOST: ${DB_HOST:-postgresql}", "      DB_HOST: ${DEPLOY_DATABASE_HOST}"),
        (BASE, "        condition: service_healthy", "        condition: service_healthy\n        required: false"),
        (BASE, "    build:\n", "    profiles: [optional]\n    build:\n"),
        (BASE, "    build:\n", "    build: &invalid\n"),
        (BASE, "services:\n", "include: [other.yml]\nservices:\n"),
        (BASE, "  openmetadata-server:\n", "  openmetadata-server: {}\n  openmetadata-server:\n"),
        (BASE, "      DB_SCHEME: ${DB_SCHEME:-postgresql}", "      DB_SCHEME: mysql\n      DB_SCHEME: postgresql"),
        (BASE, "      DB_SCHEME: ${DB_SCHEME:-postgresql}", "      DB_SCHEME: !override postgresql"),
        (OVERLAY, "  fuseki:\n", "  unrelated:\n"),
        (OVERLAY, "image: stain/jena-fuseki:5.0.0", "image: unrelated:1.0.0"),
        (OVERLAY, "${RDF_ENABLED:-true}", "false"),
        (OVERLAY, "      RDF_STORAGE_TYPE:", "      DB_HOST: mysql\n      RDF_STORAGE_TYPE:"),
    ],
)
def test_unsupported_or_unselected_configuration_is_unresolved(sources, path, before, after):
    assert before in sources[path]
    sources[path] = sources[path].replace(before, after, 1)
    claim, _ = postgres(sources)
    assert claim["status"] == "UNVERIFIED"
    assert not claim["signals"]


def test_unrelated_path_and_test_uri_never_support_conditional_claim(sources):
    sources["unrelated/" + BASE] = sources.pop(BASE)
    claim, _ = postgres(sources)
    assert claim["status"] == "UNVERIFIED" and not claim["signals"]
    declaration = extract_documentation(sources)[0]
    generic = [{"type": "database", "value": "postgresql", "path": "tests/test_connection.py", "line": 1}]
    verdict, _ = verify_claim(declaration, generic, [])
    assert verdict["status"] == "UNVERIFIED" and not verdict["signals"]


def test_quoted_command_and_claim_inside_outer_fence_are_examples(sources):
    sources[GUIDE] = "````markdown\n" + sources[GUIDE] + "````\n"
    assert not extract_documentation(sources)


def test_published_configuration_citations_keep_history_and_repository_scope(sources, signed):
    repository, baseline = import_repo(signed, sources)
    head = advance(signed, repository, baseline, {**sources, "README.md": "# Unrelated change"})
    missing = signed.post("/api/import", json={"name": "No Compose option", "files": {GUIDE: sources[GUIDE]}})
    assert missing.status_code == 200
    with main.Session() as db:

        def published(snapshot):
            return next(c for c in db.get(Record, snapshot).data["claims"] if c["expected"] == "postgresql")

        old, new = published(baseline), published(head)
        other = published(missing.json()["snapshot_id"])
        assert other["status"] == "UNVERIFIED" and not other["supporting_ids"]
        assert new["previous_version_id"] == old["id"] and new["identity_id"] == old["identity_id"]
        assert new["status"] == old["status"] == "INFERRED"
        assert new["verification_scope"] == "DECLARED_CONFIGURATION"
        assert {event["status"] for event in new["history"]} == {"INFERRED"}
    references = [signed.get(f"/api/record/{key}").json() for key in new["evidence_ids"]]
    assert {r["path"] for r in references if r["id"] in new["supporting_ids"]} == {BASE, OVERLAY}
    assert next(r for r in references if r["path"] == GUIDE)["source"] == sources[GUIDE]
    assert all(r["scope"]["snapshot_id"] == head for r in references)
    login = signed.post(
        "/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"}
    )
    assert login.status_code == 200
    for key in [new["id"], *new["evidence_ids"]]:
        assert signed.get(f"/api/record/{key}").status_code == 404
