"""Integrated administration entry points and self-service tenant/access context."""
import hashlib
import json
import secrets
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import select

from backend.admin_common import StrictBody, admin_user, session_factory
from backend.admin_features import router as feature_router
from backend.admin_models import Notification, OrganizationMembership, SessionContext
from backend.admin_operations import router as operations_router
from backend.admin_people import public_router as invitation_router
from backend.admin_people import router as people_router
from backend.admin_platform import ownership_router
from backend.admin_platform import router as platform_router
from backend.admin_quotas import router as quota_router
from backend.db import Organization, User, now
from backend.domain import audit, uid
from backend.governance import (
    CATALOG_VERSION,
    FEATURES,
    PERMISSIONS,
    PLATFORM_PERMISSIONS,
    ROLE_PERMISSIONS,
    SELF_SERVICE_PERMISSIONS,
    decision_version,
    feature_access,
    resolve_principal,
    team_ids,
)
from backend.security import authenticate, passwords

router=APIRouter(prefix="/api/admin",tags=["Administration"])
self_router=APIRouter(prefix="/api/auth",tags=["Access context"])
notification_router=APIRouter(prefix="/api/notifications",tags=["Account notices"])


class OrganizationSelection(StrictBody):
    organization_id: str=Field(min_length=1,max_length=80)


class Reauthentication(StrictBody):
    password: str=Field(min_length=1,max_length=128)


def access_context(db,user):
    delegated=team_ids(db,user,administered=True) if user.enabled else []
    permissions=sorted(ROLE_PERMISSIONS.get(user.role,())) if user.enabled else []
    if delegated:
        permissions=sorted(set(permissions)|{"teams.read","teams.manage.scoped","features.manage.scoped"})
    features={name:feature_access(db,user,name) for name in FEATURES}
    version=hashlib.sha256(json.dumps([decision_version(db,user),sorted((name,result["decision_version"],result["allowed"]) for name,result in features.items())]).encode()).hexdigest()[:24]
    return {"catalog_version":CATALOG_VERSION,"user_id":user.id,"organization_id":user.organization_id,
        "membership_version":user.membership_version,
        "organization_access_available":user.enabled,
        "role":user.role,"permissions":permissions,"admin_available":bool(set(permissions)-SELF_SERVICE_PERMISSIONS or user.platform_role or delegated),
        "platform_role":user.platform_role,"platform_permissions":sorted(PLATFORM_PERMISSIONS.get(user.platform_role,())),
        "administered_team_ids":delegated,"decision_version":version,
        "features":features}


@self_router.get("/access")
def own_access(request:Request):
    with session_factory() as db:
        user,_=authenticate(db,request)
        return access_context(db,user)


@router.get("/context")
def administration_context(request:Request):
    with session_factory() as db:
        user,_=admin_user(db,request)
        return {**access_context(db,user),"permission_definitions":PERMISSIONS,
            "roles":[{"id":name,"permissions":sorted(permissions)} for name,permissions in ROLE_PERMISSIONS.items()],
            "feature_catalog":[{"id":name,"label":label,"description":description,"control_state":"IMPLEMENTED"}
                for name,(label,description) in FEATURES.items()],
            "unavailable_controls":["Selective analyzer disabling without a declared-scope implementation", "Private source support elevation", "Irreversible personal-data erasure"],
            "active_job_policy":"Restrictions prevent new submissions, dispatches and starts; already-running work may finish its declared scope. Use explicit fenced cancellation for active jobs."}


@self_router.get("/organizations")
def own_organizations(request:Request,offset:int=Query(0,ge=0,le=10_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,token=authenticate(db,request)
        query=select(OrganizationMembership,Organization).join(Organization,Organization.id==OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id==actor.id).order_by(Organization.name,Organization.id)
        from backend.admin_common import page
        rows,pagination=page(db,query,offset=offset,limit=limit)
        items=[{"id":org.id,"name":org.name,"role":member.role,"state":member.state,
            "available":resolve_principal(db,actor,org.id).enabled,"selected":org.id==actor.organization_id} for member,org in rows]
        if not items and actor.identity.organization_id==actor.organization_id and offset==0:
            org=db.get(Organization,actor.organization_id)
            items=[{"id":org.id,"name":org.name,"role":actor.role,"state":"LEGACY_PRIMARY","available":actor.enabled,"selected":True}]
            pagination={"total":1,"offset":0,"limit":limit,"has_more":False}
        return {"items":items,"page":pagination,"selected_organization_id":actor.organization_id,"csrf":token.csrf}


@self_router.post("/organization")
def select_organization(body:OrganizationSelection,request:Request):
    with session_factory() as db:
        actor,token=authenticate(db,request,True,edit=False)
        principal=resolve_principal(db,actor,body.organization_id)
        if not principal.enabled:
            raise HTTPException(403,"This organization membership is unavailable.")
        if token.oidc_subject_id and body.organization_id!=actor.organization_id:
            raise HTTPException(403,"OIDC sessions require a fresh sign-in for the selected provider organization.")
        context=db.get(SessionContext,token.digest)
        if context is None:
            context=SessionContext(digest=token.digest,public_id=uid(),organization_id=body.organization_id,assurance="LEGACY")
            db.add(context)
        else:
            context.organization_id=body.organization_id
        token.csrf=secrets.token_urlsafe(32)
        audit(db,principal,"WORKSPACE_SELECTED",body.organization_id,{"actor_id":actor.id})
        db.commit()
        return {"csrf":token.csrf,"organization_id":body.organization_id,"organization":db.get(Organization,body.organization_id).name,
            "email":actor.email,"role":principal.role,"demo":actor.id=="demo-engineer","access":access_context(db,principal)}


@self_router.post("/reauthenticate")
def reauthenticate(body:Reauthentication,request:Request):
    with session_factory() as db:
        actor,token=authenticate(db,request,True,edit=False)
        identity=db.get(User,actor.id)
        try:
            if actor.id=="demo-engineer" or not identity.local_login_allowed or not passwords.verify(identity.password_hash,body.password):
                raise ValueError()
        except Exception:
            raise HTTPException(401,"Reauthentication failed. OIDC-only accounts must sign in through their configured provider.") from None
        context=db.get(SessionContext,token.digest)
        if context is None:
            context=SessionContext(digest=token.digest,public_id=uid(),organization_id=actor.organization_id,assurance="PASSWORD")
            db.add(context)
        context.reauthenticated_at=time.time()
        context.assurance="PASSWORD"
        audit(db,actor,"ADMIN_REAUTHENTICATED",actor.id,{"actor_id":actor.id,"method":"PASSWORD"})
        db.commit()
        return {"state":"REAUTHENTICATED","valid_seconds":300,"mfa_claimed":False}


@notification_router.get("")
def own_notices(request:Request,offset:int=Query(0,ge=0,le=1_000_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=authenticate(db,request)
        from backend.admin_common import page
        rows,pagination=page(db,select(Notification).where(Notification.organization_id==actor.organization_id,
            Notification.user_id==actor.id).order_by(Notification.created_at.desc(),Notification.id),offset=offset,limit=limit)
        return {"items":[{"id":row[0].id,"message":row[0].message,"severity":row[0].severity,
            "created_at":row[0].created_at,"read_at":row[0].read_at} for row in rows],"page":pagination}


@notification_router.post("/{notification_id}/read")
def read_notice(notification_id:str,request:Request):
    with session_factory() as db:
        actor,_=authenticate(db,request,True,edit=False)
        row=db.get(Notification,notification_id)
        if not row or (row.organization_id,row.user_id)!=(actor.organization_id,actor.id):
            raise HTTPException(404,"Notice unavailable.")
        row.read_at=row.read_at or now()
        db.commit()
        return {"id":row.id,"state":"READ"}


routers=(router,people_router,feature_router,quota_router,operations_router,platform_router,ownership_router,invitation_router,self_router,notification_router)
