from datetime import datetime
from typing import Any
from uuid import UUID

from backend.app.schemas.campaign import CampaignRef
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DiscoveryRequest(BaseModel):
    campaign_id: UUID
    domain: str = Field(min_length=3, max_length=255)

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        v = v.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        if "." not in v or " " in v:
            raise ValueError("domain must look like company.com")
        return v


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: str
    name: str | None
    description: str | None
    industry: str | None
    location: str | None


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_url: str | None
    source_title: str | None
    excerpt: str
    evidence_type: str
    created_at: datetime


class QualificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: int
    confidence: float
    decision: str
    reasoning: str
    scoring_breakdown: dict[str, Any]


class ProspectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    company_id: UUID
    status: str
    created_at: datetime


class DiscoveryResponse(BaseModel):
    prospect: ProspectRead
    company: CompanyRead
    evidence: list[EvidenceRead]
    qualification: QualificationRead | None = None
    workflow_run_id: UUID | None = None
    outreach: dict[str, Any] | None = None
    critic: dict[str, Any] | None = None


class ProspectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prospect: ProspectRead
    company: CompanyRead
    qualification: QualificationRead | None = None
    campaign: CampaignRef | None = None
    research_date: datetime | None = None
