import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from analyzers.engine import analyze
from backend import main, oidc
from backend.db import Audit, Grant, OIDCSubject, Record, User
from backend.trust import require_egress


def owner(client):
    result = client.post(
        "/api/auth/register",
        json={
            "email": "enterprise-owner@example.com",
            "password": "Enterprise-test-password-123!",
            "organization": "Enterprise fixture",
        },
    )
    assert result.status_code == 200
    client.headers["x-csrf-token"] = result.json()["csrf"]
    return client


def test_default_egress_policy_fails_closed_and_updates_are_versioned(client):
    client = owner(client)
    policy = client.get("/api/trust/policy").json()
    assert policy["source_egress"] == "NO_EXTERNAL_SOURCE_EGRESS" and policy["ai_mode"] == "DISABLED"
    assert not policy["package_coordinate_advisories"] and not policy["github_check_metadata"]
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == "enterprise-owner@example.com"))
        with pytest.raises(Exception) as error:
            require_egress(db, user.organization_id, "OSV")
        assert error.value.status_code == 403
    result = client.post("/api/trust/policy", json={**policy, "package_coordinate_advisories": True})
    assert result.status_code == 200 and result.json()["version"] == 1
    assert client.post("/api/trust/policy", json=policy).status_code == 409
    assert client.post("/api/trust/policy", json={**result.json(), "ai_mode": "FULL_SOURCE"}).status_code == 422
    assert (
        client.post("/api/trust/policy", json={**result.json(), "package_coordinate_advisories": "true"}).status_code
        == 422
    )


def test_non_admin_cannot_change_egress_or_verify_org_audit(signed):
    policy = signed.get("/api/trust/policy").json()
    assert signed.post("/api/trust/policy", json=policy).status_code == 403
    assert signed.get("/api/trust/audit-integrity").status_code == 403


def test_audit_chain_detects_mutation_and_checkpoint_authenticates_head(client, monkeypatch):
    client = owner(client)
    monkeypatch.setenv("AUDIT_CHECKPOINT_KEY", "Synthetic-checkpoint-key-at-least-32-characters")
    proof = client.get("/api/trust/audit-integrity").json()
    assert proof["state"] == "VERIFIED" and proof["linked_events"] > 0
    checkpoint = proof["checkpoint"]
    expected = hmac.new(
        b"Synthetic-checkpoint-key-at-least-32-characters", checkpoint["payload"].encode(), hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(expected, checkpoint["signature"])
    with main.Session() as db:
        row = db.scalar(select(Audit).where(Audit.organization_id == proof["organization_id"]))
        row.data = {"tampered": True}
        db.commit()
    assert client.get("/api/trust/audit-integrity").json()["state"] == "TAMPER_DETECTED"


def test_cross_tenant_orm_references_are_rejected(client):
    with main.Session() as db:
        db.add(Grant(user_id="outsider", repository_id="clean"))
        with pytest.raises(ValueError, match="Cross-tenant"):
            db.flush()
        db.rollback()
        db.add(
            Record(
                id="illegal", organization_id="other", repository_id="clean", kind="job", natural_key="illegal", data={}
            )
        )
        with pytest.raises(ValueError, match="Cross-tenant"):
            db.flush()


@pytest.mark.parametrize(
    "url",
    [
        "/api/trust/infrastructure?repository_id=private",
        "/api/trust/rule-health?repository_id=private",
        "/api/trust/infrastructure?snapshot_id=missing",
    ],
)
def test_trust_projections_require_repository_and_snapshot_scope(signed, url):
    assert signed.get(url).status_code == 404


def test_capabilities_do_not_claim_full_support_or_measured_precision(signed):
    result = signed.get("/api/trust/capabilities").json()
    assert len(result["languages"]) == 11
    assert all(row["maturity"] == "PARTIAL" and row["precision"] == "UNMEASURED" for row in result["languages"])
    assert result["scale"]["three_million_lines"] == "UNMEASURED_PARTITIONED_INTAKE"
    assert result["scale"]["hundred_concurrent_prs"] == "UNMEASURED"


def test_false_positive_feedback_has_context_and_is_not_population_precision(client):
    client = owner(client)
    imported = client.post(
        "/api/import",
        json={"name": "Enterprise feedback", "files": {"app.py": "import subprocess\nsubprocess.run(cmd, shell=True)"}},
    ).json()
    findings = client.get("/api/workspace").json()["finding"]
    finding = next(row for row in findings if row.get("rule") == "PT-SAST-002")
    response = client.post(
        f"/api/record/{finding['id']}/review",
        json={
            "action": "FALSE_POSITIVE",
            "reason": "Synthetic fixture has a fixed trusted command.",
            "expected_version": finding["version"],
        },
    )
    assert response.status_code == 200
    health = client.get("/api/trust/rule-health?repository_id=" + imported["repository_id"]).json()
    row = health["groups"][0]
    assert row["dismissed"] == row["reviewed_occurrences"] == 1
    assert row["precision"] == "UNMEASURED" and not row["blocking_eligible"]
    assert row["rule_version"] and row["language"] == "Python"


def test_native_identity_survives_lines_but_security_context_changes():
    source = "import subprocess\nsubprocess.run(command, shell=True)\n"
    first = next(f for f in analyze({"app.py": source})["findings"] if f["rule"] == "PT-SAST-002")
    moved = next(f for f in analyze({"app.py": "# comment\n\n" + source})["findings"] if f["rule"] == "PT-SAST-002")
    changed = next(
        f
        for f in analyze({"app.py": source + "command = request.args['command']\n"})["findings"]
        if f["rule"] == "PT-SAST-002"
    )
    assert first["fingerprint"] == moved["fingerprint"] == changed["fingerprint"]
    assert first["security_context_hash"] == moved["security_context_hash"] != changed["security_context_hash"]


@pytest.fixture
def identity_provider(monkeypatch):
    cfg = {
        "issuer": "https://identity.example",
        "authorization_url": "https://identity.example/authorize",
        "token_url": "https://identity.example/token",
        "jwks_url": "https://identity.example/keys",
        "client_id": "fixture-client",
        "redirect_uri": "http://testserver/api/auth/oidc/callback",
        "frontend_url": "http://127.0.0.1:5181",
    }
    monkeypatch.setattr(oidc, "config", lambda: cfg)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {
        "kid": "fixture-key",
        "alg": "RS256",
        "use": "sig",
    }
    monkeypatch.setattr(oidc, "fetch_json", lambda method, url, **kwargs: {"keys": [jwk]})
    return cfg, key, jwk


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://evil.example"},
        {"aud": "other-client"},
        {"exp": 1},
        {"nonce": "wrong"},
        {"iat": 1},
        {"azp": "other-client"},
        {"aud": ["fixture-client", "other"]},
    ],
)
def test_oidc_rejects_invalid_signature_bound_claims(identity_provider, change):
    cfg, key, _ = identity_provider
    claims = {
        "iss": cfg["issuer"],
        "aud": cfg["client_id"],
        "sub": "fixture-subject",
        "exp": time.time() + 300,
        "iat": time.time(),
        "nonce": "fixture-nonce",
    } | change
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture-key"})
    with pytest.raises(Exception):
        oidc.validate_token(token, cfg, hashlib.sha256(b"fixture-nonce").hexdigest())


def test_oidc_code_pkce_nonce_explicit_membership_and_state_replay(client, identity_provider, monkeypatch):
    client = owner(client)
    cfg, key, jwk = identity_provider
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == "enterprise-owner@example.com"))
        db.add(
            OIDCSubject(
                id="subject-binding",
                issuer=cfg["issuer"],
                subject="fixture-subject",
                organization_id=user.organization_id,
                user_id=user.id,
                enabled=True,
            )
        )
        db.commit()
    response = client.get("/api/auth/oidc/start", follow_redirects=False)
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in params
    token = jwt.encode(
        {
            "iss": cfg["issuer"],
            "aud": cfg["client_id"],
            "sub": "fixture-subject",
            "nonce": params["nonce"][0],
            "iat": time.time(),
            "exp": time.time() + 300,
        },
        key,
        algorithm="RS256",
        headers={"kid": "fixture-key"},
    )

    def provider(method, url, **kwargs):
        if method == "GET":
            return {"keys": [jwk]}
        assert kwargs["data"]["code_verifier"]
        return {"id_token": token}

    monkeypatch.setattr(oidc, "fetch_json", provider)
    before = client.cookies.get("pt_session")
    callback = f"/api/auth/oidc/callback?state={params['state'][0]}&code=fixture-code"
    result = client.get(callback, follow_redirects=False)
    assert result.status_code == 303 and client.cookies.get("pt_session") != before
    assert client.get(callback, follow_redirects=False).status_code == 400
    assert client.get("/api/auth/me").status_code == 200
    with main.Session() as db:
        subject = db.get(OIDCSubject, "subject-binding")
        subject.enabled = False
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_oidc_approved_endpoints_reject_ssrf(monkeypatch):
    monkeypatch.setenv("OIDC_ALLOWED_HOSTS", "identity.example,localhost")
    monkeypatch.setattr(oidc.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    for url in (
        "https://localhost/keys",
        "http://identity.example/keys",
        "https://evil.example/keys",
        "https://user:pass@identity.example/keys",
    ):
        with pytest.raises(Exception):
            oidc.approved_url(url)


def test_multistage_docker_final_user_and_inert_commands(tmp_path):
    marker = tmp_path / "must-not-exist"
    source = f'FROM alpine:3 AS build\nUSER root\nRUN touch {marker}\nFROM scratch\nCOPY --from=build /out /app\nUSER 65532\nCMD ["/app"]\n'
    result = analyze({"Dockerfile": source})
    assert not marker.exists()
    assert not any(f["rule"] in {"PT-IAC-002", "PT-IAC-017"} for f in result["findings"])
    assert len(result["cloud_assets"]) == 2 and result["cloud_assets"][-1]["final_stage"]
    assert result["cloud_assets"][-1]["relations"][1]["type"] == "COPIES_FROM"


def test_docker_root_evidence_points_to_effective_user_declaration():
    result = analyze(
        {"Dockerfile": "FROM alpine AS build\nRUN echo fixture\nUSER root\nFROM build\nCMD echo fixture\n"}
    )
    finding = next(row for row in result["findings"] if row["rule"] == "PT-IAC-002")
    assert finding["line"] == 3


def test_native_metadata_masks_credentials_before_caching():
    secret = "ghp_synthetic_credential_shape_1234567890"
    result = analyze(
        {
            "Dockerfile": f"FROM scratch AS {secret}\nUSER {secret}\n",
            "service.yaml": f"kind: Service\nmetadata:\n  name: fixture\n  namespace: {secret}\nspec: {{}}\n",
        }
    )
    assert secret not in json.dumps(result["cloud_assets"])
    assert secret not in json.dumps(result["analysis_cache"])
    reused = analyze(
        {"Dockerfile": f"FROM scratch AS {secret}\nUSER {secret}\n"}, cached_analysis=result["analysis_cache"]
    )
    assert secret not in json.dumps(reused["cloud_assets"])


def test_iac_process_failure_does_not_mark_unaffected_python_clean(monkeypatch):
    from analyzers import infrastructure

    def crash(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr(infrastructure.subprocess, "run", crash)
    result = analyze(
        {
            "app.py": "import subprocess\nsubprocess.run(command, shell=True)",
            "main.tf": 'resource "aws_s3_bucket" "x" { acl = "public-read" }',
        }
    )
    assert result["engines"]["IAC"]["state"] == "PARTIAL"
    assert any(f["rule"] == "PT-SAST-002" for f in result["findings"])


def test_secret_values_are_not_resource_metadata_and_rbac_is_structural():
    source = "apiVersion: v1\nkind: Secret\nmetadata:\n  name: fixture\nstringData:\n  password: synthetic-super-private-material\n---\napiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRole\nmetadata:\n  name: fixture\nrules:\n- apiGroups: ['*']\n  resources: ['*']\n  verbs: ['*']\n"
    result = analyze({"rbac.yaml": source})
    assert "synthetic-super-private-material" not in json.dumps(result["cloud_assets"])
    assert any(f["rule"] == "PT-IAC-012" for f in result["findings"])
    assert all(not asset["runtime_observed"] for asset in result["cloud_assets"])


@pytest.mark.parametrize(
    "path,source",
    [
        ("main.tf.json", '{"resource":{"aws_db_instance":{"fixture":{"publicly_accessible":true}}}}'),
        (
            "stack.json",
            '{"Resources":{"Fixture":{"Type":"AWS::RDS::DBInstance","Properties":{"PubliclyAccessible":true}}}}',
        ),
        (
            "pod.json",
            '{"kind":"Pod","metadata":{"name":"fixture"},"spec":{"containers":[{"name":"app","image":"app:latest"}]}}',
        ),
        ("compose.json", '{"services":{"app":{"image":"app:latest","privileged":true}}}'),
    ],
)
def test_json_infrastructure_intake_and_coverage_agree(path, source):
    result = analyze({path: source})
    assert result["engines"]["IAC"]["supported_files"] == 1
    assert result["engines"]["IAC"]["state"] != "SKIPPED_UNSUPPORTED"
    assert result["cloud_assets"] and result["findings"]


def test_infrastructure_api_exposes_workloads_and_coverage(client):
    client = owner(client)
    imported = client.post(
        "/api/import",
        json={
            "name": "Infra fixtures",
            "files": {"compose.yaml": "services:\n  app:\n    image: app:latest\n    privileged: true\n"},
        },
    ).json()
    report = client.get("/api/trust/infrastructure?repository_id=" + imported["repository_id"]).json()
    assert report["resources"] and report["resources"][0]["format"] == "COMPOSE"
    assert report["findings"] and report["coverage"]
    finding = report["findings"][0]
    assert finding["kind"] == "finding" and isinstance(finding["version"], int)
    evidence = client.get("/api/record/" + finding["evidence_ids"][0]).json()
    assert evidence["kind"] == "evidence" and "privileged: true" in evidence["source"]
    assert not report["runtime_observed"] and report["authority"] == "STATIC"


def test_exception_extension_and_revocation_are_audited_and_versioned(client):
    client = owner(client)
    imported = client.post(
        "/api/import",
        json={"name": "Exception lifecycle", "files": {"compose.yaml": "services:\n  app:\n    privileged: true\n"}},
    ).json()
    workspace = client.get("/api/workspace").json()
    finding = next(row for row in workspace["finding"] if row.get("rule") == "PT-IAC-001")
    result = client.post(
        f"/api/record/{finding['id']}/review",
        json={
            "action": "CREATE_EXCEPTION",
            "reason": "Synthetic temporary test exception.",
            "expires_days": 1,
            "expected_version": finding["version"],
        },
    )
    assert result.status_code == 200
    exception = client.get("/api/workspace").json()["exception"][0]
    body = {
        "action": "EXTEND",
        "days": 2,
        "reason": "Extend the synthetic test exception.",
        "expected_version": exception["version"],
    }
    changed = client.post("/api/trust/exceptions/" + exception["id"], json=body)
    assert changed.status_code == 200 and changed.json()["version"] > exception["version"]
    assert client.post("/api/trust/exceptions/" + exception["id"], json=body).status_code == 409
    assert client.get("/api/gate/" + imported["snapshot_id"]).json()["overall"] == "PASS"
    revoked = client.post(
        "/api/trust/exceptions/" + exception["id"],
        json={**body, "action": "REVOKE", "expected_version": changed.json()["version"]},
    )
    assert revoked.status_code == 200 and revoked.json()["state"] == "REVOKED"
    assert client.get("/api/gate/" + imported["snapshot_id"]).json()["overall"] == "REVIEW_REQUIRED"
    assert client.get("/api/trust/audit-integrity").json()["state"] == "VERIFIED"


def test_explicit_analysis_coverage_gate_counts_unsupported_source():
    from analyzers.code_quality.core import gate

    result = analyze(
        {"app.py": "def work():\n    return 1\n", "unknown.go": "package fixture\n"},
        profile={"quality": {"gate": {"min_analysis_coverage_percent": 100}}},
    )
    condition = next(
        row
        for row in gate(result["code_quality"], result["findings"])["results"]
        if row["policy"] == "Quality: parsed-file analysis coverage"
    )
    assert condition["measured"] == 50 and condition["result"] == "FAIL"


def test_unmeasured_native_rule_never_blocks_by_default():
    from backend.domain import policy_gate

    finding = {
        "severity": "CRITICAL",
        "confidence": "HIGH",
        "title": "Unqualified rule",
        "precision_status": "UNMEASURED",
    }
    assert policy_gate([], [finding])["overall"] == "REVIEW_REQUIRED"


def test_oidc_callback_access_log_masks_authorization_code_and_state():
    import logging

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "fixture",
        1,
        "%s",
        ("/api/auth/oidc/callback?code=SENSITIVE-CODE&state=SENSITIVE-STATE",),
        None,
    )
    assert oidc.CallbackLogFilter().filter(record)
    assert record.getMessage() == "/api/auth/oidc/callback?[redacted]"
