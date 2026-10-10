"""Metadata-only platform operations and explicitly consented ownership changes."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import delete, func, or_, select

from backend.admin_common import (
    CommandBody,
    ExpiringBody,
    admin_user,
    bump_revision,
    check_version,
    command,
    page,
    scoped_member,
    session_factory,
)
from backend.admin_models import AccountControl, Approval, OrganizationControl, PlatformOperator
from backend.db import Audit, Organization, QueueEntry, Repository, SessionToken, User
from backend.domain import uid
from backend.governance import future, require_permission, resolve_principal
from backend.security import authenticate

router=APIRouter(prefix="/api/admin/platform",tags=["Platform operations"])
ownership_router=APIRouter(prefix="/api/auth/ownership",tags=["Consented ownership"])


class LifecycleBody(ExpiringBody):
    state: Literal["ACTIVE","SUSPENDED"]


class OperatorBody(CommandBody):
    role: Literal["PLATFORM_SUPER_ADMIN","PLATFORM_SUPPORT_ADMIN","PLATFORM_AUDITOR"]
    enabled: bool=True


class OwnershipBody(CommandBody):
    target_user_id: str=Field(min_length=1,max_length=80)
    target_version: int=Field(ge=1)


def guard_operator_target(db,actor,target_id):
    if target_id in {actor.id,"demo-engineer"}:
        raise HTTPException(403,"A separate authorized operator must change this account.")
    target=db.get(User,target_id)
    if not target:
        raise HTTPException(404,"Account unavailable.")
    return target


def preserve_super_operator(db,target_id):
    others=db.scalar(select(func.count()).select_from(PlatformOperator).join(User,User.id==PlatformOperator.user_id).outerjoin(AccountControl,AccountControl.user_id==User.id)
        .where(PlatformOperator.user_id!=target_id,PlatformOperator.role=="PLATFORM_SUPER_ADMIN",PlatformOperator.enabled.is_(True),User.enabled.is_(True),
            or_(AccountControl.user_id.is_(None),AccountControl.state=="ACTIVE")))
    current=db.get(PlatformOperator,target_id)
    if current and current.role=="PLATFORM_SUPER_ADMIN" and current.enabled and not others:
        raise HTTPException(409,"This would remove the last unrestricted platform super administrator.")


@router.get("/health")
def health(request:Request):
    with session_factory() as db:
        admin_user(db,request,"platform.health")
        db.execute(select(1))
        from backend.activity import health as telemetry_health
        return {"api":"RESPONDING","database":"RESPONDING","database_engine":db.get_bind().dialect.name,
            "queue_states":dict(db.execute(select(QueueEntry.state,func.count()).group_by(QueueEntry.state)).all()),
            "telemetry":telemetry_health(),"worker_live_heartbeat":None,"customer_content_visible":False,
            "limitations":["Queue states and leases are recorded metadata, not a measured utilization percentage.","Support source elevation and deployment rollouts are unavailable."]}


@router.get("/organizations")
def organizations(request:Request,search:str=Query("",max_length=120),offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        admin_user(db,request,"platform.organizations")
        query=select(Organization,OrganizationControl).outerjoin(OrganizationControl,OrganizationControl.organization_id==Organization.id)
        if search:
            query=query.where(Organization.name.icontains(search,autoescape=True))
        rows,pagination=page(db,query.order_by(Organization.name,Organization.id),offset=offset,limit=limit)
        ids=[org.id for org,_ in rows]
        repos=dict(db.execute(select(Repository.organization_id,func.count()).where(Repository.organization_id.in_(ids)).group_by(Repository.organization_id)).all()) if ids else {}
        return {"items":[{"id":org.id,"name":org.name,"state":control.state if control else "ACTIVE","version":control.version if control else 0,
            "repositories":repos.get(org.id,0)} for org,control in rows],"page":pagination,"source_access_granted":False}


@router.post("/organizations/{organization_id}")
def lifecycle(organization_id:str,body:LifecycleBody,request:Request):
    if body.expires_at:
        raise HTTPException(422,"Organization lifecycle restrictions require explicit review and reactivation; use member or feature scope for temporary restrictions.")
    with session_factory() as db:
        actor,token=admin_user(db,request,"platform.safety",mutation=True)
        def apply(current):
            if not db.get(Organization,organization_id):
                raise HTTPException(404,"Organization unavailable.")
            row=db.get(OrganizationControl,organization_id,populate_existing=True)
            check_version(row,body.expected_version)
            before=row.state if row else "ACTIVE"
            if row:
                row.state=body.state
                row.notice="Organization access is restricted. Contact your service operator." if body.state=="SUSPENDED" else None
                row.version+=1
            else:
                row=OrganizationControl(organization_id=organization_id,state=body.state,notice="Contact the service operator." if body.state=="SUSPENDED" else None)
                db.add(row)
            bump_revision(db,organization_id)
            db.flush()
            return {"id":organization_id,"state":row.state,"version":row.version},{"before":before,"after":row.state}
        return command(db,actor,body,"platform.safety","PLATFORM_ORGANIZATION_CHANGED",organization_id,apply,token=token,sensitive=True,platform=True)


@router.get("/accounts")
def accounts(request:Request,user_id:str=Query("",max_length=80),offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        admin_user(db,request,"platform.accounts")
        query=select(User.id,User.organization_id,User.enabled,AccountControl.state,AccountControl.expires_at,AccountControl.version).outerjoin(AccountControl,AccountControl.user_id==User.id)
        if user_id:
            query=query.where(User.id==user_id)
        rows,pagination=page(db,query.order_by(User.id),offset=offset,limit=limit)
        return {"items":[{"id":r.id,"primary_organization_id":r.organization_id,"identity_enabled":r.enabled,"restriction":r.state or "ACTIVE","expires_at":r.expires_at,"version":r.version or 0} for r in rows],"page":pagination,
            "privacy":"Account IDs and operational state only; no passwords, tokens, emails or customer content."}


@router.post("/accounts/{user_id}")
def account_state(user_id:str,body:LifecycleBody,request:Request):
    with session_factory() as db:
        actor,token=admin_user(db,request,"platform.accounts",mutation=True)
        def apply(current):
            guard_operator_target(db,current,user_id)
            if body.state=="SUSPENDED":
                preserve_super_operator(db,user_id)
            row=db.get(AccountControl,user_id,populate_existing=True)
            check_version(row,body.expected_version)
            before=row.state if row else "ACTIVE"
            if row:
                row.state,row.expires_at,row.reason=body.state,body.expires_at if body.state=="SUSPENDED" else None,body.reason
                row.version+=1
            else:
                row=AccountControl(user_id=user_id,state=body.state,expires_at=body.expires_at if body.state=="SUSPENDED" else None,reason=body.reason)
                db.add(row)
            revoked=db.execute(delete(SessionToken).where(SessionToken.user_id==user_id)).rowcount if body.state=="SUSPENDED" else 0
            db.flush()
            bump_revision(db,"PLATFORM")
            return {"id":user_id,"state":row.state,"expires_at":row.expires_at,"version":row.version,"session_records_revoked":revoked},{"before":before,"after":row.state}
        return command(db,actor,body,"platform.accounts","PLATFORM_ACCOUNT_CHANGED",user_id,apply,token=token,sensitive=True,platform=True)


@router.get("/operators")
def operators(request:Request):
    with session_factory() as db:
        admin_user(db,request,"platform.operators")
        rows=db.scalars(select(PlatformOperator).order_by(PlatformOperator.user_id).limit(100))
        return {"items":[{"user_id":r.user_id,"role":r.role,"enabled":r.enabled,"version":r.version} for r in rows],"preview_limit":100}


@router.post("/operators/{user_id}")
def operator_change(user_id:str,body:OperatorBody,request:Request):
    with session_factory() as db:
        actor,token=admin_user(db,request,"platform.operators",mutation=True)
        def apply(current):
            guard_operator_target(db,current,user_id)
            row=db.get(PlatformOperator,user_id,populate_existing=True)
            check_version(row,body.expected_version)
            if not body.enabled:
                preserve_super_operator(db,user_id)
                if not row:
                    raise HTTPException(409,"This account has no operator role to revoke.")
                before={"role":row.role,"enabled":row.enabled}
                row.enabled=False
                db.flush()
                bump_revision(db,"PLATFORM")
                return {"state":"REVOKED","version":row.version},{"before":before,"after":{"enabled":False}}
            approval=Approval(id=uid(),organization_id=current.organization_id,requested_by=current.id,action="PLATFORM_OPERATOR_CHANGE",
                data={"user_id":user_id,"role":body.role,"expected_version":body.expected_version},
                expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat())
            db.add(approval)
            return {"state":"PENDING_SECOND_OPERATOR","approval_id":approval.id},{"proposed":approval.data}
        return command(db,actor,body,"platform.operators","PLATFORM_OPERATOR_REQUESTED",user_id,apply,token=token,sensitive=True,platform=True)


@router.get("/operator-requests")
def operator_requests(request:Request,offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        admin_user(db,request,"platform.operators")
        rows,pagination=page(db,select(Approval).where(Approval.action=="PLATFORM_OPERATOR_CHANGE").order_by(Approval.created_at.desc(),Approval.id),offset=offset,limit=limit)
        return {"items":[{"id":a.id,"requested_by":a.requested_by,"data":a.data,"state":a.state,"version":a.version,"expires_at":a.expires_at} for (a,) in rows],"page":pagination}


@router.post("/operator-requests/{approval_id}/approve")
def approve_operator(approval_id:str,body:CommandBody,request:Request):
    with session_factory() as db:
        actor,token=admin_user(db,request,"platform.operators",mutation=True)
        def apply(current):
            row=db.get(Approval,approval_id,populate_existing=True)
            if not row or row.action!="PLATFORM_OPERATOR_CHANGE":
                raise HTTPException(404,"Operator request unavailable.")
            check_version(row,body.expected_version)
            if row.requested_by==current.id or row.state!="PENDING" or not future(row.expires_at):
                raise HTTPException(403,"A different current super operator must approve this unexpired request.")
            requester=db.get(User,row.requested_by)
            require_permission(db,resolve_principal(db,requester,row.organization_id,platform_only=True),"platform.operators")
            target=guard_operator_target(db,current,row.data["user_id"])
            if not target.enabled or not resolve_principal(db,target,target.organization_id,platform_only=True).enabled:
                raise HTTPException(409,"The proposed operator must have an enabled account and membership.")
            operator=db.get(PlatformOperator,target.id,populate_existing=True)
            check_version(operator,row.data["expected_version"])
            if operator and operator.role=="PLATFORM_SUPER_ADMIN" and row.data["role"]!="PLATFORM_SUPER_ADMIN":
                preserve_super_operator(db,target.id)
            before={"role":operator.role,"enabled":operator.enabled} if operator else None
            if operator:
                operator.role,operator.enabled=row.data["role"],True
                operator.version+=1
            else:
                operator=PlatformOperator(user_id=target.id,role=row.data["role"],enabled=True)
                db.add(operator)
            row.state,row.approved_by="APPROVED",current.id
            db.flush()
            bump_revision(db,"PLATFORM")
            return {"state":"APPLIED","role":operator.role,"version":operator.version},{"before":before,"after":{"user_id":target.id,"role":operator.role},"requested_by":row.requested_by}
        return command(db,actor,body,"platform.operators","PLATFORM_OPERATOR_APPROVED",approval_id,apply,token=token,sensitive=True,platform=True)


@router.get("/audit")
def platform_audit(request:Request,offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        admin_user(db,request,"platform.audit")
        query=select(Audit.id,Audit.organization_id,Audit.actor,Audit.action,Audit.target,Audit.created_at).where(Audit.action.startswith("PLATFORM_"))
        rows,pagination=page(db,query.order_by(Audit.created_at.desc(),Audit.id),offset=offset,limit=limit)
        return {"items":[dict(row._mapping) for row in rows],"page":pagination,"privacy":"Platform operation metadata only; tenant source/evidence/audit payloads are excluded."}


@ownership_router.post("/requests")
def request_ownership(body:OwnershipBody,request:Request):
    with session_factory() as db:
        actor,token=authenticate(db,request,True,edit=False)
        require_permission(db,actor,"organization.ownership.transfer")
        def apply(current):
            member,_=scoped_member(db,current,current.id)
            target,identity=scoped_member(db,current,body.target_user_id)
            check_version(member,body.expected_version)
            check_version(target,body.target_version)
            if target.user_id in {current.id,"demo-engineer"} or target.role=="ORG_OWNER" or not resolve_principal(db,identity,current.organization_id).enabled:
                raise HTTPException(403,"Choose a different active non-owner member.")
            row=Approval(id=uid(),organization_id=current.organization_id,requested_by=current.id,action="OWNERSHIP_TRANSFER",
                data={"target_user_id":target.user_id,"owner_version":member.version,"target_version":target.version},
                expires_at=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat())
            db.add(row)
            return {"approval_id":row.id,"state":"PENDING_TARGET_CONSENT","expires_at":row.expires_at},{"target_user_id":target.user_id}
        return command(db,actor,body,"organization.ownership.transfer","OWNERSHIP_REQUESTED",body.target_user_id,apply,token=token,sensitive=True)


@ownership_router.get("/requests")
def own_ownership_requests(request:Request):
    with session_factory() as db:
        actor,_=authenticate(db,request)
        rows=db.scalars(select(Approval).where(Approval.organization_id==actor.organization_id,Approval.action=="OWNERSHIP_TRANSFER",
            or_(Approval.requested_by==actor.id,Approval.data["target_user_id"].as_string()==actor.id)).order_by(Approval.created_at.desc()).limit(25))
        return {"items":[{"id":a.id,"requested_by":a.requested_by,"target_user_id":a.data["target_user_id"],"state":a.state,"version":a.version,"expires_at":a.expires_at} for a in rows],"preview_limit":25}


@ownership_router.post("/requests/{approval_id}/accept")
def accept_ownership(approval_id:str,body:CommandBody,request:Request):
    with session_factory() as db:
        actor,token=authenticate(db,request,True,edit=False)
        def apply(current):
            row=db.get(Approval,approval_id,populate_existing=True)
            if not row or row.organization_id!=current.organization_id or row.action!="OWNERSHIP_TRANSFER" or row.data.get("target_user_id")!=current.id:
                raise HTTPException(404,"Ownership request unavailable.")
            check_version(row,body.expected_version)
            if row.state!="PENDING" or not future(row.expires_at) or row.requested_by==current.id:
                raise HTTPException(409,"Ownership request is no longer eligible.")
            previous,old_identity=scoped_member(db,current,row.requested_by)
            target,new_identity=scoped_member(db,current,current.id)
            if previous.role!="ORG_OWNER" or not resolve_principal(db,old_identity,current.organization_id).enabled:
                raise HTTPException(403,"The requesting owner no longer has authority.")
            check_version(previous,row.data["owner_version"])
            check_version(target,row.data["target_version"])
            previous.role,target.role="ADMIN","ORG_OWNER"
            if old_identity.organization_id==current.organization_id:
                old_identity.role="ADMIN"
            if new_identity.organization_id==current.organization_id:
                new_identity.role="ORG_OWNER"
            row.state,row.approved_by="APPROVED",current.id
            db.flush()
            return {"state":"TRANSFERRED","owner_id":current.id},{"previous_owner":previous.user_id,"new_owner":current.id,"previous_owner_role":"ADMIN"}
        return command(db,actor,body,"organization.ownership.accept","OWNERSHIP_TRANSFERRED",approval_id,apply,token=token,sensitive=True)
