"""Operational reads, privacy, ownership consent and negative platform tests."""
from sqlalchemy import select

from backend import main
from backend.admin_models import GovernanceRevision, OrganizationMembership, PlatformOperator
from backend.db import Audit, Record, User
from backend.domain import add
from backend.trust import integrity
from tests.test_administration_api import accept, body, invite, register


def owner(client):
    return register(client,"ops-owner@example.test","Operations fixture")


def operator(db,user_id,role):
    db.add(PlatformOperator(user_id=user_id,role=role))
    if not db.get(GovernanceRevision,"PLATFORM"):
        db.add(GovernanceRevision(scope_key="PLATFORM",revision=0))
    db.commit()


def test_operational_reads_are_scoped_bounded_and_do_not_load_secret_job_payload(client):
    identity=owner(client)
    user_id=identity["access"]["user_id"]
    with main.Session() as db:
        add(db,identity["organization_id"],None,"job",{"state":"FAILED","user_id":user_id,"files":{"private.py":"secret-content"},"worker_token":"secret-worker-token","ciphertext":"secret-input","duration_ms":123})
        add(db,"other",None,"job",{"state":"FAILED","marker":"cross-tenant-marker"})
        db.commit()
    jobs=client.get("/api/admin/jobs?limit=1")
    assert jobs.status_code==200,jobs.text
    assert jobs.json()["page"]["total"]==1
    assert "secret-" not in jobs.text and "cross-tenant" not in jobs.text
    assert "version" in jobs.json()["items"][0]
    assert client.get("/api/admin/jobs?limit=101").status_code==422
    usage=client.get("/api/admin/usage").json()
    assert usage["jobs"]==1 and usage["total_recorded_duration_ms"]==123
    assert usage["cpu_seconds"] is None
    assert client.get("/api/admin/dashboard").json()["members"]["total"]==1
    assert client.get("/api/admin/activity?start=2020-01-01T00:00:00&end=2030-01-01T00:00:00").status_code==422


def test_activity_and_audit_have_correct_actor_scope_and_hash_chain(client):
    identity=owner(client)
    created=client.post("/api/admin/teams",json=body(name="Audit team"))
    assert created.status_code==200,created.text
    events=client.get("/api/admin/activity?action=TEAM_CREATED&limit=1").json()
    assert events["page"]["total"]==1
    event=events["items"][0]
    assert event["actor_id"]==identity["access"]["user_id"] and event["data"]["audit_event_id"]==created.json()["audit_event_id"]
    with main.Session() as db:
        assert integrity(db,identity["organization_id"])["state"]=="VERIFIED"
    assert client.get("/api/admin/audit?limit=1").json()["page"]["has_more"]


def test_auditor_can_read_but_cannot_mutate_any_administration(client):
    owner(client)
    auditor,_=accept(invite(client,"readonly-auditor@example.test","AUDITOR"))
    for path in ("/api/admin/dashboard","/api/admin/jobs","/api/admin/activity","/api/admin/audit","/api/admin/usage"):
        assert auditor.get(path).status_code==200,path
    assert auditor.get("/api/admin/users").status_code==403
    assert auditor.post("/api/admin/teams",json=body(name="Denied team")).status_code==403
    assert auditor.post("/api/admin/quotas",json=body(scope_type="ORGANIZATION",target_id="other",metric="daily_jobs",limit=1)).status_code==403


def test_support_can_read_platform_metadata_but_has_no_tenant_source_or_super_controls(client):
    identity=owner(client)
    with main.Session() as db:
        operator(db,identity["access"]["user_id"],"PLATFORM_SUPPORT_ADMIN")
    assert client.get("/api/admin/platform/health").status_code==200
    assert client.get("/api/admin/platform/organizations").status_code==200
    for path in ("/api/admin/platform/accounts","/api/admin/platform/operators","/api/admin/platform/audit"):
        assert client.get(path).status_code==403
    assert client.get("/api/record/private").status_code==404
    assert client.get("/api/repositories?repository_id=private").status_code==404
    assert client.post("/api/admin/platform/organizations/other",json=body(state="SUSPENDED")).status_code==403


def test_ownership_is_target_consented_versioned_and_cannot_self_promote(client):
    original=owner(client)
    member,identity=accept(invite(client,"consenting-owner@example.test","VIEWER"))
    assert member.get("/api/admin/context").status_code==403
    target=identity["access"]["user_id"]
    requested=client.post("/api/auth/ownership/requests",json=body(target_user_id=target,target_version=1,expected_version=1))
    assert requested.status_code==200,requested.text
    approval=requested.json()["approval_id"]
    assert client.post(f"/api/auth/ownership/requests/{approval}/accept",json=body(expected_version=1)).status_code==404
    accepted=member.post(f"/api/auth/ownership/requests/{approval}/accept",json=body(expected_version=1))
    assert accepted.status_code==200,accepted.text
    assert member.get("/api/auth/me").json()["role"]=="ORG_OWNER"
    assert client.get("/api/auth/me").json()["role"]=="ADMIN"
    with main.Session() as db:
        assert db.get(OrganizationMembership,(original["organization_id"],target)).role=="ORG_OWNER"
        assert db.scalar(select(Audit).where(Audit.action=="OWNERSHIP_TRANSFERRED"))


def test_platform_account_suspension_revokes_all_sessions_but_not_data(client):
    identity=owner(client)
    member,member_identity=accept(invite(client,"platform-restricted@example.test"))
    target=member_identity["access"]["user_id"]
    with main.Session() as db:
        operator(db,identity["access"]["user_id"],"PLATFORM_SUPER_ADMIN")
        count=db.query(Record).count()
    changed=client.post(f"/api/admin/platform/accounts/{target}",json=body(state="SUSPENDED",expected_version=0))
    assert changed.status_code==200,changed.text
    assert member.get("/api/auth/me").status_code==401
    assert member.post("/api/auth/login",json={"email":"platform-restricted@example.test","password":"Controlled-fixture-password-123!"}).status_code==403
    assert client.post(f"/api/admin/platform/accounts/{identity['access']['user_id']}",json=body(state="SUSPENDED",expected_version=0)).status_code==403
    with main.Session() as db:
        assert db.query(Record).count()==count
        assert db.get(User,target).enabled
