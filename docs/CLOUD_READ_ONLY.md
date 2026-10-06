# Direct read-only cloud evidence

The implemented provider is a bounded AWS SDK adapter. Azure and GCP live inventory are DEFERRED. Static Terraform declarations can identify AWS/Azure/GCP resource kinds, which is separate from live provider support. No live AWS credential was available for this release, so SDK fixture tests and credential-gate tests do not establish a verified account connection.

An authorized administrator selects an accessible repository with a current snapshot, a 12-digit AWS account and a valid region in Cloud. The API rechecks repository grants and admin role before resolving credentials. STS account mismatch aborts inventory. Regional input cannot become an arbitrary URL. Only configured SDK reads run; no writes, active scanning, templates or imported code execute.

## Credential reference

`integrations/cloud.py:credential_prefix` derives `PROJECTTRACE_AWS_<ORGANIZATION_ID_ALNUM_UPPER>_` from the authenticated organization ID. Configure ACCESS_KEY_ID, SECRET_ACCESS_KEY and optional SESSION_TOKEN under that prefix in the host's protected runtime environment. Credentials are never accepted by the browser, returned in records, or bundled in source. A managed secret store, rotation, federation/assume-role onboarding and delegated cloud-account lifecycle are deferred. Do not place real credentials in repository files.

The read-operation allowlist is:

| Service | SDK operation | IAM read action |
|---|---|---|
| STS | get_caller_identity | sts:GetCallerIdentity (identity lookup) |
| S3 | list_buckets | s3:ListAllMyBuckets |
| S3 | get_bucket_acl | s3:GetBucketAcl |
| S3 | get_bucket_encryption | s3:GetEncryptionConfiguration |
| S3 | get_public_access_block | s3:GetBucketPublicAccessBlock |
| EC2 | describe_security_groups | ec2:DescribeSecurityGroups |
| IAM | list_roles | iam:ListRoles |

Grant only these reads in the authorized account and scope bucket reads to selected resources where supported. Discovery calls may require account-wide list/describe scope. This is the adapter's required operation set, not a claim that an untested IAM policy is production-ready.

## Authority and limits

Records retain account, region, read-operation provenance, observed time, CONTROL_PLANE_INVENTORY authority, warnings and UNKNOWN states. Native rules flag observed public ACLs and Internet-wide ingress as review hotspots. Bucket ACLs do not establish effective public access: account public blocks, bucket policy, attachments and network reachability need additional reads. Observed IgnorePublicAcls suppresses the ACL hotspot. Encryption read failures stay UNKNOWN. IAM ListRoles supplies limited role inventory; effective permissions and escalation are UNVERIFIED.

Inventory is capped at 50 buckets, 100 security groups and 100 roles with a 30-second deadline and bounded SDK retries/timeouts. Truncation or failures retain collected observations and mark PARTIAL. Calls already in progress can consume their configured timeout. There is no background cloud sync scheduler or full pagination/resource fleet in this release.

Live observations join the same authorized evidence graph and typed asset projections. No name-based code-to-deployment mapping or runtime attack path is fabricated. Live account validation remains a release requirement before describing a connection as verified.
