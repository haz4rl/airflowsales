import uuid
from datetime import UTC, datetime
from typing import Optional

from backend.app.db.session import Base
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Postgres keeps native JSONB / VARCHAR[] columns; other dialects (SQLite in
# tests) fall back to generic JSON so the schema stays portable.
jsonb_type = JSON().with_variant(JSONB, "postgresql")
string_array_type = JSON().with_variant(ARRAY(String), "postgresql")


def get_utc_now():
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now
    )


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    target_industries: Mapped[list[str]] = mapped_column(
        string_array_type, nullable=False, default=list
    )
    target_company_characteristics: Mapped[dict] = mapped_column(
        jsonb_type, nullable=False, default=dict
    )
    qualification_criteria: Mapped[str] = mapped_column(Text, nullable=False)

    prospects: Mapped[list["Prospect"]] = relationship("Prospect", back_populates="campaign")


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    prospects: Mapped[list["Prospect"]] = relationship("Prospect", back_populates="company")
    evidence: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="company")


class Prospect(Base, TimestampMixin):
    __tablename__ = "prospects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="DISCOVERY", nullable=False)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="prospects")
    company: Mapped["Company"] = relationship("Company", back_populates="prospects")
    qualification: Mapped[Optional["Qualification"]] = relationship(
        "Qualification", back_populates="prospect", uselist=False
    )
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun", back_populates="prospect"
    )

    __table_args__ = (UniqueConstraint("campaign_id", "company_id", name="uq_campaign_company"),)


class Evidence(Base, TimestampMixin):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str | None] = mapped_column(String(512))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_metadata: Mapped[dict] = mapped_column(jsonb_type, nullable=False, default=dict)

    company: Mapped["Company"] = relationship("Company", back_populates="evidence")


class Qualification(Base, TimestampMixin):
    __tablename__ = "qualifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id"), unique=True, nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_breakdown: Mapped[dict] = mapped_column(jsonb_type, nullable=False, default=dict)

    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="qualification")


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)

    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="workflow_runs")
    events: Mapped[list["WorkflowEvent"]] = relationship("WorkflowEvent", back_populates="run")


class WorkflowEvent(Base, TimestampMixin):
    __tablename__ = "workflow_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    input: Mapped[dict] = mapped_column(jsonb_type, nullable=False, default=dict)
    output: Mapped[dict] = mapped_column(jsonb_type, nullable=False, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict] = mapped_column(jsonb_type, nullable=False, default=dict)

    run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="events")
