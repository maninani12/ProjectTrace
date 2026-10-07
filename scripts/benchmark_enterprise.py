"""Labeled synthetic accuracy corpus; never a representative production score."""

import argparse
import hashlib
import json
import platform
import time
from collections import defaultdict
from pathlib import Path

from analyzers.engine import VERSION, analyze


def corpus():
    pairs = [
        (
            "PT-SAST-002",
            "Python",
            "NONE",
            "app.py",
            "import subprocess\nsubprocess.run(command, shell=True)",
            "import subprocess\nsubprocess.run(['echo', 'fixture'], shell=False)",
        ),
        (
            "PT-SAST-003",
            "Python",
            "NONE",
            "app.py",
            "import pickle\npickle.loads(data)",
            "import json\njson.loads(data)",
        ),
        (
            "PT-IAC-001",
            "YAML",
            "Kubernetes",
            "pod.yaml",
            "apiVersion: v1\nkind: Pod\nmetadata: {name: fixture}\nspec:\n  containers:\n  - name: app\n    image: fixture:v1\n    securityContext: {privileged: true}\n",
            "apiVersion: v1\nkind: Pod\nmetadata: {name: fixture}\nspec:\n  containers:\n  - name: app\n    image: fixture:v1\n    securityContext: {privileged: false}\n",
        ),
        (
            "PT-IAC-003",
            "HCL",
            "Terraform",
            "main.tf",
            'resource "aws_s3_bucket" "fixture" { acl = "public-read" }',
            'resource "aws_s3_bucket" "fixture" { acl = "private" }',
        ),
        (
            "PT-IAC-012",
            "YAML",
            "Kubernetes",
            "role.yaml",
            "kind: Role\nmetadata: {name: fixture}\nrules: [{apiGroups: [''], resources: ['pods'], verbs: ['*']}]",
            "kind: Role\nmetadata: {name: fixture}\nrules: [{apiGroups: [''], resources: ['pods'], verbs: ['get']}]",
        ),
        (
            "PT-IAC-014",
            "YAML",
            "Kubernetes",
            "ingress.yaml",
            "kind: Ingress\nmetadata: {name: fixture}\nspec: {rules: []}",
            "kind: Ingress\nmetadata: {name: fixture}\nspec: {tls: [{secretName: fixture}], rules: []}",
        ),
        (
            "PT-IAC-015",
            "Dockerfile",
            "Dockerfile",
            "Dockerfile",
            "FROM scratch\nADD https://example.invalid/app /app\nUSER 65532",
            "FROM scratch\nCOPY app /app\nUSER 65532",
        ),
        (
            "PT-IAC-017",
            "Dockerfile",
            "Dockerfile",
            "Dockerfile",
            "FROM scratch\nCOPY app /app",
            "FROM scratch\nCOPY app /app\nUSER 65532",
        ),
        (
            "PT-IAC-018",
            "JSON",
            "CloudFormation",
            "stack.json",
            '{"Resources":{"Db":{"Type":"AWS::RDS::DBInstance","Properties":{"PubliclyAccessible":true}}}}',
            '{"Resources":{"Db":{"Type":"AWS::RDS::DBInstance","Properties":{"PubliclyAccessible":false}}}}',
        ),
        (
            "PT-IAC-019",
            "HCL",
            "Terraform",
            "main.tf",
            'resource "aws_db_instance" "fixture" { storage_encrypted = false }',
            'resource "aws_db_instance" "fixture" { storage_encrypted = true }',
        ),
        (
            "PT-IAC-007",
            "YAML",
            "Compose",
            "compose.yaml",
            "services:\n  app:\n    image: fixture:v1\n    cap_add: [ALL]",
            "services:\n  app:\n    image: fixture:v1\n    cap_drop: [ALL]",
        ),
    ]
    return [
        {
            "id": f"{rule}:{framework}:{'positive' if expected else 'negative'}",
            "rule": rule,
            "language": lang,
            "framework": framework,
            "path": path,
            "source": source,
            "expected": expected,
        }
        for rule, lang, framework, path, positive, negative in pairs
        for source, expected in ((positive, True), (negative, False))
    ]


def measure():
    cases, groups, observations = corpus(), defaultdict(lambda: {"tp": 0, "tn": 0, "fp": 0, "fn": 0}), []
    for case in cases:
        started = time.perf_counter()
        result = analyze({case["path"]: case["source"]})
        detected = any(f["rule"] == case["rule"] for f in result["findings"])
        key = (case["rule"], case["language"], case["framework"])
        label = "tp" if detected and case["expected"] else "fp" if detected else "fn" if case["expected"] else "tn"
        groups[key][label] += 1
        observations.append(
            {
                "case_id": case["id"],
                "expected": case["expected"],
                "detected": detected,
                "classification": label,
                "elapsed_ms": round(1000 * (time.perf_counter() - started), 3),
                "source_sha256": hashlib.sha256(case["source"].encode()).hexdigest(),
            }
        )
    rows = []
    for (rule, lang, framework), counts in sorted(groups.items()):
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        precision, recall = tp / (tp + fp) if tp + fp else None, tp / (tp + fn) if tp + fn else None
        rows.append(
            {
                "rule": rule,
                "version": VERSION,
                "language": lang,
                "framework": framework,
                **counts,
                "precision": precision,
                "recall": recall,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                "blocking_eligible": False,
                "population": "SYNTHETIC_ONLY_UNQUALIFIED",
            }
        )
    return {
        "schema": "projecttrace-labeled-accuracy-v1",
        "version": VERSION,
        "python": platform.python_version(),
        "corpus_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
        "case_count": len(cases),
        "groups": rows,
        "observations": observations,
        "limitations": [
            "Two manually specified cases per selected rule/framework; no representative repository population.",
            "No universal accuracy percentage. All rules remain unqualified for default blocking.",
            "Separate 3M-line and concurrent-PR deployment benchmarks remain unmeasured.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = measure()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "cases": report["case_count"],
                "groups": len(report["groups"]),
                "fp": sum(row["fp"] for row in report["groups"]),
                "fn": sum(row["fn"] for row in report["groups"]),
                "population": "SYNTHETIC_ONLY_UNQUALIFIED",
            }
        )
    )
