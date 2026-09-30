from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PipelineStageCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    win_probability: float = Field(default=0, ge=0, le=1)
    is_closed: bool = False
    is_won: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Stage name cannot be blank")
        return value


class PipelineStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    order_index: int
    win_probability: float
    is_closed: bool
    is_won: bool
