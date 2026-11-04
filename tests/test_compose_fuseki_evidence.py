import pytest

from analyzers.compose_evidence import (
    COMMAND,
    DEFAULT_BASE,
    FUSEKI_LAYERED,
    FUSEKI_STANDALONE,
    GUIDE,
    OVERLAY,
    STANDALONE_COMMAND,
)
from analyzers.engine import analyze

FUSEKI_SERVICE = (
    '  fuseki:\n    image: stain/jena-fuseki:5.0.0\n    ports: ["3030:3030"]\n'
    '    environment: ["FUSEKI_BASE=/fuseki"]\n'
)
BACKEND = "    build:\n      context: ../../.\n      dockerfile: docker/development/Dockerfile\n"
RDF = (
    "    environment:\n      RDF_ENABLED: ${RDF_ENABLED:-true}\n      RDF_STORAGE_TYPE: FUSEKI\n"
    "      RDF_ENDPOINT: http://fuseki:3030/openmetadata\n"
    "    depends_on:\n      fuseki:\n        condition: service_healthy\n"
)


@pytest.fixture
def sources():
    return {
        GUIDE: f"{FUSEKI_LAYERED}\n\n```bash\n{COMMAND}\n```\n",
        DEFAULT_BASE: f"services:\n  openmetadata-server:\n{BACKEND}  execute-migrate-all:\n{BACKEND}",
        OVERLAY: f"services:\n{FUSEKI_SERVICE}  openmetadata-server:\n{RDF}  execute-migrate-all:\n{RDF}",
        "tests/test_connection.py": 'URI = "postgresql://localhost/synthetic"\n',
    }


def fuseki(sources):
    result = analyze(sources)
    assert not any(f["rule"] == "PT-CONSISTENCY-001" for f in result["findings"])
    claim = next(c for c in result["claims"] if c["expected"] == "fuseki")
    assert claim["confidence"] == "MEDIUM"
    return claim


def test_standalone_and_layered_selection_share_identity(sources):
    standalone = {
        **sources,
        GUIDE: f"{FUSEKI_STANDALONE}\n\n```bash\ncd /path/to/OpenMetadata\n{STANDALONE_COMMAND}\n```\n",
        OVERLAY: "services:\n" + FUSEKI_SERVICE,
    }
    old, new = fuseki(standalone), fuseki(sources)
    assert old["status"] == new["status"] == "INFERRED"
    assert old["claim_key"] == new["claim_key"]
    assert new["text"] == FUSEKI_LAYERED and "reachability are unobserved" in new["reason"]
    assert {s["path"] for s in old["signals"]} == {OVERLAY}
    assert {s["path"] for s in new["signals"]} == {DEFAULT_BASE, OVERLAY}


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (GUIDE, "up -d fuseki", "up -d openmetadata-server"),
        (GUIDE, "up -d fuseki", "up -d fuseki openmetadata-server"),
        (GUIDE, COMMAND, f"docker compose -f {OVERLAY} -f {DEFAULT_BASE} up -d fuseki"),
        (GUIDE, OVERLAY, "another/docker-compose-fuseki.yml"),
        (GUIDE, " up -d", " --profile rdf up -d"),
        (OVERLAY, '    ports: ["3030:3030"]\n', ""),
        (OVERLAY, "    image: stain/jena-fuseki:5.0.0\n", ""),
        (OVERLAY, "stain/jena-fuseki:5.0.0", "${FUSEKI_IMAGE}"),
        (OVERLAY, "FUSEKI_BASE=/fuseki", "FUSEKI_BASE=${OTHER}"),
        (OVERLAY, "  fuseki:", "  unrelated-fuseki:"),
        (OVERLAY, "  fuseki:", "  fuseki: {}\n  fuseki:"),
        (OVERLAY, "    image:", "    profiles: [rdf]\n    image:"),
        (OVERLAY, "    image:", "    depends_on: [openmetadata-server]\n    image:"),
        (OVERLAY, "      RDF_ENDPOINT: http://fuseki:3030/openmetadata", "      RDF_ENDPOINT: ${OTHER}"),
        (DEFAULT_BASE, "  openmetadata-server:", "  fuseki: {}\n  openmetadata-server:"),
        (DEFAULT_BASE, "dockerfile: docker/development/Dockerfile", "dockerfile: ${BACKEND_DOCKERFILE}"),
    ],
)
def test_unsupported_or_mismatched_selection_keeps_claim_unresolved(sources, path, before, after):
    sources[path] = sources[path].replace(before, after, 1)
    claim = fuseki(sources)
    assert claim["status"] == "UNVERIFIED" and not claim["signals"]


def test_profile_opt_in_and_ambiguous_implicit_selection_are_unresolved(sources):
    sources[GUIDE] = f"{FUSEKI_STANDALONE}\n\n```bash\ncd /path/to/OpenMetadata\n{STANDALONE_COMMAND}\n```\n"
    sources[OVERLAY] = "services:\n" + FUSEKI_SERVICE + "  unrelated: {image: demo:v1}\n"
    assert fuseki(sources)["status"] == "UNVERIFIED"
    sources[OVERLAY] = ("services:\n" + FUSEKI_SERVICE).replace("    image:", "    profiles: [rdf]\n    image:")
    sources[GUIDE] = sources[GUIDE].replace(" up -d", " --profile rdf up -d")
    assert fuseki(sources)["status"] == "UNVERIFIED"
