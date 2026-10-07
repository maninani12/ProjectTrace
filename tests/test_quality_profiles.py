import pytest

from analyzers.code_quality.core import gate
from analyzers.code_quality.rules import config
from analyzers.engine import analyze
from tests.test_enterprise_trust import owner


def test_team_inheritance_overrides_versions_and_scope(client):
    client = owner(client)
    imported = client.post(
        "/api/import", json={"name": "Quality hierarchy", "files": {"app.py": "def work(items=[]): return items"}}
    ).json()
    repo = imported["repository_id"]

    def save(configuration, **scope):
        url = "/api/code-quality/profiles/current"
        current = client.get(url, params=scope).json()
        response = client.post(
            url, json={**scope, "configuration": configuration, "expected_version": current["version"]}
        )
        assert response.status_code == 200, response.text
        return response.json()

    save({"rules": {"PT-QUALITY-001": {"threshold": 12}}, "gate": {"max_new_complexity": 22}})
    save({"rules": {"PT-QUALITY-001": {"severity": "LOW"}}, "gate": {"max_new_nesting": 5}}, team_id="payments")
    current = client.get("/api/code-quality/profiles/current", params={"repository_id": repo}).json()
    assigned = client.post(
        "/api/code-quality/profiles/team-assignment",
        json={"repository_id": repo, "team_id": "payments", "expected_version": current["version"]},
    )
    assert assigned.status_code == 200, assigned.text
    result = save({"rules": {"PT-QUALITY-001": {"threshold": 18}}}, repository_id=repo)
    assert result["configuration"]["rules"]["PT-QUALITY-001"] == {"threshold": 18, "severity": "LOW"}
    assert result["configuration"]["gate"]["max_new_nesting"] == 5
    assert result["configuration"]["gate"]["max_new_complexity"] == 22
    history = client.get("/api/code-quality/profiles/versions", params={"repository_id": repo}).json()
    assert history["total"] == 2 and history["items"][0]["overrides"] == {
        "rules": {"PT-QUALITY-001": {"threshold": 18}}
    }
    save({"gate": {"max_new_complexity": 25}})
    latest = client.get("/api/code-quality/profiles/current", params={"repository_id": repo}).json()
    assert latest["configuration"]["gate"]["max_new_complexity"] == 25
    assert history["items"][0]["configuration"]["gate"]["max_new_complexity"] == 22
    assert client.get("/api/code-quality/profiles/versions?repository_id=private").status_code == 404
    assert client.get("/api/code-quality/profiles/current?team_id=../bad").status_code == 422
    assert (
        client.post(
            "/api/code-quality/profiles/current",
            json={"repository_id": repo, "expected_version": 0, "configuration": {}},
        ).status_code
        == 409
    )


def test_configurable_conditions_results_and_deliberate_unvalidated_override():
    condition = {
        "id": "high_reliability",
        "metric": "finding_count",
        "dimension": "RELIABILITY",
        "severities": ["HIGH"],
        "operator": "EQ",
        "threshold": 0,
        "failure": "FAIL",
        "scope": "ALL_CODE",
    }
    result = analyze(
        {"app.py": "def work(items=[]): return items"},
        profile={"quality": {"gate": {"scope": "ALL_CODE", "conditions": [condition]}}},
    )
    measured = next(
        c
        for c in gate(result["code_quality"], result["findings"])["results"]
        if c["policy"] == "Quality: high_reliability"
    )
    assert (
        measured["result"] == "REVIEW_REQUIRED" and measured["measured"] == 1 and measured["file_paths"] == ["app.py"]
    )
    condition["allow_unvalidated_blocking"] = True
    result["code_quality"]["configuration"]["gate"]["conditions"] = [condition]
    assert gate(result["code_quality"], result["findings"])["status"] == "FAIL"
    condition["failure"] = "WARNING"
    assert (
        next(
            c
            for c in gate(result["code_quality"], result["findings"])["results"]
            if c["policy"] == "Quality: high_reliability"
        )["result"]
        == "WARNING"
    )
    clean = analyze(
        {"app.py": "def work(items=None): return items"},
        profile={"quality": {"gate": {"scope": "OVERALL", "conditions": [condition]}}},
    )
    assert gate(clean["code_quality"], clean["findings"])["status"] == "PASS"


def test_required_parsers_and_file_size_are_configurable():
    result = analyze(
        {"app.py": "def work(:"}, profile={"quality": {"gate": {"scope": "OVERALL", "required_languages": ["Python"]}}}
    )
    parser = next(
        c
        for c in gate(result["code_quality"], result["findings"])["results"]
        if c["policy"] == "Quality: required language parsers"
    )
    assert parser["result"] == "FAIL" and parser["file_paths"] == ["app.py"]
    files = {"app.py": "\n".join(f"value{i} = {i}" for i in range(12))}
    result = analyze(files, profile={"quality": {"rules": {"PT-QUALITY-013": {"threshold": 10}}}})
    assert any(f["rule"] == "PT-QUALITY-013" and f["measured"] == 12 for f in result["findings"])
    result = analyze(files, profile={"quality": {"rules": {"PT-QUALITY-013": {"enabled": False, "threshold": 10}}}})
    assert not any(f["rule"] == "PT-QUALITY-013" for f in result["findings"])


@pytest.mark.parametrize(
    "patch",
    [
        {"conditions": [{"id": "bad", "metric": "arbitrary_code", "operator": "EQ", "threshold": 0}]},
        {"conditions": [{"id": "bad", "metric": "finding_count", "operator": "EQ", "threshold": True}]},
        {"required_languages": ["Invented"]},
        {"max_new_nesting": -1},
    ],
)
def test_condition_validation_rejects_unsafe_or_incoherent_settings(patch):
    with pytest.raises(ValueError):
        config({"gate": patch})
