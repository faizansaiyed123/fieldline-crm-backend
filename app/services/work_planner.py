from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.standout import DailyPlannerResponse, PlannerItem
from app.services.attention import get_attention_queue
from app.services.pipeline_intelligence import get_stuck_opportunities


def get_daily_plan(
    db: Session,
    *,
    organization_id: UUID,
    limit: int = 20,
) -> DailyPlannerResponse:
    now = datetime.now(UTC)
    attention = get_attention_queue(db, organization_id=organization_id, limit=limit)
    stuck = get_stuck_opportunities(db, organization_id=organization_id, limit=limit)

    stuck_by_id = {item.id: item for item in stuck}
    items: list[PlannerItem] = []
    seen: set[tuple[str, UUID]] = set()

    for row in attention:
        key = (str(row["entity_type"]), row["entity_id"])
        if key in seen:
            continue
        seen.add(key)
        entity_type = str(row["entity_type"])
        if entity_type == "task":
            next_action = "Complete the task or reschedule it with a clear due date"
        elif entity_type == "contact":
            next_action = "Schedule a follow-up and record the outcome"
        else:
            stuck_item = stuck_by_id.get(row["entity_id"])
            next_action = stuck_item.recommended_action if stuck_item else "Review the opportunity and schedule the next step"

        evidence = [str(row["reason"])]
        if row["last_activity_at"]:
            evidence.append(f"Last activity: {row['last_activity_at'].isoformat()}")
        if row["due_at"]:
            evidence.append(f"Due: {row['due_at'].isoformat()}")

        items.append(
            PlannerItem(
                entity_type=entity_type,
                entity_id=row["entity_id"],
                priority=int(row["priority"]),
                title=str(row["title"]),
                reason=str(row["reason"]),
                next_action=next_action,
                evidence=evidence,
                due_at=row["due_at"],
                last_activity_at=row["last_activity_at"],
            )
        )

    for item in stuck:
        key = ("opportunity", item.id)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            PlannerItem(
                entity_type="opportunity",
                entity_id=item.id,
                priority=80,
                title=item.name,
                reason=item.reasons[0],
                next_action=item.recommended_action,
                evidence=item.reasons,
                due_at=None,
                last_activity_at=item.last_activity_at,
            )
        )

    items.sort(
        key=lambda item: (
            -item.priority,
            item.due_at or datetime.max.replace(tzinfo=UTC),
            item.last_activity_at or datetime.min.replace(tzinfo=UTC),
            str(item.entity_id),
        )
    )
    return DailyPlannerResponse(generated_at=now, items=items[:limit])
