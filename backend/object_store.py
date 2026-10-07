"""S3-compatible storage receives authenticated ciphertext only, under tenant-separated keys."""

import hashlib
import os
import re
from functools import lru_cache
from urllib.parse import urlsplit

from integrations.secure_http import destination


@lru_cache(maxsize=4)
def client(endpoint, region, ca_file, allowed_hosts):
    import boto3
    from botocore.config import Config

    result = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        verify=ca_file or True,
        config=Config(
            connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}, proxies={}, s3={"addressing_style": "path"}
        ),
    )
    host, port = destination(endpoint, set(allowed_hosts))

    def approve(request, **_kwargs):
        parsed = urlsplit(request.url)
        if parsed.scheme != "https" or parsed.hostname != host or (parsed.port or 443) != port:
            raise ValueError("Object storage transport escaped its operator-approved endpoint.")

    result.meta.events.register("before-send.s3", approve)
    return result


class EncryptedObjectStore:
    def __init__(self):
        endpoint = os.environ.get("SOURCE_S3_ENDPOINT", "")
        hosts = tuple(
            sorted(h.strip().lower() for h in os.getenv("SOURCE_S3_ALLOWED_HOSTS", "").split(",") if h.strip())
        )
        destination(endpoint, set(hosts))
        self.bucket = os.getenv("SOURCE_S3_BUCKET", "")
        self.prefix = os.getenv("SOURCE_S3_PREFIX", "projecttrace/source-blobs").strip("/")
        self.kms = os.getenv("SOURCE_S3_KMS_KEY_ID", "")
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", self.bucket)
            or not re.fullmatch(r"[A-Za-z0-9/_-]{1,150}", self.prefix)
            or len(self.kms) > 512
        ):
            raise ValueError("Object storage bucket/prefix/KMS configuration is invalid.")
        self.client = client(
            endpoint, os.getenv("SOURCE_S3_REGION", "us-east-1"), os.getenv("SOURCE_S3_CA_BUNDLE_FILE", ""), hosts
        )

    def key(self, organization_id, digest):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Object content identity is invalid.")
        tenant = hashlib.sha256(organization_id.encode()).hexdigest()
        return f"{self.prefix}/{tenant}/{digest[:2]}/{digest}.enc"

    def put(self, organization_id, digest, ciphertext):
        if len(ciphertext) > 700000:
            raise ValueError("Object ciphertext budget exceeded.")
        options = (
            {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms}
            if self.kms
            else {"ServerSideEncryption": "AES256"}
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.key(organization_id, digest),
            Body=ciphertext,
            ContentType="application/octet-stream",
            **options,
        )

    def read(self, organization_id, digest):
        body = None
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=self.key(organization_id, digest))
            body = result["Body"]
            value = body.read(700001)
            if len(value) > 700000:
                raise ValueError()
            return value
        except Exception:
            raise ValueError("Encrypted object is unavailable or exceeded its bounded read budget.") from None
        finally:
            if body is not None:
                body.close()
