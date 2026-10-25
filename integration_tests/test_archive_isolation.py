"""Required archive containment and actual duplex byte-range acceptance."""

import io
import os
import subprocess
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from analyzers import sandbox
from analyzers.archive_transport import archive_items as isolated_items
from analyzers.engine import read_zip
from backend.encrypted_archive import EncryptedArchive
from backend.repository_store import archive_items, limits
from integration_tests.test_parser_isolation import required_boundary  # noqa: F401 -- required autouse fixture


def owned_zip(files):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, value in files.items():
            archive.writestr(path, value)
    return target.getvalue()


def test_encrypted_stream_never_parses_archives_or_decompresses_in_host(tmp_path, monkeypatch):
    # Random data prevents compression-ratio policy from masking the IPC case.
    files = {f"owned/{n}.bin": os.urandom(400_000) for n in range(30)}
    files["owned/日本語.py"] = "print('owned')\n".encode()
    payload = owned_zip(files)  # >10 MB exercises the streaming, not legacy, path.
    monkeypatch.setenv("SOURCE_UPLOAD_DIR", str(tmp_path / "encrypted"))
    from cryptography.fernet import Fernet
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())
    with EncryptedArchive(20_000_000) as spool:
        for offset in range(0, len(payload), 512_000):
            spool.append(payload[offset:offset + 512_000])
        reads, original = [], spool.read
        def bounded(size=-1):
            reads.append(size)
            assert 0 <= size <= 512_000
            return original(size)
        spool.read = bounded
        def forbidden(*_args, **_kwargs):
            raise AssertionError("Archive interpretation escaped into coordinator")
        monkeypatch.setattr(zipfile, "ZipFile", forbidden)
        monkeypatch.setattr(zlib, "decompressobj", forbidden)
        assert list(archive_items(spool, validate_only=True)) == []
        assert dict(archive_items(spool)) == files
        assert reads and max(reads) <= 512_000
        assert all(path.suffix == ".enc" for path in spool.root.iterdir())


def test_legacy_zip_preserves_source_and_intake_without_host_zip_parser(monkeypatch):
    payload = owned_zip({"app.py": "pass\n", "blob.bin": b"\x00\xff"})
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "development")
    baseline = read_zip(payload, keep_excluded=True)
    monkeypatch.setenv("PROJECTTRACE_PARSER_ISOLATION", "required")
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Legacy ZIP parsed in coordinator")
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    result = read_zip(payload, keep_excluded=True)
    assert result == baseline and result.intake == baseline.intake


def test_concurrent_archive_streams_cannot_exchange_tenant_bytes():
    payloads = [owned_zip({"app.py": f"tenant='{tenant}'\n"}) for tenant in ("A", "B")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(lambda raw: dict(archive_items(io.BytesIO(raw))), payload) for payload in payloads]
        results = [future.result() for future in futures]
    assert results == [{"app.py": b"tenant='A'\n"}, {"app.py": b"tenant='B'\n"}]


@pytest.mark.parametrize("operation,code", [("probe_crash", "ARCHIVE_HELPER_CRASH"),
                                           ("probe_timeout", "ARCHIVE_HELPER_TIMEOUT")])
def test_actual_archive_worker_loss_never_completes_intake(monkeypatch, operation, code):
    payload = owned_zip({"app.py": "pass"})
    start = subprocess.Popen
    def failed(command, **kwargs):
        return start([*command[:-1], operation], **kwargs)
    monkeypatch.setattr(subprocess, "Popen", failed)
    with pytest.raises(sandbox.SandboxFailure, match=code):
        list(isolated_items(io.BytesIO(payload), limits(), seconds=5))
