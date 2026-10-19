from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, Company, Contact, Membership, Opportunity, Task
from app.services.audit import record_audit


def _ensure_related_entity(
    db: Session,
    model,
    entity_id: UUID | None,
    organization_id: UUID,
    label: str,
) -> None:
    if entity_id is None:
        return
    statement = select(model.id).where(
        model.id == entity_id,
        model.organization_id == organization_id,
    )
    if db.scalar(statement) is None:
        raise ValueError(f"{label} not found in organization")


def _ensure_assignment(
    db: Session,
    user_id: UUID | None,
    organization_id: UUID,
) -> None:
    if user_id is None:
        return
    statement = select(Membership.id).where(
        Membership.user_id == user_id,
        Membership.organization_id == organization_id,
    )
    if db.scalar(statement) is None:
        raise ValueError("Assigned user is not a member of the organization")


def create_activity(
    db: Session,
    organization_id: UUID,
    actor_user_id: UUID,
    payload,
) -> Activity:
    for model, entity_id, label in (
        (Company, payload.company_id, "Company"),
        (Contact, payload.contact_id, "Contact"),
        (Opportunity, payload.opportunity_id, "Opportunity"),
    ):
        _ensure_related_entity(db, model, entity_id, organization_id, label)

    activity = Activity(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        company_id=payload.company_id,
        contact_id=payload.contact_id,
        opportunity_id=payload.opportunity_id,
        activity_type=payload.activity_type,
        title=payload.title,
        body=payload.body,
    )
    db.add(activity)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="created",
        entity_type="activity",
        entity_id=activity.id,
    )
    db.commit()
    db.refresh(activity)
    return activity


def list_activities(
    db: Session,
    organization_id: UUID,
    limit: int = 100,
) -> list[Activity]:
    statement = (
        select(Activity)
        .where(Activity.organization_id == organization_id)
        .order_by(Activity.occurred_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    return list(db.scalars(statement).all())


def create_task(
    db: Session,
    organization_id: UUID,
    actor_user_id: UUID,
    payload,
) -> Task:
    for model, entity_id, label in (
        (Company, payload.company_id, "Company"),
        (Contact, payload.contact_id, "Contact"),
        (Opportunity, payload.opportunity_id, "Opportunity"),
    ):
        _ensure_related_entity(db, model, entity_id, organization_id, label)
    _ensure_assignment(db, payload.assigned_to_user_id, organization_id)

    task = Task(
        organization_id=organization_id,
        created_by_user_id=actor_user_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        company_id=payload.company_id,
        contact_id=payload.contact_id,
        opportunity_id=payload.opportunity_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
    )
    db.add(task)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="created",
        entity_type="task",
        entity_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    organization_id: UUID,
    limit: int = 100,
) -> list[Task]:
    statement = (
        select(Task)
        .where(Task.organization_id == organization_id)
        .order_by(Task.created_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    return list(db.scalars(statement).all())


def update_task(
    db: Session,
    task: Task,
    organization_id: UUID,
    actor_user_id: UUID,
    payload,
) -> Task:
    values = payload.model_dump(exclude_unset=True)
    completed = values.pop("completed", None)

    if "assigned_to_user_id" in values:
        _ensure_assignment(db, values["assigned_to_user_id"], organization_id)

    for model, key, label in (
        (Company, "company_id", "Company"),
        (Contact, "contact_id", "Contact"),
        (Opportunity, "opportunity_id", "Opportunity"),
    ):
        if key in values:
            _ensure_related_entity(db, model, values[key], organization_id, label)

    for key, value in values.items():
        setattr(task, key, value)

    if completed is not None:
        task.completed_at = datetime.utcnow() if completed else None

    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="updated",
        entity_type="task",
        entity_id=task.id,
        after_data={"completed": task.completed_at is not None},
    )
    db.commit()
    db.refresh(task)
    return task
