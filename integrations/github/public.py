"""Public one-time snapshots: pinned HTTPS metadata and bounded inert ZIP bytes."""

import hashlib
import re
from collections.abc import Mapping
from urllib.parse import quote, urlsplit

import httpx

from backend.intake_errors import IntakeError
from integrations.secure_http import PinnedTransport, ProviderResponseBudget

API = "https://api.github.com"
DOWNLOAD = "https://codeload.github.com"


def repository_url(value):
    url = urlsplit(value)
    if (url.scheme != "https" or url.hostname != "github.com" or url.port is not None
            or url.username or url.password or url.query or url.fragment):
        raise IntakeError("PUBLIC_GITHUB_URL", "Use an HTTPS github.com owner/repository URL without credentials, query or fragment.")
    path = url.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.strip("/").split("/")
    if len(parts) != 2 or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", part) or part in {".", ".."} for part in parts):
        raise IntakeError("PUBLIC_GITHUB_URL", "Paste the repository home URL; enter a branch or tag in the separate ref field.")
    return "/".join(parts)


def validate_ref(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 256 or value.startswith(("/", "."))
            or value.endswith(("/", ".", ".lock")) or any(token in value for token in ("..", "//", "@{", "\\"))
            or re.search(r"[\x00-\x20\x7f~^:?*\[]", value)):
        raise IntakeError("PUBLIC_GITHUB_REF", "The requested Git ref is invalid.", remediation="Use a branch, tag or exact commit from this public repository.")
    return value


def repository_archive_root(provenance):
    """Return the exact top-level directory emitted for a pinned codeload ZIP."""
    if not isinstance(provenance, dict):
        raise IntakeError("PUBLIC_GITHUB_ARCHIVE_LAYOUT", "Pinned GitHub archive provenance is unavailable.")
    repository, commit = provenance.get("repository"), provenance.get("commit")
    if not isinstance(repository, str) or not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise IntakeError("PUBLIC_GITHUB_ARCHIVE_LAYOUT", "Pinned GitHub archive provenance is invalid.")
    try:
        canonical_repository = repository_url("https://github.com/" + repository)
    except IntakeError:
        raise IntakeError("PUBLIC_GITHUB_ARCHIVE_LAYOUT", "Pinned GitHub archive provenance is invalid.") from None
    if canonical_repository != repository:
        raise IntakeError("PUBLIC_GITHUB_ARCHIVE_LAYOUT", "Pinned GitHub archive provenance is invalid.")
    return repository.rsplit("/", 1)[-1] + "-" + commit


def repository_archive_items(items, provenance):
    """Expose codeload files under stable repository-relative paths, lazily."""
    prefix = repository_archive_root(provenance) + "/"
    for path, value in items:
        if not isinstance(path, str) or not path.startswith(prefix) or len(path) == len(prefix):
            raise IntakeError("PUBLIC_GITHUB_ARCHIVE_LAYOUT", "Pinned GitHub archive has an unexpected root directory.")
        yield path[len(prefix):], value


class _ComparableArchiveHashes(Mapping):
    """Lazy view over historical hashes; does not duplicate a repository index."""

    def __init__(self, hashes, prefix):
        self.hashes, self.prefix = hashes, prefix

    def __iter__(self):
        for path in self.hashes:
            yield path[len(self.prefix):] if isinstance(path, str) and path.startswith(self.prefix) else path

    def __len__(self):
        return len(self.hashes)

    def get(self, path, default=None):
        exact = self.hashes.get(path, default)
        rooted = self.hashes.get(self.prefix + path, default) if isinstance(path, str) else default
        if exact is not default and rooted is not default:
            # Ambiguous historical aliases must never imply unchanged content.
            return default
        return exact if exact is not default else rooted

    def __getitem__(self, path):
        value = self.get(path, self)
        if value is self:
            raise KeyError(path)
        return value


def comparable_archive_hashes(hashes, provenance):
    """Expose legacy codeload hashes by repo path without rewriting snapshots."""
    if not isinstance(hashes, dict):
        return hashes
    try:
        prefix = repository_archive_root(provenance) + "/"
    except IntakeError:
        return hashes
    return _ComparableArchiveHashes(hashes, prefix)


class PublicGitHub:
    def __init__(self, url, ref=None):
        self.repository = repository_url(url)
        self.ref = validate_ref(ref) if ref else None

    def client(self, base):
        from backend.repository_store import limits
        maximum = limits()["archive_bytes"] if base == DOWNLOAD else 24 * 1024 * 1024
        return httpx.Client(base_url=base, timeout=httpx.Timeout(20, read=20), follow_redirects=False, trust_env=False,
                            transport=PinnedTransport(base, {"api.github.com", "codeload.github.com"}, max_response_bytes=maximum),
                            headers={"Accept": "application/vnd.github+json", "User-Agent": "ProjectTrace-public-snapshot"})

    @staticmethod
    def checked(response):
        if response.status_code in {403, 429}:
            remaining = response.headers.get("x-ratelimit-remaining")
            reset = response.headers.get("x-ratelimit-reset")
            rate = f" Rate limit remaining: {remaining}; reset Unix seconds: {reset}." if remaining and remaining.isdigit() and reset and reset.isdigit() else ""
            raise IntakeError("PUBLIC_GITHUB_RATE_LIMIT", "Public GitHub request was limited or refused." + rate,
                              remediation="Wait for the provider limit to reset, or upload an unchanged source ZIP.")
        if response.status_code == 404:
            raise IntakeError("PUBLIC_GITHUB_NOT_FOUND", "Public repository or requested ref was not found.",
                              remediation="Check the URL/ref; connect a GitHub App for private repositories.")
        if response.status_code != 200:
            raise IntakeError("PUBLIC_GITHUB_UNAVAILABLE", f"Public GitHub returned HTTP {response.status_code}.",
                              remediation="Retry this retained job after provider/network availability recovers.")

    def resolve(self):
        try:
            with self.client(API) as client:
                response = client.get("/repos/" + self.repository)
                # A repository rename can redirect metadata. Accept one pinned API
                # repository endpoint, never arbitrary locations or credentials.
                if response.status_code in {301, 302, 307, 308}:
                    target = urlsplit(response.headers.get("location", ""))
                    if (target.scheme != "https" or target.hostname != "api.github.com" or target.port is not None
                            or target.username or target.password or target.query or target.fragment
                            or not re.fullmatch(r"/(?:repositories/[0-9]+|repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", target.path)):
                        raise IntakeError("PUBLIC_GITHUB_REDIRECT", "GitHub metadata redirect escaped the approved repository endpoint.")
                    response = client.get(target.path)
                self.checked(response)
                metadata = response.json()
                if metadata.get("private") is not False or metadata.get("visibility", "public") != "public":
                    raise IntakeError("PUBLIC_GITHUB_PRIVATE", "This one-time import requires a verified public repository.")
                self.repository = repository_url("https://github.com/" + metadata.get("full_name", ""))
                ref = self.ref or validate_ref(metadata.get("default_branch", ""))
                commit = client.get("/repos/" + self.repository + "/commits/" + quote(ref, safe=""))
                self.checked(commit)
                sha = commit.json().get("sha", "")
                if not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise IntakeError("PUBLIC_GITHUB_COMMIT", "GitHub returned an invalid exact commit identity.")
                return {"source": "GITHUB_PUBLIC", "source_url": "https://github.com/" + self.repository,
                        "repository": self.repository, "ref": ref, "commit": sha, "private": False,
                        "commit_verification": "PINNED_GITHUB_API", "mode": "ONE_TIME_SNAPSHOT"}
        except ProviderResponseBudget as error:
            raise IntakeError("PUBLIC_GITHUB_METADATA_BYTES", "GitHub metadata exceeds its bounded transport limit.", budget="PROVIDER_METADATA_BYTES", actual=error.actual, maximum=error.maximum) from None
        except httpx.TransportError:
            raise IntakeError("PUBLIC_GITHUB_TRANSPORT", "Public GitHub metadata transport failed validation or connectivity.",
                              remediation="Check the network and retry the retained job; TLS/SSRF guards remain enabled.") from None

    def download(self, provenance, spool, checkpoint):
        # An exact SHA is resolved before downloading. Direct codeload avoids
        # following a provider redirect or requiring an App/GraphQL credential.
        sha = provenance["commit"]
        digest = hashlib.sha256()
        try:
            with self.client(DOWNLOAD) as client:
                with client.stream("GET", "/" + self.repository + "/zip/" + sha) as response:
                    self.checked(response)
                    length = response.headers.get("content-length", "")
                    if length.isdigit() and int(length) > spool.maximum:
                        raise IntakeError("ARCHIVE_COMPRESSED_BYTES", "Public snapshot archive exceeds its compressed byte quota.",
                                          budget="REPOSITORY_MAX_ARCHIVE_BYTES", actual=int(length), maximum=spool.maximum)
                    for chunk in response.iter_bytes(chunk_size=spool.chunk_bytes):
                        checkpoint()
                        spool.append(chunk)
                        digest.update(chunk)
                    provenance.update(archive_sha256=digest.hexdigest(), archive_bytes=spool.length)
        except ProviderResponseBudget as error:
            raise IntakeError("ARCHIVE_COMPRESSED_BYTES", "Public snapshot exceeds its compressed byte quota.", budget="REPOSITORY_MAX_ARCHIVE_BYTES", actual=error.actual, maximum=error.maximum) from None
        except httpx.TransportError:
            raise IntakeError("PUBLIC_GITHUB_TRANSPORT", "Public GitHub source download transport failed validation or connectivity.",
                              remediation="Retry the retained job; no partial inventory will be published as complete.") from None
