"""Admission, worker identity propagation and policy changes after enqueue."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend import main
from backend.admin_models import FeaturePolicy, JobAttribution, JobTeamAttribution, OrganizationMembership, QuotaPolicy
from backend.db import AnalysisInput, Grant, QueueEntry, Record, Repository, User
from backend.domain import add
from backend.governance import job_principal, policy_scope, resolve_principal
from backend.queue import check_capacity, dispatch
from tests.test_administration_api import body, register


def repository(db,user):
    repo=Repository(id="admin-work",organization_id=user.organization_id,name="controlled",component="controlled",system="controlled",owner="Fixture",provider="LOCAL")
    db.add(repo)
    db.flush()
    db.add(Grant(user_id=user.id,repository_id=repo.id))
    db.flush()
    return repo


def test_policy_change_blocks_dispatch_without_discarding_input(client,monkeypatch):
    identity=register(client,"dispatch-owner@example.test","Dispatch fixture")
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        repo=repository(db,user)
        job=add(db,user.organization_id,repo.id,"job",{"state":"QUEUED","stage":"QUEUED","source":"FILES","user_id":user.id,"execution":"CELERY"})
        db.add(AnalysisInput(job_id=job.id,organization_id=user.organization_id,repository_id=repo.id,ciphertext="controlled-retained-input",expires_at="2090-01-01T00:00:00+00:00"))
        from backend.scheduling import register as register_job
        register_job(db,job)
        db.add(FeaturePolicy(id="dispatch-deny",organization_id=user.organization_id,scope_key=policy_scope(user.organization_id,"USER",user.id),
            scope_type="USER",target_id=user.id,feature="analyses",decision="DENY",reason="Controlled restriction",changed_by=user.id))
        db.commit()
        from workers.tasks import celery
        sent=Mock()
        monkeypatch.setattr(celery,"send_task",sent)
        dispatch(db,job)
        assert not sent.called
        assert job.data["state"]=="FAILED" and job.data["dispatch"]=="POLICY_BLOCKED"
        assert db.get(AnalysisInput,job.id).ciphertext=="controlled-retained-input"
        assert db.get(QueueEntry,job.id).state=="FAILED"


def test_worker_resolves_secondary_membership_and_never_falls_back_after_removal(client):
    identity=register(client,"secondary-worker@example.test","Worker fixture")
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        db.add(OrganizationMembership(organization_id="other",user_id=user.id,role="ENGINEER"))
        db.flush()
        scoped=resolve_principal(db,user,"other")
        repo=repository(db,scoped)
        job=add(db,"other",repo.id,"job",{"state":"QUEUED","source":"FILES","user_id":user.id})
        db.commit()
        assert job_principal(db,job).organization_id=="other"
        db.get(OrganizationMembership,("other",user.id)).state="REMOVED"
        db.commit()
        with pytest.raises(HTTPException):
            job_principal(db,job)


def test_org_user_and_prospective_team_quota_admission(client):
    identity=register(client,"quota-owner@example.test","Quota fixture")
    team=client.post("/api/admin/teams",json=body(name="Capacity team")).json()["id"]
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        repo=repository(db,user)
        quota=QuotaPolicy(id="team-daily",organization_id=user.organization_id,scope_key=policy_scope(user.organization_id,"TEAM",team),scope_type="TEAM",target_id=team,metric="daily_jobs",limit=1)
        db.add(quota)
        db.commit()
        check_capacity(db,user,repo)
        job=add(db,user.organization_id,repo.id,"job",{"state":"QUEUED","user_id":user.id,"source":"FILES"})
        from backend.scheduling import register as register_job
        register_job(db,job)
        db.commit()
        assert db.get(JobAttribution,job.id).team_ids==[team]
        assert db.scalar(select(func.count()).select_from(JobTeamAttribution).where(JobTeamAttribution.job_id==job.id))==1
        with pytest.raises(HTTPException) as failure:
            check_capacity(db,user,repo)
        assert failure.value.status_code==429
        db.rollback()
        # Removing the user from a team later cannot rewrite its historical usage.
        from backend.admin_models import TeamMembership
        db.delete(db.get(TeamMembership,(team,user.id)))
        db.commit()
        assert db.get(JobTeamAttribution,(job.id,team)) is not None


def test_actual_worker_rechecks_feature_before_loading_or_executing_source(client,monkeypatch):
    identity=register(client,"worker-denied@example.test","Denied worker fixture")
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        repo=repository(db,user)
        job=add(db,user.organization_id,repo.id,"job",{"state":"QUEUED","source":"FILES","user_id":user.id,"execution":"CELERY","errors":[]})
        from backend.scheduling import register as register_job
        register_job(db,job)
        db.add(FeaturePolicy(id="worker-deny",organization_id=user.organization_id,scope_key=policy_scope(user.organization_id,"USER",user.id),
            scope_type="USER",target_id=user.id,feature="analyses",decision="DENY",reason="Controlled restriction",changed_by=user.id))
        db.commit()
        job_id=job.id
    from workers import tasks
    executed=Mock()
    monkeypatch.setattr(tasks,"execute_analysis",executed)
    with pytest.raises(HTTPException):
        tasks.run_analysis(SimpleNamespace(retry=Mock()),job_id,session_factory=main.Session)
    assert not executed.called
    with main.Session() as db:
        assert db.get(Record,job_id).data["state"]=="FAILED"
        assert db.get(QueueEntry,job_id).state=="FAILED"
