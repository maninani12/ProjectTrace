"""Native static fixture checks and local timings; never execute fixture source.

Run from the project root:
  python -m scripts.benchmark_analyzers --output <absolute-output.json>
This excludes API/database persistence, workers, providers and production load.
"""

import argparse
import io
import json
import math
import platform
import statistics
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from analyzers.engine import VERSION, analyze, python_analysis, read_zip
from analyzers.verifiers import claim_key, verify_claim


def measured(operation, samples):
    durations = []
    result = None
    for _ in range(samples):
        started = time.perf_counter()
        result = operation()
        durations.append((time.perf_counter() - started) * 1000)
    ordered = sorted(durations)
    return result, {
        "samples": samples,
        "median_ms": statistics.median(durations),
        "p95_ms": ordered[math.ceil(samples * 0.95) - 1],
        "minimum_ms": min(durations),
        "maximum_ms": max(durations),
        "samples_ms": durations,
    }


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as stream:
        for path, source in sorted(files.items()):
            stream.writestr(path, source)
    return output.getvalue()


def check_fixture(fixture):
    result = analyze(fixture["files"])
    rules = sorted({finding["rule"] for finding in result["findings"]})
    actual_claims = {
        claim["expected"]: claim["status"] for claim in result["claims"] if claim["origin"] == "DOCUMENTATION"
    }
    dependencies = {(dependency["name"], dependency["version"]) for dependency in result["dependencies"]}
    expected = set(fixture.get("expected_rules", []))
    forbidden = set(fixture.get("forbidden_rules", []))
    missing = sorted(expected - set(rules))
    unexpected = sorted(set(rules) & forbidden)
    claim_errors = [
        expected
        for expected, status in fixture.get("expected_claims", {}).items()
        if actual_claims.get(expected) != status
    ]
    dependency_errors = [
        entry
        for entry in fixture.get("expected_dependencies", [])
        if (entry["name"], entry["version"]) not in dependencies
    ]
    return {
        "name": fixture["name"],
        "passed": not (missing or unexpected or claim_errors or dependency_errors),
        "rules": rules,
        "missing_rules": missing,
        "forbidden_rules_found": unexpected,
        "claim_mismatches": claim_errors,
        "dependency_mismatches": dependency_errors,
        "scope": fixture.get("scope", "Native static patterns; exploitability is unobserved."),
    }


def monorepo_files():
    files = {}
    for service in range(10):
        prefix = f"services/service_{service}"
        files[prefix + "/README.md"] = "Backend uses FastAPI.\n"
        files[prefix + "/requirements.txt"] = "fastapi==0.115.0\n"
        for index in range(40):
            files[f"{prefix}/module_{index}.py"] = (
                f"import fastapi\ndef value_{service}_{index}():\n    return {index}\n"
            )
        for index in range(8):
            files[f"{prefix}/ui_{index}.ts"] = f"export const value_{service}_{index} = {index};\n"
    assert len(files) == 500
    return files


def snapshot_counts(result):
    return {
        "files": len(result["files"]),
        "claims": len(result["claims"]),
        "findings": len(result["findings"]),
        "dependencies": len(result["dependencies"]),
        "reused_files": result["reused_files"],
        "reused_verifications": result["reused_verifications"],
        "reverified_claims": result["reverified_claims"],
        "engine_states": {name: data["state"] for name, data in result["engines"].items()},
    }


def run(samples):
    manifest = json.loads(Path("samples/native_benchmark_manifest.json").read_text(encoding="utf-8"))
    outcomes = [check_fixture(fixture) for fixture in manifest["fixtures"]]
    files = {
        "README.md": "Authentication uses JWT. Backend uses FastAPI. Database uses PostgreSQL.",
        "app.py": "from fastapi import FastAPI\napp=FastAPI()\nDATABASE_URL='postgresql://localhost/fixture'\n@app.get('/health')\ndef health(): return True",
        "auth.py": "import jwt\njwt.decode(token, key, algorithms=['HS256'])",
        "unsafe.py": "import requests\nurl=request.args.get('url')\nrequests.get(url)\ndef query(db, value):\n    return db.execute(f'SELECT * FROM users WHERE id={value}')",
        "requirements.txt": "fastapi==0.115.0\npsycopg==3.2.0",
    }
    blob = archive(files)
    base, full = measured(lambda: analyze(read_zip(blob)), samples)
    cached, cache = measured(
        lambda: analyze(read_zip(blob), base["analysis_cache"], verification_context=base["verification_cache"]),
        samples,
    )
    changed = {
        **files,
        "auth.py": "from starlette.middleware.sessions import SessionMiddleware\napp.add_middleware(SessionMiddleware, secret_key=settings.session_key)",
    }
    changed_blob = archive(changed)
    head, incremental = measured(
        lambda: analyze(
            read_zip(changed_blob), base["analysis_cache"], verification_context=base["verification_cache"]
        ),
        samples,
    )
    _, python_scan = measured(
        lambda: [python_analysis(path, source) for path, source in files.items() if path.endswith(".py")], samples
    )
    declared = [claim for claim in base["claims"] if claim["origin"] == "DOCUMENTATION"]
    _, verification = measured(
        lambda: [verify_claim(claim, base["signals"], base["dependencies"]) for claim in declared], samples
    )
    _, cached_verification = measured(
        lambda: [
            verify_claim(
                claim, base["signals"], base["dependencies"], base["verification_cache"]["claims"].get(claim_key(claim))
            )
            for claim in declared
        ],
        samples,
    )
    large = monorepo_files()
    large_blob = archive(large)
    large_base, large_full = measured(lambda: analyze(read_zip(large_blob)), samples)
    large_cached, large_cache = measured(
        lambda: analyze(
            read_zip(large_blob), large_base["analysis_cache"], verification_context=large_base["verification_cache"]
        ),
        samples,
    )
    false_positive_cases = [
        item for fixture, item in zip(manifest["fixtures"], outcomes, strict=True) if fixture.get("false_positive_trap")
    ]
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "analyzer_version": VERSION,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "scope": "Synthetic bounded local ZIP/static analysis. No fixture code executes. Timings exclude database/API/queue/provider calls and are not production capacity.",
        "percentile_method": "Nearest-rank p95; small-sample tail values are illustrative only.",
        "fixture_manifest": "samples/native_benchmark_manifest.json",
        "fixtures": outcomes,
        "fixture_summary": {
            "total": len(outcomes),
            "passed": sum(item["passed"] for item in outcomes),
            "failed": sum(not item["passed"] for item in outcomes),
            "false_positive_traps": len(false_positive_cases),
            "traps_with_unexpected_findings": sum(bool(item["forbidden_rules_found"]) for item in false_positive_cases),
            "general_false_positive_rate": "UNMEASURED; this small synthetic corpus cannot estimate real-world precision.",
        },
        "timings": {
            "full_zip_and_analysis": full,
            "cached_zip_and_analysis": cache,
            "incremental_zip_and_analysis": incremental,
            "python_quality_and_sast_combined": python_scan,
            "claim_verification": verification,
            "cached_claim_fingerprint_and_verification": cached_verification,
            "500_file_monorepo_zip_and_analysis": large_full,
            "500_file_monorepo_cached_zip_and_analysis": large_cache,
        },
        "observations": {
            "full": snapshot_counts(base),
            "cached": snapshot_counts(cached),
            "incremental": snapshot_counts(head),
            "monorepo": snapshot_counts(large_base),
            "monorepo_cached": snapshot_counts(large_cached),
        },
        "unmeasured": [
            "Database persistence/evidence graph construction",
            "API p50/p95/p99",
            "worker queue delay",
            "OSV refresh/advisory evaluation",
            "live cloud/provider transport",
            "independent JS/Java quality AST parsers",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=12)
    options = parser.parse_args()
    if options.samples < 12:
        parser.error("Use at least 12 measured samples.")
    output = options.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = run(options.samples)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "summary": report["fixture_summary"],
                "median_ms": {name: measurements["median_ms"] for name, measurements in report["timings"].items()},
            }
        )
    )
    if report["fixture_summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
