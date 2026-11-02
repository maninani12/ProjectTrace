"""Payload-free byte counts for the historical v1 analysis checkpoint envelope."""

from __future__ import annotations

import json
import time
from collections.abc import Callable

SCHEMA = "projecttrace-checkpoint-size-diagnostic-v1"


class _Progress:
    def __init__(self, checkpoint: Callable[[], object] | None):
        self.checkpoint = checkpoint
        self.steps = 0
        self.next_check = time.monotonic() + 1 if checkpoint else 0

    def tick(self) -> None:
        if self.checkpoint is None:
            return
        self.steps += 1
        current = time.monotonic()
        if self.steps >= 256 or current >= self.next_check:
            self.checkpoint()
            self.steps = 0
            self.next_check = current + 1


def _encoder() -> json.JSONEncoder:
    # Match the published v1 constructor, including all default settings.
    encoder = json.JSONEncoder(sort_keys=True)
    if not (
        encoder.sort_keys is True
        and encoder.ensure_ascii is True
        and encoder.indent is None
        and encoder.check_circular is True
        and encoder.allow_nan is True
        and encoder.skipkeys is False
        and encoder.item_separator == ", "
        and encoder.key_separator == ": "
    ):
        raise RuntimeError("The v1 checkpoint encoder configuration changed.")
    return encoder


def _fragment_length(fragment: str) -> int:
    # v1's ensure_ascii default guarantees ASCII output, whose character count
    # equals its UTF-8 byte count. Avoid a second byte-string copy per fragment.
    if not fragment.isascii():
        raise RuntimeError("The v1 checkpoint encoder emitted a non-ASCII fragment.")
    return len(fragment)


def _v1_envelope(
    result: dict,
    *,
    job_id: str,
    organization_id: str,
    repository_id: str,
    signature: str,
    progress: _Progress,
) -> dict:
    if "files" in result:
        # Match v1's list(result['files']) normalization exactly. This can hold
        # all row references at once, but avoids constructing serialized bytes.
        normalized_files = []
        for item in result["files"]:
            normalized_files.append(item)
            progress.tick()
        normalized_result = {**result, "files": normalized_files}
    else:
        normalized_result = result
    return {
        "schema": "projecttrace-analysis-checkpoint-v1",
        "job_id": job_id,
        "organization_id": organization_id,
        "repository_id": repository_id,
        "signature": signature,
        "result": normalized_result,
    }


def count_v1_envelope_bytes(
    result: dict,
    *,
    job_id: str,
    organization_id: str,
    repository_id: str,
    signature: str,
    checkpoint: Callable[[], object] | None = None,
) -> int:
    """Count exact v1 UTF-8 envelope bytes without retaining serialized output.

    The envelope uses ``JSONEncoder(sort_keys=True)`` with defaults unchanged.
    Counting retains only one encoder fragment at a time, but ``files`` is
    normalized to a complete list, sorted dictionaries
    create the standard encoder's temporary item lists, and a very large
    scalar can still create one correspondingly large fragment. It is not a
    constant-memory guarantee.
    """
    encoder = _encoder()
    progress = _Progress(checkpoint)
    if checkpoint is not None:
        checkpoint()
    envelope = _v1_envelope(
        result,
        job_id=job_id,
        organization_id=organization_id,
        repository_id=repository_id,
        signature=signature,
        progress=progress,
    )
    total = 0
    for fragment in encoder.iterencode(envelope):
        total += _fragment_length(fragment)
        progress.tick()
    return total


def v1_size_diagnostic(
    result: dict,
    *,
    job_id: str,
    organization_id: str,
    repository_id: str,
    signature: str,
    limit_bytes: int | None = None,
    checkpoint: Callable[[], object] | None = None,
) -> dict[str, int | bool | str]:
    """Return an allowlisted aggregate receipt; never include result values."""
    if limit_bytes is None:
        from backend.analysis_checkpoints import budget

        limit_bytes = budget()
    if type(limit_bytes) is not int or limit_bytes <= 0:
        raise ValueError("Checkpoint diagnostic limit must be a positive integer.")
    actual_bytes = count_v1_envelope_bytes(
        result,
        job_id=job_id,
        organization_id=organization_id,
        repository_id=repository_id,
        signature=signature,
        checkpoint=checkpoint,
    )
    return {
        "schema": SCHEMA,
        "actual_bytes": actual_bytes,
        "limit_bytes": limit_bytes,
        "over_budget": actual_bytes > limit_bytes,
    }
