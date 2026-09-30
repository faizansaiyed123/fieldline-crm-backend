from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Membership
from app.schemas.contact import ContactCreate, ContactListResponse, ContactResponse, ContactUpdate
from app.services.contact import (
    archive_contact,
    create_contact,
    get_contact,
    search_contacts,
    update_contact,
)

router = APIRouter(prefix="/organizations/{organization_id}/contacts", tags=["contacts"])


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create(
    organization_id: UUID,
    payload: ContactCreate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> ContactResponse:
    try:
        contact = create_contact(
            db,
            organization_id=organization_id,
            actor_user_id=membership.user_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone=payload.phone,
            job_title=payload.job_title,
            lifecycle=payload.lifecycle,
            company_id=payload.company_id,
        )
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
                if isinstance(exc, ValueError)
                else status.HTTP_409_CONFLICT
            ),
            detail=str(exc),
        ) from exc
    return ContactResponse.model_validate(contact)


@router.get("", response_model=ContactListResponse)
def list_contacts(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    company_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ContactListResponse:
    items, total = search_contacts(
        db,
        organization_id=organization_id,
        query=q,
        company_id=company_id,
        page=page,
        page_size=page_size,
    )
    return ContactListResponse(
        items=[ContactResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
def get(
    organization_id: UUID,
    contact_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> ContactResponse:
    contact = get_contact(db, organization_id=organization_id, contact_id=contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return ContactResponse.model_validate(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
def update(
    organization_id: UUID,
    contact_id: UUID,
    payload: ContactUpdate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> ContactResponse:
    contact = get_contact(db, organization_id=organization_id, contact_id=contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return ContactResponse.model_validate(contact)
    try:
        update_contact(
            db,
            contact=contact,
            actor_user_id=membership.user_id,
            changes=changes,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ContactResponse.model_validate(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive(
    organization_id: UUID,
    contact_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> Response:
    contact = get_contact(db, organization_id=organization_id, contact_id=contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    archive_contact(
        db,
        contact=contact,
        actor_user_id=membership.user_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
