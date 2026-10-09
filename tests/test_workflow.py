from backend.app.main import app
from backend.app.services.providers import get_llm_provider, get_search_provider
from backend.app.tools.company_search import SearchProvider, SearchResult
from backend.app.tools.llm import LLMProvider


class FakeSearch(SearchProvider):
    def search(self, query, max_results=5):
        return [
            SearchResult(
                "https://acme.example/about",
                "Acme About",
                "Acme builds workflow software for logistics teams.",
                0.9,
            ),
            SearchResult(
                "https://news.example/acme",
                "Acme expands",
                "Acme expanded its enterprise sales team in Europe.",
                0.8,
            ),
            SearchResult(
                "https://acme.example/customers",
                "Customers",
                "Acme serves logistics companies.",
                0.7,
            ),
        ]


class FakeLLM(LLMProvider):
    calls = 0

    def generate_json(self, system, prompt):
        self.calls += 1
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
                "body": "Saw your enterprise expansion.",
                "claims": ["enterprise expansion"],
            }
        else:
            data = {"approved": True, "unsupported_claims": [], "notes": "Grounded"}
        return data, {"total_tokens": 100, "input_tokens": 70, "output_tokens": 30}


def campaign(client):
    r = client.post(
        "/v1/campaigns",
        json={
            "name": "Logistics SaaS",
            "product_description": "AI sales automation",
            "target_industries": ["SaaS"],
            "target_company_characteristics": {"region": "Europe"},
            "qualification_criteria": "Growing B2B SaaS",
        },
    )
    assert r.status_code == 200
    return r.json()


def test_end_to_end_agentic_workflow(client):
    app.dependency_overrides[get_search_provider] = lambda: FakeSearch()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    c = campaign(client)
    r = client.post(
        "/v1/prospects/discover",
        json={"campaign_id": c["id"], "domain": "https://acme.example/about"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["company"]["name"] == "Acme"
    assert len(d["evidence"]) == 3
    assert d["qualification"]["score"] == 88
    assert d["prospect"]["status"] == "AWAITING_APPROVAL"
    assert d["outreach"]["subject"] == "Acme x workflow"
    assert d["critic"]["approved"] is True
    run = client.get("/v1/workflow-runs/" + d["workflow_run_id"])
    assert run.status_code == 200
    rd = run.json()
    assert len(rd["events"]) == 5
    assert rd["total_tokens"] == 400
    assert rd["total_cost"] > 0
    approval = client.post(
        "/v1/workflow-runs/" + d["workflow_run_id"] + "/approval",
        json={"approved": True, "note": "Reviewed"},
    )
    assert approval.status_code == 200
    assert approval.json()["status"] == "APPROVED"


def test_invalid_campaign(client):
    app.dependency_overrides[get_search_provider] = lambda: FakeSearch()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    r = client.post(
        "/v1/prospects/discover",
        json={"campaign_id": "00000000-0000-0000-0000-000000000001", "domain": "acme.example"},
    )
    assert r.status_code == 404


def test_invalid_domain(client):
    c = campaign(client)
    r = client.post(
        "/v1/prospects/discover", json={"campaign_id": c["id"], "domain": "not a domain"}
    )
    assert r.status_code == 422
