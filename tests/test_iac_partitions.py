from analyzers.engine import finding
from analyzers.infrastructure import structured_iac, structured_iac_batch


def test_batched_infrastructure_preserves_rules_resources_and_partial_states():
    sources = {
        "Dockerfile": "FROM ubuntu:latest\nUSER root\n",
        "deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: app}\nspec: {template: {spec: {containers: [{name: app, image: app:latest}]}}}\n",
        "template.yaml": "{{ .Values.neverExecute }}",
    }
    expected = {path: structured_iac(path, source, finding) for path, source in sources.items()}
    observed = structured_iac_batch(sources, finding)
    assert observed == expected
    assert observed["Dockerfile"][0]
    assert observed["template.yaml"][2][0]["state"] == "PARTIAL"
