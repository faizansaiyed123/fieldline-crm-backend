from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AutomationTaskConfig(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    priority: Literal["low", "normal", "high"] = "normal"
    due_days: int = Field(default=1, ge=0, le=30)


class AutomationRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    trigger: Literal["opportunity.won", "opportunity.lost"]
    action_type: Literal["create_task"]
    action_config: AutomationTaskConfig
    enabled: bool = True


class AutomationRuleUpdate(BaseModel):
    enabled: bool


class AutomationRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    trigger: str
    action_type: str
    action_config: AutomationTaskConfig
    enabled: bool
    created_at: datetime
    updated_at: datetime
