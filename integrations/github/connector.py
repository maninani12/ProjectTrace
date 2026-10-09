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
from integrations.secure_http import PinnedTransport, ProviderTransportError


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
            # Minting a scoped token is safe to repeat after transient network
            # failure. Never retry certificate/address-policy or HTTP refusal.
            for attempt in range(3):
                try:
                    response = client.post(
                        f"/app/installations/{self.installation_id}/access_tokens",
                        headers={"Authorization": f"Bearer {assertion}"},
                    )
                    break
                except ProviderTransportError as error:
                    if not error.retryable or attempt == 2:
                        raise
                    time.sleep((0.25, 1)[attempt])
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
            if self.api_base_url == "https://api.github.com" and not recursive.get("truncated") and len(recursive["tree"]) > 1000:
                yield from self._batched_snapshot(client, full_name, recursive["tree"], quota)
                return
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
                mode = entry.get("mode")
                if entry.get("type") != "blob" and mode != "160000":
                    continue
                count += 1
                size = 0 if mode == "160000" else entry.get("size")
                if type(size) is not int or size < 0 or path in paths or count > quota["files"]:
                    raise ValueError("GitHub inventory metadata exceeds its bounded scope.")
                paths.add(path)
                total += size
                if total > quota["bytes"]:
                    raise ValueError("GitHub inventory exceeds its byte quota.")
                if mode in {"120000", "160000"}:
                    yield path, {"bytes": size, "state": "UNSUPPORTED", "source_kind": "SYMLINK" if mode == "120000" else "SUBMODULE"}
                    continue
                if size > quota["file_bytes"]:
                    yield path, {"bytes": size, "state": "SKIPPED_SIZE_LIMIT"}
                    continue
                yield path, self._read_blob(client, full_name, entry, quota)

    @staticmethod
    def _verify_blob(raw, entry, quota):
        if len(raw) != entry["size"] or len(raw) > quota["file_bytes"]:
            raise ValueError("GitHub blob does not match its declared bounded size.")
        if hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != entry["sha"]:
            raise ValueError("GitHub blob integrity check failed.")
        return raw

    def _read_blob(self, client, full_name, entry, quota):
        sha = entry.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("GitHub blob identity is invalid.")
        response = client.get(f"/repos/{full_name}/git/blobs/{sha}")
        response.raise_for_status()
        body = response.json()
        if body.get("encoding") != "base64" or not isinstance(body.get("content"), str) or len(body["content"]) > 710000:
            raise ValueError("GitHub blob encoding or response size is invalid.")
        raw = base64.b64decode("".join(body["content"].split()), validate=True)
        return self._verify_blob(raw, entry, quota)

    def _batched_snapshot(self, client, full_name, entries, quota):
        """Bound batches by 100 paths / 2 MB; keep binary reads and all Git integrity checks."""
        paths, total, count, batch, size = set(), 0, 0, [], 0
        for entry in entries:
            mode = entry.get("mode")
            if entry.get("type") != "blob" and mode != "160000":
                continue
            path = str(safe_path(entry["path"]))
            declared = 0 if mode == "160000" else entry.get("size")
            count += 1
            if type(declared) is not int or declared < 0 or path in paths or count > quota["files"]:
                raise ValueError("GitHub inventory metadata exceeds its bounded scope.")
            paths.add(path)
            total += declared
            if total > quota["bytes"]:
                raise ValueError("GitHub inventory exceeds its byte quota.")
            if mode in {"120000", "160000"}:
                yield path, {"bytes": declared, "state": "UNSUPPORTED", "source_kind": "SYMLINK" if mode == "120000" else "SUBMODULE"}
                continue
            if declared > quota["file_bytes"]:
                yield path, {"bytes": declared, "state": "SKIPPED_SIZE_LIMIT"}
                continue
            sha = entry.get("sha")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError("GitHub blob identity is invalid.")
            if batch and (len(batch) >= 100 or size + declared > 2_000_000):
                yield from self._read_batch(client, full_name, batch, quota)
                batch, size = [], 0
            batch.append((path, entry))
            size += declared
        if batch:
            yield from self._read_batch(client, full_name, batch, quota)

    def _read_batch(self, client, full_name, batch, quota):
        # Object IDs come only from the validated, exact-commit tree. No expressions,
        # mutations, transport URLs or repository-provided GraphQL are accepted.
        unique = {entry["sha"]: entry for _, entry in batch}
        aliases = {f"b{i}": sha for i, sha in enumerate(unique)}
        objects = " ".join(f'{alias}:object(oid:"{sha}"){{... on Blob{{oid byteSize isBinary isTruncated text}}}}' for alias, sha in aliases.items())
        owner, name = full_name.split("/")
        response = client.post("/graphql", json={
            "query": "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){" + objects + "}}",
            "variables": {"owner": owner, "name": name},
        })
        response.raise_for_status()
        body = response.json()
        repository = (body.get("data") or {}).get("repository")
        if body.get("errors") or not isinstance(repository, dict):
            raise ValueError("GitHub batch source response is incomplete.")
        blobs = {}
        for alias, sha in aliases.items():
            node, entry = repository.get(alias), unique[sha]
            if not isinstance(node, dict) or node.get("oid") != sha or type(node.get("byteSize")) is not int or node["byteSize"] != entry["size"]:
                raise ValueError("GitHub batch blob identity or size is invalid.")
            if node.get("isBinary") is False and node.get("isTruncated") is False and isinstance(node.get("text"), str):
                try:
                    blobs[sha] = self._verify_blob(node["text"].encode("utf-8"), entry, quota)
                except (UnicodeEncodeError, ValueError):
                    # Provider text can transcode UTF-16 or other source encodings.
                    # Reject those text bytes and verify the original raw REST blob.
                    blobs[sha] = self._read_blob(client, full_name, entry, quota)
            else:
                blobs[sha] = self._read_blob(client, full_name, entry, quota)
        for path, entry in batch:
            yield path, self._verify_blob(blobs[entry["sha"]], entry, quota)

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
