"""Tenant-scoped public source acquisition; repository code is never executed."""

from backend.db import Record, Repository, Session, SourceInventory, now
from backend.jobs import TERMINAL, execute_analysis, inventory_time_budget
from workers.tasks import celery


@celery.task(name="projecttrace.public_github", bind=True, max_retries=2,
             time_limit=inventory_time_budget(), soft_time_limit=inventory_time_budget() - 20)
def public_github_job(self, job_id):
    return run_public_import(self, job_id)


def run_public_import(self, job_id, *, session_factory=None):
    from backend.encrypted_archive import EncryptedArchive
    from backend.governance import job_principal, resolve_principal
    from backend.intake_errors import IntakeError
    from backend.repository_store import RepositoryFiles, archive_items, capture, limits
    from backend.scheduling import JobCancelled, claim, ensure_current, owns, release
    from backend.security import require_repo
    from integrations.github.public import PublicGitHub

    with (session_factory or Session)() as db:
        job = db.get(Record, job_id)
        if not job or job.kind != "job" or job.data.get("state") in TERMINAL:
            return
        claimed = claim(db, job, inventory_time_budget())
        if claimed["state"] == "DEFERRED":
            raise self.retry(countdown=2, max_retries=None)
        if claimed["state"] != "CLAIMED":
            return claimed
        try:
            user = job_principal(db,job)
            repo = db.get(Repository, job.repository_id)

            def authorized():
                ensure_current(db, job, renew_seconds=inventory_time_budget())
                db.refresh(user.identity)
                principal=resolve_principal(db,user,job.organization_id)
                if not principal.enabled:
                    raise ValueError("Public import actor is disabled or outside the tenant.")
                require_repo(db, principal, repo.id)

            authorized()
            job.data = {**job.data, "state": "FETCHING", "stage": "FETCHING", "started_at": now()}
            db.commit()
            adapter = PublicGitHub(job.data["public_url"], job.data.get("ref"))
            # Retries analyze the already resolved revision, never a moving ref.
            provenance = job.data.get("provenance") or adapter.resolve()
            adapter.repository = provenance["repository"]
            job.data = {**job.data, "head_sha": provenance["commit"], "branch": provenance["ref"], "provenance": provenance}
            db.commit()
            policy = limits()
            inventory = db.get(SourceInventory, job.data.get("inventory_id")) if job.data.get("inventory_id") else None
            if inventory:
                if (inventory.organization_id, inventory.repository_id) != (job.organization_id, repo.id) or inventory.data.get("provenance", {}).get("commit") != provenance["commit"]:
                    raise ValueError("Retained public inventory scope or commit does not match this job.")
            else:
                with EncryptedArchive(policy["archive_bytes"]) as spool:
                    adapter.download(provenance, spool, lambda: ensure_current(db, job))
                    list(archive_items(spool, policy, validate_only=True))
                    inventory = capture(db, user.organization_id, repo, archive_items(spool, policy),
                                        source="GITHUB_PUBLIC_ARCHIVE", quota=policy, checkpoint=authorized)
                    inventory.data = {**inventory.data, "provenance": provenance}
                    job.data = {**job.data, "inventory_id": inventory.id, "provenance": provenance}
                    db.commit()
            files = RepositoryFiles(db, user.organization_id, repo.id, inventory.id)
            authorized()
            execute_analysis(db, user, repo, files, job=job, branch=provenance["ref"], git_commit=provenance["commit"])
        except Exception as error:
            db.rollback()
            if not owns(db, job_id, claimed["token"]):
                return {"state": "STALE_WORKER"}
            job = db.get(Record, job_id)
            detail = error.detail() if isinstance(error, IntakeError) else job.data.get("error_detail") or {"code": "PUBLIC_ANALYSIS_FAILED", "message": "Public source analysis stopped; inspect coverage or retry retained source."}
            job.data = {**job.data, "state": "CANCELLED" if isinstance(error, JobCancelled) else "FAILED",
                        "error_type": type(error).__name__, "error_code": detail["code"], "error_detail": detail,
                        "errors": [detail["message"]], "finished_at": now()}
            db.commit()
            if not isinstance(error, JobCancelled):
                raise
        finally:
            release(db, db.get(Record, job_id), token=claimed["token"])
            db.commit()
