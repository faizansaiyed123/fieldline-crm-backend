from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, and_, case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models import Activity, Contact, Opportunity, Task
from app.services.business_rules import get_rule_value


def get_attention_queue(db: Session, *, organization_id: UUID, limit: int = 50) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    contact_days = get_rule_value(db, organization_id=organization_id, key="contact_inactivity_days")
    opportunity_days = get_rule_value(db, organization_id=organization_id, key="opportunity_inactivity_days")
    contact_cutoff = now - timedelta(days=contact_days)
    opportunity_cutoff = now - timedelta(days=opportunity_days)

    contact_last_activity = (
        select(func.max(Activity.occurred_at))
        .where(Activity.organization_id == organization_id, Activity.contact_id == Contact.id)
        .correlate(Contact)
        .scalar_subquery()
    )
    opportunity_last_activity = (
        select(func.max(Activity.occurred_at))
        .where(Activity.organization_id == organization_id, Activity.opportunity_id == Opportunity.id)
        .correlate(Opportunity)
        .scalar_subquery()
    )

    task_signal = select(
        Task.id.label("entity_id"),
        literal("task").label("entity_type"),
        literal(95).label("priority"),
        Task.title.label("title"),
        literal("Task is overdue and still incomplete").label("reason"),
        Task.due_at.label("due_at"),
        literal(None).cast(DateTime(timezone=True)).label("last_activity_at"),
        Task.due_at.label("sort_time"),
    ).where(
        Task.organization_id == organization_id,
        Task.completed_at.is_(None),
        Task.due_at.is_not(None),
        Task.due_at < now,
    )

    opportunity_is_overdue = and_(
        Opportunity.expected_close_date.is_not(None),
        Opportunity.expected_close_date < now.date(),
    )
    opportunity_is_stale = or_(
        and_(opportunity_last_activity.is_(None), Opportunity.updated_at < opportunity_cutoff),
        opportunity_last_activity < opportunity_cutoff,
    )
    opportunity_signal = select(
        Opportunity.id.label("entity_id"),
        literal("opportunity").label("entity_type"),
        case((opportunity_is_overdue, 90), else_=65).label("priority"),
        Opportunity.name.label("title"),
        case(
            (opportunity_is_overdue, literal("Open opportunity is past its expected close date")),
            else_=literal("Open opportunity has had no recent recorded activity"),
        ).label("reason"),
        func.cast(Opportunity.expected_close_date, DateTime(timezone=True)).label("due_at"),
        opportunity_last_activity.label("last_activity_at"),
        func.coalesce(
            func.cast(Opportunity.expected_close_date, DateTime(timezone=True)),
            Opportunity.updated_at,
        ).label("sort_time"),
    ).where(
        Opportunity.organization_id == organization_id,
        Opportunity.deleted_at.is_(None),
        Opportunity.status == "open",
        or_(opportunity_is_overdue, opportunity_is_stale),
    )

    contact_is_stale = func.coalesce(contact_last_activity, Contact.created_at) < contact_cutoff
    contact_signal = select(
        Contact.id.label("entity_id"),
        literal("contact").label("entity_type"),
        literal(70).label("priority"),
        func.concat(Contact.first_name, " ", Contact.last_name).label("title"),
        case(
            (contact_last_activity.is_(None), literal("Lead/prospect has gone 14+ days without recorded activity")),
            else_=literal("Lead/prospect has gone 14+ days without recorded activity"),
        ).label("reason"),
        literal(None).cast(DateTime(timezone=True)).label("due_at"),
        contact_last_activity.label("last_activity_at"),
        func.coalesce(contact_last_activity, Contact.created_at).label("sort_time"),
    ).where(
        Contact.organization_id == organization_id,
        Contact.deleted_at.is_(None),
        Contact.lifecycle.in_(["lead", "prospect"]),
        contact_is_stale,
    )

    signals = union_all(task_signal, opportunity_signal, contact_signal).subquery()
    rows = db.execute(
        select(
            signals.c.entity_id,
            signals.c.entity_type,
            signals.c.priority,
            signals.c.title,
            signals.c.reason,
            signals.c.due_at,
            signals.c.last_activity_at,
        )
        .order_by(signals.c.priority.desc(), signals.c.sort_time.asc(), signals.c.entity_id.asc())
        .limit(limit)
    ).mappings().all()
    return [dict(row) for row in rows]
