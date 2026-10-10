"""Organization-scoped people, invitations, teams and repository administration."""
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import delete, exists, func, literal, or_, select, union_all

from backend.admin_common import (
    CommandBody,
    ExpiringBody,
    StrictBody,
    admin_user,
    bump_revision,
    check_version,
    command,
    ensure_primary_membership,
    fresh_authentication,
    guard_member_change,
    lock_scope,
    page,
    role_assignment,
    scoped_member,
    scoped_team,
    session_factory,
)
from backend.admin_models import (
    ActivityEvent,
    Invitation,
    JobAttribution,
    Notification,
    OrganizationMembership,
    RepositoryControl,
    RepositoryDenial,
    SessionContext,
    Team,
    TeamMembership,
    TeamRepository,
)
from backend.db import Grant, Organization, Repository, SessionToken, User, now
from backend.domain import audit, uid
from backend.governance import expired, feature_access, future, permitted, resolve_principal, team_ids
from backend.security import authenticate, create_session, passwords, require_repo, token_hash

router=APIRouter(prefix="/api/admin",tags=["Administration"])
public_router=APIRouter(prefix="/api/auth/invitations",tags=["Invitations"])


class InviteBody(CommandBody):
    email: str=Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",max_length=200)
    role: str=Field(default="ENGINEER",max_length=40)


class MemberBody(ExpiringBody):
    action: Literal["SUSPEND","REACTIVATE","REMOVE","ROLE","REVOKE_SESSIONS"]
    role: str | None=Field(default=None,max_length=40)
    notify: bool=True


class TeamBody(CommandBody):
    name: str=Field(min_length=2,max_length=120)
    owner_id: str | None=Field(default=None,max_length=80)


class TeamChangeBody(CommandBody):
    action: Literal["RENAME","ARCHIVE","RESTORE","TRANSFER_OWNER"]
    name: str | None=Field(default=None,min_length=2,max_length=120)
    owner_id: str | None=Field(default=None,max_length=80)


class TeamMemberBody(CommandBody):
    user_id: str=Field(min_length=1,max_length=80)
    action: Literal["ADD","REMOVE"]
    role: Literal["MEMBER","ADMIN"]="MEMBER"


class AccessBody(CommandBody):
    user_id: str | None=Field(default=None,max_length=80)
    team_id: str | None=Field(default=None,max_length=80)
    action: Literal["GRANT","REVOKE","DENY","CLEAR_DENIAL"]


class RepositoryBody(CommandBody):
    action: Literal["ARCHIVE","RESTORE","PAUSE","RESUME"]


class InvitationToken(StrictBody):
    token: str=Field(min_length=32,max_length=200)


class AcceptInvitation(InvitationToken):
    password: str | None=Field(default=None,min_length=12,max_length=128)
    display_name: str | None=Field(default=None,max_length=120)


def member_view(member, user):
    state="ACTIVE" if member.state=="SUSPENDED" and expired(member.expires_at) else member.state
    return {"id":user.id,"email":user.email,"display_name":member.display_name,"role":member.role,
        "state":state,"recorded_state":member.state,"globally_enabled":user.enabled,"version":member.version,
        "membership_created_at":member.created_at,"account_created_at":None,"expires_at":member.expires_at}


def session_scope(organization_id, user):
    contexts=select(SessionContext.digest).where(SessionContext.organization_id==organization_id)
    legacy=~SessionToken.digest.in_(select(SessionContext.digest))
    return or_(SessionToken.digest.in_(contexts),legacy & (user.organization_id==organization_id))


def revoke_sessions(db, organization_id, target):
    result=db.execute(delete(SessionToken).where(SessionToken.user_id==target.id,session_scope(organization_id,target)))
    return result.rowcount


@router.get("/users")
def users(request:Request,search:str=Query("",max_length=120),state:str=Query("ALL",pattern="^(ALL|ACTIVE|SUSPENDED|REMOVED)$"),
    offset:int=Query(0,ge=0,le=1_000_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"users.read")
        statement=select(OrganizationMembership,User).join(User,User.id==OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id==actor.organization_id)
        if search:
            statement=statement.where(or_(User.email.icontains(search,autoescape=True),OrganizationMembership.display_name.icontains(search,autoescape=True)))
        if state!="ALL":
            statement=statement.where(OrganizationMembership.state==state)
        rows,pagination=page(db,statement.order_by(User.email,User.id),offset=offset,limit=limit)
        identities=[user.id for member,user in rows]
        grants=dict(db.execute(select(Grant.user_id,func.count()).join(Repository,Repository.id==Grant.repository_id).where(
            Grant.user_id.in_(identities),Repository.organization_id==actor.organization_id).group_by(Grant.user_id)).all()) if identities else {}
        memberships={}
        if identities:
            ranked=select(TeamMembership.user_id,Team.name,func.row_number().over(partition_by=TeamMembership.user_id,order_by=(Team.name,Team.id)).label("position"))\
                .join(Team,Team.id==TeamMembership.team_id).where(TeamMembership.organization_id==actor.organization_id,
                    TeamMembership.user_id.in_(identities),Team.archived.is_(False)).subquery()
            for user_id,name in db.execute(select(ranked.c.user_id,ranked.c.name).where(ranked.c.position<=20)):
                memberships.setdefault(user_id,[]).append(name)
        jobs=dict(db.execute(select(JobAttribution.user_id,func.count()).where(JobAttribution.organization_id==actor.organization_id,
            JobAttribution.user_id.in_(identities)).group_by(JobAttribution.user_id)).all()) if identities else {}
        return {"items":[{**member_view(member,user),"teams":memberships.get(user.id,[])[:20],
            "direct_repository_grants":grants.get(user.id,0),"measured_analysis_submissions":jobs.get(user.id,0),
            "historical_usage_complete":False} for member,user in rows],"page":pagination,"organization_id":actor.organization_id,
            "state_filter_basis":"RECORDED_RESTRICTION_STATE; displayed state also resolves valid expired suspensions."}


@router.get("/users/{user_id}")
def user_detail(user_id:str,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"users.read")
        member,target=scoped_member(db,actor,user_id)
        principal=resolve_principal(db,target,actor.organization_id)
        sessions=db.execute(select(SessionContext.public_id,SessionContext.created_at,SessionContext.assurance,SessionToken.expires)
            .join(SessionToken,SessionToken.digest==SessionContext.digest).where(SessionToken.user_id==user_id,
                SessionContext.organization_id==actor.organization_id,SessionToken.expires>time.time()).order_by(SessionToken.expires.desc()).limit(100)).all()
        teams=list(db.execute(select(Team.id,Team.name,TeamMembership.role).join(TeamMembership,TeamMembership.team_id==Team.id).where(
            TeamMembership.organization_id==actor.organization_id,TeamMembership.user_id==user_id).order_by(Team.name).limit(100)))
        from backend.governance import FEATURES, repository_condition
        repositories=list(db.execute(select(Repository.id,Repository.name).where(repository_condition(principal)).order_by(Repository.name).limit(100)))
        return {"member":member_view(member,target),"teams":[dict(row._mapping) for row in teams],
            "repositories":[dict(row._mapping) for row in repositories],"detail_limit":100,
            "sessions":[{"id":row.public_id,"created_at":row.created_at,"assurance":row.assurance,
                "expires_at":datetime.fromtimestamp(row.expires,timezone.utc).isoformat()} for row in sessions],
            "feature_access":[feature_access(db,principal,feature) for feature in FEATURES],
            "last_login":db.scalar(select(func.max(ActivityEvent.created_at)).where(ActivityEvent.organization_id==actor.organization_id,
                ActivityEvent.actor_id==user_id,ActivityEvent.action.in_(["LOGIN_SUCCEEDED","OIDC_LOGIN"]))),
            "last_activity":db.scalar(select(func.max(ActivityEvent.created_at)).where(ActivityEvent.organization_id==actor.organization_id,ActivityEvent.actor_id==user_id)),
            "last_login_measurement":"Successful login events recorded after instrumentation; earlier login times are unknown."}


@router.post("/users/{user_id}")
def change_member(user_id:str,body:MemberBody,request:Request):
    permission={"SUSPEND":"users.suspend","REACTIVATE":"users.reactivate","REMOVE":"users.remove",
        "ROLE":"users.roles.manage","REVOKE_SESSIONS":"sessions.revoke"}[body.action]
    with session_factory() as db:
        actor,token=admin_user(db,request,permission,mutation=True)
        def apply(actor):
            member,target=scoped_member(db,actor,user_id)
            check_version(member,body.expected_version)
            if body.action!="REVOKE_SESSIONS":
                guard_member_change(actor,member)
            elif member.role=="ORG_OWNER":
                fresh_authentication(db,token)
            before={"role":member.role,"state":member.state,"expires_at":member.expires_at}
            if body.action=="ROLE":
                role_assignment(actor,user_id,body.role)
                if body.role in {"ADMIN","SECURITY_ADMIN"}:
                    fresh_authentication(db,token)
                member.role=body.role
                if target.organization_id==actor.organization_id:
                    target.role=body.role
            elif body.action=="SUSPEND":
                member.state,member.expires_at,member.reason="SUSPENDED",body.expires_at,body.reason
            elif body.action=="REACTIVATE":
                if member.state!="SUSPENDED":
                    raise HTTPException(409,"Only a suspended membership can be reactivated; removed members require a new invitation.")
                member.state,member.expires_at,member.reason="ACTIVE",None,None
            elif body.action=="REMOVE":
                if db.scalar(select(Team.id).where(Team.organization_id==actor.organization_id,Team.owner_id==user_id,Team.archived.is_(False)).limit(1)):
                    raise HTTPException(409,"Transfer ownership of active teams before removing this membership.")
                member.state,member.expires_at="REMOVED",None
                db.execute(delete(TeamMembership).where(TeamMembership.organization_id==actor.organization_id,TeamMembership.user_id==user_id))
                repos=select(Repository.id).where(Repository.organization_id==actor.organization_id)
                db.execute(delete(Grant).where(Grant.user_id==user_id,Grant.repository_id.in_(repos)))
            revoked=revoke_sessions(db,actor.organization_id,target) if body.action!="REACTIVATE" else 0
            if body.notify:
                messages={"SUSPEND":"Your organization access is suspended. Contact your organization administrator.",
                    "REACTIVATE":"Your organization access was reactivated with its approved permissions.",
                    "REMOVE":"Your membership was removed. Your authored work and audit history are retained.",
                    "ROLE":"Your organization role changed. Sign in again to review access.",
                    "REVOKE_SESSIONS":"Your organization sessions were revoked. Please sign in again."}
                db.add(Notification(id=uid(),organization_id=actor.organization_id,user_id=user_id,message=messages[body.action],target_id=user_id))
            db.flush()
            return {"member":member_view(member,target),"session_records_revoked":revoked}, {"before":before,"after":{"role":member.role,"state":member.state,"expires_at":member.expires_at}}
        return command(db,actor,body,permission,"MEMBER_"+body.action,user_id,apply,token=token)


@router.post("/users/{user_id}/sessions/{session_id}/revoke")
def revoke_one_session(user_id:str,session_id:str,body:CommandBody,request:Request):
    with session_factory() as db:
        actor,token=admin_user(db,request,"sessions.revoke",mutation=True)
        def apply(current):
            member,_=scoped_member(db,current,user_id)
            check_version(member,body.expected_version)
            if member.role=="ORG_OWNER":
                fresh_authentication(db,token)
            row=db.execute(select(SessionContext,SessionToken).join(SessionToken,SessionToken.digest==SessionContext.digest).where(
                SessionContext.public_id==session_id,SessionContext.organization_id==current.organization_id,SessionToken.user_id==user_id)).first()
            if not row:
                raise HTTPException(404,"Session is unavailable in this organization.")
            db.delete(row[1])
            return {"state":"REVOKED","session_id":session_id},{"user_id":user_id,"session_id":session_id}
        return command(db,actor,body,"sessions.revoke","SESSION_REVOKED",session_id,apply,token=token)


@router.get("/invitations")
def invitations(request:Request,offset:int=Query(0,ge=0,le=1_000_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"users.invite")
        rows,pagination=page(db,select(Invitation).where(Invitation.organization_id==actor.organization_id).order_by(
            Invitation.created_at.desc(),Invitation.id),offset=offset,limit=limit)
        return {"items":[{"id":row[0].id,"email":row[0].email,"role":row[0].role,"version":row[0].version,
            "state":"EXPIRED" if row[0].state=="PENDING" and not future(row[0].expires_at) else row[0].state,
            "expires_at":row[0].expires_at,"created_at":row[0].created_at} for row in rows],"page":pagination}


@router.post("/invitations")
def invite(body:InviteBody,request:Request):
    with session_factory() as db:
        actor,session=admin_user(db,request,"users.invite",mutation=True)
        def apply(actor):
            email=body.email.lower()
            target=db.scalar(select(User).where(User.email==email))
            role_assignment(actor,target.id if target else "NEW_INVITEE",body.role)
            if body.role in {"ADMIN","SECURITY_ADMIN"}:
                fresh_authentication(db,session)
            existing=db.get(OrganizationMembership,(actor.organization_id,target.id)) if target else None
            if existing and existing.state!="REMOVED":
                raise HTTPException(409,"This account already belongs to the organization.")
            pending=db.scalar(select(Invitation.id).where(Invitation.organization_id==actor.organization_id,
                Invitation.email==email,Invitation.state=="PENDING",Invitation.expires_at>now()).limit(1))
            if pending:
                raise HTTPException(409,"A pending invitation exists. Resend or cancel it explicitly.")
            raw=secrets.token_urlsafe(48)
            invitation=Invitation(id=uid(),organization_id=actor.organization_id,email=email,role=body.role,
                token_digest=token_hash(raw),expires_at=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),invited_by=actor.id)
            db.add(invitation)
            db.flush()
            return {"id":invitation.id,"version":invitation.version,"invitation_token":raw,
                "delivery":"ONE_TIME_MANUAL_LINK","expires_at":invitation.expires_at}, {"role":body.role,"invitation_id":invitation.id}
        return command(db,actor,body,"users.invite","USER_INVITED",body.email.lower(),apply)


@router.post("/invitations/{invitation_id}/{action}")
def change_invitation(invitation_id:str,action:Literal["resend","cancel"],body:CommandBody,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"users.invite",mutation=True)
        def apply(actor):
            row=db.get(Invitation,invitation_id)
            if not row or row.organization_id!=actor.organization_id:
                raise HTTPException(404,"Invitation unavailable.")
            check_version(row,body.expected_version)
            if row.state!="PENDING":
                raise HTTPException(409,"Only pending invitations can be resent or cancelled.")
            raw=None
            if action=="cancel":
                row.state="CANCELLED"
            else:
                raw=secrets.token_urlsafe(48)
                row.token_digest=token_hash(raw)
                row.expires_at=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()
            db.flush()
            return {"id":row.id,"state":row.state,"version":row.version,"invitation_token":raw}, {"state":row.state,"resend_invalidates_previous_token":action=="resend"}
        return command(db,actor,body,"users.invite","INVITATION_"+action.upper(),invitation_id,apply)


@public_router.post("/preview")
def invitation_preview(body:InvitationToken):
    with session_factory() as db:
        row=db.scalar(select(Invitation).where(Invitation.token_digest==token_hash(body.token)))
        if not row or row.state!="PENDING" or not future(row.expires_at):
            raise HTTPException(404,"Invitation is unavailable, expired or already used.")
        return {"organization":db.get(Organization,row.organization_id).name,"role":row.role,"expires_at":row.expires_at}


@public_router.post("/accept")
def accept_invitation(body:AcceptInvitation,request:Request,response:Response):
    with session_factory() as db:
        row=db.scalar(select(Invitation).where(Invitation.token_digest==token_hash(body.token)))
        if not row:
            raise HTTPException(404,"Invitation unavailable.")
        lock_scope(db,row.organization_id)
        db.refresh(row)
        if row.state!="PENDING" or not future(row.expires_at):
            raise HTTPException(409,"Invitation expired, cancelled or already accepted.")
        target=db.scalar(select(User).where(User.email==row.email))
        inviter=db.get(User,row.invited_by)
        inviter=resolve_principal(db,inviter,row.organization_id) if inviter else None
        if not inviter or not permitted(db,inviter,"users.invite"):
            raise HTTPException(403,"The invitation's issuing authority is no longer available.")
        role_assignment(inviter,target.id if target else "NEW_INVITEE",row.role)
        if target:
            if not target.enabled or target.id=="demo-engineer":
                raise HTTPException(403,"This account is unavailable.")
            if request.cookies.get("pt_session"):
                existing,_=authenticate(db,request,True,edit=False)
                if existing.id!=target.id:
                    raise HTTPException(403,"Sign in as the invited account before accepting.")
            else:
                try:
                    if not target.local_login_allowed or not body.password or not passwords.verify(target.password_hash,body.password):
                        raise ValueError()
                except Exception:
                    raise HTTPException(401,"Sign in as the invited account or verify its existing local password.") from None
        else:
            if not body.password or len(body.password)<16:
                raise HTTPException(422,"A new account requires a password of at least 16 characters.")
            target=User(id=uid(),organization_id=row.organization_id,email=row.email,role=row.role,password_hash=passwords.hash(body.password))
            db.add(target)
            db.flush()
        member=db.get(OrganizationMembership,(row.organization_id,target.id))
        if member and member.state!="REMOVED":
            raise HTTPException(409,"This account already has an organization membership.")
        if member:
            member.role,member.state,member.expires_at,member.reason=row.role,"ACTIVE",None,None
        else:
            member=OrganizationMembership(organization_id=row.organization_id,user_id=target.id,role=row.role,display_name=body.display_name)
            db.add(member)
        row.state="ACCEPTED"
        db.flush()
        principal=resolve_principal(db,target,row.organization_id)
        csrf=create_session(db,principal,response,production=request.url.scheme=="https",previous_token=request.cookies.get("pt_session"))
        audit(db,principal,"INVITATION_ACCEPTED",row.id,{"actor_id":target.id,"role":row.role})
        bump_revision(db,row.organization_id)
        db.commit()
        return {"email":target.email,"role":member.role,"csrf":csrf,"organization":db.get(Organization,row.organization_id).name,
            "organization_id":row.organization_id,"demo":False}


@router.get("/teams")
def teams(request:Request,search:str=Query("",max_length=120),offset:int=Query(0,ge=0,le=1_000_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"teams.read")
        statement=select(Team).where(Team.organization_id==actor.organization_id)
        if not permitted(db,actor,"users.read") and actor.role!="AUDITOR":
            statement=statement.where(Team.id.in_(team_ids(db,actor,administered=True)))
        if search:
            statement=statement.where(Team.name.icontains(search,autoescape=True))
        rows,pagination=page(db,statement.order_by(Team.name,Team.id),offset=offset,limit=limit)
        identities=[row[0].id for row in rows]
        counts=dict(db.execute(select(TeamMembership.team_id,func.count()).where(TeamMembership.organization_id==actor.organization_id,
            TeamMembership.team_id.in_(identities)).group_by(TeamMembership.team_id)).all()) if identities else {}
        repository_counts=dict(db.execute(select(TeamRepository.team_id,func.count()).where(TeamRepository.organization_id==actor.organization_id,
            TeamRepository.team_id.in_(identities)).group_by(TeamRepository.team_id)).all()) if identities else {}
        return {"items":[{"id":row[0].id,"name":row[0].name,"owner_id":row[0].owner_id,"archived":row[0].archived,
            "version":row[0].version,"members":counts.get(row[0].id,0),"repositories":repository_counts.get(row[0].id,0)} for row in rows],"page":pagination}


@router.post("/teams")
def create_team(body:TeamBody,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"teams.create",mutation=True)
        def apply(actor):
            ensure_primary_membership(db,actor)
            owner=body.owner_id or actor.id
            member,target=scoped_member(db,actor,owner)
            if not resolve_principal(db,target,actor.organization_id).enabled:
                raise HTTPException(409,"The team owner must have active organization access.")
            if db.scalar(select(Team.id).where(Team.organization_id==actor.organization_id,Team.name==body.name)):
                raise HTTPException(409,"A team with this name already exists.")
            team=Team(id=uid(),organization_id=actor.organization_id,name=body.name,owner_id=owner)
            db.add(team)
            db.flush()
            db.add(TeamMembership(team_id=team.id,organization_id=actor.organization_id,user_id=owner,role="ADMIN"))
            return {"id":team.id,"name":team.name,"version":team.version},{"team_id":team.id,"owner_id":owner}
        return command(db,actor,body,"teams.create","TEAM_CREATED",body.name,apply)


@router.get("/teams/{team_id}")
def team_detail(team_id:str,request:Request,offset:int=Query(0,ge=0,le=1_000_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"teams.read")
        team=scoped_team(db,actor,team_id)
        rows,pagination=page(db,select(TeamMembership,User).join(User,User.id==TeamMembership.user_id).where(
            TeamMembership.team_id==team_id,TeamMembership.organization_id==actor.organization_id).order_by(User.email),offset=offset,limit=limit)
        repositories=db.execute(select(Repository.id,Repository.name).join(TeamRepository,TeamRepository.repository_id==Repository.id).where(
            TeamRepository.team_id==team_id,TeamRepository.organization_id==actor.organization_id).order_by(Repository.name).limit(100)).all()
        return {"team":{"id":team.id,"name":team.name,"owner_id":team.owner_id,"archived":team.archived,"version":team.version},
            "members":[{"id":identity.id,"email":identity.email,"role":membership.role} for membership,identity in rows],
            "page":pagination,"repositories":[dict(row._mapping) for row in repositories],"repository_preview_limit":100}


@router.post("/teams/{team_id}")
def change_team(team_id:str,body:TeamChangeBody,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"teams.manage",mutation=True,team_id=team_id)
        def apply(actor):
            team=scoped_team(db,actor,team_id,permission="teams.manage")
            check_version(team,body.expected_version)
            if body.action=="RENAME":
                if not body.name:
                    raise HTTPException(422,"A team name is required.")
                duplicate=db.scalar(select(Team.id).where(Team.organization_id==actor.organization_id,Team.name==body.name,Team.id!=team_id))
                if duplicate:
                    raise HTTPException(409,"Team name is already used.")
                team.name=body.name
            elif body.action=="TRANSFER_OWNER":
                member,target=scoped_member(db,actor,body.owner_id)
                if not resolve_principal(db,target,actor.organization_id).enabled:
                    raise HTTPException(409,"Team owner must have active organization access.")
                team.owner_id=body.owner_id
                membership=db.get(TeamMembership,(team_id,body.owner_id))
                if membership:
                    membership.role="ADMIN"
                else:
                    db.add(TeamMembership(team_id=team_id,user_id=body.owner_id,organization_id=actor.organization_id,role="ADMIN"))
            else:
                team.archived=body.action=="ARCHIVE"
            db.flush()
            return {"id":team.id,"name":team.name,"archived":team.archived,"owner_id":team.owner_id,"version":team.version},{"action":body.action}
        return command(db,actor,body,"teams.manage","TEAM_"+body.action,team_id,apply,team_id=team_id)


@router.post("/teams/{team_id}/members")
def change_team_member(team_id:str,body:TeamMemberBody,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"teams.manage",mutation=True,team_id=team_id)
        def apply(actor):
            team=scoped_team(db,actor,team_id,permission="teams.manage")
            check_version(team,body.expected_version)
            member,target=scoped_member(db,actor,body.user_id)
            current=db.get(TeamMembership,(team_id,body.user_id))
            if body.action=="REMOVE":
                if team.owner_id==body.user_id:
                    raise HTTPException(409,"Transfer team ownership before removing its owner.")
                if current:
                    db.delete(current)
            else:
                if not resolve_principal(db,target,actor.organization_id).enabled:
                    raise HTTPException(409,"An active organization member is required.")
                if team.owner_id==body.user_id and body.role!="ADMIN":
                    raise HTTPException(409,"The team owner must remain a team administrator.")
                if current:
                    current.role=body.role
                else:
                    db.add(TeamMembership(team_id=team_id,user_id=body.user_id,organization_id=actor.organization_id,role=body.role))
            team.version+=1
            db.flush()
            return {"team_id":team_id,"user_id":body.user_id,"version":team.version,"action":body.action},{"user_id":body.user_id,"role":body.role,"action":body.action}
        return command(db,actor,body,"teams.manage","TEAM_MEMBERSHIP_CHANGED",team_id,apply,team_id=team_id)


@router.get("/teams/{team_id}/candidates")
def team_candidates(team_id:str,request:Request,search:str=Query("",max_length=120),
    offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"teams.manage",team_id=team_id)
        scoped_team(db,actor,team_id,permission="teams.manage")
        # Minimal roster for delegated management, not an account directory.
        query=select(OrganizationMembership.user_id.label("id"),OrganizationMembership.display_name,OrganizationMembership.version).where(
            OrganizationMembership.organization_id==actor.organization_id,OrganizationMembership.state=="ACTIVE")
        if search:
            query=query.where(or_(OrganizationMembership.display_name.icontains(search,autoescape=True),
                OrganizationMembership.user_id.icontains(search,autoescape=True)))
        rows,pagination=page(db,query.order_by(OrganizationMembership.display_name,OrganizationMembership.user_id),offset=offset,limit=limit)
        return {"items":[dict(row._mapping) for row in rows],"page":pagination,
            "privacy":"Active organization roster IDs and optional display names for delegated team management; emails, sessions and unrelated team memberships excluded."}


@router.get("/repositories/{repository_id}/access")
def repository_access(repository_id:str,request:Request,offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"repositories.read")
        repo=db.get(Repository,repository_id)
        if not repo or repo.organization_id!=actor.organization_id:
            raise HTTPException(404,"Repository unavailable.")
        direct=exists(select(Grant.user_id).where(Grant.repository_id==repository_id,Grant.user_id==OrganizationMembership.user_id))
        denial=exists(select(RepositoryDenial.user_id).where(RepositoryDenial.organization_id==actor.organization_id,
            RepositoryDenial.repository_id==repository_id,RepositoryDenial.user_id==OrganizationMembership.user_id))
        members=select(literal("USER").label("subject_type"),OrganizationMembership.user_id.label("id"),
            OrganizationMembership.display_name.label("name"),OrganizationMembership.version,direct.label("direct_grant"),denial.label("explicit_denial"))
        members=members.where(OrganizationMembership.organization_id==actor.organization_id,or_(direct,denial))
        teams=select(literal("TEAM"),Team.id,Team.name,Team.version,literal(True),literal(False)).join(TeamRepository,TeamRepository.team_id==Team.id).where(
            Team.organization_id==actor.organization_id,TeamRepository.organization_id==actor.organization_id,TeamRepository.repository_id==repository_id)
        combined=union_all(members,teams).subquery()
        rows,pagination=page(db,select(combined).order_by(combined.c.subject_type,combined.c.id),offset=offset,limit=limit)
        return {"items":[dict(row._mapping) for row in rows],"page":pagination,"repository_id":repository_id,
            "source_access":"Explicit denial overrides direct and active-team grants. Archived teams do not grant access; membership/account restrictions are evaluated on every source request."}


@router.get("/repositories")
def repositories(request:Request,search:str=Query("",max_length=120),offset:int=Query(0,ge=0,le=1_000_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"repositories.read")
        statement=select(Repository,RepositoryControl).outerjoin(RepositoryControl,RepositoryControl.repository_id==Repository.id).where(
            Repository.organization_id==actor.organization_id)
        if search:
            statement=statement.where(Repository.name.icontains(search,autoescape=True))
        rows,pagination=page(db,statement.order_by(Repository.name,Repository.id),offset=offset,limit=limit)
        return {"items":[{"id":repo.id,"name":repo.name,"owner":repo.owner,"provider":repo.provider,
            "archived":bool(control and control.archived),"analysis_paused":bool(control and control.analysis_paused),
            "version":control.version if control else 0,"source_access":"SEPARATELY_AUTHORIZED"} for repo,control in rows],"page":pagination}


@router.post("/repositories/{repository_id}")
def change_repository(repository_id:str,body:RepositoryBody,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"repositories.manage",mutation=True)
        def apply(actor):
            repo=db.get(Repository,repository_id)
            if not repo or repo.organization_id!=actor.organization_id:
                raise HTTPException(404,"Repository unavailable.")
            control=db.get(RepositoryControl,repository_id)
            check_version(control,body.expected_version)
            if control is None:
                control=RepositoryControl(repository_id=repository_id,organization_id=actor.organization_id)
                db.add(control)
            if body.action in {"ARCHIVE","RESTORE"}:
                control.archived=body.action=="ARCHIVE"
            else:
                control.analysis_paused=body.action=="PAUSE"
            db.flush()
            return {"id":repo.id,"version":control.version,"archived":control.archived,"analysis_paused":control.analysis_paused}, {"action":body.action,"history_deleted":False}
        return command(db,actor,body,"repositories.manage","REPOSITORY_"+body.action,repository_id,apply)


@router.post("/repositories/{repository_id}/access")
def change_repository_access(repository_id:str,body:AccessBody,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"repositories.access.grant",mutation=True,team_id=body.team_id)
        def apply(actor):
            repo=db.get(Repository,repository_id)
            if not repo or repo.organization_id!=actor.organization_id:
                raise HTTPException(404,"Repository unavailable.")
            if bool(body.team_id)==bool(body.user_id):
                raise HTTPException(422,"Select exactly one user or team.")
            if body.team_id:
                team=scoped_team(db,actor,body.team_id,permission="teams.manage")
                check_version(team,body.expected_version)
                if not permitted(db,actor,"repositories.access.grant"):
                    require_repo(db,actor,repository_id)
                existing=db.get(TeamRepository,(body.team_id,repository_id))
                if body.action=="GRANT" and not existing:
                    db.add(TeamRepository(team_id=body.team_id,repository_id=repository_id,organization_id=actor.organization_id))
                elif body.action=="REVOKE" and existing:
                    db.delete(existing)
                elif body.action not in {"GRANT","REVOKE"}:
                    raise HTTPException(422,"Team repository access supports grant/revoke only.")
                team.version+=1
                db.flush()
                version=team.version
            else:
                member,target=scoped_member(db,actor,body.user_id)
                check_version(member,body.expected_version)
                existing=db.get(Grant,(body.user_id,repository_id))
                denial=db.get(RepositoryDenial,(body.user_id,repository_id))
                if body.action=="GRANT":
                    if not resolve_principal(db,target,actor.organization_id).enabled:
                        raise HTTPException(409,"An active organization membership is required.")
                    if not existing:
                        db.add(Grant(user_id=body.user_id,repository_id=repository_id))
                elif body.action=="REVOKE" and existing:
                    db.delete(existing)
                elif body.action=="DENY" and not denial:
                    db.add(RepositoryDenial(user_id=body.user_id,repository_id=repository_id,organization_id=actor.organization_id))
                elif body.action=="CLEAR_DENIAL" and denial:
                    db.delete(denial)
                member.version+=1
                db.flush()
                version=member.version
            return {"repository_id":repository_id,"action":body.action,"version":version},{"user_id":body.user_id,"team_id":body.team_id,"action":body.action}
        return command(db,actor,body,"repositories.access.grant","REPOSITORY_ACCESS_CHANGED",repository_id,apply,team_id=body.team_id)
