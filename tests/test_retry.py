import json
import logging

import httpx
import pytest
from backend.app.config import settings
from backend.app.main import app
from backend.app.models.domain import Campaign, Prospect, WorkflowRun
from backend.app.services.providers import get_llm_provider, get_search_provider
from backend.app.tools.company_search import SearchProvider, SearchResult, TavilySearchProvider
from backend.app.tools.llm import GroqProvider, LLMProviderError
from backend.app.workflows.sales_intelligence import run_sales_intelligence

# A single payload that satisfies every agent step (research, qualification,
# outreach, critic) so the workflow can run end-to-end against a scripted provider.
LLM_CONTENT = {
    "name": "Acme",
    "description": "Workflow software",
    "industry": "SaaS",
    "location": "Europe",
    "commercial_signals": ["expansion"],
    "pain_points": [],
    "evidence_summary": "Evidence-backed",
    "score": 60,
    "confidence": 0.6,
    "decision": "MAYBE",
    "reasoning": "Thin evidence",
    "scoring_breakdown": {"industry": 30},
    "subject": "Acme x workflow",
    "body": "Saw your expansion.",
    "claims": ["expansion"],
    "approved": False,
    "unsupported_claims": [],
    "notes": "Grounded",
}

LLM_BODY = {
    "choices": [{"message": {"content": json.dumps(LLM_CONTENT)}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

SEARCH_BODY = {
    "results": [
        {
            "url": "https://acme.example/about",
            "title": "Acme About",
            "content": "Acme builds workflow software.",
            "score": 0.9,
        }
    ]
}


class ScriptedPost:
    """Stand-in for httpx.post driven by a script of responses/exceptions.

    Each script item is an int status code, a JSON body dict, or an exception
    instance. Once the script is exhausted ``overflow`` is used; when it is
    None an unexpected extra call fails loudly so unintended retries show up.
    """

    def __init__(self, script, overflow=None):
        self.script = list(script)
        self.overflow = overflow
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0) if self.script else self.overflow
        if item is None:
            raise AssertionError(f"unexpected extra provider call to {url}")
        if isinstance(item, BaseException):
            raise item
        request = httpx.Request("POST", url)
        if isinstance(item, int):
            return httpx.Response(item, request=request)
        if isinstance(item, tuple):
            status, body = item
            return httpx.Response(status, json=body, request=request)
        return httpx.Response(200, json=item, request=request)


class RoutedPost:
    """Dispatch by URL substring.

    Both providers call ``httpx.post`` on the same imported module object, so
    a single patch has to serve both endpoints.
    """

    def __init__(self, **routes):
        self.routes = routes

    def __call__(self, url, **kwargs):
        for needle, post in self.routes.items():
            if needle in url:
                return post(url, **kwargs)
        raise AssertionError(f"unexpected provider call to {url}")


class FakeSearch(SearchProvider):
    def search(self, query, max_results=5):
        return [
            SearchResult(
                "https://acme.example/about", "Acme About", "Acme builds workflow software.", 0.9
            )
        ]


@pytest.fixture
def delays(monkeypatch):
    recorded = []
    monkeypatch.setattr("backend.app.tools.retry._sleep", lambda seconds: recorded.append(seconds))
    return recorded


@pytest.fixture
def groq_post(monkeypatch):
    def install(script, overflow=None):
        post = ScriptedPost(script, overflow)
        monkeypatch.setattr("backend.app.tools.llm.httpx.post", post)
        return post

    return install


def generate(provider=None, system="You qualify B2B prospects.", prompt="prompt"):
    provider = provider or GroqProvider(api_key="test-key")
    return provider.generate_json(system, prompt)


def test_rate_limit_is_retried_with_exponential_backoff(delays, groq_post):
    post = groq_post([429, 429], overflow=LLM_BODY)
    provider = GroqProvider(api_key="test-key")

    data, usage = generate(provider)

    assert data["decision"] == "MAYBE"
    assert usage["total_tokens"] == 15
    assert len(post.calls) == 3
    assert delays == [
        settings.RETRY_BASE_DELAY_SECONDS,
        settings.RETRY_BASE_DELAY_SECONDS * 2,
    ]
    assert [attempt.retry for attempt in provider.retry_attempts] == [1, 2]
    assert {attempt.reason for attempt in provider.retry_attempts} == {"rate_limit"}
    assert {attempt.status_code for attempt in provider.retry_attempts} == {429}
    assert provider.retry_attempts[0].detail == "HTTP 429 Too Many Requests"


def test_rate_limit_exhaustion_raises_clean_error(delays, groq_post):
    post = groq_post([], overflow=429)
    provider = GroqProvider(api_key="test-key")

    with pytest.raises(LLMProviderError) as excinfo:
        generate(provider)

    message = str(excinfo.value)
    assert "rate limited the request (HTTP 429)" in message
    assert f"{settings.MAX_RETRIES + 1} attempts" in message
    assert "Try again shortly" in message
    assert "api.groq.com" not in message
    assert "developer.mozilla.org" not in message
    assert len(post.calls) == settings.MAX_RETRIES + 1
    assert len(provider.retry_attempts) == settings.MAX_RETRIES
    assert delays == [
        settings.RETRY_BASE_DELAY_SECONDS,
        settings.RETRY_BASE_DELAY_SECONDS * 2,
    ]


def test_server_error_is_retried_then_succeeds(delays, groq_post):
    post = groq_post([503], overflow=LLM_BODY)
    provider = GroqProvider(api_key="test-key")

    data, _ = generate(provider)

    assert data["score"] == 60
    assert len(post.calls) == 2
    assert delays == [settings.RETRY_BASE_DELAY_SECONDS]
    assert provider.retry_attempts[0].reason == "server_error"
    assert provider.retry_attempts[0].status_code == 503


def test_server_error_exhaustion_raises_clean_error(delays, groq_post):
    groq_post([], overflow=503)

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    message = str(excinfo.value)
    assert "server error (HTTP 503" in message
    assert f"{settings.MAX_RETRIES + 1} attempts" in message
    assert "api.groq.com" not in message


def test_network_failure_is_retried_then_succeeds(delays, groq_post):
    post = groq_post([httpx.ConnectError("connection refused")], overflow=LLM_BODY)
    provider = GroqProvider(api_key="test-key")

    generate(provider)

    assert len(post.calls) == 2
    assert delays == [settings.RETRY_BASE_DELAY_SECONDS]
    assert provider.retry_attempts[0].reason == "network"
    assert provider.retry_attempts[0].status_code is None
    assert provider.retry_attempts[0].detail == "ConnectError"


def test_network_failure_exhaustion_raises_clean_error(delays, groq_post):
    groq_post([], overflow=httpx.ReadTimeout("timed out"))

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    message = str(excinfo.value)
    assert f"Could not reach Groq after {settings.MAX_RETRIES + 1} attempts" in message
    assert "ReadTimeout" in message
    assert "api.groq.com" not in message


def test_permanent_client_error_is_not_retried(delays, groq_post):
    post = groq_post([400])

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    assert "rejected the request (HTTP 400" in str(excinfo.value)
    assert len(post.calls) == 1
    assert delays == []


# The exact response body Groq returns when a json_object request is cut off
# mid-document by max_tokens: the truncated JSON fails validation and the whole
# request becomes a 400. Captured from a real figma.com research-step failure.
GROQ_TOKEN_EXHAUSTED_400 = {
    "error": {
        "message": (
            "Failed to generate JSON. Please adjust your prompt. "
            "See 'failed_generation' for more details."
        ),
        "type": "invalid_request_error",
        "code": "json_validate_failed",
        "failed_generation": "max completion tokens reached before generating a valid document",
    }
}


def test_token_exhausted_json_validate_failed_escalates_once(delays, groq_post, caplog):
    post = groq_post([(400, GROQ_TOKEN_EXHAUSTED_400)], overflow=LLM_BODY)
    provider = GroqProvider(api_key="test-key")

    with caplog.at_level(logging.WARNING, logger="backend.app.tools.llm"):
        data, usage = generate(provider)

    assert data["decision"] == "MAYBE"
    assert usage["total_tokens"] == 15
    assert len(post.calls) == 2
    first, second = post.calls
    assert first["json"]["max_tokens"] == settings.LLM_MAX_TOKENS
    assert second["json"]["max_tokens"] == settings.LLM_MAX_TOKENS_ESCALATED
    # Escalation is a budget re-request inside the provider, not a rate-limit
    # retry: no backoff sleeps, no retry attempts recorded.
    assert delays == []
    assert provider.retry_attempts == []
    assert any("json_validate_failed" in record.getMessage() for record in caplog.records)


def test_token_exhaustion_escalation_is_bounded(delays, groq_post):
    post = groq_post([(400, GROQ_TOKEN_EXHAUSTED_400), (400, GROQ_TOKEN_EXHAUSTED_400)])

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    # Exactly one escalation, then the failure surfaces with its sanitized reason.
    assert len(post.calls) == 2
    assert post.calls[1]["json"]["max_tokens"] == settings.LLM_MAX_TOKENS_ESCALATED
    message = str(excinfo.value)
    assert "rejected the request (HTTP 400)" in message
    assert "json_validate_failed" in message
    assert "max completion tokens" in message
    assert delays == []


def test_permanent_400_with_body_is_not_retried_and_surfaces_reason(delays, groq_post):
    body = {
        "error": {
            "message": "The model `missing-model` does not exist",
            "type": "invalid_request_error",
            "code": "model_not_found",
        }
    }
    post = groq_post([(400, body)])

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    message = str(excinfo.value)
    assert "rejected the request (HTTP 400)" in message
    assert "The model `missing-model` does not exist" in message
    assert "model_not_found" in message
    assert len(post.calls) == 1
    assert delays == []


def test_provider_error_detail_redacts_credentials(delays, groq_post):
    body = {"error": {"message": "invalid api_key: sk-live-123456789", "code": "invalid_auth"}}
    groq_post([(400, body)])

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    message = str(excinfo.value)
    assert "sk-live-123456789" not in message
    assert "[redacted]" in message
    assert "invalid_auth" in message


def test_unauthorized_is_not_retried_and_points_at_the_key(delays, groq_post):
    post = groq_post([401])

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    message = str(excinfo.value)
    assert "rejected the API credentials (HTTP 401)" in message
    assert "Check GROQ_API_KEY" in message
    assert len(post.calls) == 1
    assert delays == []


def test_invalid_response_body_is_not_retried(delays, groq_post):
    post = groq_post([], overflow={"choices": [{"message": {"content": "not json"}}]})

    with pytest.raises(LLMProviderError) as excinfo:
        generate()

    assert "returned an invalid response" in str(excinfo.value)
    assert len(post.calls) == 1
    assert delays == []


def test_missing_api_key_fails_before_any_call(delays, groq_post, monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    post = groq_post([], overflow=LLM_BODY)

    with pytest.raises(LLMProviderError) as excinfo:
        GroqProvider(api_key=None).generate_json("sys", "prompt")

    assert str(excinfo.value) == "GROQ_API_KEY is not configured"
    assert post.calls == []
    assert delays == []


def test_search_rate_limit_is_retried(monkeypatch, delays):
    post = ScriptedPost([429], overflow=SEARCH_BODY)
    monkeypatch.setattr("backend.app.tools.company_search.httpx.post", post)
    provider = TavilySearchProvider(api_key="test-key")

    results = provider.search("acme", 5)

    assert len(results) == 1
    assert len(post.calls) == 2
    assert delays == [settings.RETRY_BASE_DELAY_SECONDS]
    assert provider.retry_attempts[0].reason == "rate_limit"


def test_search_permanent_error_is_not_retried(monkeypatch, delays):
    post = ScriptedPost([404])
    monkeypatch.setattr("backend.app.tools.company_search.httpx.post", post)
    provider = TavilySearchProvider(api_key="test-key")

    from backend.app.tools.company_search import SearchProviderError

    with pytest.raises(SearchProviderError) as excinfo:
        provider.search("acme", 5)

    assert "rejected the request (HTTP 404" in str(excinfo.value)
    assert len(post.calls) == 1
    assert delays == []


def _campaign(db):
    campaign = Campaign(
        name="Retry campaign",
        product_description="AI sales automation",
        qualification_criteria="Growing B2B SaaS",
    )
    db.add(campaign)
    db.commit()
    return campaign


def test_workflow_records_retry_attempts_as_events(db_session, monkeypatch, delays):
    monkeypatch.setattr("backend.app.tools.llm.httpx.post", ScriptedPost([429], overflow=LLM_BODY))
    campaign = _campaign(db_session)

    prospect, run, _ = run_sales_intelligence(
        db_session, campaign, "acme.example", FakeSearch(), GroqProvider(api_key="test-key")
    )

    assert run.status == "COMPLETED"
    assert prospect.status == "MAYBE"
    assert delays == [settings.RETRY_BASE_DELAY_SECONDS]

    retry_events = [event for event in run.events if event.event_type == "RETRY"]
    assert len(retry_events) == 1
    assert retry_events[0].name == "research_agent_retry"
    assert retry_events[0].input == {"step": "research_agent"}
    assert retry_events[0].output["retry"] == 1
    assert retry_events[0].output["delay_seconds"] == settings.RETRY_BASE_DELAY_SECONDS
    assert retry_events[0].output["reason"] == "rate_limit"
    assert retry_events[0].output["status_code"] == 429
    assert retry_events[0].output["detail"] == "HTTP 429 Too Many Requests"
    assert retry_events[0].token_usage == {}

    names = [event.name for event in run.events]
    assert names.index("research_agent_retry") == names.index("research_agent") + 1
    assert len(names) == 6


def test_workflow_records_search_retry_attempts(db_session, monkeypatch, delays):
    monkeypatch.setattr(
        "backend.app.tools.company_search.httpx.post",
        RoutedPost(
            tavily=ScriptedPost([500], overflow=SEARCH_BODY),
            groq=ScriptedPost([], overflow=LLM_BODY),
        ),
    )
    campaign = _campaign(db_session)

    provider = TavilySearchProvider(api_key="test-key")
    _, run, _ = run_sales_intelligence(
        db_session, campaign, "acme.example", provider, GroqProvider(api_key="test-key")
    )

    assert run.status == "COMPLETED"
    retry_events = [event for event in run.events if event.event_type == "RETRY"]
    assert len(retry_events) == 1
    assert retry_events[0].name == "company_search_retry"
    assert retry_events[0].output["reason"] == "server_error"
    assert retry_events[0].output["status_code"] == 500


def test_workflow_failure_records_retries_and_clean_error(db_session, monkeypatch, delays):
    monkeypatch.setattr("backend.app.tools.llm.httpx.post", ScriptedPost([], overflow=429))
    campaign = _campaign(db_session)

    with pytest.raises(LLMProviderError) as excinfo:
        run_sales_intelligence(
            db_session, campaign, "acme.example", FakeSearch(), GroqProvider(api_key="test-key")
        )

    message = str(excinfo.value)
    assert "rate limited the request (HTTP 429)" in message
    assert "api.groq.com" not in message

    run = db_session.query(WorkflowRun).one()
    assert run.status == "FAILED"
    prospect = db_session.query(Prospect).one()
    assert prospect.status == "FAILED"

    retry_events = [event for event in run.events if event.event_type == "RETRY"]
    assert len(retry_events) == settings.MAX_RETRIES
    assert {event.name for event in retry_events} == {"research_agent_retry"}

    failure = next(event for event in run.events if event.name == "workflow_failure")
    assert "rate limited" in failure.output["error"]
    assert "api.groq.com" not in failure.output["error"]


def test_workflow_recovers_from_token_exhausted_json_validate_failed(
    db_session, monkeypatch, delays
):
    """Regression: a research step cut off mid-JSON by the token cap must
    recover via one escalated budget request, not fail the whole run."""
    monkeypatch.setattr(
        "backend.app.tools.llm.httpx.post",
        ScriptedPost([(400, GROQ_TOKEN_EXHAUSTED_400)], overflow=LLM_BODY),
    )
    campaign = _campaign(db_session)

    prospect, run, _ = run_sales_intelligence(
        db_session, campaign, "acme.example", FakeSearch(), GroqProvider(api_key="test-key")
    )

    assert run.status == "COMPLETED"
    assert prospect.status == "MAYBE"
    # Escalation lives inside the provider; the retry policy saw no transient
    # failure, so no RETRY events and no backoff sleeps.
    assert [event for event in run.events if event.event_type == "RETRY"] == []
    assert delays == []


def test_discover_returns_clean_error_when_retries_exhausted(client, monkeypatch, delays):
    monkeypatch.setattr("backend.app.tools.llm.httpx.post", ScriptedPost([], overflow=429))
    app.dependency_overrides[get_search_provider] = lambda: FakeSearch()
    app.dependency_overrides[get_llm_provider] = lambda: GroqProvider(api_key="test-key")

    campaign = client.post(
        "/v1/campaigns",
        json={
            "name": "Retry campaign",
            "product_description": "AI sales automation",
            "target_industries": ["SaaS"],
            "target_company_characteristics": {"region": "Europe"},
            "qualification_criteria": "Growing B2B SaaS",
        },
    )
    assert campaign.status_code == 200

    response = client.post(
        "/v1/prospects/discover",
        json={"campaign_id": campaign.json()["id"], "domain": "acme.example"},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "rate limited the request (HTTP 429)" in detail
    assert f"{settings.MAX_RETRIES + 1} attempts" in detail
    assert "api.groq.com" not in detail
    assert "Try again shortly" in detail
