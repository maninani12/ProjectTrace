"""Native quality CI: ZIPs/reports are inert data; imported builds/tests never run."""

import argparse
import difflib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from analyzers.code_quality.core import compare, gate
from analyzers.code_quality.coverage import import_report
from analyzers.engine import analyze, hash_text, read_zip
from backend.quality_api import sarif


def read_bounded(path, limit):
    if path.stat().st_size > limit:
        raise ValueError("Input exceeds its configured byte limit.")
    value = path.read_bytes()
    if len(value) > limit:
        raise ValueError("Input exceeds its configured byte limit.")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", type=Path, required=True)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--coverage", type=Path)
    parser.add_argument("--coverage-commit")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--sarif", type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(read_bounded(args.profile, 512_000).decode("utf-8")) if args.profile else None
        head_files = read_zip(read_bounded(args.head, 10_000_000), keep_excluded=True)
        head = analyze(head_files, profile={"quality": profile} if profile else None)
        base_files = read_zip(read_bounded(args.base, 10_000_000), keep_excluded=True) if args.base else {}
        baseline = analyze(base_files, profile={"quality": profile} if profile else None) if args.base else None
        changed_lines = {}
        for path, source in head_files.items():
            changed_lines[path] = [
                (j1 + 1, j2)
                for tag, _, _, j1, j2 in difflib.SequenceMatcher(
                    None, base_files.get(path, "").splitlines(), source.splitlines(), autojunk=False
                ).get_opcodes()
                if tag != "equal" and j2 > j1
            ]
        quality = compare(
            head["code_quality"],
            head["findings"],
            baseline["findings"] if baseline else [],
            changed_lines,
            base_id="local-base" if baseline else None,
        )
        baseline_metrics = (
            {(m["path"], m.get("qualified_name", m["name"])): m for m in baseline["quality_metrics"]}
            if baseline
            else {}
        )
        for metric in quality["metrics"]:
            previous = baseline_metrics.get((metric["path"], metric.get("qualified_name", metric["name"])))
            metric["new_code"] = (
                bool(baseline)
                and (not previous or metric["cyclomatic"] > previous["cyclomatic"])
                and any(
                    lo <= metric["end_line"] and hi >= metric["line"]
                    for lo, hi in changed_lines.get(metric["path"], [])
                )
            )
        content_digest = hash_text("\n".join(p + ":" + hash_text(t) for p, t in sorted(head_files.items())))
        if getattr(head_files, "intake", []):
            content_digest = hash_text(content_digest + json.dumps(head_files.intake, sort_keys=True))
        commit = content_digest[:40]
        report = (
            import_report(
                read_bounded(args.coverage, 1_000_000).decode("utf-8"),
                head_files,
                declared_commit=args.coverage_commit,
                snapshot_commit=commit,
                changed_lines=changed_lines,
            )
            if args.coverage
            else None
        )
        result = {
            "gate": gate(quality, head["findings"], report),
            "head_content_digest": commit,
            "coverage_state": report["state"] if report else "NOT_AVAILABLE",
            "analysis_state": quality["state"],
            "quality_findings": sum(f["category"] == "QUALITY" for f in head["findings"]),
            "limitations": quality["limitations"],
        }
        if args.json:
            args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if args.sarif:
            args.sarif.write_text(
                json.dumps(
                    sarif(
                        [f for f in head["findings"] if f["category"] == "QUALITY"], SimpleNamespace(id="local-head")
                    ),
                    indent=2,
                ),
                encoding="utf-8",
            )
        print(json.dumps(result))
        return {"PASS": 0, "WARNING": 0, "FAIL": 2, "REVIEW_REQUIRED": 3}[result["gate"]["status"]]
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(json.dumps({"state": "INVALID_INPUT", "error_type": type(error).__name__}))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
