from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership, require_roles
from app.db.session import get_db
from app.models import Membership, MembershipRole
from app.schemas.standout import (
    AutomationRunResponse,
    BusinessRuleResponse,
    BusinessRuleUpdate,
    DailyPlannerResponse,
    DataQualityResponse,
    MergeRequest,
    MergeResponse,
    RelationshipGraphResponse,
    StuckOpportunityResponse,
    SystemHealthResponse,
)
from app.services.automation_history import get_automation_run, list_automation_runs
from app.services.business_rules import list_rule_values, set_rule_value
from app.services.data_quality import build_data_quality_report
from app.services.merge import merge_record
from app.services.pipeline_intelligence import get_stuck_opportunities
from app.services.relationship_graph import build_relationship_graph
from app.services.system_health import get_system_health
from app.services.work_planner import get_daily_plan

router = APIRouter(
    prefix="/organizations/{organization_id}",
    tags=["standout"],
)


@router.get("/data-quality", response_model=DataQualityResponse)
def data_quality(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> DataQualityResponse:
    return build_data_quality_report(db, organization_id=organization_id)


@router.post(
    "/data-quality/{entity_type}/{merged_id}/merge",
    response_model=MergeResponse,
)
def merge(
    organization_id: UUID,
    entity_type: str,
    merged_id: UUID,
    payload: MergeRequest,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> MergeResponse:
    try:
        operation = merge_record(
            db,
            organization_id=organization_id,
            entity_type=entity_type,
            survivor_id=payload.survivor_id,
            merged_id=merged_id,
            actor_user_id=membership.user_id,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return MergeResponse(
        operation_id=operation.id,
        entity_type=entity_type,
        survivor_id=operation.survivor_id,
        merged_id=operation.merged_id,
        completed_at=operation.completed_at or datetime.now(UTC),
    )


@router.get("/business-rules", response_model=list[BusinessRuleResponse])
def business_rules(
    organization_id: UUID,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> list[BusinessRuleResponse]:
    return [
        BusinessRuleResponse.model_validate(item)
        for item in list_rule_values(db, organization_id=organization_id)
    ]


@router.patch("/business-rules/{key}", response_model=BusinessRuleResponse)
def update_business_rule(
    organization_id: UUID,
    key: str,
    payload: BusinessRuleUpdate,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> BusinessRuleResponse:
    try:
        set_rule_value(
            db,
            organization_id=organization_id,
            key=key,
            value=payload.value,
            actor_user_id=membership.user_id,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    for item in list_rule_values(db, organization_id=organization_id):
        if item["key"] == key:
            return BusinessRuleResponse.model_validate(item)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business rule not found")


@router.get("/work-planner", response_model=DailyPlannerResponse)
def work_planner(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=50),
) -> DailyPlannerResponse:
    return get_daily_plan(db, organization_id=organization_id, limit=limit)


@router.get("/pipeline/stuck", response_model=StuckOpportunityResponse)
def stuck_opportunities(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=50),
) -> StuckOpportunityResponse:
    items = get_stuck_opportunities(db, organization_id=organization_id, limit=limit)
    configured = next(
        item["value"] for item in list_rule_values(db, organization_id=organization_id)
        if item["key"] == "opportunity_stage_stuck_days"
    )
    return StuckOpportunityResponse(
        generated_at=datetime.now(UTC),
        configured_threshold_days=int(configured),
        items=items,
    )


@router.get("/automation/runs", response_model=list[AutomationRunResponse])
def automation_runs(
    organization_id: UUID,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[AutomationRunResponse]:
    return list_automation_runs(db, organization_id=organization_id, limit=limit)


@router.get("/automation/runs/{run_id}", response_model=AutomationRunResponse)
def automation_run_detail(
    organization_id: UUID,
    run_id: UUID,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> AutomationRunResponse:
    result = get_automation_run(db, organization_id=organization_id, run_id=run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation run not found")
    return result


@router.get(
    "/contacts/{contact_id}/relationship-graph",
    response_model=RelationshipGraphResponse,
)
def relationship_graph(
    organization_id: UUID,
    contact_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> RelationshipGraphResponse:
    try:
        return build_relationship_graph(
            db,
            organization_id=organization_id,
            contact_id=contact_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/system-health",
    response_model=SystemHealthResponse,
)
def system_health(
    organization_id: UUID,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> SystemHealthResponse:
    return get_system_health(db)


