"""Actual cookie/CSRF administration APIs, with real tenant boundaries."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend import main
from backend.admin_models import AdministrativeCommand, OrganizationMembership
from backend.db import Audit, User

PASSWORD="Controlled-fixture-password-123!"


def body(**values):
    return {"command_id":uuid.uuid4().hex,"reason":"Controlled administration acceptance",**values}


def register(client,email,organization):
    response=client.post("/api/auth/register",json={"email":email,"password":PASSWORD,"organization":organization})
    assert response.status_code==200,response.text
    client.headers["x-csrf-token"]=response.json()["csrf"]
    return client.get("/api/auth/me").json()


@pytest.fixture
def owner(client):
    identity=register(client,"organization-owner@example.test","Administration fixture")
    return client,identity


def invite(owner,email,role="ENGINEER"):
    response=owner.post("/api/admin/invitations",json=body(email=email,role=role))
    assert response.status_code==200,response.text
    return response.json()


def accept(invitation):
    client=TestClient(main.app)
    client.headers["origin"]="http://127.0.0.1:5173"
    response=client.post("/api/auth/invitations/accept",json={"token":invitation["invitation_token"],"password":PASSWORD})
    assert response.status_code==200,response.text
    client.headers["x-csrf-token"]=response.json()["csrf"]
    return client,client.get("/api/auth/me").json()


def test_standard_user_cannot_admin_and_owner_directory_is_bounded(signed):
    assert signed.get("/api/admin/users").status_code==403
    assert signed.get("/api/admin/context").status_code==403
    identity=register(signed,"owner-scope@example.test","Owner scope")
    listing=signed.get("/api/admin/users?limit=1").json()
    assert listing["page"]["total"]==1
    assert listing["items"][0]["email"]==identity["email"]
    assert "password_hash" not in str(listing)
    assert signed.get("/api/admin/users?limit=101").status_code==422


def test_invitation_single_use_no_password_reset_and_scoped_suspend(owner):
    alpha,alpha_identity=owner
    invitation=invite(alpha,"multi-member@example.test")
    member,member_identity=accept(invitation)
    assert member.post("/api/auth/invitations/accept",json={"token":invitation["invitation_token"],"password":PASSWORD}).status_code==409
    beta=TestClient(main.app)
    beta.headers["origin"]="http://127.0.0.1:5173"
    beta_identity=register(beta,"beta-owner@example.test","Beta fixture")
    second=invite(beta,"multi-member@example.test","VIEWER")
    with main.Session() as db:
        original_password=db.get(User,member_identity["access"]["user_id"]).password_hash
    accepted=member.post("/api/auth/invitations/accept",json={"token":second["invitation_token"]})
    assert accepted.status_code==200,accepted.text
    member.headers["x-csrf-token"]=accepted.json()["csrf"]
    assert member.get("/api/auth/me").json()["organization_id"]==beta_identity["organization_id"]
    target=member_identity["access"]["user_id"]
    changed=alpha.post(f"/api/admin/users/{target}",json=body(action="SUSPEND",expected_version=1))
    assert changed.status_code==200,changed.text
    assert member.get("/api/auth/me").status_code==200
    denied=member.post("/api/auth/organization",json={"organization_id":alpha_identity["organization_id"]})
    assert denied.status_code==403
    resumed=alpha.post(f"/api/admin/users/{target}",json=body(action="REACTIVATE",expected_version=changed.json()["member"]["version"]))
    assert resumed.status_code==200,resumed.text
    switched=member.post("/api/auth/organization",json={"organization_id":alpha_identity["organization_id"]})
    assert switched.status_code==200,switched.text
    member.headers["x-csrf-token"]=switched.json()["csrf"]
    assert member.get("/api/auth/me").json()["organization_id"]==alpha_identity["organization_id"]
    with main.Session() as db:
        assert db.get(User,target).password_hash==original_password


def test_role_escalation_csrf_and_cross_tenant_members_are_denied(owner):
    client,identity=owner
    target,member=accept(invite(client,"role-target@example.test"))
    user_id=member["access"]["user_id"]
    assert client.post(f"/api/admin/users/{user_id}",json=body(action="ROLE",role="PLATFORM_SUPER_ADMIN",expected_version=1)).status_code==403
    assert client.post(f"/api/admin/users/{identity['access']['user_id']}",json=body(action="SUSPEND",expected_version=1)).status_code==403
    assert client.get("/api/admin/users/outsider").status_code==404
    assert client.post(f"/api/admin/users/{user_id}",json=body(action="SUSPEND",expected_version=1,password_hash="injected")).status_code==422
    csrf=client.headers.pop("x-csrf-token")
    assert client.post(f"/api/admin/users/{user_id}",json=body(action="SUSPEND",expected_version=1)).status_code==403
    client.headers["x-csrf-token"]=csrf
    assert target.get("/api/auth/me").status_code==200


def test_team_commands_are_idempotent_delegated_and_versioned(owner):
    client,identity=owner
    member,member_identity=accept(invite(client,"team-admin@example.test"))
    payload=body(name="Team Alpha")
    created=client.post("/api/admin/teams",json=payload)
    assert created.status_code==200,created.text
    replay=client.post("/api/admin/teams",json=payload)
    assert replay.status_code==200 and replay.json()["id"]==created.json()["id"]
    assert replay.json()["replayed"]
    conflict=client.post("/api/admin/teams",json={**payload,"name":"Changed fields"})
    assert conflict.status_code==409
    team=created.json()["id"]
    membership=client.post(f"/api/admin/teams/{team}/members",json=body(user_id=member_identity["access"]["user_id"],action="ADD",role="ADMIN",expected_version=1))
    assert membership.status_code==200,membership.text
    renamed=member.post(f"/api/admin/teams/{team}",json=body(action="RENAME",name="Delegated Alpha",expected_version=membership.json()["version"]))
    assert renamed.status_code==200,renamed.text
    other=client.post("/api/admin/teams",json=body(name="Unrelated team")).json()["id"]
    assert member.post(f"/api/admin/teams/{other}",json=body(action="ARCHIVE",expected_version=1)).status_code==403
    assert member.get("/api/admin/users").status_code==403
    assert member.get("/api/admin/teams").json()["page"]["total"]==1


def test_concurrent_roles_have_one_winner_and_audit_failure_rolls_back(owner,monkeypatch):
    client,identity=owner
    target,member=accept(invite(client,"concurrent-member@example.test"))
    user_id=member["access"]["user_id"]
    def assign(role):
        return client.post(f"/api/admin/users/{user_id}",json=body(action="ROLE",role=role,expected_version=1)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(assign,["VIEWER","REVIEWER"]))
    assert sorted(statuses)==[200,409]
    detail=client.get(f"/api/admin/users/{user_id}").json()["member"]
    from backend import admin_common
    def broken(*_args,**_kwargs):
        raise RuntimeError("Controlled audit persistence failure")
    monkeypatch.setattr(admin_common,"audit",broken)
    with pytest.raises(RuntimeError,match="Controlled audit"):
        client.post(f"/api/admin/users/{user_id}",json=body(action="SUSPEND",expected_version=detail["version"]))
    with main.Session() as db:
        row=db.get(OrganizationMembership,(identity["organization_id"],user_id))
        assert row.state=="ACTIVE" and row.version==detail["version"]
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=="MEMBER_SUSPEND"))==0
        assert db.scalar(select(func.count()).select_from(AdministrativeCommand).where(AdministrativeCommand.actor_id==user_id))==0
