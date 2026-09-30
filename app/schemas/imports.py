from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImportRowError(BaseModel):
    row_number: int
    errors: list[str]


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    committed_rows: int
    created_at: datetime
    completed_at: datetime | None


class ImportPreviewResponse(ImportJobResponse):
    errors: list[ImportRowError] = Field(default_factory=list)
    errors_truncated: bool = False


class ImportCommitRequest(BaseModel):
    dry_run: bool = False


class ImportCommitResponse(BaseModel):
    job_id: UUID
    status: str
    dry_run: bool
    total_rows: int
    valid_rows: int
    invalid_rows: int
    would_create: int
    committed_rows: int
