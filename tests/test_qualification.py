import uuid

import pytest
from backend.app.main import app
from backend.app.models.domain import Prospect, Qualification
from backend.app.services.providers import get_llm_provider, get_search_provider
from backend.app.tools.company_search import SearchProvider, SearchResult
from backend.app.tools.llm import LLMProvider

CAMPAIGN_PAYLOAD = {
    "name": "Logistics SaaS",
    "product_description": "AI sales automation",
    "target_industries": ["SaaS"],
    "target_company_characteristics": {"region": "Europe"},
    "qualification_criteria": "Growing B2B SaaS",
}

INTEL = {
    "name": "Acme",
    "description": "Workflow software",
    "industry": "SaaS",
    "location": "Europe",
    "commercial_signals": ["sales expansion"],
    "pain_points": [],
    "evidence_summary": "Evidence-backed",
}
DRAFT = {"subject": "Acme x workflow", "body": "Saw your expansion.", "claims": ["expansion"]}
USAGE = {"total_tokens": 100, "input_tokens": 70, "output_tokens": 30}


class FakeSearch(SearchProvider):
    def search(self, query, max_results=5):
        return [
            SearchResult(
                "https://acme.example/about", "Acme About", "Acme builds workflow software.", 0.9
            )
        ]


class FakeLLM(LLMProvider):
    def __init__(self, qualification, critic_approved=True):
        self.qualification = qualification
        self.critic_approved = critic_approved

    def generate_json(self, system, prompt):
        if "qualify B2B" in system:
            return dict(self.qualification), dict(USAGE)
        if "commercial research" in system:
            return dict(INTEL), dict(USAGE)
        if "Draft concise" in system:
            return dict(DRAFT), dict(USAGE)
        return {
            "approved": self.critic_approved,
            "unsupported_claims": [],
            "notes": "Grounded",
        }, dict(USAGE)


def discover(client, qualification, critic_approved=True):
    app.dependency_overrides[get_search_provider] = lambda: FakeSearch()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM(qualification, critic_approved)
    campaign = client.post("/v1/campaigns", json=CAMPAIGN_PAYLOAD)
    assert campaign.status_code == 200, campaign.text
    response = client.post(
        "/v1/prospects/discover",
        json={"campaign_id": campaign.json()["id"], "domain": "acme.example"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_go_decision_waits_for_approval(client):
    data = discover(
        client,
        {
            "score": 88,
            "confidence": 0.91,
            "decision": "GO",
            "reasoning": "Strong fit",
            "scoring_breakdown": {"industry": 45},
        },
    )

    assert data["qualification"]["decision"] == "GO"
    assert data["prospect"]["status"] == "AWAITING_APPROVAL"


def test_go_decision_without_critic_approval_is_qualified(client):
    data = discover(
        client,
        {
            "score": 82,
            "confidence": 0.88,
            "decision": "GO",
            "reasoning": "Strong fit",
            "scoring_breakdown": {},
        },
        critic_approved=False,
    )

    assert data["qualification"]["decision"] == "GO"
    assert data["prospect"]["status"] == "QUALIFIED"


def test_maybe_decision_is_not_qualified(client):
    data = discover(
        client,
        {
            "score": 55,
            "confidence": 0.6,
            "decision": "MAYBE",
            "reasoning": "Thin evidence",
            "scoring_breakdown": {},
        },
    )

    qualification = data["qualification"]
    assert qualification["decision"] == "MAYBE"
    assert qualification["score"] == 55
    assert qualification["confidence"] == 0.6
    assert data["prospect"]["status"] == "MAYBE"
    assert data["prospect"]["status"] != "QUALIFIED"


def test_no_go_decision_is_rejected(client):
    data = discover(
        client,
        {
            "score": 12,
            "confidence": 0.8,
            "decision": "NO_GO",
            "reasoning": "Poor fit",
            "scoring_breakdown": {},
        },
    )

    assert data["qualification"]["decision"] == "NO_GO"
    assert data["prospect"]["status"] == "REJECTED"


@pytest.mark.parametrize(
    "qualification,critic_approved,expected_status",
    [
        (
            {
                "score": 82,
                "confidence": 0.88,
                "decision": "GO",
                "reasoning": "Strong fit",
                "scoring_breakdown": {},
            },
            True,
            "AWAITING_APPROVAL",
        ),
        (
            {
                "score": 82,
                "confidence": 0.88,
                "decision": "GO",
                "reasoning": "Strong fit",
                "scoring_breakdown": {},
            },
            False,
            "QUALIFIED",
        ),
        (
            {
                "score": 55,
                "confidence": 0.6,
                "decision": "MAYBE",
                "reasoning": "Thin evidence",
                "scoring_breakdown": {},
            },
            True,
            "MAYBE",
        ),
        (
            {
                "score": 12,
                "confidence": 0.8,
                "decision": "NO_GO",
                "reasoning": "Poor fit",
                "scoring_breakdown": {},
            },
            True,
            "REJECTED",
        ),
    ],
)
def test_persisted_status_consistent_with_decision(
    client, db_session, qualification, critic_approved, expected_status
):
    data = discover(client, qualification, critic_approved)

    prospect = db_session.get(Prospect, uuid.UUID(data["prospect"]["id"]))
    db_session.refresh(prospect)
    stored = db_session.query(Qualification).filter_by(prospect_id=prospect.id).one()

    assert stored.decision == qualification["decision"]
    assert prospect.status == expected_status
