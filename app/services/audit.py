from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record_audit(
    db: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID | None,
    entity_type: str,
    entity_id: UUID,
    action: str,
    summary: str | None = None,
    before_data: dict[str, object] | None = None,
    after_data: dict[str, object] | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        summary=summary,
        before_data=before_data,
        after_data=after_data,
        created_at=datetime.now(UTC),
    )
    db.add(event)
    return event
