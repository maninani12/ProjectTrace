"""Serialized job admission quotas beneath the existing technical queue caps."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import func, select

from backend.admin_common import (
    CommandBody,
    admin_user,
    check_version,
    command,
    page,
    scoped_member,
    scoped_team,
    session_factory,
)
from backend.admin_models import JobAttribution, JobTeamAttribution, QuotaPolicy
from backend.db import QueueEntry, Record
from backend.domain import uid
from backend.governance import policy_scope, require_permission, resolve_principal, team_ids

router=APIRouter(prefix="/api/admin/quotas",tags=["Resource governance"])
METRICS={"pending_jobs":"Accepted queued plus running jobs", "daily_jobs":"Distinct jobs accepted during the UTC day; retries of the same job are not new jobs"}


class QuotaChange(CommandBody):
    scope_type: Literal["ORGANIZATION","TEAM","USER"]
    target_id: str=Field(min_length=1,max_length=80)
    metric: Literal["pending_jobs","daily_jobs"]
    limit: int | None=Field(default=None,ge=0,le=50_000)


def quota_scope(db,actor,scope_type,target_id):
    require_permission(db,actor,"quotas.manage")
    if scope_type=="ORGANIZATION" and target_id!=actor.organization_id:
        raise HTTPException(404,"Organization unavailable.")
    if scope_type=="TEAM":
        scoped_team(db,actor,target_id)
    if scope_type=="USER":
        scoped_member(db,actor,target_id)


def consumption(db,organization_id,scope_type,target_id,metric):
    day=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
    if metric=="pending_jobs":
        query=select(func.count()).select_from(QueueEntry).where(QueueEntry.organization_id==organization_id,QueueEntry.state.in_(["QUEUED","RUNNING"]))
        if scope_type=="TEAM":
            query=query.join(JobTeamAttribution,JobTeamAttribution.job_id==QueueEntry.job_id).where(JobTeamAttribution.organization_id==organization_id,JobTeamAttribution.team_id==target_id)
        elif scope_type=="USER":
            query=query.join(Record,Record.id==QueueEntry.job_id).where(Record.data["user_id"].as_string()==target_id)
    else:
        query=select(func.count()).select_from(Record).where(Record.organization_id==organization_id,Record.kind=="job",Record.created_at>=day)
        if scope_type=="TEAM":
            query=query.join(JobTeamAttribution,JobTeamAttribution.job_id==Record.id).where(JobTeamAttribution.organization_id==organization_id,JobTeamAttribution.team_id==target_id)
        elif scope_type=="USER":
            query=query.where(Record.data["user_id"].as_string()==target_id)
    return db.scalar(query)


def enforce_quotas(db,user,repo,*,existing_job=None):
    # Caller holds the scheduler admission singleton. Counts and insertion of a
    # newly accepted job share that transaction; concurrent submits cannot race.
    user=resolve_principal(db,user,repo.organization_id)
    scopes=[policy_scope(repo.organization_id,"ORGANIZATION",repo.organization_id),policy_scope(repo.organization_id,"USER",user.id)]
    scopes.extend(policy_scope(repo.organization_id,"TEAM",team) for team in team_ids(db,user))
    for policy in db.scalars(select(QuotaPolicy).where(QuotaPolicy.organization_id==repo.organization_id,QuotaPolicy.scope_key.in_(scopes))):
        if existing_job and policy.metric=="daily_jobs":
            continue
        used=consumption(db,repo.organization_id,policy.scope_type,policy.target_id,policy.metric)
        if existing_job:
            entry=db.get(QueueEntry,existing_job.id)
            if entry and entry.state in {"QUEUED","RUNNING"}:
                used-=1
        if used>=policy.limit:
            raise HTTPException(429,{"code":"ADMINISTRATIVE_QUOTA","metric":policy.metric,"scope":policy.scope_type,
                "limit":policy.limit,"consumption":used,"message":"The analysis quota for this scope is exhausted. Contact your organization administrator."})


def attribute_job(db,job):
    if db.get(JobAttribution,job.id):
        return
    user_id=job.data.get("user_id")
    teams=[]
    if user_id:
        from backend.db import User
        identity=db.get(User,user_id)
        if identity:
            teams=team_ids(db,resolve_principal(db,identity,job.organization_id))
    db.add(JobAttribution(job_id=job.id,organization_id=job.organization_id,user_id=user_id,team_ids=teams,created_at=job.created_at))
    for team in teams:
        db.add(JobTeamAttribution(job_id=job.id,organization_id=job.organization_id,team_id=team,created_at=job.created_at))


@router.get("")
def quotas(request:Request,offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"usage.read")
        rows,pagination=page(db,select(QuotaPolicy).where(QuotaPolicy.organization_id==actor.organization_id).order_by(QuotaPolicy.scope_key,QuotaPolicy.metric),offset=offset,limit=limit)
        return {"items":[{"id":q.id,"scope_type":q.scope_type,"target_id":q.target_id,"metric":q.metric,"limit":q.limit,"version":q.version,
            "consumption":consumption(db,actor.organization_id,q.scope_type,q.target_id,q.metric)} for (q,) in rows],"page":pagination,"metrics":METRICS,
            "limitations":["Team attribution begins at acceptance after this release; historical team membership is not reconstructed.",
                "Technical queue, parsing, memory, input and execution budgets remain independent upper bounds.",
                "Team-specific concurrency, storage, AI and export quotas are not configured by this interface."]}


@router.post("")
def change_quota(body:QuotaChange,request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"quotas.manage",mutation=True)
        quota_scope(db,actor,body.scope_type,body.target_id)
        def apply(current):
            from backend.scheduling import lock
            lock(db)
            quota_scope(db,current,body.scope_type,body.target_id)
            key=policy_scope(current.organization_id,body.scope_type,body.target_id)
            row=db.scalar(select(QuotaPolicy).where(QuotaPolicy.scope_key==key,QuotaPolicy.metric==body.metric).execution_options(populate_existing=True))
            check_version(row,body.expected_version)
            before={"limit":row.limit,"version":row.version} if row else None
            if body.limit is None:
                if row:
                    db.delete(row)
                return {"state":"REMOVED"},{"before":before,"after":None}
            if row:
                row.limit=body.limit
                row.version+=1
            else:
                row=QuotaPolicy(id=uid(),organization_id=current.organization_id,scope_key=key,scope_type=body.scope_type,target_id=body.target_id,metric=body.metric,limit=body.limit)
                db.add(row)
            db.flush()
            return {"id":row.id,"version":row.version,"limit":row.limit},{"before":before,"after":{"limit":row.limit,"version":row.version}}
        # Scheduler first, then the tenant audit lock: same ordering as intake.
        from backend.scheduling import lock
        lock(db)
        return command(db,actor,body,"quotas.manage","QUOTA_CHANGED",body.target_id,apply)
