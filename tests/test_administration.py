"""Governance security tests use inert fixtures and isolated databases only."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.admin_models import (
    FeaturePolicy,
    OrganizationMembership,
    PlatformOperator,
    Team,
    TeamMembership,
    TeamRepository,
)
from backend.db import Base, Grant, Organization, Repository, User, make_engine
from backend.governance import feature_access, permitted, policy_scope, resolve_principal
from backend.security import allowed_repositories, require_repo


@pytest.fixture
def governance_db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/governance.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([Organization(id="alpha", name="Alpha"), Organization(id="beta", name="Beta")])
        db.flush()
        db.add_all([User(id="owner", organization_id="alpha", role="ORG_OWNER", email="owner@example.test", password_hash="unused"),
            User(id="member", organization_id="alpha", role="ENGINEER", email="member@example.test", password_hash="unused"),
            User(id="support", organization_id="beta", role="VIEWER", email="support@example.test", password_hash="unused")])
        db.flush()
        db.add_all([OrganizationMembership(organization_id="alpha", user_id="owner", role="ORG_OWNER"),
            OrganizationMembership(organization_id="alpha", user_id="member", role="ENGINEER"),
            OrganizationMembership(organization_id="beta", user_id="member", role="VIEWER"),
            OrganizationMembership(organization_id="beta", user_id="support", role="VIEWER")])
        db.add_all([Repository(id="alpha-repo", organization_id="alpha", name="Alpha repo", system="A", component="A", owner="A"),
            Repository(id="beta-repo", organization_id="beta", name="Beta repo", system="B", component="B", owner="B")])
        db.commit()
        yield db
    engine.dispose()


def policy(db, feature, scope_type, target, decision, *, org="alpha", **extra):
    identity=f"{scope_type}:{target}:{feature}"
    row=FeaturePolicy(id=identity,organization_id=None if scope_type=="PLATFORM" else org,
        scope_key=policy_scope(org,scope_type,target),scope_type=scope_type,target_id=target,
        feature=feature,decision=decision,reason="Controlled fixture policy",changed_by="owner",**extra)
    db.add(row)
    db.commit()
    return row


def test_suspension_is_membership_scoped_and_expiration_fails_closed(governance_db):
    db=governance_db
    user=db.get(User,"member")
    member=db.get(OrganizationMembership,("alpha","member"))
    member.state="SUSPENDED"
    db.commit()
    assert not resolve_principal(db,user,"alpha").enabled
    assert resolve_principal(db,user,"beta").enabled
    member.expires_at="invalid"
    db.commit()
    assert not resolve_principal(db,user,"alpha").enabled
    member.expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    db.commit()
    assert resolve_principal(db,user,"alpha").enabled
    member.state="REMOVED"
    db.commit()
    assert not resolve_principal(db,user,"alpha").enabled
    assert resolve_principal(db,user,"beta").role=="VIEWER"


def test_platform_operator_never_inherits_tenant_source_or_organization_authority(governance_db):
    db=governance_db
    db.add(PlatformOperator(user_id="support",role="PLATFORM_SUPER_ADMIN"))
    db.commit()
    support=resolve_principal(db,db.get(User,"support"))
    assert permitted(db,support,"platform.health")
    assert not permitted(db,support,"users.roles.manage")
    assert allowed_repositories(db,support)==[]
    with pytest.raises(HTTPException) as error:
        require_repo(db,support,"alpha-repo")
    assert error.value.status_code==404


def test_explicit_membership_and_team_inheritance_are_tenant_scoped(governance_db):
    db=governance_db
    db.add(Team(id="team",organization_id="alpha",name="Alpha team",owner_id="owner"))
    db.flush()
    db.add_all([TeamMembership(team_id="team",organization_id="alpha",user_id="member",role="ADMIN"),
        TeamRepository(team_id="team",organization_id="alpha",repository_id="alpha-repo")])
    db.add(Grant(user_id="member",repository_id="beta-repo"))
    db.commit()
    alpha=resolve_principal(db,db.get(User,"member"),"alpha")
    beta=resolve_principal(db,db.get(User,"member"),"beta")
    assert [repo.id for repo in allowed_repositories(db,alpha)]==["alpha-repo"]
    assert [repo.id for repo in allowed_repositories(db,beta)]==["beta-repo"]
    assert permitted(db,alpha,"teams.manage",team_id="team")
    assert not permitted(db,beta,"teams.manage",team_id="team")
    assert not permitted(db,alpha,"organization.settings.manage")
    db.add(Grant(user_id="support",repository_id="alpha-repo"))
    with pytest.raises(ValueError,match="Cross-tenant"):
        db.flush()
    db.rollback()


def test_mandatory_restrictions_win_and_user_exception_requires_organization_permission(governance_db):
    db=governance_db
    user=resolve_principal(db,db.get(User,"member"))
    db.add(Team(id="team",organization_id="alpha",name="Alpha team",owner_id="owner"))
    db.flush()
    db.add(TeamMembership(team_id="team",organization_id="alpha",user_id="member"))
    db.commit()
    policy(db,"ask_engineering","TEAM","team","DENY")
    policy(db,"ask_engineering","USER","member","ALLOW",expires_at=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat())
    assert not feature_access(db,user,"ask_engineering")["allowed"]
    organization=policy(db,"ask_engineering","ORGANIZATION","alpha","ALLOW",allow_user_exceptions=True)
    assert feature_access(db,user,"ask_engineering")["allowed"]
    organization.decision="DENY"
    organization.mandatory=True
    db.commit()
    assert feature_access(db,user,"ask_engineering")["reason"]=="MANDATORY_RESTRICTION"
    organization.decision="ALLOW"
    db.commit()
    platform=policy(db,"ask_engineering","PLATFORM","PLATFORM","DENY",mandatory=True)
    assert not feature_access(db,user,"ask_engineering")["allowed"]
    platform.expires_at="corrupt"
    db.commit()
    assert not feature_access(db,user,"ask_engineering")["allowed"]


def test_expired_user_grant_and_unknown_roles_do_not_authorize(governance_db):
    db=governance_db
    user=resolve_principal(db,db.get(User,"member"))
    policy(db,"zip_import","ORGANIZATION","alpha","DENY")
    policy(db,"zip_import","USER","member","ALLOW",expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    assert not feature_access(db,user,"zip_import")["allowed"]
    assert not feature_access(db,user,"unimplemented_advanced_analyzer")["allowed"]
    user.role="PLATFORM_SUPER_ADMIN"
    assert not permitted(db,user,"users.roles.manage")
    assert not permitted(db,user,"platform.safety")
