"""Create a clean source ZIP from tracked source plus non-ignored additions.

Run: python scripts/package_release.py --output /path/to/ProjectTrace-source.zip
Never includes local databases, credentials, uploads, caches or dependencies.
"""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "data",
    "uploads",
    "sessions",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "coverage",
    "test-results",
    "playwright-report",
    "work",
    "outputs",
    ".prerender",
}


def allowed(path):
    return not any(part in EXCLUDED for part in path.parts) and not (
        path.name == ".coverage"
        or path.name.startswith(".env")
        and path.name != ".env.example"
        or path.suffix.lower() in {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".key", ".pem", ".log", ".tsbuildinfo"}
        or path.suffix.lower() == ".zip"
        and path.parent.as_posix() != "frontend/e2e/fixtures"
        or ".db-" in path.name
        or path.name in {"coverage.xml", "credentials.json", "service-account.json"}
    )


def package(output):
    root = Path(__file__).resolve().parents[1]
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = (
        subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root)
        .decode()
        .split("\0")
    )
    names = sorted(
        {
            name
            for name in paths
            if name and allowed(Path(name)) and (root / name).is_file() and not (root / name).is_symlink()
        }
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(root / name, "ProjectTrace/" + name)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise ValueError("Release archive failed integrity verification")
    return {
        "files": len(names),
        "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip(),
        "uncommitted_changes": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root)),
        "file_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
        "paths": names,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.output), indent=2))
