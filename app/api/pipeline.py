from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership, require_roles
from app.db.session import get_db
from app.models import Membership, MembershipRole
from app.schemas.pipeline import PipelineStageCreate, PipelineStageResponse
from app.services.pipeline import create_stage, list_stages

router = APIRouter(prefix="/organizations/{organization_id}/pipeline", tags=["pipeline"])


@router.get("/stages", response_model=list[PipelineStageResponse])
def get_stages(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> list[PipelineStageResponse]:
    return [PipelineStageResponse.model_validate(stage) for stage in list_stages(
        db, organization_id=organization_id
    )]


@router.post("/stages", response_model=PipelineStageResponse, status_code=status.HTTP_201_CREATED)
def create_pipeline_stage(
    organization_id: UUID,
    payload: PipelineStageCreate,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> PipelineStageResponse:
    try:
        stage = create_stage(
            db,
            organization_id=organization_id,
            name=payload.name,
            win_probability=payload.win_probability,
            is_closed=payload.is_closed,
            is_won=payload.is_won,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pipeline stage with this name already exists",
        ) from exc
    return PipelineStageResponse.model_validate(stage)
