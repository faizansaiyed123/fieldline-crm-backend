from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PipelineStage

DEFAULT_PIPELINE: tuple[tuple[str, int, float, bool, bool], ...] = (
    ("New", 10, 0.10, False, False),
    ("Qualified", 20, 0.25, False, False),
    ("Proposal", 30, 0.50, False, False),
    ("Negotiation", 40, 0.70, False, False),
    ("Closed Won", 50, 1.00, True, True),
    ("Closed Lost", 60, 0.00, True, False),
)


def create_default_pipeline(db: Session, organization_id: UUID) -> list[PipelineStage]:
    stages = [
        PipelineStage(
            organization_id=organization_id,
            name=name,
            order_index=order_index,
            win_probability=probability,
            is_closed=is_closed,
            is_won=is_won,
        )
        for name, order_index, probability, is_closed, is_won in DEFAULT_PIPELINE
    ]
    db.add_all(stages)
    db.flush()
    return stages


def get_stage(db: Session, *, organization_id: UUID, stage_id: UUID) -> PipelineStage | None:
    return db.scalar(
        select(PipelineStage)
        .where(PipelineStage.organization_id == organization_id)
        .where(PipelineStage.id == stage_id)
        .limit(1)
    )


def list_stages(db: Session, *, organization_id: UUID) -> list[PipelineStage]:
    return db.scalars(
        select(PipelineStage)
        .where(PipelineStage.organization_id == organization_id)
        .order_by(PipelineStage.order_index)
    ).all()


def create_stage(
    db: Session,
    *,
    organization_id: UUID,
    name: str,
    win_probability: float,
    is_closed: bool,
    is_won: bool,
) -> PipelineStage:
    max_order = db.scalar(
        select(PipelineStage.order_index)
        .where(PipelineStage.organization_id == organization_id)
        .order_by(PipelineStage.order_index.desc())
        .limit(1)
    )
    stage = PipelineStage(
        organization_id=organization_id,
        name=name,
        order_index=(max_order or 0) + 10,
        win_probability=win_probability,
        is_closed=is_closed,
        is_won=is_won,
    )
    db.add(stage)
    db.flush()
    return stage
