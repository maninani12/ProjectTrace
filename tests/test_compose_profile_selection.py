import pytest

from analyzers.engine import analyze
from analyzers.source_input import SourceFiles
from backend import main
from backend.db import Record
from tests.test_code_quality import import_repo
from tests.test_engineering_changes import advance

README = "Use the optional profile in `docker-compose.yml`:\n`docker compose --profile tools up`.\n"
COMPOSE = """services:
  app: {image: example/app:1}
  toolbox:
    image: example/tools:1
    profiles: [tools]
    depends_on: [app]
    environment:
      ENDPOINT: ${TOOL_ENDPOINT}
  preview: {image: example/preview:1, profiles: [preview]}
"""


def selection(files):
    result = analyze(files)
    return next(c for c in result["claims"] if c["assertion_family"] == "compose_profile_selection")


def test_only_active_profile_and_default_services_are_cited():
    files = {"README.md": README, "docker-compose.yml": COMPOSE}
    tools = selection(files)
    assert (tools["status"], tools["confidence"], tools["verification_scope"]) == (
        "INFERRED",
        "MEDIUM",
        "DECLARED_CONFIGURATION",
    )
    assert tools["signals"] == [
        {"path": "docker-compose.yml", "line": 4, "type": "compose_profile_selection", "value": "app, toolbox"}
    ]
    assert "runtime connectivity are unobserved" in tools["reason"]
    preview = selection({**files, "README.md": README.replace("--profile tools", "--profile preview")})
    assert preview["signals"][0]["value"] == "app, preview"
    assert preview["claim_key"] != tools["claim_key"]


@pytest.mark.parametrize(
    "change",
    [
        {"README.md": README.replace("--profile tools", "--profile unknown")},
        {"docker-compose.yml": COMPOSE.replace("[app]", "[preview]")},
        {"docker-compose.yml": COMPOSE.replace("[app]", "[missing]")},
        {"docker-compose.yml": COMPOSE.replace("[app]", "[toolbox]")},
        {"docker-compose.yml": COMPOSE.replace("profiles: [tools]", "profiles: ['${SELECTED}']")},
        {"docker-compose.yml": COMPOSE.replace("profiles: [tools]", "profiles: [tools]\n    profiles: [tools]")},
        {
            "docker-compose.yml": COMPOSE.replace(
                "depends_on: [app]", "depends_on: {app: {condition: service_started, required: false}}"
            )
        },
        {"docker-compose.yml": COMPOSE.replace("depends_on: [app]", "network_mode: service:app")},
        {"docker-compose.yml": "include: [shared.yml]\n" + COMPOSE},
        {"docker-compose.yml": COMPOSE.replace("    image: example/tools:1\n", "")},
        {"compose.yaml": COMPOSE},
        {"docker-compose.override.yml": "services: {}"},
        {".env": "COMPOSE_PROFILES=preview"},
    ],
)
def test_ambiguous_or_unsupported_selection_stays_unverified(change):
    claim = selection({"README.md": README, "docker-compose.yml": COMPOSE, **change})
    assert claim["status"] == "UNVERIFIED" and not claim["signals"]


def test_non_retained_override_path_prevents_support():
    files = SourceFiles(
        {"README.md": README, "docker-compose.yml": COMPOSE},
        intake=[
            {"path": "compose.override.yaml", "bytes": 1, "physical_lines": None, "state": "BINARY"},
        ],
    )
    assert selection(files)["status"] == "UNVERIFIED"


@pytest.mark.parametrize(
    "readme",
    [
        README.replace(" up`", " up toolbox`"),
        README.replace("--profile tools", "--profile tools --profile preview"),
        README.replace("docker compose", "docker compose -f docker-compose.yml"),
        "```md\n" + README + "```\n",
        "<!--\n" + README + "-->\n",
        README.replace("`docker-compose.yml`", "`unrelated/docker-compose.yml`"),
    ],
)
def test_unrecognized_commands_and_examples_do_not_create_profile_claims(readme):
    claims = analyze({"README.md": readme, "docker-compose.yml": COMPOSE})["claims"]
    assert not any(c["assertion_family"] == "compose_profile_selection" for c in claims)


def test_published_profile_link_and_explicit_base_are_immutable(signed):
    base_sources = {"README.md": README, "docker-compose.yml": COMPOSE}
    repo, base = import_repo(signed, base_sources)
    head = advance(signed, repo, base, {**base_sources, "docker-compose.yml": COMPOSE.replace("[tools]", "[disabled]")})
    with main.Session() as db:
        old, new = (db.get(Record, sid).data for sid in (base, head))
        before = next(c for c in old["claims"] if c["expected"] == "tools")
        after = next(c for c in new["claims"] if c["expected"] == "tools")
        assert new["base_id"] == base
        assert before["status"] == "INFERRED" and after["status"] == "UNVERIFIED"
        assert after["identity_id"] == before["identity_id"] and after["previous_version_id"] == before["id"]
        assert not after["supporting_ids"] and not after["contradicting_ids"]
    [evidence] = before["supporting_ids"]
    reply = signed.get(f"/api/record/{evidence}")
    assert reply.status_code == 200
    assert reply.json()["path"] == "docker-compose.yml" and reply.json()["source"] == COMPOSE
