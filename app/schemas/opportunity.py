from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

OpportunityStatus = Literal["open", "won", "lost"]


class OpportunityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    stage_id: UUID
    amount: Decimal | None = Field(default=None, ge=0)
    company_id: UUID | None = None
    contact_id: UUID | None = None
    expected_close_date: date | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Opportunity name cannot be blank")
        return value


class OpportunityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    stage_id: UUID | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    company_id: UUID | None = None
    contact_id: UUID | None = None
    expected_close_date: date | None = None
    status: OpportunityStatus | None = None
    lost_reason: str | None = Field(default=None, max_length=300)

    @field_validator("name", "lost_reason")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    owner_user_id: UUID
    company_id: UUID | None
    contact_id: UUID | None
    stage_id: UUID
    name: str
    amount: Decimal | None
    status: str
    expected_close_date: date | None
    lost_reason: str | None


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    page: int
    page_size: int
    total: int
