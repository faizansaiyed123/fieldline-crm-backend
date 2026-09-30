from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AttentionEntityType = Literal["task", "opportunity", "contact"]


class AttentionItem(BaseModel):
    entity_type: AttentionEntityType
    entity_id: UUID
    priority: int = Field(ge=0, le=100)
    title: str
    reason: str
    due_at: datetime | None
    last_activity_at: datetime | None


class AttentionResponse(BaseModel):
    items: list[AttentionItem]
    generated_at: datetime
