from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

HealthBand = Literal["healthy", "warming", "at_risk", "dormant"]


class HealthEvidence(BaseModel):
    code: str
    impact: int
    description: str


class RelationshipHealthResponse(BaseModel):
    contact_id: UUID
    score: int = Field(ge=0, le=100)
    band: HealthBand
    last_activity_at: datetime | None
    activity_count_30d: int
    open_opportunity_count: int
    overdue_task_count: int
    evidence: list[HealthEvidence]
