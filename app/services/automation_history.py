from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AutomationRule, AutomationRun
from app.schemas.standout import AutomationRunResponse


def list_automation_runs(
    db: Session,
    *,
    organization_id: UUID,
    limit: int = 50,
) -> list[AutomationRunResponse]:
    rows = db.execute(
        select(AutomationRun, AutomationRule)
        .join(AutomationRule, AutomationRule.id == AutomationRun.rule_id)
        .where(AutomationRun.organization_id == organization_id)
        .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
        .limit(limit)
    ).all()
    return [
        AutomationRunResponse(
            id=run.id,
            workflow=rule.name,
            trigger=rule.trigger,
            event_key=run.event_key,
            status=run.status,
            action_type=rule.action_type,
            result=run.result,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )
        for run, rule in rows
    ]


def get_automation_run(
    db: Session,
    *,
    organization_id: UUID,
    run_id: UUID,
) -> AutomationRunResponse | None:
    row = db.execute(
        select(AutomationRun, AutomationRule)
        .join(AutomationRule, AutomationRule.id == AutomationRun.rule_id)
        .where(AutomationRun.organization_id == organization_id)
        .where(AutomationRun.id == run_id)
        .limit(1)
    ).first()
    if row is None:
        return None
    run, rule = row
    return AutomationRunResponse(
        id=run.id,
        workflow=rule.name,
        trigger=rule.trigger,
        event_key=run.event_key,
        status=run.status,
        action_type=rule.action_type,
        result=run.result,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )
