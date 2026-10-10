"""Operator bootstrap; credentials are entered interactively and never logged."""

import getpass

from sqlalchemy import select

from backend.db import Organization, Session, User
from backend.domain import uid
from backend.security import passwords

if __name__ == "__main__":
    email = input("Operator email: ").strip().lower()
    organization_name = input("Organization name: ").strip()
    password = getpass.getpass("New local operator password (16+ characters): ")
    if len(password) < 16 or "@" not in email or not organization_name:
        raise SystemExit("A valid email, organization and 16+ character password are required.")
    with Session() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("User already exists. Existing credentials are not overwritten.")
        organization = Organization(id=uid(), name=organization_name)
        db.add(organization)
        db.flush()
        db.add(
            User(
                id=uid(),
                organization_id=organization.id,
                email=email,
                password_hash=passwords.hash(password),
                role="ORG_OWNER",
            )
        )
        db.flush()
        from backend.admin_models import OrganizationMembership
        user=db.scalar(select(User).where(User.email==email))
        db.add(OrganizationMembership(organization_id=organization.id,user_id=user.id,role="ORG_OWNER"))
        from backend.domain import audit
        audit(db,user,"WORKSPACE_CREATED",organization.id,{"actor_id":user.id,"method":"LOCAL_OWNER_CLI"})
        db.commit()
    print("Operator created. Repository grants are required for source access.")
