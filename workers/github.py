"""Credential-gated provider workflow; never executes repository content."""

import os

from sqlalchemy import select

from backend.db import Record, Repository, Session, User, now
from backend.domain import persist_analysis
from backend.jobs import TERMINAL, execute_analysis, inventory_time_budget
from backend.security import require_repo
from integrations.github.connector import GitHubApp
from workers.tasks import celery


def configured_app(connection=None):
    if connection:
        from backend.scm_connections import approved_hosts, private_cidrs, reference, validate_metadata

        data = validate_metadata(connection.data)
        if not data.get("enabled"):
            raise ValueError("SCM connection is disabled.")
        return GitHubApp(
            data["app_id"],
            reference(data["private_key_ref"]),
            data["installation_id"],
            api_base_url=data["api_base_url"],
            allowed_hosts=approved_hosts(),
            private_cidrs=private_cidrs(),
            ca_file=reference(data["ca_bundle_ref"]) if data.get("ca_bundle_ref") else None,
            api_version=data.get("api_version", "2022-11-28"),
        )
    required = ["GITHUB_APP_ID", "GITHUB_PRIVATE_KEY", "GITHUB_INSTALLATION_ID"]
    if not all(os.getenv(key) for key in required):
        raise ValueError("GitHub App credentials and installation are required.")
    return GitHubApp(*(os.environ[key] for key in required))


@celery.task(
    name="projecttrace.github_delivery",
    bind=True,
    max_retries=2,
    time_limit=inventory_time_budget(),
    soft_time_limit=inventory_time_budget() - 20,
)
def github_delivery(self, job_id):
    from backend.repository_store import RepositoryFiles, capture
    from backend.scheduling import JobCancelled, claim, ensure_current, owns, release

    with Session() as db:
        job = db.get(Record, job_id)
        if not job or job.kind != "job" or job.data.get("state") in TERMINAL:
            return
        claimed = claim(db, job, inventory_time_budget())
        if claimed["state"] == "DEFERRED":
            raise self.retry(countdown=2, max_retries=None)
        if claimed["state"] != "CLAIMED":
            return claimed
        try:
            repo = db.get(Repository, job.repository_id)
            integration = db.scalar(
                select(Record).where(
                    Record.organization_id == job.organization_id,
                    Record.kind == "integration",
                    Record.natural_key
                    == ("github:" + job.data["connection_id"] if job.data.get("connection_id") else "github"),
                )
            )
            if not integration or not repo or repo.organization_id != job.organization_id:
                job.data = {
                    **job.data,
                    "state": "PARTIAL",
                    "reason": "GitHub installation has not been connected and tested.",
                }
                db.commit()
                return
            actor = db.get(User, integration.data["owner_id"])
            connection = db.get(Record, job.data["connection_id"]) if job.data.get("connection_id") else None
            if job.data.get("connection_id") and (
                not connection
                or connection.kind != "scm_connection"
                or connection.organization_id != job.organization_id
            ):
                raise ValueError("SCM connection is outside the job organization.")
            connection_version = connection.version if connection else None
            mapping = db.scalar(
                select(Record).where(
                    Record.organization_id == job.organization_id,
                    Record.repository_id == repo.id,
                    Record.kind == "repository_scm",
                )
            )

            def authorized():
                ensure_current(db, job, renew_seconds=inventory_time_budget())
                db.refresh(actor)
                if not actor.enabled or actor.organization_id != job.organization_id:
                    raise ValueError("SCM actor is disabled or outside the job organization.")
                require_repo(db, actor, repo.id)
                if connection:
                    db.refresh(connection)
                    if not connection.data.get("enabled") or connection.version != connection_version:
                        raise ValueError("SCM connection changed during this analysis.")
                if mapping:
                    db.refresh(mapping)
                    if not mapping.data.get("enabled", True) or (
                        connection and mapping.data.get("connection_id") != connection.id
                    ):
                        raise ValueError("SCM repository permission is revoked or changed.")

            authorized()
            adapter = configured_app(connection) if connection else configured_app()
            job.data = {**job.data, "state": "FETCHING", "stage": "FETCHING", "started_at": now()}
            db.commit()
            if not job.data.get("head_sha"):
                job.data = {**job.data, "state": "PARTIAL", "reason": "This delivery has no supported commit scope."}
                db.commit()
                return

            def fetch(commit):
                authorized()
                if hasattr(adapter, "iter_snapshot"):

                    def entries():
                        for entry in adapter.iter_snapshot(repo.name, commit):
                            ensure_current(db, job, renew_seconds=inventory_time_budget())
                            yield entry

                    inventory = capture(db, job.organization_id, repo, entries(), source="SCM_INSTALLED_REPOSITORY")
                    db.commit()
                    authorized()
                    return RepositoryFiles(db, job.organization_id, repo.id, inventory.id)
                # Controlled legacy adapters retain their bounded mapping contract.
                result = adapter.fetch_snapshot(repo.name, commit)
                authorized()
                return result

            base_id = None
            if job.data.get("base_sha"):
                base = db.scalar(
                    select(Record)
                    .where(
                        Record.organization_id == job.organization_id,
                        Record.repository_id == repo.id,
                        Record.kind == "snapshot",
                        Record.data["commit"].as_string() == job.data["base_sha"],
                        Record.data["commit_source"].as_string() == "GIT_SHA",
                    )
                    .order_by(Record.created_at.desc())
                    .limit(1)
                )
                if not base:
                    base_files = fetch(job.data["base_sha"])
                    publishing = False

                    def base_progress(state):
                        nonlocal publishing
                        authorized()
                        if not publishing:
                            db.commit()
                        if state == "BUILDING_EVIDENCE":
                            publishing = True

                    base = persist_analysis(
                        db,
                        actor,
                        repo,
                        base_files,
                        branch="base",
                        git_commit=job.data["base_sha"],
                        progress=base_progress,
                    )
                    authorized()
                    db.commit()
                base_id = base.id
            head_files = fetch(job.data["head_sha"])
            authorized()
            head, job = execute_analysis(
                db,
                actor,
                repo,
                head_files,
                job=job,
                branch=job.data.get("branch", "main"),
                base_id=base_id,
                pr_number=job.data.get("pr_number"),
                pr_title=job.data.get("pr_title"),
                git_commit=job.data["head_sha"],
            )
            job.data = {**job.data, "check_published": False}
            if integration.data.get("checks_enabled"):
                from backend.trust import policy

                authorized()
                if policy(db, job.organization_id)["github_check_metadata"]:
                    check_id = adapter.publish_check(repo.name, job.data["head_sha"], head.data["gate"])
                    job.data = {**job.data, "check_published": True, "check_id": check_id}
                else:
                    job.data = {**job.data, "check_status": "BLOCKED_BY_TENANT_POLICY"}
            db.commit()
        except Exception as error:
            db.rollback()
            if not owns(db, job_id, claimed["token"]):
                return {"state": "STALE_WORKER"}
            job = db.get(Record, job_id)
            job.data = {
                **job.data,
                "state": "CANCELLED" if isinstance(error, JobCancelled) else "FAILED",
                "reason": "Provider scope changed, analysis stopped, or provider request failed.",
                "error_type": type(error).__name__,
                "finished_at": now(),
            }
            db.commit()
            if not isinstance(error, JobCancelled):
                raise
        finally:
            current = db.get(Record, job_id)
            if current:
                release(db, current, token=claimed["token"])
                db.commit()
