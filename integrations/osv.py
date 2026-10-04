"""Exact-version OSV queries; no arbitrary URL parameter."""

import json
from pathlib import Path

import httpx
from pydantic import BaseModel, Field


class OSVAdvisory(BaseModel):
    id: str
    modified: str
    summary: str = ""
    affected: list[dict] = Field(default_factory=list)
    references: list[dict] = Field(default_factory=list)


def query(ecosystem, name, version):
    if ecosystem not in {"npm", "PyPI", "Maven"} or len(name) > 200 or len(version) > 100:
        raise ValueError("Unsupported or invalid package identity.")
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.post(
            "https://api.osv.dev/v1/query", json={"package": {"ecosystem": ecosystem, "name": name}, "version": version}
        )
        response.raise_for_status()
        return [OSVAdvisory.model_validate(v).model_dump() for v in response.json().get("vulns", [])]


def save_cache(path: Path, ecosystem, name, version):
    path.write_text(
        json.dumps(
            {
                "package": {"ecosystem": ecosystem, "name": name},
                "version": version,
                "vulns": query(ecosystem, name, version),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
