from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import String, cast, exists, func, select
from sqlalchemy.orm import Session

from app.models import Activity, AuditEvent, Opportunity, PipelineStage, Task
from app.schemas.standout import StuckOpportunity
from app.services.business_rules import get_rule_value


def get_stuck_opportunities(
    db: Session,
    *,
    organization_id: UUID,
    limit: int = 50,
) -> list[StuckOpportunity]:
    now = datetime.now(UTC)
    stuck_days = get_rule_value(
        db,
        organization_id=organization_id,
        key="opportunity_stage_stuck_days",
    )
    inactivity_days = get_rule_value(
        db,
        organization_id=organization_id,
        key="opportunity_inactivity_days",
    )

    last_activity = (
        select(func.max(Activity.occurred_at))
        .where(
            Activity.organization_id == organization_id,
            Activity.opportunity_id == Opportunity.id,
        )
        .correlate(Opportunity)
        .scalar_subquery()
    )
    stage_entered = (
        select(func.max(AuditEvent.created_at))
        .where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.entity_type == "opportunity",
            AuditEvent.entity_id == Opportunity.id,
            AuditEvent.after_data["stage_id"].astext == cast(Opportunity.stage_id, String),
        )
        .correlate(Opportunity)
        .scalar_subquery()
    )
    future_action = exists(
        select(Task.id).where(
            Task.organization_id == organization_id,
            Task.opportunity_id == Opportunity.id,
            Task.completed_at.is_(None),
            Task.due_at.is_not(None),
            Task.due_at >= now,
        )
    )
    overdue_tasks = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.organization_id == organization_id,
            Task.opportunity_id == Opportunity.id,
            Task.completed_at.is_(None),
            Task.due_at.is_not(None),
            Task.due_at < now,
        )
        .correlate(Opportunity)
        .scalar_subquery()
    )

    # Stage-entry timestamps are recorded in audit after_data. If history is incomplete,
    # fall back to the opportunity update time rather than inventing age.
    statement = (
        select(
            Opportunity,
            PipelineStage.name.label("stage_name"),
            last_activity.label("last_activity_at"),
            func.coalesce(stage_entered, Opportunity.updated_at).label("stage_entered_at"),
            overdue_tasks.label("overdue_task_count"),
            future_action.label("has_next_action"),
        )
        .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
        .where(
            Opportunity.organization_id == organization_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.status == "open",
        )
        .order_by(Opportunity.updated_at.asc(), Opportunity.id.asc())
        .limit(limit * 2)
    )

    rows = db.execute(statement).all()
    items: list[StuckOpportunity] = []
    for opportunity, stage_name, activity_at, stage_entered_at, overdue_count, has_next_action in rows:
        stage_age_days = max(0, int((now - stage_entered_at).total_seconds() // 86400))
        activity_age_days = (
            int((now - activity_at).total_seconds() // 86400) if activity_at else None
        )
        reasons: list[str] = []
        if stage_age_days >= stuck_days:
            reasons.append(f"Stage has not changed for {stage_age_days} days")
        if activity_age_days is None or activity_age_days >= inactivity_days:
            reasons.append(
                f"No recorded opportunity activity for {activity_age_days or 'an extended period'} days"
            )
        if opportunity.expected_close_date and opportunity.expected_close_date <= now.date() + timedelta(days=7):
            reasons.append("Expected close date is within 7 days or overdue")
        if int(overdue_count or 0) > 0:
            reasons.append(f"{int(overdue_count)} overdue incomplete task(s)")
        if not has_next_action:
            reasons.append("No future follow-up task is scheduled")

        if not reasons:
            continue

        if int(overdue_count or 0) > 0:
            action = "Complete or reschedule the overdue follow-up"
        elif not has_next_action:
            action = "Schedule a concrete next action"
        elif opportunity.expected_close_date and opportunity.expected_close_date <= now.date() + timedelta(days=7):
            action = "Review close plan and update the next step"
        else:
            action = "Review the opportunity and advance or requalify it"

        items.append(
            StuckOpportunity(
                id=opportunity.id,
                name=opportunity.name,
                stage_id=opportunity.stage_id,
                stage_name=stage_name,
                amount=str(opportunity.amount) if opportunity.amount is not None else None,
                status=opportunity.status,
                stage_age_days=stage_age_days,
                last_activity_at=activity_at,
                expected_close_date=opportunity.expected_close_date.isoformat() if opportunity.expected_close_date else None,
                overdue_task_count=int(overdue_count or 0),
                has_next_action=bool(has_next_action),
                reasons=reasons,
                recommended_action=action,
            )
        )
        if len(items) >= limit:
            break

    items.sort(
        key=lambda item: (
            -item.overdue_task_count,
            -item.stage_age_days,
            item.expected_close_date or "9999-12-31",
            str(item.id),
        )
    )
    return items

