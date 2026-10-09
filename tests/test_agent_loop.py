"""Critic-driven revision loop, approval-gate coercion, cost accounting, and API bounds."""

import pytest
from backend.app.config import settings
from backend.app.main import app
from backend.app.models.domain import WorkflowRun
from backend.app.services.providers import get_llm_provider, get_search_provider
from backend.app.tools.company_search import SearchProvider, SearchResult
from backend.app.tools.llm import LLMProvider

CAMPAIGN_PAYLOAD = {
    "name": "Revision campaign",
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
QUALIFICATION = {
    "score": 85,
    "confidence": 0.9,
    "decision": "GO",
    "reasoning": "Strong fit",
    "scoring_breakdown": {"industry": 45},
}
USAGE = {"total_tokens": 100, "input_tokens": 70, "output_tokens": 30}
DRAFT = {"subject": "Acme x workflow", "body": "Saw your expansion.", "claims": ["expansion"]}
REVISED_DRAFT = {"subject": "Acme x workflow", "body": "Saw your growth.", "claims": ["growth"]}


class FakeSearch(SearchProvider):
    def search(self, query, max_results=5):
        return [
            SearchResult(
                "https://acme.example/about", "Acme About", "Acme builds workflow software.", 0.9
            )
        ]


class CriticScriptedLLM(LLMProvider):
    """Routes by system prompt; critic replies come from a script.

    ``critic_responses`` is consumed one entry per critic/revision review so
    tests can drive multi-pass behaviour deterministically.
    """

    def __init__(self, critic_responses, draft=None):
        self.critic_responses = list(critic_responses)
        self.draft = draft or dict(DRAFT)
        self.prompts = []

    def generate_json(self, system, prompt):
        self.prompts.append({"system": system, "prompt": prompt})
        # Mirror GroqProvider: expose the messages for WorkflowEvent.input.
        self.last_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        if "commercial research" in system:
            return dict(INTEL), dict(USAGE)
        if "qualify B2B" in system:
            return dict(QUALIFICATION), dict(USAGE)
        if "Revise" in system:
            return dict(REVISED_DRAFT), dict(USAGE)
        if "Draft concise" in system:
            return dict(self.draft), dict(USAGE)
        return dict(self.critic_responses.pop(0)), dict(USAGE)


def discover(client, critic_responses, draft=None):
    llm = CriticScriptedLLM(critic_responses, draft=draft)
    app.dependency_overrides[get_search_provider] = lambda: FakeSearch()
    app.dependency_overrides[get_llm_provider] = lambda: llm
    campaign = client.post("/v1/campaigns", json=CAMPAIGN_PAYLOAD)
    assert campaign.status_code == 200, campaign.text
    response = client.post(
        "/v1/prospects/discover",
        json={"campaign_id": campaign.json()["id"], "domain": "acme.example"},
    )
    assert response.status_code == 200, response.text
    return response.json(), llm


def run_events(client, run_id):
    response = client.get(f"/v1/workflow-runs/{run_id}")
    assert response.status_code == 200
    return response.json()["events"]


def test_critic_string_false_does_not_route_to_approval(client, db_session):
    """bool("false") is True; the gate must coerce LLM strings to real booleans."""
    data, _ = discover(
        client,
        critic_responses=[
            {"approved": "false", "unsupported_claims": [], "notes": "Thin grounding"}
        ],
    )

    assert data["prospect"]["status"] == "QUALIFIED"
    run = db_session.query(WorkflowRun).one()
    assert run.status == "COMPLETED"


def test_revision_loop_revives_draft_and_persists_events(client):
    data, _ = discover(
        client,
        critic_responses=[
            {"approved": False, "unsupported_claims": ["expansion"], "notes": "Unsupported."},
            {"approved": True, "unsupported_claims": [], "notes": "Grounded."},
        ],
    )

    assert data["prospect"]["status"] == "AWAITING_APPROVAL"
    # The final outreach artifact is the revised draft, not the rejected one.
    assert data["outreach"]["body"] == "Saw your growth."
    assert data["critic"]["approved"] is True

    names = [event["name"] for event in run_events(client, data["workflow_run_id"])]
    assert names.count("outreach_revision") == 1
    assert names.count("critic_revision") == 1
    # Original draft is still on the timeline before the revision.
    assert names.index("outreach_agent") < names.index("outreach_revision")
    assert names.index("outreach_revision") < names.index("critic_revision")


def test_revision_loop_is_bounded(client):
    rejection = {
        "approved": False,
        "unsupported_claims": ["expansion"],
        "notes": "Still unsupported.",
    }
    data, _ = discover(client, critic_responses=[dict(rejection) for _ in range(5)])

    names = [event["name"] for event in run_events(client, data["workflow_run_id"])]
    assert names.count("outreach_revision") == settings.OUTREACH_MAX_REVISIONS
    assert names.count("critic_revision") == settings.OUTREACH_MAX_REVISIONS
    # After the bound is hit the final review still gates the prospect.
    assert data["prospect"]["status"] == "QUALIFIED"


def test_workflow_computes_nonzero_estimated_cost(client, db_session):
    data, _ = discover(
        client,
        critic_responses=[{"approved": True, "unsupported_claims": [], "notes": "Grounded."}],
    )

    run = db_session.query(WorkflowRun).one()
    # 4 LLM steps x (70 in + 30 out) tokens at configured pricing.
    assert run.total_tokens == 400
    expected = 4 * (
        70 / 1_000_000 * settings.GROQ_PRICE_PER_M_INPUT_TOKENS
        + 30 / 1_000_000 * settings.GROQ_PRICE_PER_M_OUTPUT_TOKENS
    )
    assert run.total_cost == pytest.approx(expected)
    assert run.total_cost > 0
    assert data["workflow_run_id"]


def test_llm_events_persist_prompts_for_auditability(client):
    data, llm = discover(
        client,
        critic_responses=[{"approved": True, "unsupported_claims": [], "notes": "Grounded."}],
    )

    events = run_events(client, data["workflow_run_id"])
    llm_events = [e for e in events if e["event_type"] == "LLM"]
    assert llm_events
    for event in llm_events:
        assert event["input"]["system"]
        assert event["input"]["prompt"]
    # Research prompt embeds serialized evidence, not a Python repr.
    research = next(e for e in llm_events if e["name"] == "research_agent")
    assert '"url": "https://acme.example/about"' in research["input"]["prompt"]
    assert "untrusted data" in research["input"]["prompt"]


def test_get_prospect_returns_run_id_and_agent_artifacts(client):
    data, _ = discover(
        client,
        critic_responses=[{"approved": True, "unsupported_claims": [], "notes": "Grounded."}],
    )

    response = client.get(f"/v1/prospects/{data['prospect']['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_run_id"] == data["workflow_run_id"]
    assert body["outreach"] == data["outreach"]
    assert body["critic"] == data["critic"]


def test_get_prospect_returns_final_critic_review_after_revision(client):
    """After the revision loop, GET must return the final critic_revision
    review (which gated the run), not the stale first-pass critic_agent one."""
    first_rejection = {
        "approved": False,
        "unsupported_claims": ["expansion"],
        "notes": "Unsupported by evidence.",
    }
    final_approval = {"approved": True, "unsupported_claims": [], "notes": "Grounded."}
    data, _ = discover(client, critic_responses=[first_rejection, final_approval])

    response = client.get(f"/v1/prospects/{data['prospect']['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["critic"]["approved"] is True
    assert body["critic"]["unsupported_claims"] == []
    assert body["outreach"] == data["outreach"]  # final revised draft
    assert data["critic"]["approved"] is True  # discover POST agrees


def test_list_campaigns_rejects_out_of_range_pagination(client):
    assert client.get("/v1/campaigns?limit=0").status_code == 422
    assert client.get("/v1/campaigns?limit=501").status_code == 422
    assert client.get("/v1/campaigns?skip=-1").status_code == 422


class CapturingLLM(LLMProvider):
    """Captures the (system, prompt) pair and returns a fixed review."""

    def __init__(self):
        self.calls = []

    def generate_json(self, system, prompt):
        self.calls.append((system, prompt))
        return {"approved": True, "unsupported_claims": [], "notes": "Grounded."}, dict(USAGE)


def _evidence(count: int, excerpt_len: int = 400) -> list[dict]:
    return [
        {
            "url": f"https://example.com/{i}",
            "title": f"Source {i}",
            "excerpt": f"MARKER_{i} " + "x" * excerpt_len,
        }
        for i in range(1, count + 1)
    ]


def test_critique_sends_only_top_ranked_evidence_excerpts():
    from backend.app.agents.critic import critique

    llm = CapturingLLM()
    evidence = _evidence(5)

    critique(llm, evidence, dict(DRAFT))

    prompt = llm.calls[0][1]
    assert "MARKER_1" in prompt
    assert "MARKER_2" in prompt
    assert "MARKER_3" in prompt
    assert "MARKER_4" not in prompt
    assert "MARKER_5" not in prompt


def test_critique_evidence_budget_caps_total_size(monkeypatch):
    from backend.app.agents.critic import critique

    monkeypatch.setattr(settings, "CRITIC_EVIDENCE_MAX_EXCERPTS", 3)
    monkeypatch.setattr(settings, "CRITIC_EVIDENCE_BUDGET_CHARS", 1500)
    llm = CapturingLLM()
    evidence = _evidence(3, excerpt_len=5000)

    critique(llm, evidence, dict(DRAFT))

    prompt = llm.calls[0][1]
    start = prompt.index("<evidence>") + len("<evidence>")
    end = prompt.index("</evidence>")
    block = prompt[start:end]
    # render_evidence may overshoot the budget by one char for the "…" marker;
    # the surrounding newlines add a couple more. The point is the ~3x5000-char
    # untruncated set is nowhere near reaching the prompt.
    assert len(block) <= 1500 + 10
    assert "…" in block  # excerpts were truncated, not silently dropped


def test_critique_preserves_rank_order_and_source_metadata():
    from backend.app.agents.critic import critique

    llm = CapturingLLM()
    evidence = _evidence(4)

    critique(llm, evidence, dict(DRAFT))

    prompt = llm.calls[0][1]
    assert prompt.index("MARKER_1") < prompt.index("MARKER_2") < prompt.index("MARKER_3")
    assert "https://example.com/1" in prompt
    assert "Source 1" in prompt
    assert "https://example.com/4" not in prompt


def test_critique_handles_fewer_excerpts_than_cap():
    from backend.app.agents.critic import critique

    llm = CapturingLLM()
    evidence = _evidence(2)

    critique(llm, evidence, dict(DRAFT))

    prompt = llm.calls[0][1]
    assert "MARKER_1" in prompt
    assert "MARKER_2" in prompt
