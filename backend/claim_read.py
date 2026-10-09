"""Disclose path-derived claims without presenting an invented source line."""


def inventory_basis(data):
    if data.get("origin") == "IMPLEMENTATION" and data.get("expected") == "test files" and data.get("assertion_family") == "source_testing":
        return {**data, "recorded_text": data.get("recorded_text", data.get("text")),
            "recorded_line": data.get("recorded_line", data.get("line")),
            "text": "Repository contains a file under a test path.", "line": None,
            "evidence_basis": "PATH_INVENTORY",
            "reason": "The captured file path supports file presence only. Test implementation, execution and test quality are unobserved."}
    return data
