"""Read deployment-bundled benchmark evidence; never infer production precision."""

import json
from pathlib import Path

from analyzers.engine import PARSER_SIGNATURE, VERSION


def report():
    path = Path(__file__).resolve().parents[1] / "benchmarks/accuracy-hardening-v2.json"
    if not path.exists():
        return {
            "state": "UNMEASURED",
            "groups": [],
            "observations": [],
            "limitations": ["No current labeled evaluation is bundled."],
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    current = value.get("analyzer_version") == VERSION and value.get("parser_signature") == PARSER_SIGNATURE
    return {
        **value,
        "state": "MEASURED_LABELED_SLICES" if current else "HISTORICAL_MODEL",
        "matches_current_model": current,
        "production_precision": "UNMEASURED",
        "default_blocking_qualification": "NONE",
    }
