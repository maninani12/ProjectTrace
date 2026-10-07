"""GitHub App transport is allowlisted. Live verification requires an installation."""

import base64
import hashlib
import hmac
import re
import time

import httpx
import jwt

from analyzers.engine import MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES, safe_path, validate_files
from analyzers.source_input import SourceFiles
from integrations.secure_http import PinnedTransport


def verify_signature(body, signature, secret):
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class GitHubApp:
    def __init__(
        self,
        app_id,
        private_key,
        installation_id,
        *,
        api_base_url="https://api.github.com",
        allowed_hosts=("api.github.com",),
        private_cidrs=(),
        ca_file=None,
        api_version="2022-11-28",
    ):
        self.app_id = str(app_id)
        self.private_key = private_key
        self.installation_id = str(int(installation_id))
        self.api_base_url = api_base_url.rstrip("/")
        self.allowed_hosts, self.private_cidrs, self.ca_file = allowed_hosts, private_cidrs, ca_file
        self.api_version = api_version

    def client(self, headers=None):
        return httpx.Client(
            base_url=self.api_base_url,
            timeout=20,
            follow_redirects=False,
            trust_env=False,
            transport=PinnedTransport(self.api_base_url, self.allowed_hosts, self.private_cidrs, self.ca_file),
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": self.api_version,
                **(headers or {}),
            },
        )

    def authenticate(self):
        now = int(time.time())
        assertion = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self.app_id}, self.private_key, algorithm="RS256"
        )
        with self.client() as client:
            response = client.post(
                f"/app/installations/{self.installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {assertion}"},
            )
            response.raise_for_status()
            token = response.json()["token"]
            if not isinstance(token, str) or not token or len(token) > 4096:
                raise ValueError("Installation token response is invalid.")
            return token

    def test_connection(self):
        token = self.authenticate()
        with self.client() as client:
            response = client.get(
                "/installation/repositories",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            return {"status": "CONNECTED", "repositories": response.json().get("total_count", 0)}

    def repositories(self):
        token = self.authenticate()
        with self.client({"Authorization": f"Bearer {token}"}) as client:
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
        files, total = SourceFiles(), 0
        with self.client({"Authorization": f"Bearer {token}"}) as client:
            response = client.get(f"/repos/{full_name}/git/trees/{commit}", params={"recursive": "1"})
            response.raise_for_status()
            tree = response.json()
            if tree.get("truncated") or len(tree.get("tree", [])) > MAX_FILES:
                raise ValueError("GitHub tree exceeds the configured file count or provider truncation limit.")
            for entry in tree.get("tree", []):
                path = safe_path(entry["path"])
                if entry.get("mode") in {"120000", "160000"}:
                    raise ValueError("Symlinks and submodules are not ingested.")
                if entry["type"] != "blob":
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
                    files.intake.append(
                        {
                            "path": str(path),
                            "bytes": len(raw),
                            "hash": hashlib.sha256(raw).hexdigest(),
                            "physical_lines": None,
                        }
                    )
                    continue
        return validate_files(files, keep_excluded=True)

    def iter_snapshot(self, full_name, commit):
        """Stream bounded blobs to CAS; a truncated tree is walked as bounded subtrees."""
        from collections import deque

        from backend.repository_store import limits

        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("GitHub source identity is invalid.")
        quota = limits()
        token = self.authenticate()
        with self.client({"Authorization": f"Bearer {token}"}) as client:

            def tree(sha, recursive=False):
                if not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise ValueError("GitHub tree identity is invalid.")
                response = client.get(
                    f"/repos/{full_name}/git/trees/{sha}", params={"recursive": "1"} if recursive else {}
                )
                response.raise_for_status()
                result = response.json()
                if not isinstance(result.get("tree"), list):
                    raise ValueError("GitHub tree response is invalid.")
                return result

            recursive = tree(commit, True)
            if len(recursive["tree"]) > quota["files"] * 2:
                raise ValueError("GitHub recursive tree metadata budget exceeded.")
            pending = (
                deque([(str(safe_path(e["path"])), e) for e in recursive["tree"]])
                if not recursive.get("truncated")
                else deque()
            )
            subtrees = deque([("", commit)]) if recursive.get("truncated") else deque()
            paths, count, total, requests = set(), 0, 0, 0
            while pending or subtrees:
                if not pending:
                    prefix, sha = subtrees.popleft()
                    requests += 1
                    if requests > quota["files"]:
                        raise ValueError("GitHub subtree request budget exceeded.")
                    subtree = tree(sha)
                    if subtree.get("truncated") or len(subtree["tree"]) > quota["files"]:
                        raise ValueError("GitHub non-recursive tree exceeded its inventory budget.")
                    for entry in subtree["tree"]:
                        path = str(safe_path(prefix + entry["path"]))
                        if entry.get("type") == "tree":
                            if len(subtrees) >= quota["files"]:
                                raise ValueError("GitHub pending subtree budget exceeded.")
                            subtrees.append((path + "/", entry["sha"]))
                        else:
                            pending.append((path, entry))
                path, entry = pending.popleft() if pending else (None, None)
                if entry is None:
                    continue
                if entry.get("mode") in {"120000", "160000"}:
                    raise ValueError("Symlinks and submodules require explicit separate intake and are not ingested.")
                if entry.get("type") != "blob":
                    continue
                count += 1
                size = entry.get("size")
                if type(size) is not int or size < 0 or path in paths or count > quota["files"]:
                    raise ValueError("GitHub inventory metadata exceeds its bounded scope.")
                paths.add(path)
                total += size
                if total > quota["bytes"]:
                    raise ValueError("GitHub inventory exceeds its byte quota.")
                if size > quota["file_bytes"]:
                    yield path, {"bytes": size, "state": "SKIPPED_SIZE_LIMIT"}
                    continue
                sha = entry["sha"]
                if not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise ValueError("GitHub blob identity is invalid.")
                response = client.get(f"/repos/{full_name}/git/blobs/{sha}")
                response.raise_for_status()
                body = response.json()
                if (
                    body.get("encoding") != "base64"
                    or not isinstance(body.get("content"), str)
                    or len(body["content"]) > 710000
                ):
                    raise ValueError("GitHub blob encoding or response size is invalid.")
                raw = base64.b64decode("".join(body["content"].split()), validate=True)
                if len(raw) != size or len(raw) > quota["file_bytes"]:
                    raise ValueError("GitHub blob does not match its declared bounded size.")
                # Git blob identity binds the received bytes to the captured tree.
                if hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != sha:
                    raise ValueError("GitHub blob integrity check failed.")
                yield path, raw

    def publish_check(self, full_name, commit, gate):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("GitHub check scope is invalid.")
        token = self.authenticate()
        # Reasons may quote a source-backed claim. Transfer system policy names
        # and result enums only; never forward claim text or source excerpts.
        summary = "\n".join(f"- {r['result']}: {r['policy']}" for r in gate["results"])[:60000]
        with self.client() as client:
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
        except (httpx.HTTPError, jwt.PyJWTError, ValueError):
            return {"status": "ERROR", "reason": "Installation authentication or provider request failed."}
