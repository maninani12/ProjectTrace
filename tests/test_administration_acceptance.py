"""Delegation, temporal policy, concurrency, operator and retention acceptance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend import governance, main
from backend.admin_models import (
    ActivityEvent,
    OrganizationControl,
    OrganizationMembership,
    PlatformOperator,
    TeamMembership,
)
from backend.db import Audit, Grant, Record, User
from backend.domain import add, audit
from tests.test_administration_api import PASSWORD, accept, body, invite, register
from tests.test_administration_features import change
from tests.test_administration_operations import operator
from tests.test_administration_workers import repository


def owner(client):
    return register(client,"acceptance-owner@example.test","Acceptance organization")


def test_delegated_team_operational_scope_is_prospective_and_not_member_surveillance(client):
    identity=owner(client)
    delegate,person=accept(invite(client,"delegate-ops@example.test"))
    team=client.post("/api/admin/teams",json=body(name="Scoped team")).json()["id"]
    assert client.post(f"/api/admin/teams/{team}/members",json=body(user_id=person["access"]["user_id"],action="ADD",role="ADMIN",expected_version=1)).status_code==200
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        job=add(db,user.organization_id,None,"job",{"state":"COMPLETED","user_id":user.id,"duration_ms":17})
        audit(db,user,"ANALYSIS_COMPLETED",job.id,{})
        audit(db,user,"UNRELATED_PRIVATE_ACTION",user.id,{})
        db.commit()
        first=job.id
        db.delete(db.get(TeamMembership,(team,user.id)))
        db.commit()
        second=add(db,user.organization_id,None,"job",{"state":"COMPLETED","user_id":user.id,"duration_ms":99})
        db.commit()
        unrelated=second.id
    for path in ("usage","activity","jobs"):
        assert delegate.get(f"/api/admin/{path}").status_code==403
        assert delegate.get(f"/api/admin/{path}?team_id=unknown").status_code==403
    usage=delegate.get(f"/api/admin/usage?team_id={team}")
    assert usage.status_code==200,usage.text
    assert usage.json()["jobs"]==1 and usage.json()["total_recorded_duration_ms"]==17
    assert usage.json()["source_plaintext_bytes"] is None
    jobs=delegate.get(f"/api/admin/jobs?team_id={team}").json()["items"]
    assert [j["id"] for j in jobs]==[first]
    assert delegate.get(f"/api/admin/jobs/{unrelated}?team_id={team}").status_code==404
    activity=delegate.get(f"/api/admin/activity?team_id={team}")
    assert "ANALYSIS_COMPLETED" in activity.text and "UNRELATED_PRIVATE_ACTION" not in activity.text
    visible=activity.json()["items"][0]["id"]
    assert delegate.get(f"/api/admin/activity/{visible}?team_id={team}").status_code==200
    private=client.get("/api/admin/activity?action=UNRELATED_PRIVATE_ACTION").json()["items"][0]["id"]
    assert delegate.get(f"/api/admin/activity/{private}?team_id={team}").status_code==404
    assert delegate.get(f"/api/admin/activity/{visible}").status_code==403
    roster=delegate.get(f"/api/admin/teams/{team}/candidates?limit=1")
    assert roster.status_code==200 and roster.json()["page"]["total"]==2
    assert "password" not in roster.text and "delegate-ops@example" not in roster.text
    assert client.get("/api/admin/usage/actors?limit=1").json()["page"]["total"]==1


def test_repository_access_inspection_matches_explicit_deny_and_inheritance(client):
    identity=owner(client)
    member,person=accept(invite(client,"access-inspect@example.test"))
    target=person["access"]["user_id"]
    team=client.post("/api/admin/teams",json=body(name="Access team")).json()["id"]
    added=client.post(f"/api/admin/teams/{team}/members",json=body(user_id=target,action="ADD",expected_version=1)).json()
    with main.Session() as db:
        repo=repository(db,db.get(User,identity["access"]["user_id"]))
        repo_id=repo.id
        db.commit()
    granted=client.post(f"/api/admin/repositories/{repo_id}/access",json=body(team_id=team,action="GRANT",expected_version=added["version"]))
    assert granted.status_code==200,granted.text
    assert member.get(f"/api/repositories?repository_id={repo_id}").status_code==200
    denied=client.post(f"/api/admin/repositories/{repo_id}/access",json=body(user_id=target,action="DENY",expected_version=1))
    assert denied.status_code==200,denied.text
    assert member.get(f"/api/repositories?repository_id={repo_id}").status_code==404
    access=client.get(f"/api/admin/repositories/{repo_id}/access?limit=1")
    assert access.status_code==200,access.text
    assert access.json()["page"]["total"]==3 and access.json()["page"]["has_more"]
    assert member.get(f"/api/admin/repositories/{repo_id}/access").status_code==403
    assert client.get("/api/admin/repositories/private/access").status_code==404
    restored=client.post(f"/api/admin/repositories/{repo_id}/access",json=body(user_id=target,action="CLEAR_DENIAL",expected_version=denied.json()["version"]))
    assert restored.status_code==200
    assert member.get(f"/api/repositories?repository_id={repo_id}").status_code==200


def test_policy_expiration_invalidates_access_version_without_an_admin_write(client,monkeypatch):
    identity=owner(client)
    expiry=datetime.now(timezone.utc)+timedelta(hours=1)
    changed,_,_=change(client,scope_type="ORGANIZATION",target_id=identity["organization_id"],feature="cloud",decision="DENY",expires_at=expiry.isoformat())
    assert changed.status_code==200,changed.text
    before=client.get("/api/auth/access").json()
    assert not before["features"]["cloud"]["allowed"]
    monkeypatch.setattr(governance,"timestamp",lambda:expiry+timedelta(seconds=1))
    after=client.get("/api/auth/access").json()
    assert after["features"]["cloud"]["allowed"]
    assert before["decision_version"]!=after["decision_version"]


def test_unknown_role_fails_closed_and_platform_own_org_suspension_does_not_grant_source(client):
    identity=owner(client)
    user_id=identity["access"]["user_id"]
    with main.Session() as db:
        member=db.get(OrganizationMembership,(identity["organization_id"],user_id))
        member.role="UNKNOWN_ROLE"
        db.commit()
    assert client.get("/api/workspace").status_code==403
    with main.Session() as db:
        db.get(OrganizationMembership,(identity["organization_id"],user_id)).role="ORG_OWNER"
        operator(db,user_id,"PLATFORM_SUPPORT_ADMIN")
        db.add(OrganizationControl(organization_id=identity["organization_id"],state="SUSPENDED"))
        db.commit()
    context=client.get("/api/admin/context")
    assert context.status_code==200,context.text
    assert context.json()["permissions"]==[] and not context.json()["organization_access_available"]
    assert client.get("/api/admin/platform/health").status_code==200
    assert client.get("/api/admin/users").status_code==403
    assert client.get("/api/workspace").status_code==403


def test_operator_grant_needs_distinct_current_approver_and_preserves_source_grants(client):
    first=owner(client)
    second=TestClient(main.app)
    second.headers["origin"]="http://127.0.0.1:5173"
    other=register(second,"acceptance-operator@example.test","Second organization")
    _,person=accept(invite(client,"proposed-support@example.test"))
    target=person["access"]["user_id"]
    with main.Session() as db:
        operator(db,first["access"]["user_id"],"PLATFORM_SUPER_ADMIN")
        operator(db,other["access"]["user_id"],"PLATFORM_SUPER_ADMIN")
        grants=db.scalar(select(func.count()).select_from(Grant))
    requested=client.post(f"/api/admin/platform/operators/{target}",json=body(role="PLATFORM_SUPPORT_ADMIN"))
    assert requested.status_code==200,requested.text
    approval=requested.json()["approval_id"]
    assert client.post(f"/api/admin/platform/operator-requests/{approval}/approve",json=body(expected_version=1)).status_code==403
    applied=second.post(f"/api/admin/platform/operator-requests/{approval}/approve",json=body(expected_version=1))
    assert applied.status_code==200,applied.text
    with main.Session() as db:
        assert db.get(PlatformOperator,target).role=="PLATFORM_SUPPORT_ADMIN"
        assert db.scalar(select(func.count()).select_from(Grant))==grants
    assert second.post(f"/api/admin/platform/operator-requests/{approval}/approve",json=body(expected_version=2)).status_code==403


def test_two_concurrent_submissions_cannot_bypass_daily_quota(client):
    identity=owner(client)
    assert client.post("/api/admin/quotas",json=body(scope_type="ORGANIZATION",target_id=identity["organization_id"],metric="daily_jobs",limit=1)).status_code==200
    with main.Session() as db:
        repository(db,db.get(User,identity["access"]["user_id"]))
        db.commit()
    def submit(_):
        from backend.queue import check_capacity
        from backend.scheduling import register as register_job
        with main.Session() as db:
            try:
                user=db.get(User,identity["access"]["user_id"])
                from backend.db import Repository
                repo=db.get(Repository,"admin-work")
                check_capacity(db,user,repo)
                job=add(db,user.organization_id,repo.id,"job",{"state":"QUEUED","user_id":user.id,"source":"FILES"})
                register_job(db,job)
                db.commit()
                return 202
            except HTTPException as error:
                db.rollback()
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit,range(2)))==[202,429]
    with main.Session() as db:
        assert db.scalar(select(func.count()).select_from(Record).where(Record.organization_id==identity["organization_id"],Record.kind=="job"))==1


def test_retention_is_bounded_scoped_and_preserves_required_audit_mirrors(client):
    identity=owner(client)
    from scripts.retain_activity import retain
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        old=(datetime.now(timezone.utc)-timedelta(days=100)).isoformat()
        for i in range(5):
            db.add(ActivityEvent(id=f"routine-{i}",organization_id=user.organization_id,actor_id=user.id,action="LOGIN_FAILED",category="AUTHENTICATION",outcome="FAILED",created_at=old,data={}))
        db.add(ActivityEvent(id="other-routine",organization_id="other",action="LOGIN_FAILED",category="AUTHENTICATION",outcome="FAILED",created_at=old,data={}))
        db.add(ActivityEvent(id="required-mirror",organization_id=user.organization_id,actor_id=user.id,action="ADMIN_TEST",category="ADMINISTRATION",outcome="SUCCEEDED",created_at=old,data={"audit_event_id":"kept"}))
        db.commit()
        audits=db.scalar(select(func.count()).select_from(Audit))
        assert retain(db,user,days=90,batch_size=2)["eligible_routine_events"]==5
        assert retain(db,user,days=90,batch_size=2,apply=True,reason="Privacy retention qualification")["removed"]==2
        assert db.get(ActivityEvent,"other-routine") and db.get(ActivityEvent,"required-mirror")
        assert db.scalar(select(func.count()).select_from(Audit))==audits+1
        with pytest.raises(HTTPException):
            retain(db,user,days=1,apply=True,reason="Invalid safety bypass")


def test_offline_bootstrap_requires_two_credentials_and_cannot_be_reopened(client,monkeypatch):
    first=owner(client)
    second=TestClient(main.app)
    second.headers["origin"]="http://127.0.0.1:5173"
    other=register(second,"bootstrap-second@example.test","Bootstrap second")
    from backend.admin_models import GovernanceRevision
    from scripts import bootstrap_platform
    with main.Session() as db:
        db.add(GovernanceRevision(scope_key="PLATFORM",revision=0))
        db.commit()
        credentials={u.id:u.password_hash for u in db.scalars(select(User))}
    monkeypatch.setattr(bootstrap_platform,"Session",main.Session)
    def provide():
        answers=iter([first["email"],other["email"],"BOOTSTRAP TWO PLATFORM SUPER ADMINISTRATORS"])
        monkeypatch.setattr("builtins.input",lambda _:next(answers))
        monkeypatch.setattr(bootstrap_platform.getpass,"getpass",lambda _:PASSWORD)
    provide()
    bootstrap_platform.main()
    with main.Session() as db:
        assert db.scalar(select(func.count()).select_from(PlatformOperator))==2
        assert {u.id:u.password_hash for u in db.scalars(select(User))}==credentials
    provide()
    with pytest.raises(SystemExit,match="Bootstrap is closed"):
        bootstrap_platform.main()


def test_routine_telemetry_redacts_private_context_and_handles_write_failure(client):
    identity=owner(client)
    from backend import activity
    activity.emit(main.Session,organization_id=identity['organization_id'],actor_id=identity['access']['user_id'],
        action='CONTROLLED_PRIVACY',category='TEST_FIXTURE',outcome='DENIED',data={'access_token':'private-token-value',
            'question':'private-user-question','request_body':{'files':'private-source'},'safe_metric':4})
    assert activity.flush(timeout=5)
    with main.Session() as db:
        event=db.scalar(select(ActivityEvent).where(ActivityEvent.action=='CONTROLLED_PRIVACY'))
        assert event.data['safe_metric']==4
        assert event.data['access_token']=='[redacted]' and event.data['question']=='[redacted]'
        assert event.data['request_body']=='[redacted]'
    before=activity.health()['dropped_this_process']
    def broken():
        raise RuntimeError('Controlled telemetry unavailable')
    activity.emit(broken,organization_id=identity['organization_id'],action='CONTROLLED_UNAVAILABLE',category='TEST_FIXTURE',outcome='FAILED')
    assert activity.flush(timeout=5)
    assert activity.health()['dropped_this_process']==before+1
    assert client.get('/api/auth/me').status_code==200


def test_admin_job_cancel_is_versioned_idempotent_and_preserves_history(client,monkeypatch):
    identity=owner(client)
    monkeypatch.setenv("JOB_MODE","local")
    from backend.db import AnalysisInput, QueueEntry
    from backend.queue import enqueue_analysis
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        repo=repository(db,user)
        job=enqueue_analysis(db,user,repo,{"static.py":"VALUE = 1\n"})
        db.commit()
        job_id,version=job.id,job.version
    request=body(expected_version=version)
    cancelled=client.post(f"/api/admin/jobs/{job_id}/cancel",json=request)
    assert cancelled.status_code==200,cancelled.text
    assert cancelled.json()["state"]=="CANCELLED"
    assert client.post(f"/api/admin/jobs/{job_id}/cancel",json=request).json()["replayed"]
    with main.Session() as db:
        assert db.get(QueueEntry,job_id).state=="CANCELLED"
        assert db.get(AnalysisInput,job_id) is None
        assert db.get(Record,job_id) is not None
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=="ADMIN_JOB_CANCEL"))==1
    assert client.post("/api/admin/jobs/private/cancel",json=body(expected_version=1)).status_code==404


def test_admin_retry_rechecks_original_submitter_and_retains_attempt_diagnostics(client,monkeypatch):
    identity=owner(client)
    monkeypatch.setenv("JOB_MODE","local")
    from backend import queue
    monkeypatch.setattr(queue,"dispatch",lambda *_:None)
    from backend.db import AnalysisInput
    with main.Session() as db:
        user=db.get(User,identity["access"]["user_id"])
        repo=repository(db,user)
        job=queue.enqueue_analysis(db,user,repo,{"static.py":"VALUE = 1\n"})
        job.data={**job.data,"state":"FAILED","stage":"PARSING","duration_ms":901000,"error_code":"ANALYSIS_TIME_BUDGET","stages":[{"stage":"PARSING","state":"FAILED"}]}
        db.commit()
        job_id=job.id
        retained=db.get(AnalysisInput,job_id).ciphertext
        user.enabled=False
        db.commit()
    # The actor must remain authenticated, so reject disabled original actors
    # at the shared transition independently of an administrator's authority.
    from backend.job_control import transition_job
    with main.Session() as db:
        with pytest.raises(HTTPException):
            transition_job(db,db.get(User,identity["access"]["user_id"]),db.get(Record,job_id),"retry")
        db.get(User,identity["access"]["user_id"]).enabled=True
        db.commit()
        version=db.get(Record,job_id).version
    request=body(expected_version=version)
    retried=client.post(f"/api/admin/jobs/{job_id}/retry",json=request)
    assert retried.status_code==200,retried.text
    assert client.post(f"/api/admin/jobs/{job_id}/retry",json=request).json()["replayed"]
    with main.Session() as db:
        job=db.get(Record,job_id)
        assert job.data["retry_count"]==1
        assert job.data["attempt_history"][-1]["duration_ms"]==901000
        assert job.data["attempt_history"][-1]["stages"]==[{"stage":"PARSING","state":"FAILED"}]
        assert db.get(AnalysisInput,job_id).ciphertext==retained


def test_actual_activity_queries_cover_outcome_counts_and_avoid_timeline_sort(client):
    identity=owner(client)
    from sqlalchemy import event
    with main.Session() as db:
        engine=db.get_bind()
        at=datetime.now(timezone.utc).isoformat()
        for i in range(60):
            db.add(ActivityEvent(id=f"tied-event-{i:03}",organization_id=identity["organization_id"],
                action="CONTROLLED_TIED_EVENT",category="TEST_FIXTURE",outcome="DENIED",created_at=at,data={"metric":i}))
        db.commit()
    statements=[]
    def capture(conn,cursor,statement,params,context,many):
        if "application_activity" in statement:
            statements.append((statement,params))
    event.listen(engine,"before_cursor_execute",capture)
    try:
        first=client.get("/api/admin/activity?limit=25").json()
        second=client.get("/api/admin/activity?offset=25&limit=25").json()
        assert not {r["id"] for r in first["items"]}&{r["id"] for r in second["items"]}
        assert client.get("/api/admin/security").json()["denied_operations"]==60
    finally:
        event.remove(engine,"before_cursor_execute",capture)
    with engine.connect() as conn:
        for statement,params in statements:
            plan=" ".join(str(row) for row in conn.exec_driver_sql("EXPLAIN QUERY PLAN "+statement,params))
            if "application_activity.outcome =" in statement and "count(" in statement:
                assert "COVERING INDEX ix_activity_outcome" in plan
            if "ORDER BY application_activity.created_at DESC" in statement:
                assert "TEMP B-TREE" not in plan
                assert "ix_activity_timeline" in plan


def test_sqlite_admin_deadline_returns_safe_retry_and_does_not_leak_to_worker_connection(client,monkeypatch):
    owner(client)
    from sqlalchemy import text

    from backend import admin_common, admin_operations
    monkeypatch.setattr(admin_common,"ADMIN_QUERY_SECONDS",0.05)
    original=admin_operations.count
    def expensive(db,*args):
        db.execute(text("WITH RECURSIVE work(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM work WHERE n<10000000) SELECT sum(n) FROM work"))
        return original(db,*args)
    monkeypatch.setattr(admin_operations,"count",expensive)
    response=client.get("/api/admin/dashboard")
    assert response.status_code==503,response.text
    assert response.json()["detail"]["code"]=="DATABASE_BUDGET"
    assert "WITH RECURSIVE" not in response.text
    # Checkout of the same engine's returned connections must support a query
    # longer than the ended admin deadline (repository workers use this pool).
    import time
    time.sleep(0.06)
    with main.Session() as db:
        assert db.scalar(text("WITH RECURSIVE work(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM work WHERE n<250000) SELECT max(n) FROM work"))==250000
