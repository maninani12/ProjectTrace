"""Safe idempotent demo bootstrap. Never imports or executes fixture source."""

import json
import secrets
from pathlib import Path

from backend.db import Grant, Organization, Repository, Session, User
from backend.domain import persist_analysis
from backend.security import passwords

ROOT = Path(__file__).resolve().parents[1]


def seed(db):
    if not db.get(Organization, "northstar"):
        db.add(Organization(id="northstar", name="Northstar Labs"))
        db.flush()
    user = db.get(User, "demo-engineer")
    if not user:
        user = User(
            id="demo-engineer",
            organization_id="northstar",
            email="demo@projecttrace.local",
            password_hash=passwords.hash(secrets.token_urlsafe(32)),
            role="ENGINEER",
        )
        db.add(user)
        db.flush()
    fixture = json.loads((ROOT / "samples/demo.json").read_text())
    osv_path = ROOT / "samples/osv-lodash.json"
    osv = json.loads(osv_path.read_text()).get("vulns", []) if osv_path.exists() else []
    cache = (
        {
            "npm:lodash@4.17.20": [
                {
                    "id": v["id"],
                    "summary": v.get("summary", ""),
                    "url": f"https://osv.dev/vulnerability/{v['id']}",
                    "modified": v["modified"],
                    "severity": {"MODERATE": "MEDIUM", "HIGH": "HIGH", "LOW": "LOW", "CRITICAL": "CRITICAL"}.get(
                        v.get("database_specific", {}).get("severity"), "UNKNOWN"
                    ),
                    "affected": v.get("affected", []),
                    "source": "OSV query for npm lodash 4.17.20",
                }
                for v in osv
            ]
        }
        if osv
        else {}
    )
    configurations = [
        ("identity", "identity-api", "Identity Platform", "Identity Team"),
        ("payments", "payment-worker", "Payments Platform", "Payments Team"),
        ("commerce", "commerce-events", "Commerce Platform", "Commerce Team"),
        ("clean", "platform-status", "Platform Services", "Platform Team"),
    ]
    for key, name, system, owner in configurations:
        repo = db.get(Repository, key)
        if not repo:
            repo = Repository(
                id=key,
                organization_id="northstar",
                name=name,
                system=system,
                component=name,
                owner=owner,
                provider="DEMO",
            )
            db.add(repo)
            db.flush()
            db.add(Grant(user_id=user.id, repository_id=repo.id))
        value = fixture[key]
        if "base" in value:
            base = persist_analysis(db, user, repo, value["base"], advisory_cache=cache)
            persist_analysis(
                db,
                user,
                repo,
                value["head"],
                branch="pr/1842" if key == "identity" else "main",
                base_id=base.id,
                pr_number=1842 if key == "identity" else None,
                pr_title="Replace JWT authentication with server-side sessions" if key == "identity" else None,
                advisory_cache=cache,
            )
        else:
            persist_analysis(db, user, repo, value, advisory_cache=cache)
    db.commit()


if __name__ == "__main__":
    with Session() as db:
        seed(db)
    print("Northstar Labs demo fixtures initialized. No source code was executed.")
