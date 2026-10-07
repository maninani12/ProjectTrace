"""Fetch explicitly selected public fixtures as inert text, pinned to commits."""

import hashlib
import json
from pathlib import Path

import httpx


def fetch():
    root = Path(__file__).resolve().parents[1] / "benchmarks" / "accuracy-corpus" / "opensource"
    root.mkdir(parents=True, exist_ok=True)
    sources = []
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        for repo, ref, paths, license_path in (
            ("python/cpython", "v3.14.3", ("Lib/urllib/parse.py", "Lib/ipaddress.py"), "LICENSE"),
            ("django/django", "5.2", ("django/utils/html.py", "django/utils/text.py"), "LICENSE"),
        ):
            response = client.get(f"https://api.github.com/repos/{repo}/commits/{ref}")
            response.raise_for_status()
            commit = response.json()["sha"]
            for path in (*paths, license_path):
                response = client.get(f"https://raw.githubusercontent.com/{repo}/{commit}/{path}")
                response.raise_for_status()
                if len(response.content) > 512000:
                    raise ValueError("Public fixture exceeds bounded file budget")
                filename = repo.replace("/", "-") + "-" + path.replace("/", "-") + ".txt"
                (root / filename).write_bytes(response.content)
                sources.append(
                    {
                        "repository": repo,
                        "ref": ref,
                        "commit": commit,
                        "path": path,
                        "file": filename,
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                        "license_file": path == license_path,
                        "source_url": f"https://github.com/{repo}/blob/{commit}/{path}",
                    }
                )
    (root / "manifest.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "files": len(sources),
                "repositories": sorted({r["repository"] for r in sources}),
                "manifest": str(root / "manifest.json"),
            }
        )
    )


if __name__ == "__main__":
    fetch()
