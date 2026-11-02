"""Read-only path equivalence for proven public codeload snapshots.

Stored paths, IDs and source citations are never rewritten. URL decoding is
deliberately absent: percent signs in Git paths are literal characters.
"""
from analyzers.engine import safe_path
from analyzers.verifiers import claim_key
from backend.db import SourceInventory
from backend.intake_errors import IntakeError
from integrations.github.public import repository_archive_root


class Paths:
    def __init__(self, data, repository, *, basis=None, public_expected=False):
        self.prefix = ""
        self.state = "EXACT_PATHS"
        provenance = data.get("source_provenance", {})
        hashes = data.get("hashes", {})
        self.public = public_expected or (isinstance(provenance, dict) and provenance.get("source") == "GITHUB_PUBLIC")
        if not isinstance(provenance, dict) or provenance.get("source") != "GITHUB_PUBLIC":
            if public_expected:
                self.state = "UNRESOLVED_PUBLIC_PROVENANCE"
            return
        if not isinstance(provenance.get("repository"), str) or provenance["repository"].casefold() != repository.casefold():
            self.state = "UNRESOLVED_PUBLIC_PROVENANCE"
            return
        try:
            prefix = repository_archive_root(provenance) + "/"
        except (IntakeError, ValueError):
            self.state = "UNRESOLVED_PUBLIC_PROVENANCE"
            return
        if basis == "GITHUB_REPOSITORY_RELATIVE":
            return
        if not hashes or not all(isinstance(p, str) and p.startswith(prefix) and len(p) > len(prefix)
                                 for p in hashes):
            self.state = "UNRESOLVED_PUBLIC_LAYOUT"
            return
        for path in hashes:
            relative = path[len(prefix):]
            try:
                if str(safe_path(relative)) != relative:
                    raise ValueError()
            except ValueError:
                self.state = "UNRESOLVED_PUBLIC_LAYOUT"
                return
        self.prefix, self.state = prefix, "LEGACY_CODELOAD_ROOT"

    def path(self, path):
        return path[len(self.prefix):] if self.prefix and isinstance(path, str) and path.startswith(self.prefix) else path

    def key(self, claim):
        original = claim.get("claim_key") or claim_key(claim)
        # Unknown historical key schemas are never silently reinterpreted.
        if claim.get("claim_key") and original != claim_key(claim):
            return original
        return claim_key({**claim, "path": self.path(claim.get("path"))})


def for_snapshot(db, data, organization_id, repository_id, repository, *, public_expected=False):
    basis = data.get("source_path_basis")
    if not basis and data.get("source_inventory_id"):
        inventory = db.get(SourceInventory, data["source_inventory_id"])
        if not inventory or (inventory.organization_id, inventory.repository_id) != (organization_id, repository_id):
            result = Paths(data, repository, public_expected=public_expected)
            result.prefix, result.state = "", "UNRESOLVED_INVENTORY_SCOPE"
            return result
        basis = inventory.data.get("path_basis")
    return Paths(data, repository, basis=basis, public_expected=public_expected)


def claim_index(claims, paths):
    """Reject duplicate canonical identities instead of choosing an arbitrary row."""
    result = {}
    for claim in claims:
        key = paths.key(claim)
        result[key] = None if key in result else claim
    return result
