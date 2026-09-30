from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ContactLifecycle = Literal["lead", "prospect", "customer", "churned"]


class ContactCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=160)
    lifecycle: ContactLifecycle = "lead"
    company_id: UUID | None = None

    @field_validator("first_name", "last_name", "job_title")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).lower() if value else None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class ContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=160)
    lifecycle: ContactLifecycle | None = None
    company_id: UUID | None = None

    @field_validator("first_name", "last_name", "job_title")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).lower() if value else None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    company_id: UUID | None
    owner_user_id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    job_title: str | None
    lifecycle: str


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    page: int
    page_size: int
    total: int
