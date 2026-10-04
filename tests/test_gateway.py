import pytest

from backend.llm_gateway import safe_context, validate_output
from integrations.providers import normalize


def test_fake_citation_rejected():
    with pytest.raises(ValueError):
        validate_output({"answer": "Unsupported", "evidence_ids": ["invented"], "limitations": []}, ["real"])


def test_context_redacts_and_bounds_source():
    context = safe_context([{"id": "real", "source": 'api_key="secret_fixture_123456"' + "x" * 200}], 50)
    assert "secret_fixture" not in context[0]["untrusted_evidence"]
    assert len(context[0]["untrusted_evidence"]) <= 50


def test_external_evidence_preserves_provider():
    result = normalize(
        "Wiz fixture",
        {
            "id": "external-1",
            "path": "deploy.yaml",
            "line": 1,
            "rule": "example",
            "severity": "HIGH",
            "title": "Public workload",
        },
    )
    assert result["source"] == "EXTERNAL_TOOL"
    assert result["provider_id"] == "external-1"
