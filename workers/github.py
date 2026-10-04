"""Credential-gated provider workflow; never executes repository content."""

import os

from sqlalchemy import select

from backend.db import Record, Repository, Session, User, now
from backend.domain import persist_analysis
from backend.security import require_repo
from integrations.github.connector import GitHubApp
from workers.tasks import celery


def configured_app():
    required = ["GITHUB_APP_ID", "GITHUB_PRIVATE_KEY", "GITHUB_INSTALLATION_ID"]
    if not all(os.getenv(key) for key in required):
        raise ValueError("GitHub App credentials and installation are required.")
    return GitHubApp(*(os.environ[key] for key in required))


@celery.task(name="projecttrace.github_delivery", bind=True, max_retries=2)
def github_delivery(self, job_id):
    with Session() as db:
        job = db.get(Record, job_id)
        if not job or job.kind != "job" or job.data.get("state") in {"COMPLETED", "CANCELLED"}:
            return
        repo = db.get(Repository, job.repository_id)
        integration = db.scalar(
            select(Record).where(
                Record.organization_id == job.organization_id,
                Record.kind == "integration",
                Record.natural_key == "github",
            )
        )
        if not integration or not repo:
            job.data = {
                **job.data,
                "state": "PARTIAL",
                "reason": "GitHub installation has not been connected and tested.",
            }
            db.commit()
            return
        try:
            actor = db.get(User, integration.data["owner_id"])
            require_repo(db, actor, repo.id)
            adapter = configured_app()
            job.data = {**job.data, "state": "FETCHING"}
            db.commit()
            if not job.data.get("head_sha"):
                job.data = {**job.data, "state": "PARTIAL", "reason": "This delivery has no supported commit scope."}
                db.commit()
                return
            head_files = adapter.fetch_snapshot(repo.name, job.data["head_sha"])
            base_id = None
            if job.data.get("base_sha"):
                base_files = adapter.fetch_snapshot(repo.name, job.data["base_sha"])
                base = persist_analysis(db, actor, repo, base_files, branch="base", git_commit=job.data["base_sha"])
                base_id = base.id
            head = persist_analysis(
                db,
                actor,
                repo,
                head_files,
                branch=job.data.get("branch", "main"),
                base_id=base_id,
                pr_number=job.data.get("pr_number"),
                pr_title=job.data.get("pr_title"),
                git_commit=job.data["head_sha"],
            )
            job.data = {
                **job.data,
                "state": head.data["status"],
                "snapshot_id": head.id,
                "check_published": False,
                "warnings": head.data.get("warnings", []),
                "finished_at": now(),
            }
            db.commit()
            if integration.data.get("checks_enabled"):
                check_id = adapter.publish_check(repo.name, job.data["head_sha"], head.data["gate"])
                job.data = {**job.data, "check_published": True, "check_id": check_id}
                db.commit()
        except Exception as error:
            db.rollback()
            job = db.get(Record, job_id)
            job.data = {
                **job.data,
                "state": "FAILED",
                "reason": "Provider fetch, scope validation, or check publication failed.",
                "error_type": type(error).__name__,
                "finished_at": now(),
            }
            db.commit()
            raise
