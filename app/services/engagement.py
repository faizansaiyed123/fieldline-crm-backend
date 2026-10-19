from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, Company, Contact, Membership, Opportunity, Task, User
from app.services.audit import record_audit


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _ensure_related_entity(
    db: AsyncSession,
    model,
    entity_id: UUID | None,
    organization_id: UUID,
    label: str,
) -> None:
    if entity_id is None:
        return
    stmt = select(model.id).where(
        model.id == entity_id,
        model.organization_id == organization_id,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise ValueError(f"{label} not found in organization")


async def _ensure_assignment(
    db: AsyncSession,
    user_id: UUID | None,
    organization_id: UUID,
) -> None:
    if user_id is None:
        return
    stmt = select(Membership.id).where(
        Membership.user_id == user_id,
        Membership.organization_id == organization_id,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise ValueError("Assigned user is not a member of the organization")


async def create_activity(
    db: AsyncSession,
    organization_id: UUID,
    actor_user_id: UUID,
    payload,
) -> Activity:
    for model, entity_id, label in (
        (Company, payload.company_id, "Company"),
        (Contact, payload.contact_id, "Contact"),
        (Opportunity, payload.opportunity_id, "Opportunity"),
    ):
        await _ensure_related_entity(db, model, entity_id, organization_id, label)

    activity = Activity(
        organization_id=organization_id,
        company_id=payload.company_id,
        contact_id=payload.contact_id,
        opportunity_id=payload.opportunity_id,
        activity_type=payload.activity_type,
        title=payload.title,
        body=payload.body,
        created_by_user_id=actor_user_id,
    )
    db.add(activity)
    await db.flush()
    await record_audit(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="created",
        entity_type="activity",
        entity_id=activity.id,
    )
    await db.commit()
    await db.refresh(activity)
    return activity


async def list_activities(
    db: AsyncSession,
    organization_id: UUID,
    limit: int = 100,
) -> list[Activity]:
    stmt = (
        select(Activity)
        .where(Activity.organization_id == organization_id)
        .order_by(Activity.created_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_task(
    db: AsyncSession,
    organization_id: UUID,
    actor_user_id: UUID,
    payload,
) -> Task:
    for model, entity_id, label in (
        (Company, payload.company_id, "Company"),
        (Contact, payload.contact_id, "Contact"),
        (Opportunity, payload.opportunity_id, "Opportunity"),
    ):
        await _ensure_related_entity(db, model, entity_id, organization_id, label)
    await _ensure_assignment(db, payload.assigned_to_user_id, organization_id)

    task = Task(
        organization_id=organization_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        company_id=payload.company_id,
        contact_id=payload.contact_id,
        opportunity_id=payload.opportunity_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=_as_utc(payload.due_at),
        completed=False,
        created_by_user_id=actor_user_id,
    )
    db.add(task)
    await db.flush()
    await record_audit(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="created",
        entity_type="task",
        entity_id=task.id,
    )
    await db.commit()
    await db.refresh(task)
    return task


async def list_tasks(
    db: AsyncSession,
    organization_id: UUID,
    limit: int = 100,
) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.organization_id == organization_id)
        .order_by(Task.created_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_task(
    db: AsyncSession,
    task: Task,
    organization_id: UUID,
    actor_user_id: UUID,
    payload,
) -> Task:
    values = payload.model_dump(exclude_unset=True)

    if "assigned_to_user_id" in values:
        await _ensure_assignment(db, values["assigned_to_user_id"], organization_id)

    for model, key, label in (
        (Company, "company_id", "Company"),
        (Contact, "contact_id", "Contact"),
        (Opportunity, "opportunity_id", "Opportunity"),
    ):
        if key in values:
            await _ensure_related_entity(db, model, values[key], organization_id, label)

    if "due_at" in values:
        values["due_at"] = _as_utc(values["due_at"])

    if "completed" in values:
        values["completed_at"] = datetime.now(timezone.utc).replace(tzinfo=None) if values["completed"] else None

    for key, value in values.items():
        setattr(task, key, value)

    await db.flush()
    await record_audit(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="updated",
        entity_type="task",
        entity_id=task.id,
    )
    await db.commit()
    await db.refresh(task)
    return task
