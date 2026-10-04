"""GitHub App transport is allowlisted. Live verification requires an installation."""

import base64
import hashlib
import hmac
import re
import time

import httpx
import jwt

from analyzers.engine import MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES, TEXT_SUFFIXES, safe_path, validate_files


def verify_signature(body, signature, secret):
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class GitHubApp:
    def __init__(self, app_id, private_key, installation_id):
        self.app_id = str(app_id)
        self.private_key = private_key
        self.installation_id = str(int(installation_id))

    def authenticate(self):
        now = int(time.time())
        assertion = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self.app_id}, self.private_key, algorithm="RS256"
        )
        with httpx.Client(
            base_url="https://api.github.com",
            timeout=20,
            follow_redirects=False,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"},
        ) as client:
            response = client.post(
                f"/app/installations/{self.installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {assertion}"},
            )
            response.raise_for_status()
            return response.json()["token"]

    def test_connection(self):
        token = self.authenticate()
        with httpx.Client(base_url="https://api.github.com", timeout=20, follow_redirects=False) as client:
            response = client.get(
                "/installation/repositories",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            return {"status": "CONNECTED", "repositories": response.json().get("total_count", 0)}

    def repositories(self):
        token = self.authenticate()
        with httpx.Client(
            base_url="https://api.github.com",
            timeout=20,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        ) as client:
            response = client.get("/installation/repositories", params={"per_page": 100})
            response.raise_for_status()
            data = response.json()
            if data.get("total_count", 0) > 100:
                raise ValueError(
                    "Initial connector supports at most 100 installation repositories; narrow the installation scope."
                )
            return data.get("repositories", [])

    def fetch_snapshot(self, full_name, commit):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("GitHub source identity is invalid.")
        token = self.authenticate()
        files, total = {}, 0
        with httpx.Client(
            base_url="https://api.github.com",
            timeout=20,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        ) as client:
            response = client.get(f"/repos/{full_name}/git/trees/{commit}", params={"recursive": "1"})
            response.raise_for_status()
            tree = response.json()
            if tree.get("truncated") or len(tree.get("tree", [])) > MAX_FILES:
                raise ValueError("GitHub tree exceeds the configured file count or provider truncation limit.")
            for entry in tree.get("tree", []):
                path = safe_path(entry["path"])
                if entry.get("mode") in {"120000", "160000"}:
                    raise ValueError("Symlinks and submodules are not ingested.")
                if (
                    entry["type"] != "blob"
                    or path.suffix.lower() not in TEXT_SUFFIXES
                    and path.name not in {"Dockerfile", "CODEOWNERS", ".env"}
                ):
                    continue
                size = entry.get("size", 0)
                total += size
                if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise ValueError("GitHub source exceeds static ingestion size limits.")
                blob_sha = entry["sha"]
                if not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
                    raise ValueError("GitHub blob identity is invalid.")
                blob = client.get(f"/repos/{full_name}/git/blobs/{blob_sha}")
                blob.raise_for_status()
                body = blob.json()
                if body.get("encoding") != "base64":
                    raise ValueError("Unsupported GitHub blob encoding.")
                raw = base64.b64decode(body["content"])
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError("GitHub blob exceeds the file size limit.")
                try:
                    files[str(path)] = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
        return validate_files(files)

    def publish_check(self, full_name, commit, gate):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("GitHub check scope is invalid.")
        token = self.authenticate()
        summary = "\n".join(f"- {r['result']}: {r['policy']} — {r['reason']}" for r in gate["results"])[:60000]
        with httpx.Client(base_url="https://api.github.com", timeout=20, follow_redirects=False) as client:
            response = client.post(
                f"/repos/{full_name}/check-runs",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                json={
                    "name": "ProjectTrace",
                    "head_sha": commit,
                    "status": "completed",
                    "conclusion": "neutral",
                    "output": {"title": f"ProjectTrace: {gate['overall']} (advisory)", "summary": summary},
                },
            )
            response.raise_for_status()
            return response.json()["id"]

    def get_health(self):
        try:
            return self.test_connection()
        except httpx.HTTPError, jwt.PyJWTError, ValueError:
            return {"status": "ERROR", "reason": "Installation authentication or provider request failed."}
