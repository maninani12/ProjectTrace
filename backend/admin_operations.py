"""Bounded operational metadata; no source/evidence privileges are implied."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import exists, func, or_, select

from backend.admin_common import (
    CommandBody,
    admin_user,
    check_version,
    command,
    fresh_authentication,
    page,
    safe_metadata,
    scoped_member,
    scoped_team,
    session_factory,
)
from backend.admin_models import (
    ActivityEvent,
    FeaturePolicy,
    Invitation,
    JobTeamAttribution,
    OrganizationMembership,
    Team,
)
from backend.db import Audit, AuditLink, QueueEntry, Record, Repository, SourceBlob, SourceInventoryFile

router=APIRouter(prefix="/api/admin",tags=["Administration operations"])
JOB_FIELDS=("state","stage","source","type","execution","user_id","snapshot_id","branch","queued_at","started_at","finished_at",
    "duration_ms","queue_wait_ms","error_code","error_type","retry_count","recovery_count","dispatch")


def dates(start=None,end=None,days=30):
    current=datetime.now(timezone.utc)
    try:
        upper=datetime.fromisoformat(end) if end else current
        lower=datetime.fromisoformat(start) if start else upper-timedelta(days=days)
        if lower.tzinfo is None or upper.tzinfo is None or lower>=upper or upper-lower>timedelta(days=90) or upper>current+timedelta(minutes=5):
            raise ValueError()
    except (TypeError,ValueError):
        raise HTTPException(422,"Use a timezone-aware time range of at most 90 days.") from None
    return lower.astimezone(timezone.utc).isoformat(),upper.astimezone(timezone.utc).isoformat()


def count(db,model,*conditions):
    return db.scalar(select(func.count()).select_from(model).where(*conditions))


def job_statement(org):
    return select(Record.id,Record.repository_id,Record.created_at,Record.version,*(Record.data[key].label(key) for key in JOB_FIELDS)).where(Record.organization_id==org,Record.kind=="job")


def operational_actor(db, request, permission, team_id=""):
    actor,token=admin_user(db,request,permission,team_id=team_id or None)
    if team_id:
        scoped_team(db,actor,team_id,permission=permission)
    return actor,token


def team_jobs(org, team_id, column=Record.id):
    return exists(select(JobTeamAttribution.job_id).where(JobTeamAttribution.organization_id==org,
        JobTeamAttribution.team_id==team_id,JobTeamAttribution.job_id==column))


def job_value(row):
    value=dict(row._mapping)
    value["diagnostic_policy"]="Operational fields only; encrypted inputs, raw cache, source and worker credentials are excluded."
    return safe_metadata(value)


@router.get("/dashboard")
def dashboard(request:Request,start:str | None=Query(None,max_length=50),end:str | None=Query(None,max_length=50)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"usage.read")
        org=actor.organization_id
        lower,upper=dates(start,end)
        members=dict(db.execute(select(OrganizationMembership.state,func.count()).where(OrganizationMembership.organization_id==org).group_by(OrganizationMembership.state)).all())
        state=Record.data["state"].as_string()
        jobs=dict(db.execute(select(state,func.count()).where(Record.organization_id==org,Record.kind=="job",Record.created_at>=lower,Record.created_at<upper)
            .group_by(state)).all())
        return {"organization_id":org,"range":{"start":lower,"end":upper},"members":{"total":sum(members.values()),"recorded_states":members},
            "teams":count(db,Team,Team.organization_id==org,Team.archived.is_(False)),"repositories":count(db,Repository,Repository.organization_id==org),
            "pending_invitations":count(db,Invitation,Invitation.organization_id==org,Invitation.state=="PENDING",Invitation.expires_at>upper),
            "active_jobs":count(db,QueueEntry,QueueEntry.organization_id==org,QueueEntry.state.in_(["RUNNING","QUEUED"])),"jobs_by_state":jobs,
            "policy_count":count(db,FeaturePolicy,FeaturePolicy.organization_id==org),
            "activity_count":count(db,ActivityEvent,ActivityEvent.organization_id==org,ActivityEvent.created_at>=lower,ActivityEvent.created_at<upper),
            "limitations":["Membership states are recorded restrictions; expired temporary suspensions are evaluated live by authorization.",
                "Operational metadata does not grant access to repository source or evidence.","Activity collection starts with this release; historical events are not invented."]}


@router.get("/jobs")
def jobs(request:Request,state:str=Query("",max_length=40),repository_id:str=Query("",max_length=80),user_id:str=Query("",max_length=80),team_id:str=Query("",max_length=80),
    offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=operational_actor(db,request,"analyses.read",team_id)
        query=job_statement(actor.organization_id)
        if team_id:
            query=query.where(team_jobs(actor.organization_id,team_id))
        if state:
            query=query.where(Record.data["state"].as_string()==state)
        if repository_id:
            query=query.where(Record.repository_id==repository_id)
        if user_id:
            query=query.where(Record.data["user_id"].as_string()==user_id)
        rows,pagination=page(db,query.order_by(Record.created_at.desc(),Record.id),offset=offset,limit=limit)
        return {"items":[job_value(row) for row in rows],"page":pagination,"organization_id":actor.organization_id}


@router.get("/jobs/{job_id}")
def job_details(job_id:str,request:Request,team_id:str=Query("",max_length=80)):
    with session_factory() as db:
        actor,_=operational_actor(db,request,"analyses.read",team_id)
        query=job_statement(actor.organization_id).where(Record.id==job_id)
        if team_id:
            query=query.where(team_jobs(actor.organization_id,team_id))
        row=db.execute(query).first()
        if not row:
            raise HTTPException(404,"Job unavailable.")
        # Stages/performance are bounded metadata, never the full Record payload.
        detail=db.execute(select(Record.data["stages"],Record.data["performance"],Record.data["error_detail"],Record.data["errors"])
            .where(Record.id==job_id,Record.organization_id==actor.organization_id,Record.kind=="job")).first()
        entry=db.get(QueueEntry,job_id)
        return {**job_value(row),"diagnostics":safe_metadata({"stages":detail[0],"performance":detail[1],"error":detail[2],"errors":detail[3]}),
            "queue":{"state":entry.state,"cancel_requested":entry.cancel_requested,"lease_expires_at":entry.lease_expires_at} if entry else None}


@router.post("/jobs/{job_id}/{action}")
def control_job(job_id:str,action:Literal["cancel","retry"],body:CommandBody,request:Request):
    permission="analyses.cancel" if action=="cancel" else "analyses.retry"
    with session_factory() as db:
        actor,_=admin_user(db,request,permission,mutation=True)
        from backend.scheduling import lock
        lock(db)
        def apply(current):
            job=db.scalar(select(Record).where(Record.id==job_id,Record.organization_id==current.organization_id,Record.kind=="job").with_for_update())
            if not job:
                raise HTTPException(404,"Job unavailable.")
            check_version(job,body.expected_version)
            if action=="retry":
                from backend.security import require_repo
                require_repo(db,current,job.repository_id)
            from backend.job_control import transition_job
            before=job.data.get("state")
            result=transition_job(db,current,job,action)
            return {"id":job.id,"state":job.data.get("state"),**result},{"before":before,"after":job.data.get("state"),"retry_count":job.data.get("retry_count")}
        result=command(db,actor,body,permission,"ADMIN_JOB_"+action.upper(),job_id,apply)
        if action=="retry" and not result.get("replayed"):
            from backend.queue import dispatch
            job=db.get(Record,job_id)
            dispatch(db,job)
            result={**result,"state":job.data.get("state"),"dispatch":job.data.get("dispatch")}
        return result


@router.get("/usage")
def usage(request:Request,start:str | None=Query(None,max_length=50),end:str | None=Query(None,max_length=50),
    team_id:str=Query("",max_length=80),user_id:str=Query("",max_length=80)):
    with session_factory() as db:
        actor,_=operational_actor(db,request,"usage.read",team_id)
        org=actor.organization_id
        lower,upper=dates(start,end)
        conditions=[Record.organization_id==org,Record.kind=="job",Record.created_at>=lower,Record.created_at<upper]
        if team_id:
            conditions.append(team_jobs(org,team_id))
        if user_id:
            scoped_member(db,actor,user_id)
            conditions.append(Record.data["user_id"].as_string()==user_id)
        duration=Record.data["duration_ms"].as_float()
        waiting=Record.data["queue_wait_ms"].as_float()
        aggregate=db.execute(select(func.count(),func.count(duration),func.sum(duration),func.avg(duration),func.count(waiting),func.avg(waiting))
            .where(*conditions)).one()
        day=func.substr(Record.created_at,1,10)
        source=Record.data["source"].as_string()
        daily=db.execute(select(day.label("day"),func.count().label("jobs"))
            .where(*conditions)
            .group_by(day).order_by("day")).all()
        sources=db.execute(select(source.label("source"),func.count().label("jobs"))
            .where(*conditions).group_by(source)).all()
        storage=db.scalar(select(func.sum(SourceBlob.bytes)).where(SourceBlob.organization_id==org)) if not team_id and not user_id else None
        return {"organization_id":org,"team_id":team_id or None,"user_id":user_id or None,"range":{"start":lower,"end":upper},"jobs":aggregate[0],"duration_samples":aggregate[1],
            "total_recorded_duration_ms":aggregate[2],"mean_recorded_duration_ms":aggregate[3],"queue_wait_samples":aggregate[4],"mean_queue_wait_ms":aggregate[5],
            "daily_jobs":[dict(row._mapping) for row in daily],"sources":[dict(row._mapping) for row in sources],
            "source_plaintext_bytes":storage,"inventory_file_records":count(db,SourceInventoryFile,SourceInventoryFile.organization_id==org) if not team_id and not user_id else None,
            "cpu_seconds":None,"peak_memory_bytes":None,"worker_utilization_percent":None,
            "provenance":{"duration":"Recorded pipeline wall time, not CPU or billed worker time.","storage":"Deduplicated stored source plaintext bytes, not encrypted filesystem or database allocation.",
                "missing_metrics":"Null means unavailable. Missing job timing is never interpreted as zero.",
                "team_scope":"Submission-time team attribution starts with this release. Current team membership never invents historical usage. Jobs can count in several teams; team totals are not additive.",
                "storage_scope":"Storage is measured only for an entire organization; shared blobs are not charged to individual users or teams."}}


@router.get("/usage/actors")
def actor_usage(request:Request,start:str | None=Query(None,max_length=50),end:str | None=Query(None,max_length=50),
    offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,_=admin_user(db,request,"usage.read")
        lower,upper=dates(start,end)
        owner=Record.data["user_id"].as_string()
        duration=Record.data["duration_ms"].as_float()
        query=select(owner.label("user_id"),func.count().label("jobs"),func.count(duration).label("duration_samples"),func.sum(duration).label("recorded_duration_ms")).where(
            Record.organization_id==actor.organization_id,Record.kind=="job",Record.created_at>=lower,Record.created_at<upper).group_by(owner)
        rows,pagination=page(db,query.order_by(func.count().desc(),owner),offset=offset,limit=limit)
        return {"items":[dict(r._mapping) for r in rows],"page":pagination,"organization_id":actor.organization_id,
            "provenance":"Existing recorded job actor IDs; null means unattributed. Wall time is not CPU time."}


@router.get("/activity")
def activity(request:Request,start:str | None=Query(None,max_length=50),end:str | None=Query(None,max_length=50),
    actor_id:str=Query("",max_length=80),repository_id:str=Query("",max_length=80),action:str=Query("",max_length=80),
    category:str=Query("",max_length=30),outcome:str=Query("",max_length=20),correlation_id:str=Query("",max_length=100),target_id:str=Query("",max_length=100),
    team_id:str=Query("",max_length=80),export:bool=False,offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,token=operational_actor(db,request,"audit.export" if export else "activity.read",team_id)
        if export:
            from backend.governance import require_feature
            require_feature(db,actor,"exports")
            fresh_authentication(db,token)
        lower,upper=dates(start,end)
        query=select(ActivityEvent).where(ActivityEvent.organization_id==actor.organization_id,ActivityEvent.created_at>=lower,ActivityEvent.created_at<upper)
        if team_id:
            query=query.where(or_(ActivityEvent.target_id==team_id,team_jobs(actor.organization_id,team_id,ActivityEvent.target_id),
                team_jobs(actor.organization_id,team_id,ActivityEvent.correlation_id)))
        for column,value in ((ActivityEvent.actor_id,actor_id),(ActivityEvent.repository_id,repository_id),(ActivityEvent.action,action),
            (ActivityEvent.category,category),(ActivityEvent.outcome,outcome),(ActivityEvent.correlation_id,correlation_id),(ActivityEvent.target_id,target_id)):
            if value:
                query=query.where(column==value)
        rows,pagination=page(db,query.order_by(ActivityEvent.created_at.desc(),ActivityEvent.id.desc()),offset=offset,limit=limit)
        result={"items":[{"id":a.id,"actor_id":a.actor_id,"repository_id":a.repository_id,"action":a.action,"category":a.category,"outcome":a.outcome,
            "target_id":a.target_id,"correlation_id":a.correlation_id,"created_at":a.created_at,"data":safe_metadata(a.data)} for (a,) in rows],
            "page":pagination,"range":{"start":lower,"end":upper},"organization_id":actor.organization_id,"team_id":team_id or None,
            "team_scope":"Team-targeted events and jobs attributed at submission; unrelated actions by current team members are excluded."}
        if export:
            from backend.domain import audit
            audit(db,actor,"ADMIN_ACTIVITY_EXPORTED",actor.organization_id,{"actor_id":actor.id,"rows":len(rows),"offset":offset})
            db.commit()
        return result


@router.get("/activity/{event_id}")
def activity_details(event_id:str,request:Request,team_id:str=Query("",max_length=80)):
    with session_factory() as db:
        actor,_=operational_actor(db,request,"activity.read",team_id)
        query=select(ActivityEvent).where(ActivityEvent.id==event_id,ActivityEvent.organization_id==actor.organization_id)
        if team_id:
            query=query.where(or_(ActivityEvent.target_id==team_id,team_jobs(actor.organization_id,team_id,ActivityEvent.target_id),
                team_jobs(actor.organization_id,team_id,ActivityEvent.correlation_id)))
        event=db.scalar(query)
        if not event:
            raise HTTPException(404,"Activity unavailable in this scope.")
        return {"id":event.id,"organization_id":event.organization_id,"actor_id":event.actor_id,"repository_id":event.repository_id,
            "action":event.action,"category":event.category,"outcome":event.outcome,"target_id":event.target_id,
            "correlation_id":event.correlation_id,"created_at":event.created_at,"metadata":safe_metadata(event.data)}


@router.get("/audit")
def audit_events(request:Request,action:str=Query("",max_length=80),target_id:str=Query("",max_length=100),
    start:str | None=Query(None,max_length=50),end:str | None=Query(None,max_length=50),export:bool=False,
    offset:int=Query(0,ge=0,le=100_000),limit:int=Query(25,ge=1,le=100)):
    with session_factory() as db:
        actor,token=admin_user(db,request,"audit.export" if export else "audit.read")
        if export:
            from backend.governance import require_feature
            require_feature(db,actor,"exports")
            fresh_authentication(db,token)
        lower,upper=dates(start,end)
        query=select(Audit,AuditLink.sequence,AuditLink.digest).outerjoin(AuditLink,AuditLink.event_id==Audit.id).where(
            Audit.organization_id==actor.organization_id,Audit.created_at>=lower,Audit.created_at<upper)
        if action:
            query=query.where(Audit.action==action)
        if target_id:
            query=query.where(Audit.target==target_id)
        rows,pagination=page(db,query.order_by(Audit.created_at.desc(),Audit.id.desc()),offset=offset,limit=limit)
        result={"items":[{"id":a.id,"actor":a.actor,"action":a.action,"target_id":a.target,"repository_id":a.repository_id,"created_at":a.created_at,
            "sequence":sequence,"digest":chain_digest,"data":safe_metadata({key:a.data[key] for key in ("actor_id","permission","command_id","reason","change","before","after","request_id","error_type","retry_count") if key in a.data})}
            for a,sequence,chain_digest in rows],"page":pagination,"integrity":"Existing transactionally chained audit; not immutable external storage.","organization_id":actor.organization_id}
        if export:
            from backend.domain import audit
            audit(db,actor,"ADMIN_AUDIT_EXPORTED",actor.organization_id,{"actor_id":actor.id,"rows":len(rows),"offset":offset})
            db.commit()
        return result


@router.get("/security")
def security_summary(request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"security.investigate")
        lower,upper=dates(days=7)
        org=actor.organization_id
        denied=count(db,ActivityEvent,ActivityEvent.organization_id==org,ActivityEvent.outcome=="DENIED",ActivityEvent.created_at>=lower,ActivityEvent.created_at<upper)
        failed_login=count(db,ActivityEvent,ActivityEvent.organization_id==org,ActivityEvent.action=="LOGIN_FAILED",ActivityEvent.created_at>=lower,ActivityEvent.created_at<upper)
        expiring=count(db,FeaturePolicy,FeaturePolicy.organization_id==org,FeaturePolicy.expires_at.is_not(None),FeaturePolicy.expires_at>upper,
            FeaturePolicy.expires_at<(datetime.now(timezone.utc)+timedelta(days=7)).isoformat())
        return {"organization_id":org,"range":{"start":lower,"end":upper},"denied_operations":denied,"recorded_failed_logins":failed_login,
            "expiring_policies_next_7_days":expiring,"suspended_memberships":count(db,OrganizationMembership,OrganizationMembership.organization_id==org,OrganizationMembership.state=="SUSPENDED"),
            "mfa":"Use configured OIDC provider MFA; local password step-up is not MFA.","support_content_elevation":"Unavailable; platform roles have no automatic tenant source grants.",
            "limitations":["Events are bounded operational telemetry. This page makes no anomaly-detection or legal-compliance claim."]}


@router.get("/health")
def organization_health(request:Request):
    with session_factory() as db:
        actor,_=admin_user(db,request,"analyses.read")
        db.execute(select(1))
        entries=db.execute(select(QueueEntry.state,func.count()).where(QueueEntry.organization_id==actor.organization_id).group_by(QueueEntry.state)).all()
        return {"organization_id":actor.organization_id,"api":"RESPONDING","database":"RESPONDING","database_engine":db.get_bind().dialect.name,
            "queue_states":dict(entries),"worker_live_heartbeat":None,"notice":"Queue state and lease metadata are available. A live worker heartbeat is not instrumented."}
