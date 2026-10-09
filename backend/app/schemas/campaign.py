from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignBase(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Enterprise Sales Q4"})
    product_description: str = Field(
        ..., json_schema_extra={"example": "Our AI-powered sales platform."}
    )
    target_industries: list[str] = Field(
        default_factory=list, json_schema_extra={"example": ["SaaS", "FinTech"]}
    )
    target_company_characteristics: dict[str, Any] = Field(
        default_factory=dict, json_schema_extra={"example": {"min_headcount": 50}}
    )
    qualification_criteria: str = Field(
        ..., json_schema_extra={"example": "Must have a sales team of at least 5 people."}
    )

    @field_validator("name", "product_description", "qualification_criteria")
    @classmethod
    def non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class CampaignCreate(CampaignBase):
    pass


class Campaign(CampaignBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class CampaignRef(BaseModel):
    """Lightweight campaign reference embedded in list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
