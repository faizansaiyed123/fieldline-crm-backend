from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ViewSort = Literal["updated_desc", "updated_asc", "name_asc", "name_desc"]


class ContactViewDefinition(BaseModel):
    query: str | None = Field(default=None, max_length=100)
    lifecycle: list[Literal["lead", "prospect", "customer", "churned"]] = Field(
        default_factory=list,
        max_length=4,
    )
    company_id: UUID | None = None
    owner_user_id: UUID | None = None
    has_email: bool | None = None
    sort: ViewSort = "updated_desc"

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class SavedViewCreate(BaseModel):
    resource: Literal["contacts"] = "contacts"
    name: str = Field(min_length=2, max_length=120)
    shared: bool = False
    definition: ContactViewDefinition


class SavedViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    shared: bool | None = None
    definition: ContactViewDefinition | None = None


class SavedViewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    resource: str
    name: str
    shared: bool
    definition_version: int
    definition: ContactViewDefinition
