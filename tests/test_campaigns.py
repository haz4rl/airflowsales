import uuid

from backend.app.models.domain import (
    Campaign,
    Company,
    Evidence,
    Prospect,
    Qualification,
    WorkflowEvent,
    WorkflowRun,
)

VALID_PAYLOAD = {
    "name": "Enterprise Sales Q4",
    "product_description": "Our AI-powered sales platform.",
    "target_industries": ["SaaS", "FinTech"],
    "target_company_characteristics": {"min_headcount": 50},
    "qualification_criteria": "Must have a sales team of at least 5 people.",
}


def test_create_campaign(client):
    response = client.post("/v1/campaigns", json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert uuid.UUID(data["id"])
    assert data["name"] == VALID_PAYLOAD["name"]
    assert data["product_description"] == VALID_PAYLOAD["product_description"]
    assert data["target_industries"] == VALID_PAYLOAD["target_industries"]
    assert data["target_company_characteristics"] == VALID_PAYLOAD["target_company_characteristics"]
    assert data["qualification_criteria"] == VALID_PAYLOAD["qualification_criteria"]
    assert data["created_at"]
    assert data["updated_at"]


def test_create_campaign_with_trailing_slash(client):
    response = client.post("/v1/campaigns/", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert uuid.UUID(response.json()["id"])


def test_create_campaign_persists_to_database(client, db_session):
    response = client.post("/v1/campaigns", json=VALID_PAYLOAD)

    assert response.status_code == 200
    campaign = db_session.query(Campaign).one()
    assert campaign.id == uuid.UUID(response.json()["id"])
    assert campaign.name == VALID_PAYLOAD["name"]
    assert campaign.target_industries == VALID_PAYLOAD["target_industries"]
    assert (
        campaign.target_company_characteristics == VALID_PAYLOAD["target_company_characteristics"]
    )
    assert campaign.created_at is not None
    assert campaign.updated_at is not None


def test_create_campaign_rejects_invalid_payload(client):
    response = client.post("/v1/campaigns", json={"name": "missing required fields"})

    assert response.status_code == 422
    error_locs = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "product_description") in error_locs
    assert ("body", "qualification_criteria") in error_locs


def test_list_campaigns(client):
    client.post("/v1/campaigns", json=VALID_PAYLOAD)
    client.post(
        "/v1/campaigns",
        json={**VALID_PAYLOAD, "name": "Second campaign"},
    )

    response = client.get("/v1/campaigns")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {campaign["name"] for campaign in data} == {
        VALID_PAYLOAD["name"],
        "Second campaign",
    }


def _seed_campaign_with_history(db_session):
    """Campaign → prospect → qualification + workflow run + event, plus a
    shared company that also owns evidence (evidence must survive)."""
    campaign = Campaign(
        name="Enterprise Sales Q4",
        product_description="Our AI-powered sales platform.",
        qualification_criteria="Must have a sales team of at least 5 people.",
    )
    company = Company(domain="acme.example", name="Acme")
    db_session.add_all([campaign, company])
    db_session.flush()

    prospect = Prospect(campaign_id=campaign.id, company_id=company.id)
    db_session.add(prospect)
    db_session.flush()

    db_session.add(
        Qualification(
            prospect_id=prospect.id,
            score=60,
            confidence=0.7,
            decision="NO_GO",
            reasoning="No sales team evidence.",
        )
    )
    run = WorkflowRun(prospect_id=prospect.id, status="COMPLETED")
    db_session.add(run)
    db_session.flush()
    db_session.add(WorkflowEvent(run_id=run.id, event_type="TOOL", name="company_search"))
    db_session.add(
        Evidence(company_id=company.id, excerpt="Shared evidence.", evidence_type="SEARCH_RESULT")
    )
    db_session.commit()
    return campaign, company, prospect, run


def test_delete_empty_campaign(client, db_session):
    created = client.post("/v1/campaigns", json=VALID_PAYLOAD).json()

    response = client.delete(f"/v1/campaigns/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert db_session.query(Campaign).count() == 0
    # Deleting again reports 404.
    assert client.delete(f"/v1/campaigns/{created['id']}").status_code == 404


def test_delete_campaign_not_found(client):
    response = client.delete(f"/v1/campaigns/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Campaign not found"


def test_delete_campaign_with_history_is_refused(client, db_session):
    campaign, company, prospect, run = _seed_campaign_with_history(db_session)

    response = client.delete(f"/v1/campaigns/{campaign.id}")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "1 prospect" in detail
    assert "preserved" in detail

    # Nothing was removed.
    assert db_session.query(Campaign).count() == 1
    assert db_session.query(Prospect).count() == 1
    assert db_session.query(Qualification).count() == 1
    assert db_session.query(WorkflowRun).count() == 1
    assert db_session.query(WorkflowEvent).count() == 1
    assert db_session.query(Evidence).count() == 1
    assert db_session.get(Campaign, campaign.id) is not None


def test_delete_refused_counts_multiple_prospects(client, db_session):
    campaign = Campaign(
        name="Enterprise Sales Q4",
        product_description="Our AI-powered sales platform.",
        qualification_criteria="Criteria.",
    )
    company_a = Company(domain="a.example")
    company_b = Company(domain="b.example")
    db_session.add_all([campaign, company_a, company_b])
    db_session.flush()
    db_session.add_all(
        [
            Prospect(campaign_id=campaign.id, company_id=company_a.id),
            Prospect(campaign_id=campaign.id, company_id=company_b.id),
        ]
    )
    db_session.commit()

    response = client.delete(f"/v1/campaigns/{campaign.id}")

    assert response.status_code == 409
    assert "2 prospect" in response.json()["detail"]
    assert db_session.query(Campaign).count() == 1
    assert db_session.query(Prospect).count() == 2


def test_delete_empty_campaign_keeps_shared_company_and_evidence(client, db_session):
    campaign, company, prospect, run = _seed_campaign_with_history(db_session)
    # Second, empty campaign sharing nothing with the first.
    empty = client.post("/v1/campaigns", json={**VALID_PAYLOAD, "name": "Empty twin"}).json()

    response = client.delete(f"/v1/campaigns/{empty['id']}")

    assert response.status_code == 204
    # The history-bearing campaign and all research data survive.
    assert db_session.get(Campaign, campaign.id) is not None
    assert db_session.query(Prospect).count() == 1
    assert db_session.query(Evidence).count() == 1
    assert db_session.get(Company, company.id) is not None


def test_delete_campaign_trailing_slash(client):
    created = client.post("/v1/campaigns", json=VALID_PAYLOAD).json()

    response = client.delete(f"/v1/campaigns/{created['id']}/")

    assert response.status_code == 204
