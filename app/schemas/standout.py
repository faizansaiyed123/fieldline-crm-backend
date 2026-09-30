from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

QualitySeverity = Literal["high", "medium", "low"]
EntityType = Literal["contact", "company", "opportunity", "task"]


class DuplicateCandidate(BaseModel):
    entity_type: Literal["contact", "company"]
    first_id: UUID
    second_id: UUID
    first_label: str
    second_label: str
    similarity: float = Field(ge=0, le=1)
    reasons: list[str]


class QualityIssue(BaseModel):
    code: str
    entity_type: EntityType
    entity_id: UUID
    severity: QualitySeverity
    title: str
    detail: str
    fixable: bool


class DataQualitySummary(BaseModel):
    total_issues: int
    high: int
    medium: int
    low: int
    duplicate_contacts: int
    duplicate_companies: int
    incomplete_records: int
    stale_contacts: int
    opportunity_issues: int
    overdue_tasks: int


class DataQualityResponse(BaseModel):
    generated_at: datetime
    summary: DataQualitySummary
    duplicate_candidates: list[DuplicateCandidate]
    issues: list[QualityIssue]


class MergeRequest(BaseModel):
    survivor_id: UUID


class MergeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operation_id: UUID
    entity_type: Literal["contact", "company"]
    survivor_id: UUID
    merged_id: UUID
    completed_at: datetime


class BusinessRuleResponse(BaseModel):
    key: str
    value: int
    default: int
    description: str


class BusinessRuleUpdate(BaseModel):
    value: int = Field(ge=0, le=365)


class StuckOpportunity(BaseModel):
    id: UUID
    name: str
    stage_id: UUID
    stage_name: str
    amount: str | None
    status: str
    stage_age_days: int
    last_activity_at: datetime | None
    expected_close_date: str | None
    overdue_task_count: int
    has_next_action: bool
    reasons: list[str]
    recommended_action: str


class StuckOpportunityResponse(BaseModel):
    generated_at: datetime
    configured_threshold_days: int
    items: list[StuckOpportunity]


class PlannerItem(BaseModel):
    entity_type: Literal["task", "opportunity", "contact"]
    entity_id: UUID
    priority: int
    title: str
    reason: str
    next_action: str
    evidence: list[str]
    due_at: datetime | None
    last_activity_at: datetime | None


class DailyPlannerResponse(BaseModel):
    generated_at: datetime
    items: list[PlannerItem]


class AutomationRunResponse(BaseModel):
    id: UUID
    workflow: str
    trigger: str
    event_key: str
    status: str
    action_type: str
    result: dict[str, object] | None
    created_at: datetime
    completed_at: datetime | None


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    meta: dict[str, str | None] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str


class RelationshipGraphResponse(BaseModel):
    contact_id: UUID
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SystemHealthCheck(BaseModel):
    status: Literal["ok", "warning", "error"]
    detail: str


class SystemHealthResponse(BaseModel):
    generated_at: datetime
    status: Literal["ok", "warning", "error"]
    checks: dict[str, SystemHealthCheck]
