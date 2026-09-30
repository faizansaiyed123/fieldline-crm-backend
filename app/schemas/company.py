from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, field_validator


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    website: AnyUrl | None = None
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Company name cannot be blank")
        return value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    website: AnyUrl | None = None
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("Company name cannot be blank")
        return value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    owner_user_id: UUID
    name: str
    website: str | None
    phone: str | None


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    page: int
    page_size: int
    total: int
