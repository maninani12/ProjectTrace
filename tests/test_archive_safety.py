import io
import stat
import struct
import zipfile

import pytest

from backend.intake_errors import IntakeError
from backend.repository_store import archive_items, limits


def archive(entries, compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as writer:
        for path, value in entries:
            writer.writestr(path, value)
    stream.seek(0)
    return stream


def test_links_are_inert_metadata_and_special_entries_are_rejected():
    link = zipfile.ZipInfo("root/link.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    items = dict(archive_items(archive([(link, "../../outside.py"), ("root/app.py", "pass\n")])))
    assert items["root/link.py"] == {"bytes": 16, "state": "UNSUPPORTED", "source_kind": "SYMLINK"}
    assert items["root/app.py"] == b"pass\n"
    device = zipfile.ZipInfo("device")
    device.create_system = 3
    device.external_attr = stat.S_IFCHR << 16
    with pytest.raises(IntakeError) as failure:
        list(archive_items(archive([(device, b"")])))
    assert failure.value.code == "ARCHIVE_SPECIAL_ENTRY"


@pytest.mark.parametrize("path", ["../escape.py", "/etc/escape", "C:/escape.py", "bad\\escape.py"])
def test_directory_validation_rejects_traversal_before_emitting_source(path):
    stream = archive([("safe.py", b"pass"), (path, b"evil")])
    if "\\" in path:
        stream = io.BytesIO(stream.getvalue().replace(path.replace("\\", "/").encode(), path.encode()))
    with pytest.raises(IntakeError) as failure:
        next(archive_items(stream))
    assert failure.value.code == "ARCHIVE_UNSAFE_PATH"


def test_duplicate_paths_and_aggregate_budgets_report_actual_values():
    with pytest.raises(IntakeError) as duplicate:
        list(archive_items(archive([("app.py", b"pass"), ("./app.py", b"pass")])))
    assert duplicate.value.code == "DUPLICATE_PATH"
    with pytest.raises(IntakeError) as count:
        list(archive_items(archive([("a.py", b"abc"), ("b.py", b"def")]), {**limits(), "files": 1}))
    assert count.value.detail()["actual"] == 2
    assert count.value.detail()["maximum"] == 1
    assert count.value.detail()["budget"] == "REPOSITORY_MAX_FILES"
    with pytest.raises(IntakeError) as total:
        list(archive_items(archive([("a.py", b"abc"), ("b.py", b"def")]), {**limits(), "bytes": 5}))
    assert total.value.detail()["actual"] == 6
    assert total.value.detail()["budget"] == "REPOSITORY_MAX_BYTES"


def test_parser_limit_skips_oversized_files_without_rejecting_archive():
    result = dict(archive_items(archive([("big.py", b"x" * 512_001), ("app.py", b"pass")])))
    assert result["big.py"]["state"] == "SKIPPED_SIZE_LIMIT"
    assert result["big.py"]["bytes"] == 512_001
    assert result["app.py"] == b"pass"


def test_compression_bomb_encrypted_and_corrupt_zip_are_precise():
    with pytest.raises(IntakeError) as bomb:
        list(archive_items(archive([("bomb.py", b"x" * 100_000)], zipfile.ZIP_DEFLATED)))
    assert bomb.value.code == "ARCHIVE_COMPRESSION_RATIO"
    raw = bytearray(archive([("app.py", b"pass")]).getvalue())
    central = raw.index(b"PK\x01\x02")
    struct.pack_into("<H", raw, 6, 1)
    struct.pack_into("<H", raw, central + 8, 1)
    with pytest.raises(IntakeError) as encrypted:
        list(archive_items(io.BytesIO(raw)))
    assert encrypted.value.code == "ARCHIVE_ENCRYPTED_ENTRY"
    with pytest.raises(IntakeError) as corrupt:
        list(archive_items(io.BytesIO(b"invalid zip")))
    assert corrupt.value.code == "ARCHIVE_INVALID"


def test_metadata_preflight_does_not_read_source(monkeypatch):
    stream = archive([("app.py", b"pass")])
    def forbidden(*args, **kwargs):
        pytest.fail("Preflight must not decompress file payloads")
    monkeypatch.setattr(zipfile.ZipFile, "open", forbidden)
    assert list(archive_items(stream, validate_only=True)) == []
