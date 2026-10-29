"""Capture synthetic JWT -> session inputs through the local application API.

Only ProjectTrace runs. Source strings in samples/auth-drift.json never run.
Creates a fresh synthetic organization, preserving all existing workspaces.
"""
import argparse
import http.cookiejar
import json
import secrets
import time
import urllib.parse
import urllib.request
from pathlib import Path


def run(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Use an HTTP loopback ProjectTrace API origin without credentials or a path.")
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = ""

    def request(path, body=None):
        headers = {"Origin": "http://127.0.0.1:5181", "Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = urllib.request.Request(url.rstrip("/") + "/api" + path,
                                     data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with client.open(req, timeout=120) as response:
            return json.load(response)

    def completed(response):
        if response.get("snapshot_id"):
            return response["snapshot_id"]
        if response.get("kind") == "snapshot":
            return response["id"]
        job_id = response.get("job_id")
        if not job_id:
            raise RuntimeError("Analysis did not return a snapshot or durable job reference.")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = request("/record/" + job_id)
            if job.get("state") in {"COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"} and job.get("snapshot_id"):
                return job["snapshot_id"]
            if job.get("state") in {"FAILED", "CANCELLED"}:
                raise RuntimeError("Demo analysis stopped; inspect its authorized job diagnostics.")
            time.sleep(1)
        raise TimeoutError("Demo analysis is still pending; retained job data has not been removed.")

    fixture = json.loads((Path(__file__).resolve().parent.parent / "samples/auth-drift.json").read_text())
    identity = request("/auth/register", {"email": f"auth-demo-{secrets.token_hex(8)}@projecttrace.test",
                                         "password": secrets.token_urlsafe(32) + "Aa1!",
                                         "organization": "Authentication drift demonstration"})
    csrf = identity["csrf"]
    try:
        base = request("/import", {"name": "Authentication drift", "files": fixture["base"]})
        base_id = completed(base)
        repo = base["repository_id"]
        head_id = completed(request(f"/repositories/{repo}/analyze", {"base_id": base_id, "files": fixture["head"]}))
        listing = request(f"/engineering-changes?repository_id={repo}")
        item = next(c for c in listing["items"] if c["head_snapshot_id"] == head_id)
        change = request("/engineering-changes/" + item["id"])
        comparison = next(c for c in change["claim_comparisons"] if c["text"] == "Authentication uses JWT.")
        if (comparison["before"]["status"], comparison["after"]["status"]) != ("VERIFIED", "CONTRADICTED"):
            raise AssertionError("Expected an evidence-backed VERIFIED -> CONTRADICTED transition.")
        proof = {"repository_id": repo, "base_snapshot_id": base_id, "head_snapshot_id": head_id,
                 "engineering_change_id": change["id"], "comparison": comparison,
                 "runtime_evidence": change["runtime_evidence"], "source": {}}
        for label, verdict in (("BASE", comparison["before"]), ("HEAD", comparison["after"])):
            source = request("/record/" + verdict["evidence"][0]["id"])
            proof["source"][label] = {"path": source["path"], "hash": source["hash"], "source": source["source"]}
        return proof
    finally:
        request("/auth/logout", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    args = parser.parse_args()
    print(json.dumps(run(args.url), indent=2))


if __name__ == "__main__":
    main()
