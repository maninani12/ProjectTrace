"""Pure archive policy, called only inside containment in required mode."""

import zipfile
import zlib

from analyzers.engine import safe_path
from backend.intake_errors import IntakeError


def archive_items(stream, policy, *, validate_only=False):
    import stat

    # Check the bounded end-directory metadata before ZipFile allocates its
    # central-directory objects. ZIP64 metadata is handled by the stdlib reader.
    end = zipfile._EndRecData(stream)
    if end is None:
        raise IntakeError("ARCHIVE_INVALID", "Archive has no valid ZIP end directory.")
    metadata_bytes = end[zipfile._ECD_SIZE]
    if metadata_bytes > 64_000_000:
        raise IntakeError("ARCHIVE_METADATA_BYTES", "Archive directory exceeds its metadata budget.",
                          budget="ARCHIVE_METADATA_BYTES", actual=metadata_bytes, maximum=64_000_000)
    declared_count = end[zipfile._ECD_ENTRIES_TOTAL]
    if declared_count > policy["files"]:
        raise IntakeError("ARCHIVE_ENTRY_COUNT", "Archive directory exceeds the inventory quota.",
                          budget="REPOSITORY_MAX_FILES", actual=declared_count, maximum=policy["files"])
    if end[zipfile._ECD_DISK_NUMBER] or end[zipfile._ECD_DISK_START]:
        raise IntakeError("ARCHIVE_MULTIDISK", "Multi-volume ZIP archives are unsupported.")
    with zipfile.ZipFile(stream) as archive:
        entries = archive.infolist()
        if len(entries) > policy["files"]:
            raise IntakeError("ARCHIVE_ENTRY_COUNT", "Archive directory exceeds the inventory quota.",
                              budget="REPOSITORY_MAX_FILES", actual=len(entries), maximum=policy["files"])
        total, seen = 0, set()
        # Validate the entire directory before decompressing any eligible entry.
        for entry in entries:
            try:
                safe_path(entry.orig_filename)
                path = str(safe_path(entry.filename))
            except ValueError:
                raise IntakeError("ARCHIVE_UNSAFE_PATH", "Archive contains an invalid path or path traversal.") from None
            if path in seen:
                raise IntakeError("DUPLICATE_PATH", "Archive contains duplicate canonical paths.")
            seen.add(path)
            if entry.flag_bits & 1:
                raise IntakeError("ARCHIVE_ENCRYPTED_ENTRY", "Encrypted ZIP entries cannot be inspected safely.",
                                  remediation="Export an unencrypted source-only ZIP and retry.")
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if mode not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
                raise IntakeError("ARCHIVE_SPECIAL_ENTRY", "Archive contains an unsupported device or special entry.")
            if entry.is_dir():
                continue
            total += entry.file_size
            if total > policy["bytes"]:
                raise IntakeError("REPOSITORY_UNCOMPRESSED_BYTES", "Archive exceeds its uncompressed byte quota.",
                                  budget="REPOSITORY_MAX_BYTES", actual=total, maximum=policy["bytes"],
                                  remediation="Import a bounded source component without generated/build output.")
            if entry.file_size > max(entry.compress_size, 1) * 200:
                raise IntakeError("ARCHIVE_COMPRESSION_RATIO", "Archive entry exceeds the compression ratio policy.",
                                  budget="ARCHIVE_MAX_COMPRESSION_RATIO", actual=round(entry.file_size / max(entry.compress_size, 1), 2),
                                  maximum=200)
        if validate_only:
            return
        for entry in entries:
            if entry.is_dir():
                continue
            path = str(safe_path(entry.filename))
            if stat.S_ISLNK(entry.external_attr >> 16):
                # Retain only the name/type/declared size. Never read a target,
                # extract anything, resolve a link or follow a filesystem path.
                yield path, {"bytes": entry.file_size, "state": "UNSUPPORTED", "source_kind": "SYMLINK"}
                continue
            if entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                yield path, {"bytes": entry.file_size, "state": "UNSUPPORTED", "source_kind": "ZIP_COMPRESSION_METHOD"}
                continue
            if entry.file_size > policy["file_bytes"]:
                yield path, {"bytes": entry.file_size, "state": "SKIPPED_SIZE_LIMIT"}
            else:
                try:
                    with archive.open(entry) as source:
                        raw = source.read(policy["file_bytes"] + 1)
                except (zipfile.BadZipFile, EOFError, RuntimeError, OSError, zlib.error) as error:
                    raise IntakeError("ARCHIVE_ENTRY_CORRUPT", "Archive entry failed its ZIP integrity check.") from error
                if len(raw) != entry.file_size or len(raw) > policy["file_bytes"]:
                    raise IntakeError("ARCHIVE_ENTRY_SIZE", "Archive entry size is inconsistent with its directory.")
                yield path, raw
