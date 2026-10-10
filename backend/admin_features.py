"""Versioned entitlement commands; previews never mutate effective policy."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import func, or_, select

from backend.admin_common import (
    CommandBody,
    ExpiringBody,
    admin_user,
    bump_revision,
    check_version,
    command,
    digest,
    fresh_authentication,
    page,
    scoped_member,
    scoped_team,
    session_factory,
)
from backend.admin_models import (
    Approval,
    FeaturePolicy,
    OrganizationMembership,
    PolicyPreview,
    PolicyRevision,
    TeamMembership,
)
from backend.db import User, now
from backend.domain import uid
from backend.governance import (
    FEATURES,
    ROLE_PERMISSIONS,
    decision_version,
    feature_access,
    future,
    policy_scope,
    require_permission,
    resolve_principal,
)

router=APIRouter(prefix="/api/admin",tags=["Feature governance"])


class FeatureChange(ExpiringBody):
    scope_type: Literal["PLATFORM","ORGANIZATION","TEAM","USER","ROLE"]
    target_id: str=Field(min_length=1,max_length=80)
    feature: str=Field(min_length=1,max_length=60)
    decision: Literal["ALLOW","DENY","INHERIT"]
    mandatory: bool=False
    allow_user_exceptions: bool=False
    preview_id: str | None=Field(default=None,max_length=80)


FIELDS=("scope_type","target_id","feature","decision","mandatory","allow_user_exceptions","expires_at","reason")


def policy_data(row):
    return {"id":row.id,**{key:getattr(row,key) for key in FIELDS},"version":row.version,
        "changed_by":row.changed_by,"changed_at":row.changed_at}


def validate_scope(db,actor,scope_type,target_id,*,write=True):
    if scope_type=="PLATFORM":
        require_permission(db,actor,"platform.safety" if write else "platform.audit")
        if target_id!="PLATFORM":
            raise HTTPException(422,"Platform target must be PLATFORM.")
        return "platform.safety",None
    if scope_type=="TEAM":
        scoped_team(db,actor,target_id,permission="features.manage" if write else "teams.read")
        return "features.manage",target_id
    require_permission(db,actor,"features.manage")
    if scope_type=="ORGANIZATION" and target_id!=actor.organization_id:
        raise HTTPException(404,"Organization is outside your scope.")
    if scope_type=="USER":
        member,_=scoped_member(db,actor,target_id)
        if member.state=="REMOVED":
            raise HTTPException(409,"Removed memberships cannot receive feature grants.")
    if scope_type=="ROLE" and target_id not in ROLE_PERMISSIONS:
        raise HTTPException(422,"Unknown organizational role.")
    if scope_type not in {"ORGANIZATION","USER","ROLE"}:
        raise HTTPException(422,"Unknown policy scope.")
    return "features.manage",None


def validate_change(db,actor,body):
    permission,team=validate_scope(db,actor,body.scope_type,body.target_id)
    if body.feature not in FEATURES:
        raise HTTPException(422,"This capability has no implemented entitlement control.")
    if body.mandatory and body.scope_type not in {"ORGANIZATION","PLATFORM"}:
        raise HTTPException(422,"Only organization and platform restrictions may be mandatory.")
    if body.allow_user_exceptions and (body.scope_type!="ORGANIZATION" or body.mandatory):
        raise HTTPException(422,"User exceptions require an ordinary organization policy.")
    if body.scope_type=="USER" and body.decision=="ALLOW" and body.expires_at is None:
        raise HTTPException(422,"Individual feature grants must expire within 90 days.")
    if body.scope_type=="PLATFORM" and body.decision=="DENY" and (not body.mandatory or body.expires_at):
        raise HTTPException(422,"Platform safety restrictions must be mandatory and cannot expire without approval.")
    return permission,team


def candidates(db,actor,scope_type,target_id):
    query=select(OrganizationMembership.organization_id,OrganizationMembership.user_id).where(OrganizationMembership.state!="REMOVED")
    if scope_type!="PLATFORM":
        query=query.where(OrganizationMembership.organization_id==actor.organization_id)
    if scope_type=="TEAM":
        query=query.join(TeamMembership,(TeamMembership.organization_id==OrganizationMembership.organization_id)&
            (TeamMembership.user_id==OrganizationMembership.user_id)).where(TeamMembership.team_id==target_id)
    if scope_type=="USER":
        query=query.where(OrganizationMembership.user_id==target_id)
    if scope_type=="ROLE":
        query=query.where(OrganizationMembership.role==target_id)
    return query


def candidate_count(db,actor,body):
    return db.scalar(select(func.count()).select_from(candidates(db,actor,body.scope_type,body.target_id).subquery()))


def current_policy(db,actor,body):
    return db.scalar(select(FeaturePolicy).where(FeaturePolicy.scope_key==policy_scope(actor.organization_id,body.scope_type,body.target_id),
        FeaturePolicy.feature==body.feature).execution_options(populate_existing=True))


def preview_digest(body):
    return digest(body.model_dump(exclude={"preview_id","command_id"}))


@router.get("/features")
def policies(request:Request,scope_type:Literal["PLATFORM","ORGANIZATION","TEAM","USER","ROLE"]="ORGANIZATION",
    target_id:str=Query(...,min_length=1,max_length=80),offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request)
        validate_scope(db,actor,scope_type,target_id,write=False)
        rows,pagination=page(db,select(FeaturePolicy).where(FeaturePolicy.scope_key==policy_scope(actor.organization_id,scope_type,target_id))
            .order_by(FeaturePolicy.feature),offset=offset,limit=limit)
        effective=None
        if scope_type=="USER":
            principal=resolve_principal(db,db.get(User,target_id),actor.organization_id)
            effective={name:feature_access(db,principal,name) for name in FEATURES}
        return {"items":[policy_data(row[0]) for row in rows],"page":pagination,"effective":effective,
            "scope":{"type":scope_type,"target_id":target_id},"candidate_memberships":candidate_count(db,actor,SimpleNamespace(scope_type=scope_type,target_id=target_id))}


@router.post("/features/preview")
def preview(body:FeatureChange,request:Request):
    with session_factory() as db:
        actor,token=admin_user(db,request,mutation=True)
        validate_change(db,actor,body)
        if body.scope_type=="PLATFORM":
            fresh_authentication(db,token)
        existing=current_policy(db,actor,body)
        check_version(existing,body.expected_version)
        proposed=SimpleNamespace(**{key:getattr(body,key) for key in FIELDS},scope_key=policy_scope(actor.organization_id,body.scope_type,body.target_id),
            id=existing.id if existing else "PROPOSED",version=(existing.version if existing else 0)+1)
        sample=[]
        for org,user_id in db.execute(candidates(db,actor,body.scope_type,body.target_id).order_by(OrganizationMembership.organization_id,OrganizationMembership.user_id).limit(10)):
            principal=resolve_principal(db,db.get(User,user_id),org)
            sample.append({"organization_id":org,"user_id":user_id,"before":feature_access(db,principal,body.feature),
                "after":feature_access(db,principal,body.feature,proposed=proposed)})
        count=candidate_count(db,actor,body)
        # A preview cannot outlive a scheduled inherited-policy transition.
        expiration=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
        relevant=select(func.min(FeaturePolicy.expires_at)).where(FeaturePolicy.feature==body.feature,FeaturePolicy.expires_at>now())
        if body.scope_type!="PLATFORM":
            relevant=relevant.where(or_(FeaturePolicy.organization_id==actor.organization_id,FeaturePolicy.organization_id.is_(None)))
        boundary=db.scalar(relevant)
        if boundary and boundary<expiration:
            expiration=boundary
        row=PolicyPreview(id=uid(),organization_id=actor.organization_id,actor_id=actor.id,request_digest=preview_digest(body),
            decision_version=decision_version(db,actor),affected_count=count,
            expires_at=expiration)
        db.add(row)
        db.commit()
        return {"preview_id":row.id,"expires_at":row.expires_at,"candidate_memberships":count,"sample":sample,
            "sample_limit":10,"exact_changed_count":None,"count_description":"Memberships in the target scope; only the bounded sample has effective before/after decisions.",
            "approval_required":body.scope_type=="PLATFORM" and body.decision!="DENY",
            "active_job_policy":"New submissions, dispatch and starts are checked. Already-running work retains its declared scope; explicit cancellation is separate."}


def write_policy(db,actor,body):
    row=current_policy(db,actor,body)
    check_version(row,body.expected_version)
    before=policy_data(row) if row else None
    if row is None:
        row=FeaturePolicy(id=uid(),organization_id=None if body.scope_type=="PLATFORM" else actor.organization_id,
            scope_key=policy_scope(actor.organization_id,body.scope_type,body.target_id),changed_by=actor.id,
            **{key:getattr(body,key) for key in FIELDS})
        db.add(row)
    else:
        for key in FIELDS:
            setattr(row,key,getattr(body,key))
        row.changed_by,row.changed_at=actor.id,now()
        # A deliberate reapplication is a new revision even when the value is equal.
        row.version+=1
    db.flush()
    result=policy_data(row)
    db.add(PolicyRevision(id=uid(),policy_id=row.id,version=row.version,data=result))
    if body.scope_type=="PLATFORM":
        bump_revision(db,"PLATFORM")
    return result,{"before":before,"after":result}


@router.post("/features")
def save(body:FeatureChange,request:Request):
    with session_factory() as db:
        actor,token=admin_user(db,request,mutation=True)
        permission,team=validate_change(db,actor,body)
        def apply(current):
            validate_change(db,current,body)
            row=db.get(PolicyPreview,body.preview_id) if body.preview_id else None
            if not row or (row.organization_id,row.actor_id)!=(current.organization_id,current.id) or not future(row.expires_at) or row.request_digest!=preview_digest(body):
                raise HTTPException(409,"Create a fresh preview of these exact fields before applying this policy.")
            if row.decision_version!=decision_version(db,current) or row.affected_count!=candidate_count(db,current,body):
                raise HTTPException(409,"Access or target membership changed. Preview the policy again.")
            check_version(current_policy(db,current,body),body.expected_version)
            if body.scope_type=="PLATFORM" and body.decision!="DENY":
                approval=Approval(id=uid(),organization_id=current.organization_id,requested_by=current.id,action="PLATFORM_FEATURE_RELEASE",
                    data={"change":body.model_dump(exclude={"preview_id","command_id"}),"candidate_memberships":row.affected_count},
                    expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat())
                db.add(approval)
                return {"state":"PENDING_SECOND_OPERATOR","approval_id":approval.id,"expires_at":approval.expires_at},{"proposed":approval.data}
            result,delta=write_policy(db,current,body)
            return {"state":"APPLIED","policy":result},delta
        return command(db,actor,body,permission,"FEATURE_POLICY_CHANGED",body.feature,apply,team_id=team,token=token,
            sensitive=body.scope_type=="PLATFORM",platform=body.scope_type=="PLATFORM")


@router.get("/features/{policy_id}/history")
def history(policy_id:str,request:Request,offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request)
        policy=db.get(FeaturePolicy,policy_id)
        if not policy or policy.scope_type!="PLATFORM" and policy.organization_id!=actor.organization_id:
            raise HTTPException(404,"Policy unavailable.")
        validate_scope(db,actor,policy.scope_type,policy.target_id,write=False)
        rows,pagination=page(db,select(PolicyRevision).where(PolicyRevision.policy_id==policy.id).order_by(PolicyRevision.version.desc()),offset=offset,limit=limit)
        return {"items":[{"id":row[0].id,"version":row[0].version,"created_at":row[0].created_at,"policy":row[0].data} for row in rows],
            "page":pagination,"revert_policy":"Reapply eligible previous fields through a new preview and save; old revisions remain unchanged."}


@router.get("/platform/approvals")
def approvals(request:Request,offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"platform.safety")
        rows,pagination=page(db,select(Approval).where(Approval.action=="PLATFORM_FEATURE_RELEASE").order_by(Approval.created_at.desc(),Approval.id),offset=offset,limit=limit)
        return {"items":[{"id":a.id,"requested_by":a.requested_by,"state":a.state,"expires_at":a.expires_at,"version":a.version,"data":a.data} for (a,) in rows],"page":pagination}


@router.post("/platform/approvals/{approval_id}/approve")
def approve(approval_id:str,body:CommandBody,request:Request):
    with session_factory() as db:
        actor,token=admin_user(db,request,"platform.safety",mutation=True)
        def apply(current):
            row=db.get(Approval,approval_id,populate_existing=True)
            if not row or row.action!="PLATFORM_FEATURE_RELEASE":
                raise HTTPException(404,"Approval unavailable.")
            check_version(row,body.expected_version)
            if row.requested_by==current.id or row.state!="PENDING" or not future(row.expires_at):
                raise HTTPException(403,"A different authorized operator must approve an unexpired pending request.")
            requester=db.get(User,row.requested_by)
            require_permission(db,resolve_principal(db,requester,row.organization_id,platform_only=True),"platform.safety")
            proposal=FeatureChange(command_id=body.command_id,**row.data["change"])
            validate_change(db,current,proposal)
            if candidate_count(db,current,proposal)!=row.data["candidate_memberships"]:
                raise HTTPException(409,"The target membership count changed. Request a new preview and approval.")
            result,delta=write_policy(db,current,proposal)
            row.state,row.approved_by="APPROVED",current.id
            return {"state":"APPLIED","approval_id":row.id,"policy":result},{**delta,"requested_by":row.requested_by,"approved_by":current.id}
        return command(db,actor,body,"platform.safety","PLATFORM_FEATURE_RELEASED",approval_id,apply,token=token,sensitive=True,platform=True)
