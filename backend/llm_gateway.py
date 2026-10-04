"""Read/generate boundary for future providers; external calls disabled by default."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from analyzers.engine import redact


class GroundedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(max_length=8000)
    evidence_ids: list[str] = Field(max_length=20)
    limitations: list[str] = Field(max_length=20)


class LLMProvider(Protocol):
    def answer_engineering_question(self, question: str, evidence: list[dict]) -> GroundedOutput: ...
    def extract_claims(self, text: str) -> list[dict]: ...


def validate_output(payload, authorized_evidence_ids):
    result = GroundedOutput.model_validate(payload)
    if not set(result.evidence_ids) <= set(authorized_evidence_ids):
        raise ValueError("AI output cites evidence outside the retrieved authorized scope.")
    result.answer = redact(result.answer)
    return result


def safe_context(evidence, max_characters=12000):
    remaining, context = max_characters, []
    for row in evidence[:20]:
        source = redact(row.get("source", ""))[:remaining]
        context.append({"id": row["id"], "untrusted_evidence": source})
        remaining -= len(source)
        if remaining <= 0:
            break
    return context
