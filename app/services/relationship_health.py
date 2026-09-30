from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Activity, Contact, Opportunity, Task

RECENT_3D = timedelta(days=3)
RECENT_7D = timedelta(days=7)
RECENT_14D = timedelta(days=14)
RECENT_30D = timedelta(days=30)


def _band(score: int) -> str:
    if score >= 75:
        return "healthy"
    if score >= 50:
        return "warming"
    if score >= 25:
        return "at_risk"
    return "dormant"


def _recency_points(now: datetime, last_activity: datetime | None) -> tuple[int, str, str]:
    if last_activity is None:
        return 0, "no_recent_activity", "No recorded relationship activity"
    age = now - last_activity
    if age <= RECENT_3D:
        return 35, "active_3d", "Activity recorded within the last 3 days"
    if age <= RECENT_7D:
        return 28, "active_7d", "Activity recorded within the last 7 days"
    if age <= RECENT_14D:
        return 18, "active_14d", "Activity recorded within the last 14 days"
    if age <= RECENT_30D:
        return 8, "stale_30d", "Activity is 15–30 days old"
    return 0, "stale_30d_plus", "No activity recorded in more than 30 days"


def calculate_relationship_health(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID,
) -> dict[str, object]:
    now = datetime.now(UTC)
    contact = db.scalar(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .where(Contact.id == contact_id)
        .where(Contact.deleted_at.is_(None))
        .limit(1)
    )
    if contact is None:
        raise ValueError("Contact not found")

    last_activity = db.scalar(
        select(func.max(Activity.occurred_at))
        .where(Activity.organization_id == organization_id)
        .where(Activity.contact_id == contact_id)
    )
    activity_count_30d = db.scalar(
        select(func.count())
        .select_from(Activity)
        .where(Activity.organization_id == organization_id)
        .where(Activity.contact_id == contact_id)
        .where(Activity.occurred_at >= now - RECENT_30D)
    ) or 0
    open_opportunity_count = db.scalar(
        select(func.count())
        .select_from(Opportunity)
        .where(Opportunity.organization_id == organization_id)
        .where(Opportunity.contact_id == contact_id)
        .where(Opportunity.deleted_at.is_(None))
        .where(Opportunity.status == "open")
    ) or 0
    overdue_task_count = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.organization_id == organization_id)
        .where(Task.contact_id == contact_id)
        .where(Task.completed_at.is_(None))
        .where(Task.due_at.is_not(None))
        .where(Task.due_at < now)
    ) or 0

    recency, recency_code, recency_description = _recency_points(now, last_activity)
    engagement = min(25, int(activity_count_30d) * 5)
    commercial = min(20, int(open_opportunity_count) * 10)
    task_penalty = min(25, int(overdue_task_count) * 10)

    score = max(0, min(100, recency + engagement + commercial - task_penalty + 20))
    evidence = [
        {"code": recency_code, "impact": recency, "description": recency_description},
        {
            "code": "engagement_30d",
            "impact": engagement,
            "description": f"{activity_count_30d} activity event(s) recorded in the last 30 days",
        },
        {
            "code": "open_opportunities",
            "impact": commercial,
            "description": f"{open_opportunity_count} open opportunity/opportunities linked",
        },
        {
            "code": "overdue_tasks",
            "impact": -task_penalty,
            "description": f"{overdue_task_count} overdue incomplete task(s) linked",
        },
    ]

    return {
        "contact_id": contact.id,
        "score": score,
        "band": _band(score),
        "last_activity_at": last_activity,
        "activity_count_30d": int(activity_count_30d),
        "open_opportunity_count": int(open_opportunity_count),
        "overdue_task_count": int(overdue_task_count),
        "evidence": evidence,
    }
