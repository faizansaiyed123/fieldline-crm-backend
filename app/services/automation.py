from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import AutomationRule, AutomationRun, Opportunity, Task
from app.services.audit import record_audit


def list_rules(db: Session, *, organization_id: UUID) -> list[AutomationRule]:
    return db.scalars(
        select(AutomationRule)
        .where(AutomationRule.organization_id == organization_id)
        .order_by(AutomationRule.created_at.asc())
    ).all()


def get_rule(
    db: Session,
    *,
    organization_id: UUID,
    rule_id: UUID,
) -> AutomationRule | None:
    return db.scalar(
        select(AutomationRule)
        .where(AutomationRule.organization_id == organization_id)
        .where(AutomationRule.id == rule_id)
        .limit(1)
    )


def create_rule(
    db: Session,
    *,
    organization_id: UUID,
    name: str,
    trigger: str,
    action_type: str,
    action_config: dict[str, object],
    enabled: bool,
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=organization_id,
        name=name,
        trigger=trigger,
        action_type=action_type,
        action_config=action_config,
        enabled=enabled,
    )
    db.add(rule)
    db.flush()
    return rule


def update_rule(
    db: Session,
    *,
    rule: AutomationRule,
    enabled: bool,
) -> AutomationRule:
    rule.enabled = enabled
    db.flush()
    return rule


def run_opportunity_automations(
    db: Session,
    *,
    opportunity: Opportunity,
    previous_status: str,
    actor_user_id: UUID,
) -> list[Task]:
    new_status = opportunity.status
    if previous_status == new_status or new_status not in {"won", "lost"}:
        return []

    trigger = f"opportunity.{new_status}"
    rules = db.scalars(
        select(AutomationRule)
        .where(AutomationRule.organization_id == opportunity.organization_id)
        .where(AutomationRule.trigger == trigger)
        .where(AutomationRule.enabled.is_(True))
        .order_by(AutomationRule.id.asc())
    ).all()

    created_tasks: list[Task] = []
    now = datetime.now(UTC)
    event_key = f"opportunity:{opportunity.id}:{previous_status}:{new_status}:{opportunity.stage_id}"

    for rule in rules:
        run_insert = (
            insert(AutomationRun)
            .values(
                organization_id=opportunity.organization_id,
                rule_id=rule.id,
                event_key=event_key,
                status="running",
            )
            .on_conflict_do_nothing(index_elements=["rule_id", "event_key"])
            .returning(AutomationRun.id)
        )
        run_id = db.execute(run_insert).scalar_one_or_none()
        if run_id is None:
            continue

        config = dict(rule.action_config)
        if rule.action_type != "create_task":
            raise ValueError("Unsupported automation action")

        title = str(config.get("title", "Automated follow-up"))
        priority = str(config.get("priority", "normal"))
        due_days = int(config.get("due_days", 1))
        task = Task(
            organization_id=opportunity.organization_id,
            created_by_user_id=actor_user_id,
            assigned_to_user_id=opportunity.owner_user_id,
            company_id=opportunity.company_id,
            contact_id=opportunity.contact_id,
            opportunity_id=opportunity.id,
            title=title,
            priority=priority,
            due_at=now + timedelta(days=due_days),
        )
        db.add(task)
        db.flush()

        run = db.scalar(
            select(AutomationRun)
            .where(AutomationRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise RuntimeError("Automation run could not be loaded")
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.result = {"task_id": str(task.id), "action": "create_task"}

        record_audit(
            db,
            organization_id=opportunity.organization_id,
            actor_user_id=actor_user_id,
            entity_type="task",
            entity_id=task.id,
            action="automation_created",
            summary=f"Created task from automation rule {rule.name}",
            after_data={
                "title": task.title,
                "priority": task.priority,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "opportunity_id": str(opportunity.id),
            },
        )
        created_tasks.append(task)

    return created_tasks
