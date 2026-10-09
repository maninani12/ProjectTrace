import pytest

from scripts.dev_workers import ensure_no_existing_worker, missing_credentials, validate_local, validate_redis_container


def test_development_bootstrap_refuses_production_and_nonlocal_or_credentialed_brokers():
    validate_local({})
    for environment in ({"APP_ENV": "production"}, {"REDIS_URL": "redis://remote.example:6379/0"}, {"REDIS_URL": "redis://user:secret@127.0.0.1:6379/0"}):
        with pytest.raises(ValueError):
            validate_local(environment)


def test_preflight_names_missing_references_without_returning_values():
    metadata = [{"enabled": True, "private_key_ref": "ENV:SCM_FIXTURE_KEY", "webhook_secret_ref": "ENV:SCM_FIXTURE_WEBHOOK"}]
    assert missing_credentials(metadata, {"SCM_FIXTURE_KEY": "synthetic"}) == ["SCM_FIXTURE_WEBHOOK"]
    assert missing_credentials(metadata, {"SCM_FIXTURE_KEY": "synthetic", "SCM_FIXTURE_WEBHOOK": "synthetic"}) == []
    assert missing_credentials([{**metadata[0], "enabled": False}], {}) == []
    with pytest.raises(ValueError):
        missing_credentials([{**metadata[0], "private_key_ref": "ENV:DATABASE_URL"}], {})


def test_redis_reuse_requires_exact_local_binding_and_expected_image():
    data = {"HostConfig": {"PortBindings": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6379"}]}}, "Config": {"Image": "redis:7-alpine"}}
    validate_redis_container(data)
    for binding in ([{"HostIp": "0.0.0.0", "HostPort": "6379"}], [{"HostIp": "::", "HostPort": "6379"}], []):
        with pytest.raises(ValueError):
            validate_redis_container({**data, "HostConfig": {"PortBindings": {"6379/tcp": binding}}})
    with pytest.raises(ValueError):
        validate_redis_container({**data, "Config": {"Image": "unknown/image"}})


def test_busy_existing_solo_worker_is_not_duplicated_when_control_cannot_reply(monkeypatch):
    from types import SimpleNamespace

    def unavailable_ping(**options):
        raise AssertionError("A busy existing worker must not depend on control ping.")

    monkeypatch.setattr("scripts.dev_workers.local_process_running", lambda role: role == "worker")
    with pytest.raises(ValueError, match="worker already exists"):
        ensure_no_existing_worker(SimpleNamespace(control=SimpleNamespace(ping=unavailable_ping)))
