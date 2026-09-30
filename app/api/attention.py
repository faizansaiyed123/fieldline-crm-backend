from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Membership
from app.schemas.attention import AttentionItem, AttentionResponse
from app.services.attention import get_attention_queue

router = APIRouter(prefix="/organizations/{organization_id}", tags=["attention"])


@router.get("/attention", response_model=AttentionResponse)
def attention(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> AttentionResponse:
    rows = get_attention_queue(
        db,
        organization_id=organization_id,
        limit=limit,
    )
    return AttentionResponse(
        items=[AttentionItem.model_validate(row) for row in rows],
        generated_at=datetime.now(UTC),
    )
