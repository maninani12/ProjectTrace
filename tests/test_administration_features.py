"""Preview integrity, effective enforcement and two-person global recovery."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend import main
from backend.admin_models import FeaturePolicy, GovernanceRevision, PlatformOperator, PolicyRevision
from backend.governance import feature_access, resolve_principal
from tests.test_administration_api import accept, body, invite, register


def owner_client(client):
    return register(client,"feature-owner@example.test","Feature fixture")


def change(client,**values):
    payload=body(**values)
    preview=client.post("/api/admin/features/preview",json=payload)
    assert preview.status_code==200,preview.text
    saved=client.post("/api/admin/features",json={**payload,"preview_id":preview.json()["preview_id"]})
    return saved,payload,preview


def test_user_feature_policy_enforces_direct_api_and_preserves_history(client):
    owner_client(client)
    member,identity=accept(invite(client,"feature-member@example.test"))
    target=identity["access"]["user_id"]
    response,payload,preview=change(client,scope_type="USER",target_id=target,feature="ask_engineering",decision="DENY")
    assert response.status_code==200,response.text
    assert preview.json()["candidate_memberships"]==1
    assert preview.json()["sample"][0]["after"]["allowed"] is False
    assert member.get("/api/auth/access").json()["features"]["ask_engineering"]["allowed"] is False
    assert member.post("/api/ask",json={"question":"controlled"}).status_code==403
    policy=response.json()["policy"]
    response,_,_=change(client,scope_type="USER",target_id=target,feature="ask_engineering",decision="ALLOW",expected_version=policy["version"],
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
    assert response.status_code==200,response.text
    history=client.get(f"/api/admin/features/{policy['id']}/history").json()
    assert [row["version"] for row in history["items"]]==[2,1]
    assert member.get("/api/auth/access").json()["features"]["ask_engineering"]["allowed"] is True
    with main.Session() as db:
        row=db.get(FeaturePolicy,policy["id"])
        row.expires_at="2020-01-01T00:00:00+00:00"
        db.commit()
        assert feature_access(db,resolve_principal(db,db.get(main.User,target),identity["organization_id"]),"ask_engineering")["source_policy"] is None


def test_preview_cannot_be_replayed_for_different_fields_or_stale_membership(client):
    identity=owner_client(client)
    payload=body(scope_type="ORGANIZATION",target_id=identity["organization_id"],feature="zip_import",decision="DENY",mandatory=True)
    preview=client.post("/api/admin/features/preview",json=payload).json()
    changed={**payload,"preview_id":preview["preview_id"],"feature":"analyses"}
    assert client.post("/api/admin/features",json=changed).status_code==409
    accept(invite(client,"new-after-preview@example.test"))
    assert client.post("/api/admin/features",json={**payload,"preview_id":preview["preview_id"]}).status_code==409
    with main.Session() as db:
        assert db.scalar(select(func.count()).select_from(FeaturePolicy))==0


def test_team_admin_scope_and_org_mandatory_precedence(client):
    owner=owner_client(client)
    delegate,identity=accept(invite(client,"feature-team-admin@example.test"))
    target=identity["access"]["user_id"]
    team=client.post("/api/admin/teams",json=body(name="Feature team")).json()["id"]
    assert client.post(f"/api/admin/teams/{team}/members",json=body(user_id=target,action="ADD",role="ADMIN",expected_version=1)).status_code==200
    response,_,_=change(delegate,scope_type="TEAM",target_id=team,feature="cloud",decision="DENY")
    assert response.status_code==200,response.text
    assert delegate.post("/api/admin/features/preview",json=body(scope_type="ORGANIZATION",target_id=owner["organization_id"],feature="cloud",decision="ALLOW")).status_code==403
    response,_,_=change(client,scope_type="ORGANIZATION",target_id=owner["organization_id"],feature="cloud",decision="DENY",mandatory=True)
    assert response.status_code==200,response.text
    response,_,_=change(delegate,scope_type="TEAM",target_id=team,feature="cloud",decision="ALLOW",expected_version=1)
    assert response.status_code==200,response.text
    assert delegate.get("/api/auth/access").json()["features"]["cloud"]["reason"]=="MANDATORY_RESTRICTION"


def test_global_restriction_release_requires_distinct_current_super_operators(client):
    first=owner_client(client)
    second=TestClient(main.app)
    second.headers["origin"]="http://127.0.0.1:5173"
    other=register(second,"second-operator@example.test","Second operator")
    with main.Session() as db:
        db.add_all([PlatformOperator(user_id=first["access"]["user_id"],role="PLATFORM_SUPER_ADMIN"),
            PlatformOperator(user_id=other["access"]["user_id"],role="PLATFORM_SUPER_ADMIN"),GovernanceRevision(scope_key="PLATFORM",revision=0)])
        db.commit()
    denied,_,_=change(client,scope_type="PLATFORM",target_id="PLATFORM",feature="public_github",decision="DENY",mandatory=True)
    assert denied.status_code==200,denied.text
    released,_,_=change(client,scope_type="PLATFORM",target_id="PLATFORM",feature="public_github",decision="INHERIT",expected_version=1)
    assert released.status_code==200,released.text
    assert released.json()["state"]=="PENDING_SECOND_OPERATOR"
    approval=released.json()["approval_id"]
    assert client.post(f"/api/admin/platform/approvals/{approval}/approve",json=body(expected_version=1)).status_code==403
    result=second.post(f"/api/admin/platform/approvals/{approval}/approve",json=body(expected_version=1))
    assert result.status_code==200,result.text
    assert result.json()["policy"]["version"]==2
    with main.Session() as db:
        assert db.scalar(select(func.count()).select_from(PolicyRevision))==2


def test_unknown_and_unbounded_feature_grants_fail_closed(client):
    identity=owner_client(client)
    assert client.post("/api/admin/features/preview",json=body(scope_type="USER",target_id=identity["access"]["user_id"],feature="analyses",decision="ALLOW")).status_code==422
    assert client.post("/api/admin/features/preview",json=body(scope_type="ORGANIZATION",target_id=identity["organization_id"],feature="missing-analyzer",decision="ALLOW")).status_code==422
    assert client.post("/api/admin/features/preview",json=body(scope_type="ORGANIZATION",target_id="other",feature="cloud",decision="DENY")).status_code==404
