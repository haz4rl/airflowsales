"""Scoring-path audit tests.

The numeric qualification score is **delegated to the LLM**: `qualify()` asks
the model for a 0-100 score and then validates it (int coercion, 0-100
clamp, 0-1 confidence clamp, GO|MAYBE|NO_GO enum with MAYBE fallback). There
is no deterministic weighting formula in code and no threshold, normalization
step, or hidden ceiling that could suppress high scores — scores above 68,
including 80/90/100, are accepted and persisted verbatim when the model
produces them.

These tests therefore pin the deterministic shell around the model's
judgment: prompt composition (campaign criteria + evidence-derived
intelligence reach the model), range validation, enum fallback, persistence,
and the decision -> prospect-status mapping — using synthetic evidence for a
near-perfect ICP match, a partial match, and a clear non-match. They do not
(and cannot) assert what the live model would score; the fixtures model the
responses a fact-following model produces for evidence that clearly
satisfies, partially satisfies, or contradicts the campaign criteria.
"""

import pytest
from backend.app.agents.qualification import qualify
from backend.app.config import settings
from backend.app.models.domain import Campaign, Prospect, Qualification, WorkflowRun
from backend.app.tools.company_search import SearchProvider, SearchResult
from backend.app.tools.llm import LLMProvider, LLMProviderError
from backend.app.workflows.sales_intelligence import run_sales_intelligence

USAGE = {"total_tokens": 100, "input_tokens": 70, "output_tokens": 30}

# A concrete ICP: growing European B2B SaaS with an active commercial team.
CAMPAIGN_CRITERIA = "Growing B2B SaaS company headquartered in Europe with an active sales team"
CAMPAIGN = {
    "product_description": "AI sales automation for revenue teams",
    "target_industries": ["SaaS"],
    "target_company_characteristics": {"region": "Europe", "min_headcount": 50},
    "qualification_criteria": CAMPAIGN_CRITERIA,
}

# Synthetic evidence: ranked snippets that clearly satisfy every criterion.
NEAR_PERFECT_EVIDENCE = [
    SearchResult(
        "https://example.com/about",
        "About Meridian",
        "Meridian is a European B2B SaaS company headquartered in Berlin, founded 2019. "
        "Headcount grew from 60 to 140 over the last year, and the commercial team of 12 "
        "sells an AI sales automation platform to revenue teams across Europe.",
        0.95,
    ),
    SearchResult(
        "https://example.com/blog/growth",
        "Meridian doubles ARR",
        "Meridian reported doubling ARR this year with aggressive sales hiring in Germany "
        "and France, confirming rapid growth in the European SaaS market.",
        0.92,
    ),
]

# Evidence that only partially satisfies the criteria (right industry, wrong region,
# modest growth).
PARTIAL_EVIDENCE = [
    SearchResult(
        "https://example.com/about",
        "About Northlake",
        "Northlake builds B2B SaaS workflow tools with a small sales team of three, "
        "operating from Canada with flat growth over the past two years.",
        0.8,
    )
]

# Evidence that clearly contradicts the ICP: consumer retail, no sales team, shrinking.
NON_MATCH_EVIDENCE = [
    SearchResult(
        "https://example.com/about",
        "About BrightMart",
        "BrightMart is a consumer retail chain operating brick-and-store locations. "
        "Revenue declined sharply and the company has no B2B software product or sales team.",
        0.85,
    )
]


class FakeSearch(SearchProvider):
    def __init__(self, results):
        self.results = results

    def search(self, query, max_results=5):
        return list(self.results)


class ScriptedQualificationLLM(LLMProvider):
    """Routes by system prompt; records every prompt for prompt-level assertions.

    The qualification response models what a fact-following model returns for
    each evidence profile; research synthesizes facts drawn from the same
    evidence, so the qualification prompt genuinely contains evidence-derived
    intelligence.
    """

    def __init__(self, qualification, intel, critic_approved=True):
        self.qualification = dict(qualification)
        self.intel = dict(intel)
        self.critic_approved = critic_approved
        self.qualify_prompts = []
        self.last_messages = []

    def generate_json(self, system, prompt):
        self.last_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        if "commercial research" in system:
            return dict(self.intel), dict(USAGE)
        if "qualify B2B" in system:
            self.qualify_prompts.append(prompt)
            return dict(self.qualification), dict(USAGE)
        if "Draft concise" in system:
            return {
                "subject": "Meridian x AI sales",
                "body": "Saw your European expansion.",
                "claims": ["European expansion"],
            }, dict(USAGE)
        return {
            "approved": self.critic_approved,
            "unsupported_claims": [],
            "notes": "Grounded",
        }, dict(USAGE)


def run_case(db_session, evidence, qualification, intel, critic_approved=True):
    campaign = Campaign(
        name="ICP audit campaign",
        product_description=CAMPAIGN["product_description"],
        target_industries=CAMPAIGN["target_industries"],
        target_company_characteristics=CAMPAIGN["target_company_characteristics"],
        qualification_criteria=CAMPAIGN["qualification_criteria"],
    )
    db_session.add(campaign)
    db_session.commit()
    llm = ScriptedQualificationLLM(qualification, intel, critic_approved=critic_approved)
    prospect, run, artifacts = run_sales_intelligence(
        db_session, campaign, "meridian.example", FakeSearch(evidence), llm
    )
    return prospect, run, artifacts, llm


NEAR_PERFECT = {
    "score": 95,
    "confidence": 0.93,
    "decision": "GO",
    "reasoning": "All criteria satisfied with strong evidence",
    "scoring_breakdown": {"industry_fit": 30, "region": 25, "growth": 25, "team": 15},
}
NEAR_PERFECT_INTEL = {
    "name": "Meridian",
    "description": "European B2B SaaS AI sales automation platform",
    "industry": "SaaS",
    "location": "Berlin, Germany",
    "commercial_signals": ["headcount grew 60 to 140", "doubled ARR", "hiring sales team"],
    "pain_points": [],
    "evidence_summary": "Rapidly growing European B2B SaaS with an active commercial team",
}
PARTIAL = {
    "score": 55,
    "confidence": 0.6,
    "decision": "MAYBE",
    "reasoning": "Right industry, wrong region, thin growth",
    "scoring_breakdown": {"industry_fit": 30, "region": 0, "growth": 10},
}
PARTIAL_INTEL = {
    "name": "Northlake",
    "description": "B2B SaaS workflow tools",
    "industry": "SaaS",
    "location": "Canada",
    "commercial_signals": ["flat growth"],
    "pain_points": [],
    "evidence_summary": "SaaS vendor outside the target region with modest scale",
}
NON_MATCH = {
    "score": 12,
    "confidence": 0.88,
    "decision": "NO_GO",
    "reasoning": "Consumer retail, no B2B product, declining revenue",
    "scoring_breakdown": {"industry_fit": 0, "region": 0, "growth": 0},
}
NON_MATCH_INTEL = {
    "name": "BrightMart",
    "description": "Consumer retail chain",
    "industry": "Retail",
    "location": "USA",
    "commercial_signals": ["revenue declined sharply"],
    "pain_points": [],
    "evidence_summary": "Declining consumer retailer with no B2B software motion",
}


def test_near_perfect_icp_match_reaches_model_and_persists_high_score(db_session):
    prospect, run, artifacts, llm = run_case(
        db_session, NEAR_PERFECT_EVIDENCE, NEAR_PERFECT, NEAR_PERFECT_INTEL
    )

    # The qualification prompt receives the campaign criteria and the
    # evidence-derived intelligence — the model judges facts, not vibes.
    prompt = llm.qualify_prompts[0]
    assert CAMPAIGN_CRITERIA in prompt
    assert "Meridian" in prompt
    assert "doubled ARR" in prompt
    assert "Berlin" in prompt

    # A high score from the model is accepted verbatim — no hidden ceiling.
    assert artifacts["qualification"]["score"] == 95
    assert artifacts["qualification"]["decision"] == "GO"
    assert run.status == "AWAITING_APPROVAL"
    assert prospect.status == "AWAITING_APPROVAL"

    stored = db_session.query(Qualification).filter_by(prospect_id=prospect.id).one()
    assert stored.score == 95
    assert stored.confidence == pytest.approx(0.93)
    assert stored.decision == "GO"


def test_partial_match_maps_to_maybe_status(db_session):
    prospect, run, _, _ = run_case(db_session, PARTIAL_EVIDENCE, PARTIAL, PARTIAL_INTEL)

    assert run.status == "COMPLETED"
    assert prospect.status == "MAYBE"
    stored = db_session.query(Qualification).filter_by(prospect_id=prospect.id).one()
    assert stored.score == 55
    assert stored.decision == "MAYBE"


def test_clear_non_match_maps_to_rejected_status(db_session):
    prospect, run, _, _ = run_case(db_session, NON_MATCH_EVIDENCE, NON_MATCH, NON_MATCH_INTEL)

    assert run.status == "COMPLETED"
    assert prospect.status == "REJECTED"
    stored = db_session.query(Qualification).filter_by(prospect_id=prospect.id).one()
    assert stored.score == 12
    assert stored.decision == "NO_GO"


def test_go_without_critic_approval_maps_to_qualified(db_session):
    prospect, run, _, _ = run_case(
        db_session, NEAR_PERFECT_EVIDENCE, NEAR_PERFECT, NEAR_PERFECT_INTEL, critic_approved=False
    )

    assert run.status == "COMPLETED"
    assert prospect.status == "QUALIFIED"


class _FixedLLM(LLMProvider):
    def __init__(self, response):
        self.response = dict(response)

    def generate_json(self, system, prompt):
        return dict(self.response), dict(USAGE)


BASE_QUAL = {
    "score": 50,
    "confidence": 0.5,
    "decision": "MAYBE",
    "reasoning": "x",
    "scoring_breakdown": {},
}


@pytest.mark.parametrize("raw,expected", [(80, 80), (90, 90), (100, 100), (150, 100), (-5, 0)])
def test_score_range_has_no_hidden_ceiling_and_clamps_out_of_range(raw, expected):
    data, _ = qualify(_FixedLLM({**BASE_QUAL, "score": raw}), CAMPAIGN, NEAR_PERFECT_INTEL)
    assert data["score"] == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("92.7", 92), ("100", 100), (None, 0), ("not-a-number", 0), (True, 1)],
)
def test_score_coerces_types_before_clamping(raw, expected):
    data, _ = qualify(_FixedLLM({**BASE_QUAL, "score": raw}), CAMPAIGN, NEAR_PERFECT_INTEL)
    assert data["score"] == expected


@pytest.mark.parametrize("raw,expected", [(1.5, 1.0), (-0.2, 0.0), ("0.75", 0.75), (None, 0.0)])
def test_confidence_is_clamped_to_unit_interval(raw, expected):
    data, _ = qualify(_FixedLLM({**BASE_QUAL, "confidence": raw}), CAMPAIGN, NEAR_PERFECT_INTEL)
    assert data["confidence"] == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["GO!", "yes", "", None, "no_go"])
def test_invalid_decision_falls_back_to_maybe(raw):
    data, _ = qualify(_FixedLLM({**BASE_QUAL, "decision": raw}), CAMPAIGN, NEAR_PERFECT_INTEL)
    assert data["decision"] == "MAYBE"


@pytest.mark.parametrize("raw", ["GO", "MAYBE", "NO_GO"])
def test_valid_decisions_pass_through(raw):
    data, _ = qualify(_FixedLLM({**BASE_QUAL, "decision": raw}), CAMPAIGN, NEAR_PERFECT_INTEL)
    assert data["decision"] == raw


def test_failed_run_preserves_qualification_outcome_separately(db_session):
    """A later-stage failure marks the prospect FAILED but the qualification
    row keeps its score/decision — execution status and judgment stay distinct."""
    campaign = Campaign(
        name="Partial failure",
        product_description=CAMPAIGN["product_description"],
        qualification_criteria=CAMPAIGN["qualification_criteria"],
    )
    db_session.add(campaign)
    db_session.commit()

    class FailAtOutreachLLM(ScriptedQualificationLLM):
        def generate_json(self, system, prompt):
            if "Draft concise" in system:
                raise LLMProviderError("Groq rate limited the request (HTTP 429) after 3 attempts.")
            return super().generate_json(system, prompt)

    llm = FailAtOutreachLLM(NEAR_PERFECT, NEAR_PERFECT_INTEL)
    with pytest.raises(LLMProviderError):
        run_sales_intelligence(
            db_session, campaign, "meridian.example", FakeSearch(NEAR_PERFECT_EVIDENCE), llm
        )

    run = db_session.query(WorkflowRun).one()
    assert run.status == "FAILED"
    prospect = db_session.query(Prospect).one()
    assert prospect.status == "FAILED"
    stored = db_session.query(Qualification).one()
    # The judgment survived the failure and is still inspectable.
    assert stored.score == 95
    assert stored.decision == "GO"
    assert settings.OUTREACH_MAX_REVISIONS >= 1
