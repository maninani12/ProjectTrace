import json

from analyzers.engine import analyze


def rules(result):
    return {f["rule"] for f in result["findings"]}


def test_local_terraform_declarations_link_without_evaluation_or_remote_fetch():
    files = {
        "main.tf": 'module "storage" { source = "./modules/storage" }\nmodule "remote" { source = "registry.invalid/module" }\n',
        "modules/storage/main.tf": 'variable "bucket" { type = string }\nlocals { name = var.bucket }\nresource "aws_s3_bucket" "data" { bucket = local.name }\noutput "bucket" { value = aws_s3_bucket.data.id }\n',
    }
    result = analyze(files)
    local = next(a for a in result["cloud_assets"] if a["identity"] == "module.storage")
    assert local["module_resolution"] == "LOCAL_DECLARATIONS_LINKED_SYMBOLIC"
    assert local["local_module_files"] == ["modules/storage/main.tf"]
    assert any(r["target"] == "aws_s3_bucket.data" for r in local["relations"])
    assert any(a["identity"] == "locals.name" for a in result["cloud_assets"])
    assert any(w["code"] == "EXTERNAL_MODULE_UNRESOLVED" for w in result["warnings"])
    assert all(not a["runtime_observed"] for a in result["cloud_assets"])


def test_cloudformation_sections_network_trust_and_unresolved_transforms():
    template = {
        "Transform": "AWS::Serverless-2016-10-31",
        "Parameters": {"Env": {"Type": "String"}},
        "Outputs": {"Result": {"Value": {"Ref": "Group"}}},
        "Resources": {
            "Group": {
                "Type": "AWS::EC2::SecurityGroup",
                "Properties": {
                    "SecurityGroupIngress": [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIp": "0.0.0.0/0"}]
                },
            },
            "Role": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "AssumeRolePolicyDocument": {
                        "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "sts:AssumeRole"}]
                    }
                },
            },
        },
    }
    result = analyze({"stack.json": json.dumps(template)})
    assert {"PT-IAC-021", "PT-IAC-023"} <= rules(result)
    assert {"Parameters.Env", "Outputs.Result"} <= {a["identity"] for a in result["cloud_assets"]}
    assert any(w["code"] == "TRANSFORM_UNRESOLVED" for w in result["warnings"])


def test_kubernetes_contextual_policy_and_config_references():
    source = "apiVersion: v1\nkind: Pod\nmetadata: {name: app, namespace: sandbox}\nspec:\n  containers:\n  - name: app\n    image: external.invalid/app:v1\n    envFrom: [{secretRef: {name: runtime-secret}}]\n"
    profile = {
        "infrastructure": {
            "require_network_policy": True,
            "require_resource_requests": True,
            "allowed_image_registries": ["approved.invalid"],
            "environment": "PRODUCTION",
        }
    }
    result = analyze({"pod.yaml": source}, profile=profile)
    assert {"PT-IAC-025", "PT-IAC-026", "PT-IAC-031", "PT-IAC-032"} <= rules(result)
    workload = next(a for a in result["cloud_assets"] if a["kind"] == "Pod")
    assert workload["environment"] == "PRODUCTION"
    assert any(r["target"] == "Secret/sandbox/runtime-secret" for r in workload["relations"])
    result = analyze(
        {
            "pod.yaml": source,
            "network.yaml": "apiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nmetadata: {name: restrict, namespace: sandbox}\nspec: {podSelector: {}, policyTypes: [Ingress]}",
        },
        profile=profile,
    )
    assert "PT-IAC-026" not in rules(result)


def test_compose_exposure_devices_and_declarations_are_structural():
    result = analyze(
        {
            "compose.yaml": "services:\n  app:\n    ports: ['8080:80']\n    ipc: host\n    secrets: [runtime]\n    networks: [private]\nsecrets:\n  runtime: {file: .env}\nnetworks:\n  private: {internal: true}\n"
        }
    )
    assert {"PT-IAC-027", "PT-IAC-028"} <= rules(result)
    assert {"compose:secrets:runtime", "compose:networks:private"} <= {a["identity"] for a in result["cloud_assets"]}
    loopback = analyze({"compose.yaml": "services:\n  app:\n    ports: ['127.0.0.1:8080:80']\n"})
    assert "PT-IAC-027" not in rules(loopback)


def test_docker_permissions_healthcheck_and_policy_cache_invalidation():
    source = "FROM scratch\nUSER 65532\nRUN chmod 777 /app\n"
    first = analyze({"Dockerfile": source, "app.ts": "const x = 1;"})
    assert "PT-IAC-029" in rules(first) and "PT-IAC-030" not in rules(first)
    second = analyze(
        {"Dockerfile": source, "app.ts": "const x = 1;"},
        first["analysis_cache"],
        profile={"infrastructure": {"require_healthcheck": True}},
    )
    assert "PT-IAC-030" in rules(second) and second["reused_files"] == 1
    assert not any(w.get("analyzer") == "PARSING" for w in second["warnings"])
    disabled = analyze(
        {"Dockerfile": source},
        profile={
            "infrastructure": {"environment": "DEVELOPMENT", "rules": {"PT-IAC-029": {"environments": ["PRODUCTION"]}}}
        },
    )
    assert "PT-IAC-029" not in rules(disabled)


def test_infrastructure_profile_validation_rbac_versions_and_no_filename_environment(signed):
    response = signed.post(
        "/api/native/profile",
        json={"repository_id": "clean", "version": 0, "infrastructure": {"environment": "PRODUCTION"}},
    )
    assert response.status_code == 403
    assert (
        next(
            a
            for a in analyze({"prod/compose.yaml": "services:\n  app: {image: fixture:v1}\n"})["cloud_assets"]
            if a["identity"] == "compose:app"
        )["environment"]
        == "UNKNOWN"
    )
