import json
import logging

import httpx
from backend.app.config import settings
from backend.app.tools.retry import call_with_retries, describe_failure, http_error_detail

log = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    pass


class LLMProvider:
    def generate_json(self, system: str, prompt: str) -> tuple[dict, dict]:
        raise NotImplementedError


def _token_exhausted(exc: httpx.HTTPStatusError) -> bool:
    """Detect Groq's ``json_validate_failed`` caused solely by hitting the
    completion-token cap.

    When ``response_format: json_object`` is on and the model runs out of
    ``max_tokens`` mid-document, Groq validates the truncated (invalid) JSON
    and rejects the request with 400 ``json_validate_failed`` and
    ``failed_generation: "max completion tokens reached…"``. That failure is a
    deterministic function of the token budget, so one escalated re-request is
    a principled recovery — unlike other 400s, which stay non-retryable.
    """
    if exc.response.status_code != 400:
        return False
    try:
        data = exc.response.json()
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    error = data.get("error")
    if not isinstance(error, dict) or error.get("code") != "json_validate_failed":
        return False
    text = " ".join(str(error.get(key, "")) for key in ("message", "failed_generation"))
    return "max completion tokens" in text.lower()


class GroqProvider(LLMProvider):
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        self.retry_attempts: list = []
        # Messages from the most recent generate_json call, persisted by the
        # workflow as WorkflowEvent.input so decisions stay reproducible.
        self.last_messages: list = []

    def _post(self, payload: dict) -> httpx.Response:
        r = httpx.post(
            self.URL,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        return r

    def generate_json(self, system: str, prompt: str) -> tuple[dict, dict]:
        self.retry_attempts = []
        self.last_messages = []
        if not self.api_key:
            raise LLMProviderError("GROQ_API_KEY is not configured")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        self.last_messages = messages
        max_tokens = settings.LLM_MAX_TOKENS
        for attempt in range(2):
            payload = {
                "model": self.model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_tokens": max_tokens,
            }
            try:
                r = call_with_retries(lambda p=payload: self._post(p), attempts=self.retry_attempts)
                body = r.json()
                content = body["choices"][0]["message"]["content"]
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise LLMProviderError("LLM response was not a JSON object")
                u = body.get("usage", {})
                return data, {
                    "input_tokens": u.get("prompt_tokens", 0),
                    "output_tokens": u.get("completion_tokens", 0),
                    "total_tokens": u.get("total_tokens", 0),
                }
            except LLMProviderError:
                raise
            except httpx.HTTPStatusError as exc:
                if attempt == 0 and _token_exhausted(exc):
                    max_tokens = settings.LLM_MAX_TOKENS_ESCALATED
                    log.warning(
                        "Groq json_validate_failed at max_tokens=%d (completion-token "
                        "exhaustion); retrying once with escalated budget %d",
                        settings.LLM_MAX_TOKENS,
                        max_tokens,
                    )
                    continue
                log.warning(
                    "Groq request rejected: status=%s detail=%s",
                    exc.response.status_code,
                    http_error_detail(exc) or "no error body",
                )
                raise LLMProviderError(
                    describe_failure(exc, self.retry_attempts, "Groq", "GROQ_API_KEY")
                ) from exc
            except Exception as exc:
                raise LLMProviderError(
                    describe_failure(exc, self.retry_attempts, "Groq", "GROQ_API_KEY")
                ) from exc
