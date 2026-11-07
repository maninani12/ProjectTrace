"""Published snapshots captured with the pre-normalization public archive layout."""
import copy

import pytest
from sqlalchemy import select, text

from backend.db import Record
from backend.jobs import execute_analysis
from backend.public_snapshot_paths import Paths, claim_index
from backend.repository_store import RepositoryFiles, capture
from tests.test_repository_store import storage  # noqa: F401


def public_snapshot(storage, sources, commit, *, legacy=False, base=None, provenance_commit=None):  # noqa: F811
    db, actor, repo = storage
    repo.name, repo.provider = "owner/repo", "GITHUB_PUBLIC"
    prefix = f"repo-{commit}/" if legacy else ""
    inventory = capture(db, actor.organization_id, repo,
                        ((prefix + p, value.encode()) for p, value in sources.items()),
                        source="GITHUB_PUBLIC_ARCHIVE")
    inventory.data = {**inventory.data, "provenance": {
        "source": "GITHUB_PUBLIC", "repository": "owner/repo", "commit": provenance_commit or commit,
        "ref": "main", "source_url": "https://github.com/owner/repo",
    }, **({} if legacy else {"path_basis": "GITHUB_REPOSITORY_RELATIVE"})}
    db.commit()
    result = execute_analysis(db, actor, repo,
        RepositoryFiles(db, actor.organization_id, repo.id, inventory.id),
        branch="main", git_commit=commit, base_id=base)
    return result[0]


def historical_identity_snapshot(owned_storage, sources, commit, version, monkeypatch):
    """Publish a fixture with an older schema after either analyzer mode returns."""
    from backend import partitioned_analysis

    analyze = partitioned_analysis.analyze_inventory

    def historical_result(*args, **kwargs):
        result = analyze(*args, **kwargs)
        for finding in result["findings"]:
            finding["identity_version"] = version
        return result

    with monkeypatch.context() as patch:
        patch.setattr(partitioned_analysis, "analyze_inventory", historical_result)
        return public_snapshot(owned_storage, sources, commit, legacy=True)


def documentation(snapshot):
    return [c for c in snapshot.data["claims"] if c.get("origin") == "DOCUMENTATION"]


@pytest.mark.parametrize("legacy_first", [True, False])
def test_published_public_paths_preserve_identity_and_real_drift(storage, legacy_first):  # noqa: F811
    db, actor, repo = storage
    sources = {
        "docs/README.md": "Production storage is private.\n",
        "other/README.md": "Production storage is private.\n",
        "docs/a%20b.md": "Production storage is private.\n",
        "docs/a b.md": "Production storage is private.\n",
        "main.tf": 'resource "aws_s3_bucket" "production" { acl = "private" }\n',
    }
    base = public_snapshot(storage, sources, "a" * 40, legacy=legacy_first)
    db.refresh(base)
    original = copy.deepcopy(base.data)
    original_claims = {c["path"].split("/", 1)[-1] if legacy_first else c["path"]: c for c in documentation(base)}
    same = public_snapshot(storage, sources, "b" * 40, legacy=not legacy_first, base=base.id)
    assert same.data["changed_files"] == []
    assert not any(d["type"] == "CLAIM_REMOVED" for d in same.data["drifts"])
    for claim in documentation(same):
        path = claim["path"].split("/", 1)[-1] if not legacy_first else claim["path"]
        prior = original_claims[path]
        assert claim["previous_version_id"] == prior["id"]
        assert claim["identity_id"] == prior["identity_id"]
        assert not any(h["status"] == "STALE" for h in claim["history"])
    changed = public_snapshot(storage, {**sources, "main.tf":
        'resource "aws_s3_bucket" "production" { acl = "public-read" }\n'}, "c" * 40, base=same.id)
    assert changed.data["changed_files"] == ["main.tf"]
    assert all(c["status"] == "CONTRADICTED" for c in documentation(changed))
    change = db.scalar(select(Record).where(Record.kind == "engineering_change",
        Record.data["head_snapshot_id"].as_string() == changed.id))
    assert len(change.data["claim_comparisons"]) == 4
    assert all(c["document"]["id"] for c in change.data["claim_comparisons"])
    for comparison in change.data["claim_comparisons"]:
        document = db.get(Record, comparison["document"]["id"])
        assert comparison["document"]["path"] == document.data["path"]
        assert comparison["document"]["hash"] == document.data["hash"]
        assert document.data["scope"]["snapshot_id"] == same.id
        assert comparison["after"]["evidence"][0]["path"] == "main.tf"
    removed = dict(sources)
    del removed["docs/README.md"]
    removed["new/README.md"] = "Production storage is private.\n"
    final = public_snapshot(storage, removed, "d" * 40, base=changed.id, legacy=not legacy_first)
    removals = [d for d in final.data["drifts"] if d["type"] == "CLAIM_REMOVED"]
    assert [d["path"] for d in removals] == ["docs/README.md"]
    added_path = "new/README.md" if legacy_first else "repo-" + "d" * 40 + "/new/README.md"
    assert next(c for c in documentation(final) if c["path"] == added_path)["previous_version_id"] is None
    db.refresh(base)
    assert base.data == original
    assert db.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    assert db.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.parametrize("patch,paths", [
    ({"commit": "invalid"}, ["repo-" + "a" * 40 + "/docs/README.md"]),
    ({"repository": "other/repo"}, ["repo-" + "a" * 40 + "/docs/README.md"]),
    ({"repository": None}, ["repo-" + "a" * 40 + "/docs/README.md"]),
    ({}, ["repo-" + "a" * 40 + "/docs/README.md", "docs/README.md"]),
    ({}, ["repo-" + "b" * 40 + "/docs/README.md"]),
    ({}, ["repo-" + "a" * 40 + "/docs/../README.md"]),
])
def test_ambiguous_public_layouts_never_strip_or_merge(patch, paths):
    data = {"source_provenance": {"source": "GITHUB_PUBLIC", "repository": "owner/repo",
                                 "commit": "a" * 40, **patch}, "hashes": dict.fromkeys(paths, "digest")}
    resolver = Paths(data, "owner/repo")
    assert resolver.state.startswith("UNRESOLVED")
    assert [resolver.path(p) for p in paths] == paths


def test_relative_basis_and_unknown_claim_schemas_do_not_alias_literal_git_paths():
    from analyzers.verifiers import claim_key

    path = "repo-" + "a" * 40 + "/docs/README.md"
    data = {"source_provenance": {"source": "GITHUB_PUBLIC", "repository": "owner/repo", "commit": "a" * 40},
            "hashes": {path: "hash"}}
    assert Paths(data, "owner/repo", basis="GITHUB_REPOSITORY_RELATIVE").path(path) == path
    resolver = Paths(data, "owner/repo")
    claim = {"id": "one", "path": path, "expected": "private", "category": "SECURITY"}
    assert resolver.key(claim) == claim_key({**claim, "path": "docs/README.md"})
    assert resolver.key({**claim, "claim_key": "unknown-key-schema"}) == "unknown-key-schema"
    assert list(claim_index([claim, {**claim, "id": "two"}], resolver).values()) == [None]
    missing = Paths({"hashes": {path: "hash"}}, "owner/repo", public_expected=True)
    assert missing.state == "UNRESOLVED_PUBLIC_PROVENANCE" and missing.path(path) == path


def test_malformed_historical_provenance_reports_partial_without_inventing_removal(storage):  # noqa: F811
    sources = {"README.md": "Production storage is private.\n"}
    base = public_snapshot(storage, sources, "a" * 40, legacy=True, provenance_commit="malformed")
    head = public_snapshot(storage, sources, "b" * 40, base=base.id)
    assert head.data["status"] == "PARTIAL"
    assert head.data["comparison"]["public_path_identity"]["base"] == "UNRESOLVED_PUBLIC_PROVENANCE"
    assert not any(d["type"] == "CLAIM_REMOVED" for d in head.data["drifts"])
    assert any(w["analyzer"] == "PUBLIC_SNAPSHOT_IDENTITY" for w in head.data["warnings"])
    assert all(c["status"] == "UNVERIFIED" for c in documentation(head))


def test_inventory_scope_cannot_supply_a_relative_path_marker(storage):  # noqa: F811
    from backend.db import Repository, SourceInventory
    from backend.public_snapshot_paths import for_snapshot

    db, actor, repo = storage
    db.add(Repository(id="foreign-repo", organization_id="other", name="owner/repo",
                      provider="GITHUB_PUBLIC", system="Other", component="Other", owner="Other"))
    db.flush()
    foreign = SourceInventory(id="foreign-inventory", organization_id="other", repository_id="foreign-repo",
                              data={"path_basis": "GITHUB_REPOSITORY_RELATIVE"})
    db.add(foreign)
    db.commit()
    resolver = for_snapshot(db, {"source_inventory_id": foreign.id,
        "source_provenance": {"source": "GITHUB_PUBLIC", "repository": "owner/repo", "commit": "a" * 40},
        "hashes": {"repo-" + "a" * 40 + "/README.md": "hash"}}, actor.organization_id, repo.id, "owner/repo")
    assert resolver.state == "UNRESOLVED_INVENTORY_SCOPE" and not resolver.prefix


def test_existing_contradiction_finding_is_not_new_on_layout_change(storage):  # noqa: F811
    sources = {"README.md": "Production storage is private.\n",
               "main.tf": 'resource "aws_s3_bucket" "production" { acl = "public-read" }\n'}
    base = public_snapshot(storage, sources, "a" * 40, legacy=True)
    same = public_snapshot(storage, sources, "b" * 40, base=base.id)
    before = next(f for f in base.data["findings"] if f["rule"] == "PT-CONSISTENCY-001")
    after = next(f for f in same.data["findings"] if f["rule"] == "PT-CONSISTENCY-001")
    assert after["identity_id"] == before["identity_id"]
    assert after["previous_version_id"] == before["id"]
    assert after["delta"] == "EXISTING"


@pytest.mark.parametrize("stage", ["CLAIMS", "CORRELATION"])
def test_legacy_continuity_survives_private_stage_restart(storage, monkeypatch, stage):  # noqa: F811
    from backend.generation_models import AnalysisGeneration
    from backend.generations import Generation

    db, actor, repo = storage
    sources = {"README.md": "Production storage is private.\n",
               "main.tf": 'resource "aws_s3_bucket" "production" { acl = "public-read" }\n'}
    base = public_snapshot(storage, sources, "a" * 40, legacy=True)
    save = Generation.save

    def interrupt(self, name, state):
        save(self, name, state)
        if name == stage:
            raise RuntimeError("Owned legacy continuity interruption")

    monkeypatch.setattr(Generation, "save", interrupt)
    with pytest.raises(RuntimeError, match="Owned legacy continuity"):
        public_snapshot(storage, sources, "b" * 40, base=base.id)
    pending = db.scalar(select(AnalysisGeneration).where(AnalysisGeneration.state == "STAGING"))
    assert list(db.scalars(select(Record.id).where(Record.kind == "snapshot"))) == [base.id]
    job = db.get(Record, pending.job_id)
    files = RepositoryFiles(db, actor.organization_id, repo.id, pending.inventory_id)
    monkeypatch.setattr(Generation, "save", save)
    recovered, _ = execute_analysis(db, actor, repo, files, job=job,
        branch="main", git_commit="b" * 40, base_id=base.id)
    assert recovered.data["base_id"] == base.id
    assert documentation(recovered)[0]["previous_version_id"] == documentation(base)[0]["id"]
    assert next(f for f in recovered.data["findings"] if f["rule"] == "PT-CONSISTENCY-001")["previous_version_id"]
    duplicate, _ = execute_analysis(db, actor, repo, files, job=job,
        branch="main", git_commit="b" * 40, base_id=base.id)
    assert duplicate.id == recovered.id
