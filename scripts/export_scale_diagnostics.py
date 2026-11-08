"""Validate and project two fixed, candidate-only SCALE artifact receipts."""

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from scripts.qualify_scale_workload import ARCHIVE_SHA
from scripts.scale_diagnostic import MAX_RECEIPT_BYTES

NATIVE = "scale-diagnostic-native.json"
RESOURCES = "scale-diagnostic-resources.json"
FORMATS = {
    NATIVE: ("projecttrace-scale-native-diagnostic-v1", ("routes", "packets", "spans", "gc", "counts", "overhead")),
    RESOURCES: ("projecttrace-scale-resource-diagnostic-v1", ("stage_wall_ns", "cgroup", "cgroup_scope")),
}
COMMON = ("identity", "state", "failure_code", "stage", "elapsed_ns")


def unique(pairs):
    values = dict(pairs)
    if len(values) != len(pairs):
        raise ValueError("Duplicate diagnostic fields.")
    return values


def read_snapshot(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECEIPT_BYTES:
            raise ValueError("Invalid diagnostic file type or size.")
        raw = stream.read(MAX_RECEIPT_BYTES + 1)
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError("Oversized diagnostic snapshot.")
    return json.loads(raw, object_pairs_hook=unique)


def export_snapshots(source, destination, validator, identity):
    final = destination / "receipts"
    scratch = destination / ".pending"
    if any(path.exists() or path.is_symlink() for path in (final, scratch)):
        raise ValueError("Use a fresh diagnostic export directory.")
    phases, rejected = {}, False
    for phase in ("cold", "warm"):
        try:
            row = read_snapshot(source / f"scale-diagnostic-{phase}.json")
        except FileNotFoundError:
            phases[phase] = ("MISSING", None)
            continue
        except (OSError, ValueError, RecursionError):
            row = None
        try:
            validator.validate(row)
            if row["identity"] != {**identity, "revision": "candidate", "cache": phase}:
                raise ValueError("Unexpected diagnostic identity.")
        except (ValidationError, ValueError, RecursionError):
            phases[phase] = ("REJECTED", None)
            rejected = True
            continue
        status = "INCOMPLETE" if row["state"] == "RUNNING" or row["counts"].get("write_errors") else "TERMINAL"
        phases[phase] = (status, row)

    if not any(row is not None for _, row in phases.values()):
        return not rejected

    # Serialize both projections before creating anything in the upload path.
    payloads = {}
    for name, (schema, keys) in FORMATS.items():
        payload = {"schema": schema, "input_schema": "projecttrace-scale-diagnostic-v1", "phases": {
            phase: {"capture": status, "observation": None if row is None else {key: row[key] for key in COMMON + keys}}
            for phase, (status, row) in phases.items()
        }}
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        if len(data) > MAX_RECEIPT_BYTES:
            raise ValueError("Diagnostic projection exceeds its byte budget.")
        payloads[name] = data

    scratch.mkdir(mode=0o700)
    try:
        for name, data in payloads.items():
            (scratch / name).write_bytes(data)
        scratch.rename(final)
    finally:
        if scratch.is_dir():
            for name in FORMATS:
                (scratch / name).unlink(missing_ok=True)
            scratch.rmdir()
    return not rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_sha256")
    parser.add_argument("image_sha256")
    parser.add_argument("--slice-sha256", default=ARCHIVE_SHA)
    args = parser.parse_args()
    identity = vars(args)
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in identity.values()):
        parser.error("Diagnostic identities require SHA-256 hex digests.")
    try:
        schema = json.loads(Path("/receipt-schema.json").read_bytes())
        ok = export_snapshots(Path("/"), Path("/diagnostic-export"), Draft202012Validator(schema), identity)
    except (OSError, ValueError, RecursionError):
        ok = False
    if not ok:
        print("Candidate diagnostic export rejected invalid or unavailable output.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
