import time
import uuid

import pytest
from backend.app.db.session import Base
from backend.app.models.domain import (
    Campaign,
    Company,
    Evidence,
    Prospect,
    Qualification,
    WorkflowEvent,
    WorkflowRun,
)
from sqlalchemy.exc import IntegrityError


def _campaign(name="Test campaign"):
    return Campaign(
        name=name,
        product_description="A product.",
        qualification_criteria="Criteria.",
    )


def _company(domain="example.com"):
    return Company(domain=domain)


def _prospect(campaign, company):
    return Prospect(campaign=campaign, company=company)


def test_all_domain_tables_registered():
    assert set(Base.metadata.tables) == {
        "campaigns",
        "companies",
        "prospects",
        "evidence",
        "qualifications",
        "workflow_runs",
        "workflow_events",
    }


def test_foreign_keys_and_created_at_are_indexed():
    """Postgres does not auto-index foreign keys; list endpoints order by created_at."""
    indexed = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.index
    }
    assert indexed == {
        ("companies", "domain"),
        ("campaigns", "created_at"),
        ("companies", "created_at"),
        ("prospects", "campaign_id"),
        ("prospects", "company_id"),
        ("prospects", "created_at"),
        ("evidence", "company_id"),
        ("evidence", "created_at"),
        ("qualifications", "created_at"),
        ("workflow_runs", "prospect_id"),
        ("workflow_runs", "created_at"),
        ("workflow_events", "run_id"),
        ("workflow_events", "created_at"),
    }


def test_primary_keys_are_uuids(db_session):
    campaign = _campaign()
    db_session.add(campaign)
    db_session.commit()

    assert isinstance(campaign.id, uuid.UUID)
    assert db_session.get(Campaign, campaign.id) is campaign


def test_created_and_updated_timestamps(db_session):
    campaign = _campaign()
    db_session.add(campaign)
    db_session.commit()

    created_at = campaign.created_at
    updated_at = campaign.updated_at
    assert created_at is not None
    assert updated_at is not None

    time.sleep(0.01)
    campaign.name = "Renamed campaign"
    db_session.commit()
    db_session.refresh(campaign)

    assert campaign.created_at == created_at
    assert campaign.updated_at > updated_at


def test_prospect_unique_per_campaign_and_company(db_session):
    campaign = _campaign()
    company = _company()
    db_session.add_all([campaign, company])
    db_session.commit()

    db_session.add(_prospect(campaign, company))
    db_session.commit()

    db_session.add(_prospect(campaign, company))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_prospect_status_default_and_relationships(db_session):
    campaign = _campaign()
    company = _company()
    prospect = _prospect(campaign, company)
    db_session.add_all([campaign, company, prospect])
    db_session.commit()

    assert prospect.status == "DISCOVERY"
    assert prospect.campaign is campaign
    assert prospect.company is company
    assert prospect in campaign.prospects
    assert prospect in company.prospects
    assert prospect.qualification is None


def test_evidence_qualification_and_workflow_models(db_session):
    campaign = _campaign()
    company = _company()
    prospect = _prospect(campaign, company)
    db_session.add_all([campaign, company, prospect])
    db_session.commit()

    evidence = Evidence(
        company_id=company.id,
        excerpt="Company raised a Series B.",
        evidence_type="news",
        source_url="https://example.com/news",
    )
    qualification = Qualification(
        prospect_id=prospect.id,
        score=85,
        confidence=0.9,
        decision="QUALIFIED",
        reasoning="Strong fit.",
    )
    run = WorkflowRun(prospect_id=prospect.id, status="RUNNING")
    event = WorkflowEvent(
        run=run,
        event_type="node",
        name="research",
        latency_ms=120,
    )
    db_session.add_all([evidence, qualification, run, event])
    db_session.commit()

    assert evidence in company.evidence
    assert qualification.prospect is prospect
    assert prospect.qualification is qualification
    assert run.prospect is prospect
    assert run.events == [event]
