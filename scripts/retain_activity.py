"""Preview or prune old routine telemetry in one tenant; never prune audit history."""
import argparse
import getpass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from backend.admin_common import lock_scope
from backend.admin_models import ActivityEvent
from backend.db import Session, User
from backend.domain import audit
from backend.governance import resolve_principal
from backend.security import passwords


def retain(db, actor, *, days=90, batch_size=500, apply=False, reason=""):
    actor=resolve_principal(db,actor,actor.organization_id)
    if not actor.enabled or actor.role!="ORG_OWNER" or not 30<=days<=3650 or not 1<=batch_size<=1000:
        raise HTTPException(403,"An enabled organization owner and bounded retention window are required.")
    if apply and len(reason.strip())<10:
        raise HTTPException(422,"Provide a meaningful retention reason.")
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    # Audit-derived mirrors remain available with their permanent audit chain.
    conditions=(ActivityEvent.organization_id==actor.organization_id,ActivityEvent.created_at<cutoff,
        ActivityEvent.data["audit_event_id"].as_string().is_(None))
    if apply:
        lock_scope(db,actor.organization_id)
    eligible=db.scalar(select(func.count()).select_from(ActivityEvent).where(*conditions))
    removed=0
    if apply:
        ids=list(db.scalars(select(ActivityEvent.id).where(*conditions).order_by(ActivityEvent.created_at,ActivityEvent.id).limit(batch_size)))
        if ids:
            removed=db.execute(delete(ActivityEvent).where(ActivityEvent.organization_id==actor.organization_id,ActivityEvent.id.in_(ids))).rowcount
        audit(db,actor,"ADMIN_ROUTINE_ACTIVITY_RETENTION",actor.organization_id,{"actor_id":actor.id,
            "permission":"OFFLINE_OWNER_RETENTION","reason":reason,"days":days,"removed":removed,"audit_history_deleted":False})
        db.commit()
    return {"organization_id":actor.organization_id,"cutoff":cutoff,"eligible_routine_events":eligible,
        "removed":removed,"batch_limit":batch_size,"apply":apply,"audit_history_deleted":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id",required=True)
    parser.add_argument("--owner-email",required=True)
    parser.add_argument("--days",type=int,default=90)
    parser.add_argument("--batch-size",type=int,default=500)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--reason",default="")
    args=parser.parse_args()
    with Session() as db:
        user=db.scalar(select(User).where(User.email==args.owner_email.strip().lower()))
        supplied=getpass.getpass("Owner's own existing local password: ")
        try:
            if not user or not user.local_login_allowed or not passwords.verify(user.password_hash,supplied):
                raise ValueError()
        except Exception:
            raise SystemExit("Owner authentication failed. No data changed.") from None
        supplied=""
        actor=resolve_principal(db,user,args.organization_id)
        if args.apply and input(f"Type RETAIN ROUTINE ACTIVITY {args.organization_id} to confirm: ")!=f"RETAIN ROUTINE ACTIVITY {args.organization_id}":
            raise SystemExit("No data changed.")
        import json
        print(json.dumps(retain(db,actor,days=args.days,batch_size=args.batch_size,apply=args.apply,reason=args.reason)))


if __name__=="__main__":
    main()
