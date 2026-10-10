"""One-time, two-account consent bootstrap. Never run from an HTTP endpoint."""
import getpass

from sqlalchemy import func, select, update

from backend.admin_models import GovernanceRevision, PlatformOperator
from backend.db import Session, User
from backend.domain import audit
from backend.governance import resolve_principal
from backend.security import passwords


def main():
    print("Initial platform governance requires two distinct existing organization-owner accounts and their local password consent.")
    with Session() as db:
        if not db.get(GovernanceRevision,"PLATFORM"):
            raise SystemExit("Apply and verify the administration migration before initial bootstrap.")
        identities=[]
        for label in ("First", "Second"):
            email=input(f"{label} consenting owner email: ").strip().lower()
            password=getpass.getpass(f"{label} owner's own existing password: ")
            user=db.scalar(select(User).where(User.email==email))
            try:
                principal=resolve_principal(db,user) if user else None
                if not principal or not principal.enabled or principal.role!="ORG_OWNER" or user.id=="demo-engineer" or not user.local_login_allowed or not passwords.verify(user.password_hash,password):
                    raise ValueError()
            except Exception:
                raise SystemExit("Existing enabled local owner authentication failed. No accounts or credentials were changed.") from None
            identities.append(principal)
            password=""
        if identities[0].id==identities[1].id:
            raise SystemExit("Two distinct consenting identities are required.")
        if input("Type BOOTSTRAP TWO PLATFORM SUPER ADMINISTRATORS to confirm: ").strip()!="BOOTSTRAP TWO PLATFORM SUPER ADMINISTRATORS":
            raise SystemExit("No changes made.")
        db.execute(update(GovernanceRevision).where(GovernanceRevision.scope_key=="PLATFORM").values(revision=GovernanceRevision.revision+1))
        if db.scalar(select(func.count()).select_from(PlatformOperator)):
            raise SystemExit("Bootstrap is closed because operator records already exist. Use the audited approval workflow; this tool cannot reset governance.")
        for principal in identities:
            db.add(PlatformOperator(user_id=principal.id,role="PLATFORM_SUPER_ADMIN",enabled=True))
            audit(db,principal,"PLATFORM_BOOTSTRAPPED",principal.id,{"actor_id":principal.id,"permission":"OFFLINE_TWO_ACCOUNT_BOOTSTRAP",
                "reason":"Two distinct enabled local organization-owner credentials and explicit local operator confirmation.",
                "consenting_account_ids":[person.id for person in identities],"source_access_granted":False})
        db.commit()
    print("Two platform operators created with audited consent. Tenant source grants remain separate. Existing passwords were preserved.")


if __name__=="__main__":
    main()
