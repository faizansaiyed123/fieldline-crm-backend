from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id
from app.db.session import get_db
from app.models import Membership, MembershipRole


def require_membership(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Membership:
    membership = db.scalar(
        select(Membership)
        .where(Membership.organization_id == organization_id)
        .where(Membership.user_id == user_id)
        .limit(1)
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return membership


def require_roles(*roles: MembershipRole):
    def dependency(membership: Membership = Depends(require_membership)) -> Membership:
        if membership.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return membership

    return dependency
