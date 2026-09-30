from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BusinessRule

DEFAULT_RULES: dict[str, tuple[int, str]] = {
    "contact_inactivity_days": (14, "Days without contact activity before a lead/prospect becomes stale"),
    "opportunity_inactivity_days": (21, "Days without opportunity activity before an open opportunity becomes stale"),
    "opportunity_stage_stuck_days": (21, "Days in the same opportunity stage before it is considered stuck"),
    "follow_up_due_days": (2, "Default future follow-up horizon used by the daily planner"),
}


def get_rule_value(db: Session, *, organization_id: UUID, key: str) -> int:
    default = DEFAULT_RULES.get(key)
    if default is None:
        raise KeyError(key)
    row = db.scalar(
        select(BusinessRule.value_int)
        .where(BusinessRule.organization_id == organization_id)
        .where(BusinessRule.key == key)
        .limit(1)
    )
    return int(row) if row is not None else default[0]


def list_rule_values(db: Session, *, organization_id: UUID) -> list[dict[str, object]]:
    configured = {
        row.key: row.value_int
        for row in db.scalars(
            select(BusinessRule)
            .where(BusinessRule.organization_id == organization_id)
            .order_by(BusinessRule.key.asc())
        ).all()
    }
    return [
        {
            "key": key,
            "value": int(configured.get(key, default)),
            "default": default,
            "description": description,
        }
        for key, (default, description) in DEFAULT_RULES.items()
    ]


def set_rule_value(
    db: Session,
    *,
    organization_id: UUID,
    key: str,
    value: int,
    actor_user_id: UUID,
) -> None:
    if key not in DEFAULT_RULES:
        raise ValueError("Unknown business rule")
    default, _ = DEFAULT_RULES[key]
    if value < 0 or value > 365:
        raise ValueError("Business rule value must be between 0 and 365 days")
    statement = (
        insert(BusinessRule)
        .values(
            organization_id=organization_id,
            key=key,
            value_int=value,
            updated_by_user_id=actor_user_id,
        )
        .on_conflict_do_update(
            constraint="uq_business_rule_org_key",
            set_={
                "value_int": value,
                "updated_by_user_id": actor_user_id,
            },
        )
    )
    db.execute(statement)
