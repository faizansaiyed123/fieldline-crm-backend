from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Membership
from app.schemas.opportunity import (
    OpportunityCreate,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from app.services.opportunity import (
    archive_opportunity,
    create_opportunity,
    get_opportunity,
    search_opportunities,
    update_opportunity,
)

router = APIRouter(prefix="/organizations/{organization_id}/opportunities", tags=["opportunities"])


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
def create(
    organization_id: UUID,
    payload: OpportunityCreate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> OpportunityResponse:
    try:
        opportunity = create_opportunity(
            db,
            organization_id=organization_id,
            actor_user_id=membership.user_id,
            name=payload.name,
            stage_id=payload.stage_id,
            amount=payload.amount,
            company_id=payload.company_id,
            contact_id=payload.contact_id,
            expected_close_date=payload.expected_close_date,
        )
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        code = (
            status.HTTP_400_BAD_REQUEST
            if isinstance(exc, ValueError)
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return OpportunityResponse.model_validate(opportunity)


@router.get("", response_model=OpportunityListResponse)
def list_all(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    stage_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> OpportunityListResponse:
    items, total = search_opportunities(
        db,
        organization_id=organization_id,
        query=q,
        stage_id=stage_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return OpportunityListResponse(
        items=[OpportunityResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def get(
    organization_id: UUID,
    opportunity_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> OpportunityResponse:
    opportunity = get_opportunity(
        db,
        organization_id=organization_id,
        opportunity_id=opportunity_id,
    )
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return OpportunityResponse.model_validate(opportunity)


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
def update(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: OpportunityUpdate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> OpportunityResponse:
    opportunity = get_opportunity(
        db,
        organization_id=organization_id,
        opportunity_id=opportunity_id,
    )
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    try:
        changes = payload.model_dump(exclude_unset=True)
        update_opportunity(
            db,
            opportunity=opportunity,
            actor_user_id=membership.user_id,
            changes=changes,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OpportunityResponse.model_validate(opportunity)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive(
    organization_id: UUID,
    opportunity_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> Response:
    opportunity = get_opportunity(
        db,
        organization_id=organization_id,
        opportunity_id=opportunity_id,
    )
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    archive_opportunity(
        db,
        opportunity=opportunity,
        actor_user_id=membership.user_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
