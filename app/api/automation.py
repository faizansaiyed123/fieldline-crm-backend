from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import require_roles
from app.db.session import get_db
from app.models import Membership, MembershipRole
from app.schemas.automation import (
    AutomationRuleCreate,
    AutomationRuleResponse,
    AutomationRuleUpdate,
)
from app.services.automation import create_rule, get_rule, list_rules, update_rule

router = APIRouter(
    prefix="/organizations/{organization_id}/automation",
    tags=["automation"],
)


@router.get("/rules", response_model=list[AutomationRuleResponse])
def get_rules(
    organization_id: UUID,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> list[AutomationRuleResponse]:
    return [
        AutomationRuleResponse.model_validate(rule)
        for rule in list_rules(db, organization_id=organization_id)
    ]


@router.post(
    "/rules",
    response_model=AutomationRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    organization_id: UUID,
    payload: AutomationRuleCreate,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> AutomationRuleResponse:
    try:
        rule = create_rule(
            db,
            organization_id=organization_id,
            name=payload.name,
            trigger=payload.trigger,
            action_type=payload.action_type,
            action_config=payload.action_config.model_dump(),
            enabled=payload.enabled,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An automation rule with this name already exists",
        ) from exc
    return AutomationRuleResponse.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=AutomationRuleResponse)
def update(
    organization_id: UUID,
    rule_id: UUID,
    payload: AutomationRuleUpdate,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> AutomationRuleResponse:
    rule = get_rule(db, organization_id=organization_id, rule_id=rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    update_rule(db, rule=rule, enabled=payload.enabled)
    db.commit()
    return AutomationRuleResponse.model_validate(rule)
