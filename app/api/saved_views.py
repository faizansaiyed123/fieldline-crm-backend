from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Membership, MembershipRole
from app.schemas.contact import ContactListResponse, ContactResponse
from app.schemas.saved_view import (
    SavedViewCreate,
    SavedViewResponse,
    SavedViewUpdate,
)
from app.services.saved_view import (
    can_manage_saved_view,
    create_saved_view,
    delete_saved_view,
    execute_contact_view,
    get_saved_view,
    list_saved_views,
    update_saved_view,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/saved-views",
    tags=["saved-views"],
)


@router.get("", response_model=list[SavedViewResponse])
def list_views(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> list[SavedViewResponse]:
    return [
        SavedViewResponse.model_validate(view)
        for view in list_saved_views(db, organization_id=organization_id, user_id=membership.user_id)
    ]


@router.post("", response_model=SavedViewResponse, status_code=status.HTTP_201_CREATED)
def create(
    organization_id: UUID,
    payload: SavedViewCreate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> SavedViewResponse:
    if payload.shared and membership.role == MembershipRole.MEMBER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners/admins can create shared views",
        )
    try:
        view = create_saved_view(
            db,
            organization_id=organization_id,
            user_id=membership.user_id,
            name=payload.name,
            shared=payload.shared,
            definition=payload.definition.model_dump(mode="json"),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Saved view could not be created",
        ) from exc
    return SavedViewResponse.model_validate(view)


@router.get("/{view_id}", response_model=SavedViewResponse)
def get(
    organization_id: UUID,
    view_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> SavedViewResponse:
    view = get_saved_view(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        view_id=view_id,
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    return SavedViewResponse.model_validate(view)


@router.patch("/{view_id}", response_model=SavedViewResponse)
def update(
    organization_id: UUID,
    view_id: UUID,
    payload: SavedViewUpdate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> SavedViewResponse:
    view = get_saved_view(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        view_id=view_id,
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    is_admin = membership.role in {MembershipRole.OWNER, MembershipRole.ADMIN}
    if not can_manage_saved_view(view, user_id=membership.user_id, is_admin=is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if payload.shared and membership.role == MembershipRole.MEMBER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners/admins can create shared views",
        )
    update_saved_view(
        db,
        view=view,
        actor_user_id=membership.user_id,
        name=payload.name,
        shared=payload.shared,
        definition=payload.definition.model_dump(mode="json") if payload.definition else None,
    )
    db.commit()
    return SavedViewResponse.model_validate(view)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    organization_id: UUID,
    view_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> None:
    view = get_saved_view(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        view_id=view_id,
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    is_admin = membership.role in {MembershipRole.OWNER, MembershipRole.ADMIN}
    if not can_manage_saved_view(view, user_id=membership.user_id, is_admin=is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    delete_saved_view(db, view=view, actor_user_id=membership.user_id)
    db.commit()


@router.get("/{view_id}/execute", response_model=ContactListResponse)
def execute(
    organization_id: UUID,
    view_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ContactListResponse:
    view = get_saved_view(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        view_id=view_id,
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")

    items, total = execute_contact_view(
        db,
        view=view,
        organization_id=organization_id,
        limit=page_size,
        page=page,
    )
    return ContactListResponse(
        items=[ContactResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )
