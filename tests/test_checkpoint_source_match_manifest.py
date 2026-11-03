import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH_MANIFEST_40280429009.json"
DECISION = ROOT / "docs/evidence/SCALE001_CHECKPOINT_POLICY_DECISION.json"
VALID_STATUSES = {"VERIFIED_MATCH", "VERIFIED_MISMATCH", "NOT_AVAILABLE"}


def assert_evidence_bytes(raw, item):
    """Bind checkout bytes to the original receipt without rewriting its digest."""
    checkout = item.get("checkout_bytes")
    if checkout is None:
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        return
    assert checkout["representation"] == "git-lf"
    assert checkout["historical_representation"] == "crlf"
    normalized = raw.replace(b"\r\n", b"\n")
    assert b"\r" not in normalized
    assert raw in (normalized, normalized.replace(b"\n", b"\r\n"))
    assert hashlib.sha256(normalized).hexdigest() == checkout["sha256"]
    assert hashlib.sha256(normalized.replace(b"\n", b"\r\n")).hexdigest() == item["sha256"]


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_historical_digest_is_bound_to_explicit_checkout_representation(newline):
    raw = b'{"owned": true}\n'
    item = {"sha256": hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest(),
            "checkout_bytes": {"representation": "git-lf", "historical_representation": "crlf",
                               "sha256": hashlib.sha256(raw).hexdigest()}}
    assert_evidence_bytes(raw.replace(b"\n", newline), item)
    with pytest.raises(AssertionError):
        assert_evidence_bytes(raw.replace(b"true", b"false"), item)


def test_source_match_manifest_preserves_unknown_checkpoint_measurement():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checks = manifest["identity_checks"]
    assert checks and all(check["status"] in VALID_STATUSES for check in checks)
    identities = {check["identity"]: check for check in checks}
    assert identities["github_actions_projecttrace_commit"]["status"] == "VERIFIED_MATCH"
    assert identities["run_inventory_manifest"]["status"] == "VERIFIED_MATCH"
    assert identities["run_archive_equals_prior_historical_archive"]["status"] == "VERIFIED_MISMATCH"
    assert identities["analyzer_parser_versions_and_signatures"]["status"] == "NOT_AVAILABLE"
    assert identities["apt_snapshot_identity"]["status"] == "VERIFIED_MISMATCH"
    assert identities["final_application_image_digest"]["status"] == "NOT_AVAILABLE"
    assert manifest["result_availability"]["status"] == "NOT_AVAILABLE"
    assert manifest["result_availability"]["v1_exact_raw_json_bytes"] is None
    assert manifest["measurement_readiness"]["source_matched_measurement_ready"] is False


def test_checkpoint_and_sanitizer_owner_decisions_are_separate_and_pending():
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    assert decision["checkpoint_policy_state"] == "PENDING_PRODUCT_OWNER_APPROVAL"
    assert decision["explicit_approval_found"] is False
    assert decision["owner_selection"] is None
    assert decision["choices"]["CP-B"]["authorization_scope"].startswith("Investigation only")
    assert decision["sanitizer_policy"]["state"] == "PENDING_PRODUCT_OWNER_APPROVAL"
    assert decision["sanitizer_policy"]["separate_decision"] is True
    assert decision["release_status"]["scale_001"] == "NOT QUALIFIED"

def test_canonical_source_match_manifest_records_unavailable_result_and_policy_gates():
    canonical = ROOT / "docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH.json"
    manifest = json.loads(canonical.read_text(encoding="utf-8"))
    checks = manifest["identity_checks"]
    assert checks
    assert all(check["status"] in VALID_STATUSES for check in checks)
    counts = {
        status: sum(check["status"] == status for check in checks)
        for status in VALID_STATUSES
    }
    assert counts == manifest["identity_status_counts"]
    identities = {check["identity"]: check for check in checks}
    assert identities["github_actions_projecttrace_commit"]["status"] == "VERIFIED_MATCH"
    assert identities["run_inventory_manifest"]["status"] == "VERIFIED_MATCH"
    assert identities["exact_failed_checkpoint_result_object"]["status"] == "NOT_AVAILABLE"
    assert identities["requirements_lock_bytes_used_by_runner"]["status"] == "NOT_AVAILABLE"
    assert identities["local_measurement_python_matches_failed_run"]["status"] == "VERIFIED_MISMATCH"
    assert manifest["result_availability"]["receipt_actual"] is None
    assert manifest["measurement_readiness"]["source_matched_measurement_ready"] is False
    assert manifest["execution_preflight"]["full_workload_run"] is False
    assert manifest["execution_preflight"]["decision"].startswith("NOT RUN")
    assert manifest["policy_status"]["checkpoint_policy"] == "PENDING_PRODUCT_OWNER_APPROVAL"
    assert manifest["policy_status"]["sanitizer_policy"] == "PENDING_PRODUCT_OWNER_APPROVAL"
    assert manifest["policy_status"]["checkpoint_limit_bytes"] == 64_000_000
    assert manifest["policy_status"]["sanitizer_limit_nodes"] == 1_000_000

def test_canonical_source_match_manifest_evidence_hashes_are_current():
    manifest = json.loads(
        (ROOT / "docs/evidence/SCALE001_CHECKPOINT_SOURCE_MATCH.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = manifest["evidence_index"]
    representations = json.loads(
        (ROOT / "docs/evidence/CI_EVIDENCE_BYTE_REPRESENTATIONS_20261102.json").read_text(encoding="utf-8")
    )["files"]
    for key in (
        "candidate_cgroup_receipt",
        "candidate_memory_samples",
        "prior_source_match_review",
        "owner_decision_record",
    ):
        item = evidence[key]
        checkout = representations.get(item["path"])
        if checkout:
            assert checkout["historical_sha256"] == item["sha256"]
        assert_evidence_bytes((ROOT / item["path"]).read_bytes(), {**item, "checkout_bytes": checkout})
