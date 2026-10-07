import pytest

from analyzers.engine import analyze
from integrations.cloud import aws_inventory


@pytest.mark.parametrize(
    "path,source",
    [
        ("main.ts", "function f(x: number) { if(x) return 1; return 0; }"),
        ("main.tsx", "const App = () => <div>ok</div>;"),
        ("main.js", "function f(x) { if(x) return 1; return 0; }"),
        ("Demo.java", "class Demo { int f(int x) { if(x > 0) return 1; return 0; } }"),
    ],
)
def test_native_languages_have_versioned_parser_metrics(path, source):
    result = analyze({path: source})
    parser = next(item for item in result["signals"] if item["type"] == "parser")
    assert parser["state"] == "COMPLETED" and parser["grammar_version"]
    assert result["quality_metrics"] and result["engines"]["QUALITY"]["state"] == "COMPLETED"


def test_native_large_tsx_locations_and_parser_lifecycle():
    import gc

    source = "\n".join(
        f"export function C{index}({{ok}}: {{ok: boolean}}) {{ if(ok) return <div>Unicode ✓ {index}</div>; return <span>No</span>; }}"
        for index in range(300)
    )
    for _ in range(3):
        result = analyze({"main.tsx": source, "tsconfig.json": '{"strict": true}'})
        assert len(result["quality_metrics"]) == 300
        assert [item["line"] for item in result["quality_metrics"]] == list(range(1, 301))
        assert result["engines"]["PARSING"]["state"] == "COMPLETED"
        del result
        gc.collect()


def test_native_parser_process_failure_is_partial_not_clean(monkeypatch):
    from types import SimpleNamespace

    from analyzers import languages

    monkeypatch.setattr(
        languages.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=139, stdout=b"")
    )
    result = analyze({"main.ts": "eval(userInput)"})
    assert all(result["engines"][name]["state"] == "PARTIAL" for name in ("PARSING", "QUALITY", "SAST"))
    assert result["analysis_cache"]["main.ts"]["warnings"]


def test_native_duplicate_body_fingerprint_preserves_operators():
    body = "const a=x+1; const b=x+2; const c=x+3; return a+b+c;"
    different = analyze({"main.js": "function plus(x){" + body + "} function minus(x){" + body.replace("+", "-") + "}"})
    assert not any(item["rule"] == "PT-QUALITY-007" for item in different["findings"])
    identical = analyze({"main.js": "function first(x){" + body + "} function second(x){ /* comment */ " + body + "}"})
    # The 1.5 noise guard excludes one-line boilerplate; substantial blocks remain detected.
    assert not any(item["rule"] == "PT-QUALITY-007" for item in identical["findings"])
    substantial = "\n".join(f"const value{i}=x+{i};" for i in range(10)) + "\nreturn value0;"
    repeated = analyze({"main.js": "function first(x){\n" + substantial + "\n}\nfunction second(x){\n" + substantial + "\n}"})
    assert any(item["rule"] == "PT-QUALITY-007" for item in repeated["findings"])


def test_python_source_assignment_local_helper_sink_flow():
    result = analyze(
        {
            "app.py": "def execute_sql(query):\n    db.execute(query)\ndef endpoint():\n    value = request.args['name']\n    query = f'SELECT {value}'\n    execute_sql(query)\n"
        }
    )
    item = next(f for f in result["findings"] if f["rule"] == "PT-SAST-001")
    assert item["classification"] == "CONFIRMED_STATIC_FINDING"
    assert [part["kind"] for part in item["flow"]] == ["SOURCE", "PROPAGATION", "PROPAGATION", "PROPAGATION", "SINK"]
    assert item["flow"][0]["line"] == 4 and item["flow"][-1]["line"] == 2


def test_context_sanitizer_and_separate_sql_parameters_do_not_create_flows():
    result = analyze(
        {
            "app.py": "import html\ndef endpoint():\n    value = request.args['name']\n    escaped = html.escape(value)\n    HTMLResponse(escaped)\n    db.execute('SELECT * FROM x WHERE name=?', (value,))\n"
        }
    )
    assert not [f for f in result["findings"] if f.get("flow")]


def test_unknown_call_transformation_is_review_hotspot():
    result = analyze(
        {"app.py": "def endpoint():\n    value = unknown_transform(request.args['name'])\n    db.execute(value)\n"}
    )
    item = next(f for f in result["findings"] if f.get("flow"))
    assert item["classification"] == "SECURITY_HOTSPOT"


def test_storage_claim_contradiction_uses_structured_hcl_evidence():
    result = analyze(
        {
            "main.tf": 'resource "aws_s3_bucket" "production" {\n acl = "public-read"\n}\n',
            "README.md": "Production storage is private.",
        }
    )
    claim = next(c for c in result["claims"] if c["category"] == "CLOUD_SECURITY")
    assert claim["status"] == "CONTRADICTED" and claim["signals"][0]["path"] == "main.tf"
    assert result["cloud_assets"][0]["public"] == "DECLARED_PUBLIC"
    assert result["cloud_assets"][0]["runtime_observed"] is False


def test_comments_and_string_properties_are_not_iac_facts():
    result = analyze(
        {"main.tf": 'resource "aws_s3_bucket" "x" {\n # acl = "public-read"\n description = "acl = public-read"\n}\n'}
    )
    assert not result["findings"]


def test_kubernetes_structure_and_alias_budgets():
    result = analyze(
        {
            "pod.yaml": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: demo\nspec:\n  containers:\n    - name: app\n      image: app:1\n      securityContext:\n        privileged: true\n        runAsUser: 0\n"
        }
    )
    assert {"PT-IAC-001", "PT-IAC-002", "PT-IAC-008"} <= {f["rule"] for f in result["findings"]}
    hostile = analyze({"pod.yaml": "a: &a [*a]"})
    assert hostile["engines"]["IAC"]["state"] == "PARTIAL"


def test_native_profile_does_not_poison_analysis_cache():
    files = {"main.js": "eval(value);"}
    first = analyze(files, profile={"rules": {"PT-SAST-005": {"enabled": False}}})
    assert not first["findings"]
    second = analyze(files, cached_analysis=first["analysis_cache"])
    assert any(f["rule"] == "PT-SAST-005" for f in second["findings"])


def test_native_profiles_are_authorized_versioned_and_audited(signed):
    assert signed.post("/api/native/profile", json={"repository_id": "clean"}).status_code == 403
    registration = signed.post(
        "/api/auth/register",
        json={
            "email": "native-owner@example.com",
            "password": "Strong-test-password-123!",
            "organization": "Native fixture",
        },
    )
    signed.headers["x-csrf-token"] = registration.json()["csrf"]
    result = signed.post("/api/native/profile", json={"rules": {"PT-SAST-005": {"severity": "LOW"}}})
    assert result.status_code == 200 and result.json()["version"] == 1
    assert signed.post("/api/native/profile", json={"version": 0}).status_code == 409
    assert signed.get("/api/native/profile?repository_id=clean").status_code == 404
    assert signed.get("/api/native/rules").json()["rules"]


def test_cloud_asset_graph_and_risk_path_are_actual_scoped_records(signed):
    registration = signed.post(
        "/api/auth/register",
        json={
            "email": "native-cloud@example.com",
            "password": "Strong-test-password-123!",
            "organization": "Native cloud fixture",
        },
    )
    signed.headers["x-csrf-token"] = registration.json()["csrf"]
    response = signed.post(
        "/api/import",
        json={
            "name": "native-cloud",
            "system": "Cloud",
            "files": {
                "main.tf": 'resource "aws_s3_bucket" "x" {\n acl = "public-read"\n}\n',
                "README.md": "Production storage is private.",
            },
        },
    )
    assert response.status_code == 200, response.text
    workspace = signed.get("/api/workspace").json()
    assert workspace["risk_path"]
    node_ids = {item["id"] for item in workspace["graph_node"]}
    assert any(item["class"] == "CLOUD_RESOURCE" for item in workspace["graph_node"])
    risk = workspace["risk_path"][0]
    assert risk["node_ids"][0] in node_ids and risk["node_ids"][1] in node_ids
    assert any(
        edge["source"] == risk["node_ids"][0] and edge["target"] == risk["node_ids"][1] for edge in workspace["edge"]
    )


class FixtureService:
    def __init__(self, responses):
        self.responses = responses
        self.operations = []

    def __getattr__(self, operation):
        def read(**kwargs):
            self.operations.append(operation)
            return self.responses[operation]

        return read


def test_native_aws_read_only_inventory_and_account_boundary():
    clients = {
        "sts": FixtureService({"get_caller_identity": {"Account": "123456789012"}}),
        "s3": FixtureService(
            {
                "list_buckets": {"Buckets": [{"Name": "fixture"}]},
                "get_bucket_acl": {"Grants": [{"Grantee": {"URI": "http://acs.amazonaws.com/groups/global/AllUsers"}}]},
                "get_public_access_block": {"PublicAccessBlockConfiguration": {"BlockPublicAcls": True}},
                "get_bucket_encryption": {"ServerSideEncryptionConfiguration": {"Rules": [{}]}},
            }
        ),
        "ec2": FixtureService({"describe_security_groups": {"SecurityGroups": []}}),
        "iam": FixtureService({"list_roles": {"Roles": [{"Arn": "arn:aws:iam::123456789012:role/fixture"}]}}),
    }
    result = aws_inventory(clients, "123456789012", "us-east-1")
    assert result["state"] == "COMPLETED"
    assert (
        result["assets"][0]["public"] == "PUBLIC_ACL_OBSERVED"
        and result["assets"][0]["encryption"] == "OBSERVED_ENABLED"
    )
    assert result["assets"][1]["effective_permissions"] == "UNVERIFIED"
    with pytest.raises(ValueError):
        aws_inventory(clients, "999999999999", "us-east-1")


def test_cloud_inventory_scope_and_credential_gate(signed, monkeypatch):
    body = {"repository_id": "private", "account_id": "123456789012", "region": "us-east-1"}
    assert signed.post("/api/cloud/aws/inventory", json=body).status_code == 403
    registration = signed.post(
        "/api/auth/register",
        json={
            "email": "cloud-owner@example.com",
            "password": "Strong-test-password-123!",
            "organization": "Cloud owner fixture",
        },
    )
    signed.headers["x-csrf-token"] = registration.json()["csrf"]
    assert signed.post("/api/cloud/aws/inventory", json=body).status_code == 404
    imported = signed.post(
        "/api/import", json={"name": "Cloud credential gate", "files": {"app.py": "import fastapi"}}
    ).json()
    body["repository_id"] = imported["repository_id"]
    assert signed.post("/api/cloud/aws/inventory", json=body).status_code == 409
    assert signed.post("/api/cloud/aws/inventory", json={**body, "region": "http://127.0.0.1"}).status_code == 422


def test_license_policy_and_new_code_gate_are_explicit():
    from backend.domain import policy_gate

    result = analyze(
        {
            "package-lock.json": '{"lockfileVersion":3,"packages":{"node_modules/fixture":{"version":"1.0.0","license":"GPL-3.0-only"}}}'
        },
        profile={"licenses": {"restricted": ["GPL-3.0-only"]}},
    )
    assert result["dependencies"][0]["license_status"] == "RESTRICTED"
    assert any(item["rule"] == "PT-LICENSE-001" for item in result["findings"])
    issue = {"id": "legacy", "title": "Legacy issue", "category": "SAST", "severity": "HIGH", "delta": "EXISTING"}
    assert policy_gate([], [issue])["overall"] == "REVIEW_REQUIRED"
    assert policy_gate([], [issue], new_findings_only=True)["overall"] == "PASS"


def test_native_function_metadata_masks_credential_patterns():
    material = "ghp_synthetic_credential_shape_1234567890"
    result = analyze(
        {
            "app.ts": f"function {material}() {{ return 1; }}",
            "storage.tf": 'resource "aws_s3_bucket" "fixture" { tags = { Environment = "' + material + '" } }',
        }
    )
    import json

    assert material not in json.dumps(
        {
            "signals": result["signals"],
            "metrics": result["quality_metrics"],
            "cache": result["analysis_cache"],
            "assets": result["cloud_assets"],
        }
    )


def test_production_privacy_claim_does_not_use_an_unbound_development_bucket():
    result = analyze(
        {
            "main.tf": 'resource "aws_s3_bucket" "development" { acl = "public-read" }',
            "README.md": "Production storage is private.",
        }
    )
    assert next(item for item in result["claims"] if item["category"] == "CLOUD_SECURITY")["status"] == "UNVERIFIED"


def test_hcl_literal_identity_policy_is_parsed_without_execution():
    result = analyze(
        {
            "policy.tf": 'resource "aws_iam_policy" "production" { policy = jsonencode({ Statement = [{ Effect = "Allow", Action = "*", Resource = "*" }] }) }'
        }
    )
    assert any(item["rule"] == "PT-IAC-005" for item in result["findings"])


def test_conditional_identity_grant_does_not_prove_public_exposure():
    result = analyze(
        {
            "stack.yaml": 'Resources:\n  Role:\n    Type: AWS::IAM::Policy\n    Properties:\n      PolicyDocument:\n        Statement:\n          - Effect: Allow\n            Action: s3:GetObject\n            Resource: "*"\n            Principal: "*"\n            Condition:\n              StringEquals:\n                aws:SourceAccount: "123456789012"\n'
        }
    )
    assert result["cloud_assets"][0]["public"] == "POTENTIAL_EXPOSURE"
