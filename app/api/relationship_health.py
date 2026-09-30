from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Membership
from app.schemas.relationship_health import RelationshipHealthResponse
from app.services.relationship_health import calculate_relationship_health

router = APIRouter(
    prefix="/organizations/{organization_id}",
    tags=["relationship-health"],
)


@router.get(
    "/contacts/{contact_id}/relationship-health",
    response_model=RelationshipHealthResponse,
)
def relationship_health(
    organization_id: UUID,
    contact_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> RelationshipHealthResponse:
    try:
        result = calculate_relationship_health(
            db,
            organization_id=organization_id,
            contact_id=contact_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return RelationshipHealthResponse.model_validate(result)
