import gzip
import hashlib
import json
from pathlib import Path


def test_pinned_manifest_hashes_every_member_without_source_execution():
    raw = gzip.decompress((Path(__file__).resolve().parents[1] / "docs/evidence/SCALE001_OPENMETADATA_MANIFEST.jsonl.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == "081071ce099d103270175ab53ef12842586d7b0f1ee0c58dadbc3654a2246a89"
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == len({r["path"] for r in rows}) == 21_636
    assert sum(r["bytes"] for r in rows) == 330_420_155
    assert sum(r["kind"] == "SYMLINK" for r in rows) == 38
    assert sum(r["kind"] == "FILE" and r["bytes"] > 512_000 for r in rows) == 32
    assert all(len(r["sha256"]) == 64 and set(r["sha256"]) <= set("0123456789abcdef") for r in rows)
    assert all(r["path"].startswith("OpenMetadata-b1fab2bc21c63335dead4daaaa28194c9878e9bf/") for r in rows)
    assert [r["path"] for r in rows] == sorted(r["path"] for r in rows)
