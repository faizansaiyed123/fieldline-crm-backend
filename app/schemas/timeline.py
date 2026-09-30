from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TimelineKind = Literal["activity", "task", "audit"]


class TimelineItem(BaseModel):
    id: UUID
    kind: TimelineKind
    timestamp: datetime
    title: str
    summary: str | None
    actor_user_id: UUID | None


class TimelineResponse(BaseModel):
    items: list[TimelineItem]
    limit: int = Field(ge=1, le=100)
    next_before: datetime | None = None
    next_before_id: UUID | None = None
