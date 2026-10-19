from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


ActivityType = Literal["note", "call", "email", "meeting"]
TaskPriority = Literal["low", "normal", "high", "urgent"]


class ActivityCreate(BaseModel):
    company_id: UUID | None = None
    contact_id: UUID | None = None
    opportunity_id: UUID | None = None
    activity_type: ActivityType
    title: str = Field(min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_subject(self) -> "ActivityCreate":
        if not any((self.company_id, self.contact_id, self.opportunity_id)):
            raise ValueError("At least one related entity is required")
        return self


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    actor_user_id: UUID | None = None
    company_id: UUID | None = None
    contact_id: UUID | None = None
    opportunity_id: UUID | None = None
    activity_type: ActivityType
    title: str
    body: str | None = None
    occurred_at: datetime
    created_at: datetime | None = None


class TaskCreate(BaseModel):
    assigned_to_user_id: UUID | None = None
    company_id: UUID | None = None
    contact_id: UUID | None = None
    opportunity_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority = "normal"
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    assigned_to_user_id: UUID | None = None
    company_id: UUID | None = None
    contact_id: UUID | None = None
    opportunity_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    completed: bool | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    assigned_to_user_id: UUID | None = None
    company_id: UUID | None = None
    contact_id: UUID | None = None
    opportunity_id: UUID | None = None
    title: str
    description: str | None = None
    priority: str
    due_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed: bool = False
