from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    name: str
    input: dict[str, Any]
    output: dict[str, Any]
    latency_ms: int | None
    token_usage: dict[str, Any]
    created_at: datetime


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prospect_id: UUID
    status: str
    total_tokens: int
    total_cost: float
    created_at: datetime
    updated_at: datetime
    events: list[WorkflowEventRead] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    approved: bool
    note: str | None = Field(None, max_length=2000)


class WorkflowRunListItem(BaseModel):
    id: UUID
    prospect_id: UUID
    status: str
    total_tokens: int
    total_cost: float
    created_at: datetime
    updated_at: datetime
    event_count: int = 0
    company_name: str | None = None
    company_domain: str | None = None
