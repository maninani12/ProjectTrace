"""Direct read-only AWS inventory; credentials remain in a tenant-scoped host reference.

No competitor findings, write APIs, policy execution or active scanning.
"""

import os
import re
import time

READ_OPERATIONS = {
    "sts": {"get_caller_identity"},
    "s3": {"list_buckets", "get_bucket_acl", "get_bucket_encryption", "get_public_access_block"},
    "ec2": {"describe_security_groups"},
    "iam": {"list_roles"},
}


def credential_prefix(organization_id):
    return "PROJECTTRACE_AWS_" + re.sub(r"[^A-Za-z0-9]", "", organization_id).upper() + "_"


def configured_clients(organization_id, region):
    import boto3
    from botocore.config import Config

    prefix = credential_prefix(organization_id)
    access, secret = os.getenv(prefix + "ACCESS_KEY_ID"), os.getenv(prefix + "SECRET_ACCESS_KEY")
    if not access or not secret:
        raise ValueError("Tenant-scoped read-only AWS credential reference is not configured.")
    config = Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}, max_pool_connections=4)
    session = boto3.Session(
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        aws_session_token=os.getenv(prefix + "SESSION_TOKEN"),
        region_name=region,
    )
    return {service: session.client(service, config=config) for service in READ_OPERATIONS}


def aws_inventory(clients, account_id, region, budget_seconds=30):
    if not re.fullmatch(r"[0-9]{12}", account_id) or not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", region):
        raise ValueError("Invalid AWS account or region.")
    deadline, assets, warnings = time.monotonic() + budget_seconds, [], []

    def read(service, operation, **kwargs):
        if operation not in READ_OPERATIONS[service]:
            raise ValueError("Only declared read operations are allowed.")
        if time.monotonic() > deadline:
            raise TimeoutError("Cloud inventory budget exceeded")
        return getattr(clients[service], operation)(**kwargs)

    caller = read("sts", "get_caller_identity")
    if caller.get("Account") != account_id:
        raise ValueError("The credential account does not match the authorized inventory scope.")

    def asset(identity, kind, **metadata):
        result = {
            "identity": identity,
            "asset_kind": kind,
            "provider": "AWS",
            "account_id": account_id,
            "region": region,
            "authority": "CLOUD_API",
            "verification_scope": "CONTROL_PLANE_INVENTORY",
            "public": "UNKNOWN",
            "encryption": "UNKNOWN",
            "runtime_reachability": "UNOBSERVED",
            **metadata,
        }
        assets.append(result)
        return result

    try:
        buckets = read("s3", "list_buckets").get("Buckets", [])
        if len(buckets) > 50:
            warnings.append("Bucket inventory truncated at 50; coverage is partial.")
        for bucket in buckets[:50]:
            name = bucket["Name"]
            target = asset(
                "arn:aws:s3:::" + name, "StorageBucket", region="GLOBAL", read_operations=["s3:ListAllMyBuckets"]
            )
            try:
                acl = read("s3", "get_bucket_acl", Bucket=name)
                public_grants = any(
                    grant.get("Grantee", {}).get("URI", "").endswith("/AllUsers") for grant in acl.get("Grants", [])
                )
                if public_grants:
                    target["public"] = "PUBLIC_ACL_OBSERVED"
                    target["public_access_note"] = (
                        "Public ACL grant observed; account/bucket blocks, policies and effective anonymous access require correlation."
                    )
                target["read_operations"].append("s3:GetBucketAcl")
                try:
                    block = read("s3", "get_public_access_block", Bucket=name).get("PublicAccessBlockConfiguration", {})
                    target["public_access_block"] = {key: value for key, value in block.items() if type(value) is bool}
                except Exception:
                    warnings.append("A bucket public access block could not be read; effective access is unknown.")
                try:
                    encryption = read("s3", "get_bucket_encryption", Bucket=name)
                    if encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules"):
                        target["encryption"] = "OBSERVED_ENABLED"
                except Exception:
                    warnings.append("A bucket encryption setting could not be read; encryption is unknown.")
            except Exception:
                warnings.append("A bucket configuration could not be read; coverage is partial.")
        groups = read("ec2", "describe_security_groups", MaxResults=100)
        if groups.get("NextToken"):
            warnings.append("Security group inventory truncated at 100; coverage is partial.")
        for group in groups.get("SecurityGroups", [])[:100]:
            public = any(
                item.get("CidrIp") == "0.0.0.0/0" or item.get("CidrIpv6") == "::/0"
                for permission in group.get("IpPermissions", [])
                for item in permission.get("IpRanges", []) + permission.get("Ipv6Ranges", [])
            )
            asset(
                group["GroupId"],
                "SecurityGroup",
                public="INTERNET_INGRESS_OBSERVED" if public else "NO_INTERNET_RANGE_OBSERVED",
                read_operations=["ec2:DescribeSecurityGroups"],
            )
        roles = read("iam", "list_roles", MaxItems=100)
        if roles.get("IsTruncated"):
            warnings.append("Identity inventory truncated at 100; coverage is partial.")
        for role in roles.get("Roles", [])[:100]:
            asset(
                role["Arn"],
                "CloudIdentity",
                region="GLOBAL",
                permission_scope="TRUST_POLICY_ONLY",
                effective_permissions="UNVERIFIED",
                read_operations=["iam:ListRoles"],
            )
    except Exception:
        warnings.append("One inventory stage failed or exhausted its budget; previously collected assets are retained.")
    return {
        "provider": "AWS",
        "account_id": account_id,
        "region": region,
        "state": "PARTIAL" if warnings else "COMPLETED",
        "assets": assets,
        "warnings": warnings,
        "credential_storage": "TENANT_SCOPED_HOST_REFERENCE",
        "limitations": [
            "Bounded S3/EC2/IAM inventory subset; no deployed application reachability proof.",
            "Identity effective permissions, cross-account escalation and code-to-deployment mappings are unverified.",
        ],
    }
