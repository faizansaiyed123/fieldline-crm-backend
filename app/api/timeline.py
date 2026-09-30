from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Contact, Membership
from app.schemas.timeline import TimelineItem, TimelineResponse
from app.services.timeline import get_contact_timeline

router = APIRouter(prefix="/organizations/{organization_id}", tags=["timeline"])


@router.get("/contacts/{contact_id}/timeline", response_model=TimelineResponse)
def contact_timeline(
    organization_id: UUID,
    contact_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = Query(default=None),
    before_id: UUID | None = Query(default=None),
) -> TimelineResponse:
    contact_exists = db.scalar(
        select(Contact.id)
        .where(Contact.organization_id == organization_id)
        .where(Contact.id == contact_id)
        .where(Contact.deleted_at.is_(None))
        .limit(1)
    )
    if contact_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    rows, next_before, next_before_id = get_contact_timeline(
        db,
        organization_id=organization_id,
        contact_id=contact_id,
        limit=limit,
        before=before,
        before_id=before_id,
    )
    return TimelineResponse(
        items=[TimelineItem.model_validate(row) for row in rows],
        limit=limit,
        next_before=next_before,
        next_before_id=next_before_id,
    )
