import pytest

from analyzers.engine import analyze
from tests.test_code_quality import import_repo


def issue(source):
    return next(f for f in analyze({"app.py": source})["findings"] if f["rule"] == "PT-QUALITY-011")


def test_structural_anchor_formatting_movement_context_and_duplicates():
    source = "def work(items=[]):\n    return items\n"
    original = issue(source)
    moved = issue("# comment\nother = 1\n\n" + source.replace("items=[]", "items = []"))
    assert original["structural_key"] == moved["structural_key"]
    assert original["structural_context_hash"] == moved["structural_context_hash"]
    changed = issue(source.replace("return items", "items.append(1)\n    return items"))
    assert changed["structural_key"] == original["structural_key"]
    assert changed["structural_context_hash"] != original["structural_context_hash"]
    result = analyze(
        {"app.py": "import subprocess\nsubprocess.run(command, shell=True)\nsubprocess.run(command, shell=True)\n"}
    )
    repeats = [f for f in result["findings"] if f.get("structural_key") and f["identity_confidence"] == "AMBIGUOUS"]
    assert len(repeats) >= 2


def test_identity_rename_review_context_resolution_reopening_and_authorization(signed):
    source = "def work(items=[]):\n    return items\n"
    repo, base = import_repo(signed, {"app.py": source})
    original = signed.get(f"/api/code-quality/{repo}/findings").json()["items"][0]
    assert (
        signed.post(
            f"/api/record/{original['id']}/review",
            json={
                "action": "FALSE_POSITIVE",
                "reason": "Owned regression fixture",
                "expected_version": original["version"],
            },
        ).status_code
        == 200
    )

    def advance(files, parent):
        response = signed.post(f"/api/repositories/{repo}/analyze", json={"base_id": parent, "files": files})
        assert response.status_code == 200, response.text
        return response.json()["id"], signed.get(f"/api/code-quality/{repo}/findings").json()["items"]

    renamed, rows = advance({"renamed.py": "# moved\n" + source}, base)
    moved = rows[0]
    assert moved["identity_id"] == original["identity_id"]
    assert moved["review_identity_id"] == original["review_identity_id"]
    assert moved["review_status"] == "FALSE_POSITIVE" and moved["delta"] == "EXISTING"
    changed, rows = advance(
        {"renamed.py": source.replace("return items", "items.append(1)\n    return items")}, renamed
    )
    assert rows[0]["identity_id"] == original["identity_id"]
    assert rows[0]["review_status"] == "OPEN" and rows[0]["review_identity_id"] != moved["review_identity_id"]
    cleared, rows = advance({"renamed.py": "def work(items=None):\n    return items\n"}, changed)
    assert not rows
    _, rows = advance({"renamed.py": source}, cleared)
    assert rows[0]["identity_id"] == original["identity_id"] and rows[0]["delta"] == "REOPENED"
    assert rows[0]["reopened_count"] == 1 and rows[0]["review_status"] == "OPEN"
    history = signed.get(f"/api/findings/{original['id']}/history").json()
    assert {e["status"] for e in history["items"]} >= {"INTRODUCED", "MOVED", "CONTEXT_CHANGED", "RESOLVED", "REOPENED"}
    assert signed.get(f"/api/findings/{original['id']}/history?limit=101").status_code == 422
    signed.post("/api/auth/logout", json={})
    signed.post("/api/auth/login", json={"email": "outside@example.com", "password": "Strong-test-password-123!"})
    assert signed.get(f"/api/findings/{original['id']}/history").status_code == 404


def test_copy_is_not_rename_and_ambiguous_matches_do_not_inherit_reviews(signed):
    source = "def work(items=[]):\n    return items\n"
    repo, base = import_repo(signed, {"app.py": source})
    original = signed.get(f"/api/code-quality/{repo}/findings").json()["items"][0]
    response = signed.post(
        f"/api/repositories/{repo}/analyze", json={"base_id": base, "files": {"app.py": source, "copy.py": source}}
    )
    assert response.status_code == 200
    rows = signed.get(f"/api/code-quality/{repo}/findings").json()["items"]
    assert len({r["identity_id"] for r in rows}) == 2
    assert next(r for r in rows if r["path"] == "copy.py")["identity_id"] != original["identity_id"]


@pytest.mark.parametrize(
    "path,source,rule",
    [
        ("app.js", "function work(value) { eval(value); }", "PT-SAST-005"),
        ("app.ts", "function work(value: string) { eval(value); }", "PT-SAST-005"),
        ("App.java", "class App { void work() { try { run(); } catch(Exception error) {} } }", "PT-QUALITY-006"),
        (
            "app.py",
            "import subprocess\ndef work(command):\n    subprocess.run(\n        command,\n        shell=True\n    )\n",
            "PT-SAST-002",
        ),
        ("compose.yaml", "services:\n  app:\n    privileged: true\n", "PT-IAC-001"),
        ("Dockerfile", "FROM ubuntu:latest\nUSER root\n", "PT-IAC-002"),
    ],
)
def test_native_structural_anchor_survives_comments_and_line_movement(path, source, rule):
    prefix = "// inserted\n\n" if path.endswith((".js", ".ts", ".java")) else "# inserted\n\n"
    original = next(f for f in analyze({path: source})["findings"] if f["rule"] == rule)
    moved = next(f for f in analyze({path: prefix + source})["findings"] if f["rule"] == rule)
    assert original["identity_confidence"] == moved["identity_confidence"] == "HIGH"
    assert original["structural_key"] == moved["structural_key"]
    assert original["structural_context_hash"] == moved["structural_context_hash"]
