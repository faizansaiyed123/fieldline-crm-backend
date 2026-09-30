from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models import Activity, AuditEvent, Task


def get_contact_timeline(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID,
    limit: int,
    before: datetime | None = None,
    before_id: UUID | None = None,
) -> tuple[list[dict[str, object]], datetime | None, UUID | None]:
    activity_query = select(
        Activity.id.label("id"),
        literal("activity").label("kind"),
        Activity.occurred_at.label("timestamp"),
        Activity.title.label("title"),
        Activity.body.label("summary"),
        Activity.actor_user_id.label("actor_user_id"),
    ).where(
        Activity.organization_id == organization_id,
        Activity.contact_id == contact_id,
    )

    task_query = select(
        Task.id.label("id"),
        literal("task").label("kind"),
        func.coalesce(Task.completed_at, Task.due_at, Task.created_at).label("timestamp"),
        Task.title.label("title"),
        Task.description.label("summary"),
        Task.created_by_user_id.label("actor_user_id"),
    ).where(
        Task.organization_id == organization_id,
        Task.contact_id == contact_id,
    )

    audit_query = select(
        AuditEvent.id.label("id"),
        literal("audit").label("kind"),
        AuditEvent.created_at.label("timestamp"),
        AuditEvent.action.label("title"),
        AuditEvent.summary.label("summary"),
        AuditEvent.actor_user_id.label("actor_user_id"),
    ).where(
        AuditEvent.organization_id == organization_id,
        AuditEvent.entity_type == "contact",
        AuditEvent.entity_id == contact_id,
    )

    timeline = union_all(activity_query, task_query, audit_query).subquery()
    statement = select(timeline)

    if before is not None:
        timestamp = timeline.c.timestamp
        event_id = timeline.c.id
        if before_id is None:
            statement = statement.where(timestamp < before)
        else:
            statement = statement.where(
                or_(
                    timestamp < before,
                    and_(timestamp == before, event_id < before_id),
                )
            )

    rows = db.execute(
        statement.order_by(
            timeline.c.timestamp.desc(),
            timeline.c.id.desc(),
        ).limit(limit + 1)
    ).mappings().all()

    has_more = len(rows) > limit
    visible = rows[:limit]
    if not visible:
        return [], None, None

    last = visible[-1]
    next_before = last["timestamp"] if has_more else None
    next_before_id = last["id"] if has_more else None
    return [dict(row) for row in visible], next_before, next_before_id
