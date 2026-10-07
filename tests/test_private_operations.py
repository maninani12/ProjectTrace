import io
import json
import os
import sqlite3

import pytest
import yaml
from cryptography.fernet import Fernet

from backend.local_backup import backup_local, restore_local
from backend.repository_store import BlobStore
from backend.settings import load_secrets, validate_production
from tests.test_repository_store import captured
from tests.test_repository_store import storage as storage


def test_s3_adapter_keeps_tenant_keys_and_sends_only_authenticated_ciphertext(storage, monkeypatch):
    from backend import object_store

    objects, writes = {}, []

    class Client:
        def put_object(self, **kwargs):
            writes.append(kwargs)
            objects[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(objects[kwargs["Key"]])}

    monkeypatch.setattr(object_store, "client", lambda *args: Client())
    monkeypatch.setenv("SOURCE_BLOB_BACKEND", "s3")
    monkeypatch.setenv("SOURCE_S3_ENDPOINT", "https://storage.example")
    monkeypatch.setenv("SOURCE_S3_ALLOWED_HOSTS", "storage.example")
    monkeypatch.setenv("SOURCE_S3_BUCKET", "controlled-private")
    monkeypatch.setenv("SOURCE_S3_KMS_KEY_ID", "controlled-kms-key")
    db = storage[0]
    store = BlobStore()
    raw = b"owned confidential fixture"
    digest, reused = store.put(db, "tenant", raw)
    assert not reused and raw not in writes[0]["Body"]
    assert writes[0]["ServerSideEncryption"] == "aws:kms"
    assert store.read("tenant", digest) == raw
    assert store.put(db, "tenant", raw) == (digest, True)
    store.put(db, "other", raw)
    assert len(objects) == 2 and store.remote.key("tenant", digest) != store.remote.key("other", digest)
    objects[store.remote.key("tenant", digest)] = b"invalid ciphertext"
    with pytest.raises(ValueError):
        store.read("tenant", digest)


def test_secret_file_loading_bounds_conflicts_and_production_tls(tmp_path, monkeypatch):
    secret = tmp_path / "key"
    key = Fernet.generate_key().decode()
    secret.write_text(key)
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", "")
    monkeypatch.setenv("ANALYSIS_INPUT_KEY_FILE", str(secret))
    load_secrets()
    assert os.environ["ANALYSIS_INPUT_KEY"] == key
    secret.write_text("conflicting-value")
    with pytest.raises(RuntimeError):
        load_secrets()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://owned@database.example/projecttrace?sslmode=verify-full")
    monkeypatch.setenv("REDIS_URL", "rediss://redis.example:6380/0?ssl_cert_reqs=required")
    monkeypatch.setenv("CORS_ORIGINS", "https://projecttrace.example")
    monkeypatch.setenv("JOB_MODE", "celery")
    validate_production()
    monkeypatch.setenv("REDIS_URL", "redis://redis.example/0")
    with pytest.raises(RuntimeError):
        validate_production()


def test_local_recovery_bundle_restores_snapshots_and_encrypted_evidence(storage, tmp_path):
    from backend.domain import persist_analysis

    db, user, repo = storage
    files = captured(storage, {"app.py": "def run(value):\n    return eval(value)\n"})
    snapshot = persist_analysis(db, user, repo, files)
    db.commit()
    key = tmp_path / "operator.key"
    key.write_text(os.environ["ANALYSIS_INPUT_KEY"])
    bundle, restored = tmp_path / "private-backup", tmp_path / "private-restored"
    manifest = backup_local(tmp_path / "source.db", tmp_path / "blobs", bundle, key)
    assert manifest["encrypted_blobs"] > 0 and not manifest["key_included"]
    assert restore_local(bundle, restored, key)["state"] == "VERIFIED_LOCAL_RESTORE"
    with sqlite3.connect(restored / "database.db") as recovered:
        row = recovered.execute("SELECT data FROM records WHERE id=?", (snapshot.id,)).fetchone()
        assert json.loads(row[0])["source_inventory_id"] == files.inventory_id
        assert recovered.execute("PRAGMA foreign_key_check").fetchone() is None
    with pytest.raises(ValueError):
        restore_local(bundle, restored, key)
    # A forged absolute/parent path must be rejected before writing any destination.
    manifest["files"]["../escape"] = "0" * 64
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        restore_local(bundle, tmp_path / "unsafe-restored", key)
    assert not (tmp_path / "unsafe-restored").exists()


def test_rotation_retains_content_identity_and_removes_need_for_old_key(storage, monkeypatch):
    from scripts.rotate_analysis_key import rotate

    db, user, repo = storage
    files = captured(storage, {"app.py": "pass\n"})
    db.commit()
    digest = files.hash_for("app.py")
    old = os.environ["ANALYSIS_INPUT_KEY"]
    new = Fernet.generate_key().decode()
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", new)
    monkeypatch.setenv("ANALYSIS_PREVIOUS_KEYS", json.dumps([old]))
    assert BlobStore().read(user.organization_id, digest) == b"pass\n"
    assert rotate(db)["applied"] is False
    assert rotate(db, apply=True)["applied"] is True
    monkeypatch.setenv("ANALYSIS_PREVIOUS_KEYS", "[]")
    assert BlobStore().read(user.organization_id, digest) == b"pass\n"


def test_private_manifests_keep_closed_network_and_restricted_workloads():
    from pathlib import Path

    documents = list(yaml.safe_load_all(Path("infrastructure/kubernetes/production.yaml").read_text()))
    workloads = [item for item in documents if item["kind"] in {"Deployment", "Job"}]
    assert len(workloads) == 6
    for item in workloads:
        pod = item["spec"]["template"]["spec"]
        assert pod["automountServiceAccountToken"] is False and pod["securityContext"]["runAsNonRoot"]
        for container in pod["containers"]:
            assert container["securityContext"]["readOnlyRootFilesystem"]
            assert container["securityContext"]["allowPrivilegeEscalation"] is False
            assert container["resources"]["limits"]["memory"]
    deny = next(
        item
        for item in documents
        if item["kind"] == "NetworkPolicy" and item["metadata"]["name"] == "projecttrace-default-deny"
    )
    assert "ingress" not in deny["spec"] and "egress" not in deny["spec"]
