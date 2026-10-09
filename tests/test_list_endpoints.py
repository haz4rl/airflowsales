import uuid
from datetime import UTC, datetime, timedelta

from backend.app.main import app
from backend.app.models.domain import (
    Campaign,
    Company,
    Prospect,
    Qualification,
    WorkflowEvent,
    WorkflowRun,
)
from backend.app.services.providers import get_llm_provider, get_search_provider
from backend.app.tools.company_search import SearchProvider, SearchResult
from backend.app.tools.llm import LLMProvider

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def seed_campaign(db, name="Logistics SaaS"):
    campaign = Campaign(
        name=name,
        product_description="AI sales automation",
        target_industries=["SaaS"],
        target_company_characteristics={"region": "Europe"},
        qualification_criteria="Growing B2B SaaS",
    )
    db.add(campaign)
    db.commit()
    return campaign


def seed_prospect(
    db,
    campaign,
    domain,
    *,
    status="QUALIFIED",
    score=70,
    confidence=0.7,
    decision="GO",
    research_at=None,
    created_at=None,
):
    company = Company(
        domain=domain,
        name=domain.split(".")[0].title(),
        description="Builds workflow software.",
        industry="SaaS",
        location="Europe",
        last_researched_at=research_at,
    )
    db.add(company)
    db.flush()
    prospect = Prospect(
        campaign_id=campaign.id,
        company_id=company.id,
        status=status,
        **({"created_at": created_at} if created_at else {}),
    )
    db.add(prospect)
    db.flush()
    qualification = Qualification(
        prospect_id=prospect.id,
        score=score,
        confidence=confidence,
        decision=decision,
        reasoning="Strong fit",
        scoring_breakdown={"industry": 45},
    )
    db.add(qualification)
    db.commit()
    return prospect, company, qualification


def seed_run(db, prospect, status="COMPLETED", events=0):
    run = WorkflowRun(
        prospect_id=prospect.id,
        status=status,
        total_tokens=120,
        total_cost=0.004,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(run)
    db.flush()
    for index in range(events):
        db.add(
            WorkflowEvent(
                run_id=run.id,
                event_type="LLM",
                name=f"stage_{index}",
                input={},
                output={},
                latency_ms=10,
                token_usage={"total_tokens": 10},
            )
        )
    db.commit()
    return run


def test_list_prospects_is_empty_by_default(client):
    response = client.get("/v1/prospects")

    assert response.status_code == 200
    assert response.json() == []


def test_list_prospects_returns_joined_company_qualification_and_campaign(client, db_session):
    campaign = seed_campaign(db_session, "Logistics SaaS")
    prospect, company, qualification = seed_prospect(
        db_session,
        campaign,
        "acme.example",
        score=88,
        confidence=0.91,
        decision="GO",
        research_at=NOW,
    )

    response = client.get("/v1/prospects")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    item = items[0]

    assert uuid.UUID(item["prospect"]["id"]) == prospect.id
    assert item["prospect"]["status"] == "QUALIFIED"
    assert item["company"]["name"] == "Acme"
    assert item["company"]["industry"] == "SaaS"
    assert uuid.UUID(item["company"]["id"]) == company.id
    assert item["qualification"]["score"] == 88
    assert item["qualification"]["confidence"] == 0.91
    assert item["qualification"]["decision"] == "GO"
    assert item["qualification"]["scoring_breakdown"] == {"industry": 45}
    assert item["campaign"]["name"] == "Logistics SaaS"
    assert uuid.UUID(item["campaign"]["id"]) == campaign.id
    assert item["research_date"].startswith("2026-03-01")


def test_list_prospects_research_date_falls_back_to_prospect_creation(client, db_session):
    campaign = seed_campaign(db_session)
    prospect, _, _ = seed_prospect(db_session, campaign, "fallback.example", research_at=None)

    item = client.get("/v1/prospects").json()[0]

    assert item["research_date"] is not None
    assert item["research_date"] == prospect.created_at.isoformat()


def test_list_prospects_is_newest_first_and_honours_limit(client, db_session):
    campaign = seed_campaign(db_session)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    seed_prospect(db_session, campaign, "oldest.example", created_at=base)
    seed_prospect(db_session, campaign, "newest.example", created_at=base + timedelta(days=2))
    seed_prospect(db_session, campaign, "middle.example", created_at=base + timedelta(days=1))

    items = client.get("/v1/prospects?limit=2").json()

    assert [item["company"]["domain"] for item in items] == ["newest.example", "middle.example"]

    skipped = client.get("/v1/prospects?limit=2&skip=2").json()
    assert [item["company"]["domain"] for item in skipped] == ["oldest.example"]


def test_list_prospects_rejects_out_of_range_limit(client):
    assert client.get("/v1/prospects?limit=0").status_code == 422
    assert client.get("/v1/prospects?limit=501").status_code == 422
    assert client.get("/v1/prospects?skip=-1").status_code == 422


def test_get_single_prospect_still_works(client, db_session):
    campaign = seed_campaign(db_session)
    prospect, _, _ = seed_prospect(db_session, campaign, "single.example")

    response = client.get(f"/v1/prospects/{prospect.id}")

    assert response.status_code == 200
    body = response.json()
    assert uuid.UUID(body["prospect"]["id"]) == prospect.id
    assert body["company"]["domain"] == "single.example"


def test_list_workflow_runs_is_empty_by_default(client):
    response = client.get("/v1/workflow-runs")

    assert response.status_code == 200
    assert response.json() == []


def test_list_workflow_runs_returns_counts_and_company(client, db_session):
    campaign = seed_campaign(db_session)
    prospect, _, _ = seed_prospect(db_session, campaign, "runs.example")
    other, _, _ = seed_prospect(db_session, campaign, "other.example")
    run = seed_run(db_session, prospect, status="AWAITING_APPROVAL", events=3)
    seed_run(db_session, other, status="FAILED", events=1)

    response = client.get("/v1/workflow-runs")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2

    row = next(item for item in items if item["id"] == str(run.id))
    assert row["prospect_id"] == str(prospect.id)
    assert row["status"] == "AWAITING_APPROVAL"
    assert row["event_count"] == 3
    assert row["total_tokens"] == 120
    assert row["total_cost"] == 0.004
    assert row["company_name"] == "Runs"
    assert row["company_domain"] == "runs.example"
    assert row["created_at"]


def test_list_workflow_runs_filters_by_prospect_and_status(client, db_session):
    campaign = seed_campaign(db_session)
    prospect, _, _ = seed_prospect(db_session, campaign, "filter.example")
    other, _, _ = seed_prospect(db_session, campaign, "filter-other.example")
    seed_run(db_session, prospect, status="COMPLETED", events=2)
    seed_run(db_session, other, status="FAILED", events=1)

    by_prospect = client.get(f"/v1/workflow-runs?prospect_id={prospect.id}").json()
    assert len(by_prospect) == 1
    assert by_prospect[0]["company_domain"] == "filter.example"
    assert by_prospect[0]["event_count"] == 2

    by_status = client.get("/v1/workflow-runs?status=FAILED").json()
    assert len(by_status) == 1
    assert by_status[0]["company_domain"] == "filter-other.example"

    assert client.get("/v1/workflow-runs?prospect_id=not-a-uuid").status_code == 422


class FakeSearch(SearchProvider):
    def search(self, query, max_results=5):
        return [
            SearchResult(
                "https://acme.example/about",
                "Acme About",
                "Acme builds workflow software for logistics teams.",
                0.9,
            )
        ]


class FakeLLM(LLMProvider):
    def generate_json(self, system, prompt):
        if "commercial research" in system:
            data = {
                "name": "Acme",
                "description": "Workflow software",
                "industry": "SaaS",
                "location": "Europe",
                "commercial_signals": ["sales expansion"],
                "pain_points": [],
                "evidence_summary": "Evidence-backed",
            }
        elif "qualify B2B" in system:
            data = {
                "score": 88,
                "confidence": 0.91,
                "decision": "GO",
                "reasoning": "Strong fit",
                "scoring_breakdown": {"industry": 45, "signal": 43},
            }
        elif "Draft concise" in system:
            data = {
                "subject": "Acme x workflow",
                "body": "Saw your expansion.",
                "claims": ["expansion"],
            }
        else:
            data = {"approved": True, "unsupported_claims": [], "notes": "Grounded"}
        return data, {"total_tokens": 100, "input_tokens": 70, "output_tokens": 30}


def test_discovered_prospect_appears_in_list(client):
    app.dependency_overrides[get_search_provider] = lambda: FakeSearch()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()

    campaign = client.post(
        "/v1/campaigns",
        json={
            "name": "Listed campaign",
            "product_description": "AI sales automation",
            "target_industries": ["SaaS"],
            "target_company_characteristics": {"region": "Europe"},
            "qualification_criteria": "Growing B2B SaaS",
        },
    ).json()
    discovered = client.post(
        "/v1/prospects/discover",
        json={"campaign_id": campaign["id"], "domain": "acme.example"},
    ).json()

    items = client.get("/v1/prospects").json()
    assert len(items) == 1
    assert items[0]["prospect"]["id"] == discovered["prospect"]["id"]
    assert items[0]["campaign"]["name"] == "Listed campaign"
    assert items[0]["qualification"]["score"] == 88
    assert items[0]["research_date"] is not None

    runs = client.get(f"/v1/workflow-runs?prospect_id={discovered['prospect']['id']}").json()
    assert len(runs) == 1
    assert runs[0]["id"] == discovered["workflow_run_id"]
    assert runs[0]["event_count"] == 5
