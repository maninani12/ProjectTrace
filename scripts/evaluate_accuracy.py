"""Versioned labeled evaluation. Fixtures and public source are never executed."""

import argparse
import hashlib
import json
import math
import platform
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from analyzers.code_quality.rules import DEFINITIONS
from analyzers.engine import PARSER_SIGNATURE, VERSION, analyze
from backend.db import Base, Organization, Repository, User, make_engine
from backend.domain import persist_analysis
from scripts.benchmark_enterprise import corpus as infrastructure_corpus
from tests.test_code_quality import RULE_CASES

ROOT = Path(__file__).resolve().parents[1]


def cases():
    result = []

    def pair(rule, domain, language, framework, path, positive, negative, tier=1):
        for source, expected in ((positive, True), (negative, False)):
            result.append(
                {
                    "id": f"{domain}:{rule}:{framework}:{len(result)}",
                    "rule": rule,
                    "domain": domain,
                    "language": language,
                    "framework": framework,
                    "files": {path: source},
                    "expected": expected,
                    "tier": tier,
                    "predicate": "finding",
                }
            )

    for item in infrastructure_corpus():
        result.append(
            {
                **item,
                "domain": "IaC" if item["rule"].startswith("PT-IAC") else "SAST",
                "tier": 1,
                "files": {item["path"]: item["source"]},
                "predicate": "finding",
            }
        )
    for suffix, path, positive, negative in RULE_CASES:
        rule = "PT-QUALITY-" + suffix
        pair(
            rule,
            "Reliability" if DEFINITIONS[rule][1] == "RELIABILITY" else "Code Quality",
            "Python" if path.endswith(".py") else "JavaScript",
            "NONE",
            path,
            positive,
            negative,
        )
    pair(
        "PT-QUALITY-013", "Code Quality", "Python", "NONE", "app.py", "\n".join(f"v{i}={i}" for i in range(1001)), "x=1"
    )
    pair(
        "PT-SAST-001",
        "SAST",
        "Python",
        "DBAPI",
        "app.py",
        "def work(db, x):\n    db.execute(f'select * from users where id={x}')",
        "def work(db, x):\n    db.execute('select * from users where id=?', (x,))",
        3,
    )
    pair(
        "PT-SAST-004",
        "SAST",
        "Python",
        "hashlib",
        "app.py",
        "import hashlib\nhashlib.md5(data)",
        "import hashlib\nhashlib.sha256(data)",
        3,
    )
    pair(
        "PT-SAST-005",
        "SAST",
        "Python",
        "builtin-eval",
        "app.py",
        "eval(user_input)",
        "def eval(value):\n    return value\neval(user_input)",
    )
    pair(
        "PT-SAST-005",
        "SAST",
        "JavaScript",
        "builtin-eval",
        "app.js",
        "function work(value){ eval(value); }",
        "function eval(value) { return value; } eval('safe');",
    )
    pair(
        "PT-SAST-006",
        "SAST",
        "TypeScript",
        "DOMPurify",
        "app.ts",
        "node.innerHTML = requestValue;",
        "node.innerHTML = DOMPurify.sanitize(requestValue);",
        3,
    )
    pair(
        "PT-SECRET-001",
        "Secrets",
        "Configuration",
        "ENV",
        ".env",
        "API_KEY=ghp_synthetic_benchmark_token_123456789",
        "API_KEY=${FROM_SECRET_MANAGER}",
    )
    for rule, domain, files, expected, predicate in (
        ("CLAIM_EXTRACTION", "Claim extraction", {"README.md": "Backend uses FastAPI."}, True, "document_claim"),
        ("CLAIM_EXTRACTION", "Claim extraction", {"README.md": "This project is an example."}, False, "document_claim"),
        (
            "CLAIM_VERIFICATION",
            "Claim verification",
            {"README.md": "Backend uses FastAPI.", "app.py": "from fastapi import FastAPI\napp = FastAPI()"},
            True,
            "verified",
        ),
        (
            "CLAIM_VERIFICATION",
            "Claim verification",
            {"README.md": "Backend uses FastAPI.", "app.py": "pass"},
            False,
            "verified",
        ),
        (
            "CONTRADICTION",
            "Contradiction detection",
            {
                "README.md": "Authentication uses JWT.",
                "app.py": "from fastapi import FastAPI\nfrom starlette.middleware.sessions import SessionMiddleware\napp=FastAPI()\napp.add_middleware(SessionMiddleware, secret_key='synthetic_fixture_123456789')",
            },
            True,
            "contradicted",
        ),
        (
            "CONTRADICTION",
            "Contradiction detection",
            {"README.md": "Authentication uses JWT.", "app.py": "import jwt\njwt.decode(token,key)"},
            False,
            "contradicted",
        ),
    ):
        result.append(
            {
                "id": f"{rule}:{expected}",
                "rule": rule,
                "domain": domain,
                "files": files,
                "expected": expected,
                "predicate": predicate,
                "tier": 1,
                "language": "Python / Markdown",
                "framework": "FastAPI",
            }
        )
    manifest_path = ROOT / "benchmarks/accuracy-corpus/opensource/manifest.json"
    if manifest_path.exists():
        for item in json.loads(manifest_path.read_text(encoding="utf-8")):
            if item["license_file"]:
                continue
            source = (manifest_path.parent / item["file"]).read_text(encoding="utf-8")
            if hashlib.sha256(source.encode()).hexdigest() != item["sha256"]:
                raise ValueError("Public fixture hash mismatch")
            result.append(
                {
                    "id": "public:" + item["repository"] + ":" + item["path"],
                    "rule": "PT-QUALITY-011",
                    "domain": "Reliability",
                    "files": {item["path"]: source},
                    "expected": False,
                    "predicate": "finding",
                    "tier": 2,
                    "language": "Python",
                    "framework": item["repository"],
                    "provenance": item,
                    "label_reason": "Selected functions have no mutable list/dict/set literal default parameters; negative-only curated slice.",
                }
            )
    return result


def evaluate(case):
    result = analyze(case["files"])
    predicate = case["predicate"]
    if predicate == "finding":
        return any(f["rule"] == case["rule"] for f in result["findings"]), result["warnings"]
    docs = [c for c in result["claims"] if c.get("origin") == "DOCUMENTATION"]
    return bool(docs) if predicate == "document_claim" else any(
        c["status"] == ("VERIFIED" if predicate == "verified" else "CONTRADICTED") for c in docs
    ), result["warnings"]


def graph_cases():
    observations = []
    with tempfile.TemporaryDirectory(prefix="projecttrace-accuracy-") as temporary:
        engine = make_engine("sqlite:///" + str(Path(temporary) / "fixture.db").replace("\\", "/"))
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory() as db:
            db.add(Organization(id="accuracy", name="Owned accuracy fixtures"))
            db.flush()
            user = User(
                id="accuracy-user",
                organization_id="accuracy",
                email="fixture@example.invalid",
                password_hash="inert-no-login",
                role="ADMIN",
            )
            repository = Repository(
                id="accuracy-repo",
                organization_id="accuracy",
                name="Owned fixtures",
                system="Fixture",
                component="Fixture",
                owner="Fixture",
                provider="LOCAL",
            )
            db.add_all([user, repository])
            db.flush()
            original = {
                "README.md": "Authentication uses JWT. Backend uses FastAPI.",
                "auth.py": "import jwt\njwt.decode(token,key)",
                "app.py": "from fastapi import FastAPI\napp = FastAPI()",
            }
            base = persist_analysis(db, user, repository, original, git_commit="a" * 40)
            db.commit()
            for expected, head_files in (
                (True, {p: s for p, s in original.items() if p != "auth.py"}),
                (False, {**original, "notes.txt": "Unrelated edit"}),
            ):
                head = persist_analysis(
                    db, user, repository, head_files, base_id=base.id, git_commit=("b" if expected else "c") * 40
                )
                db.commit()
                for domain, detected in (
                    ("Drift detection", bool(head.data["drifts"])),
                    (
                        "Impact relationship",
                        any(
                            c["id"] in head.data["impact"]["affected_claims"]
                            for c in head.data["claims"]
                            if c.get("expected") == "jwt"
                        ),
                    ),
                ):
                    observations.append(
                        {
                            "id": f"{domain}:{expected}",
                            "rule": domain.upper().replace(" ", "_"),
                            "domain": domain,
                            "language": "Python / Markdown",
                            "framework": "JWT",
                            "tier": 1,
                            "expected": expected,
                            "detected": detected,
                        }
                    )
            for expected, cache in (
                (
                    True,
                    {
                        "npm:fixture@1.0.0": [
                            {"id": "FIXTURE-ADVISORY", "severity": "HIGH", "summary": "Synthetic cache label"}
                        ]
                    },
                ),
                (False, {"npm:fixture@1.0.0": []}),
            ):
                snapshot = persist_analysis(
                    db, user, repository, {"package.json": '{"dependencies":{"fixture":"1.0.0"}}'}, advisory_cache=cache
                )
                db.commit()
                observations.append(
                    {
                        "id": f"SCA:{expected}",
                        "rule": "FIXTURE-ADVISORY",
                        "domain": "SCA",
                        "language": "JSON",
                        "framework": "Owned advisory cache",
                        "tier": 1,
                        "expected": expected,
                        "detected": any(f["category"] == "SCA" for f in snapshot.data["findings"]),
                    }
                )
        engine.dispose()
    return observations


def wilson(successes, count):
    if not count:
        return None
    z, p = 1.96, successes / count
    center = (p + z * z / (2 * count)) / (1 + z * z / count)
    distance = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / (1 + z * z / count)
    return [round(max(0, center - distance), 4), round(min(1, center + distance), 4)]


def measure():
    corpus = cases()
    observations = []
    for case in corpus:
        started = time.perf_counter()
        detected, diagnostics = evaluate(case)
        observations.append(
            {k: case[k] for k in ("id", "rule", "domain", "language", "framework", "tier", "expected")}
            | {
                "detected": detected,
                "elapsed_ms": round(1000 * (time.perf_counter() - started), 3),
                "source_sha256": hashlib.sha256(json.dumps(case["files"], sort_keys=True).encode()).hexdigest(),
                "parser_diagnostics": len([d for d in diagnostics if d.get("analyzer") == "PARSING"]),
            }
        )
    observations.extend(graph_cases())
    groups = defaultdict(Counter)
    for item in observations:
        label = (
            "tp"
            if item["detected"] and item["expected"]
            else "fp"
            if item["detected"]
            else "fn"
            if item["expected"]
            else "tn"
        )
        item["classification"] = label
        groups[(item["domain"], item["rule"], item["language"], item["framework"], item["tier"])][label] += 1
    rows = []
    for (domain, rule, language, framework, tier), counts in sorted(groups.items()):
        tp, tn, fp, fn = (counts[k] for k in ("tp", "tn", "fp", "fn"))
        rows.append(
            {
                "domain": domain,
                "rule": rule,
                "language": language,
                "framework": framework,
                "tier": tier,
                "analyzer_version": VERSION,
                "tp": tp,
                "tn": tn,
                "fp": fp,
                "fn": fn,
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                "precision_wilson_95": wilson(tp, tp + fp),
                "rule_status": DEFINITIONS.get(rule, (None,) * 5 + ("BETA",))[5],
                "validated_examples": tp + tn,
                "blocking_eligible": False,
                "qualification": "UNQUALIFIED_SMALL_PURPOSIVE_SAMPLE",
            }
        )
    return {
        "schema": "projecttrace-accuracy-v2",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "analyzer_version": VERSION,
        "parser_signature": PARSER_SIGNATURE,
        "python": platform.python_version(),
        "corpus_hash": hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
        "case_count": len(observations),
        "groups": rows,
        "observations": observations,
        "tiers": {
            "1": "Owned synthetic labels",
            "2": "Pinned public CPython/Django negative-only selected rule slice",
            "3": "Owned framework-specific fixture pairs",
            "4": "UNAVAILABLE: no approved design-partner evaluation",
        },
        "limitations": [
            "No universal accuracy score or production precision claim.",
            "Labels are purposefully selected, not independent random production ground truth.",
            "Public negative-only examples do not estimate production precision or recall.",
            "Confidence intervals describe small labeled slices and cannot remove corpus selection bias.",
            "No rule is qualified for default merge blocking from these samples.",
            "SCA tests owned advisory-cache correlation, not upstream advisory completeness.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/accuracy-hardening-v2.json")
    args = parser.parse_args()
    report = measure()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "cases": report["case_count"],
                "groups": len(report["groups"]),
                "failures": [o["id"] for o in report["observations"] if o["classification"] in {"fp", "fn"}],
                "output": str(args.output),
            }
        )
    )
