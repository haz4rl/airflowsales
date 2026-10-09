"""Shared retry policy for external HTTP providers.

Transient failures (rate limits, 5xx, network/timeouts) are retried with
exponential backoff; permanent client errors are surfaced immediately so a bad
key or malformed request is never hammered with retries. Every attempt that
gave birth to a retry is captured so the workflow layer can persist it as a
WorkflowEvent, and exhausted retries are re-raised with a message that is safe
to show to an operator.
"""

import re
import time
from dataclasses import dataclass

import httpx
from backend.app.config import settings

# Anything that looks like a credential must never reach logs or error messages.
_SECRET_RE = re.compile(r"(?i)\b(authorization|api[-_]?key|apikey|bearer|token)\b\s*[:=]?\s*\S+")


@dataclass(frozen=True)
class RetryAttempt:
    retry: int  # 1-based retry ordinal (the retry about to be performed)
    delay_seconds: float
    reason: str  # rate_limit | server_error | network
    status_code: int | None
    detail: str


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def classify(exc: BaseException) -> tuple[bool, str, int | None]:
    """Return (retryable, reason, status_code) for a provider failure."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return True, "rate_limit", code
        if code >= 500:
            return True, "server_error", code
        return False, "client_error", code
    if isinstance(exc, httpx.TransportError):
        return True, "network", None
    return False, "unexpected", None


def _detail(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} {exc.response.reason_phrase}".strip()
    return type(exc).__name__


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds) from a rate-limit response."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    raw = exc.response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    if seconds < 0:
        return None
    return seconds


def _delay_for(
    exc: BaseException, reason: str, retry: int, default_base: float, ceiling: float
) -> float:
    """Backoff delay: fast exponential for ordinary transient failures,
    window-aware for rate limits (Retry-After when provided, otherwise a
    rate-limit-specific schedule capped at the rate-limit ceiling)."""
    if reason == "rate_limit":
        rate_ceiling = settings.RETRY_RATE_LIMIT_MAX_DELAY_SECONDS
        retry_after = _retry_after_seconds(exc)
        if retry_after is not None:
            return min(max(retry_after, 1.0), rate_ceiling)
        return min(settings.RETRY_RATE_LIMIT_BASE_DELAY_SECONDS * (2**retry), rate_ceiling)
    return min(default_base * (2**retry), ceiling)


def sanitize_error_text(text: str, limit: int = 200) -> str:
    """Single-line, credential-redacted, truncated provider error text."""
    cleaned = _SECRET_RE.sub(lambda m: f"{m.group(1)} [redacted]", text or "")
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def http_error_detail(exc: BaseException) -> str | None:
    """Best-effort sanitized reason from a provider's HTTP error response body.

    Providers put the useful part of a failure (``error.message``,
    ``error.code``, …) in the JSON body — the status line alone is usually just
    "Bad Request". Returns None when no body is available or it cannot be read.
    """
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    response = exc.response
    try:
        data = response.json()
    except Exception:
        text = (response.text or "").strip()
        return sanitize_error_text(text) if text else None
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            parts = [
                str(error[key])
                for key in ("message", "code", "failed_generation")
                if error.get(key)
            ]
            if parts:
                return sanitize_error_text(" · ".join(parts))
        elif isinstance(error, str):
            return sanitize_error_text(error)
    return sanitize_error_text(str(data))


def _attempts_label(total: int) -> str:
    return f"{total} attempt{'' if total == 1 else 's'}"


def describe_failure(
    exc: BaseException, attempts: list[RetryAttempt], service: str, api_key_hint: str
) -> str:
    """Build a clean, user-facing message for a provider failure."""
    total = len(attempts) + 1
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        phrase = exc.response.reason_phrase
        if code in (401, 403):
            return f"{service} rejected the API credentials (HTTP {code}). Check {api_key_hint}."
        if code == 429:
            return f"{service} rate limited the request (HTTP 429) after {_attempts_label(total)}. Try again shortly."
        if code >= 500:
            return f"{service} returned a server error (HTTP {code} {phrase}) after {_attempts_label(total)}. Try again shortly."
        detail = http_error_detail(exc)
        if detail:
            return f"{service} rejected the request (HTTP {code}): {detail}"
        return f"{service} rejected the request (HTTP {code} {phrase})."
    if isinstance(exc, httpx.TransportError):
        return f"Could not reach {service} after {_attempts_label(total)} ({type(exc).__name__}). Try again shortly."
    if isinstance(exc, KeyError | IndexError | TypeError | AttributeError | ValueError):
        return f"{service} returned an invalid response ({type(exc).__name__})."
    return f"{service} request failed: {exc}"


def call_with_retries(
    operation, *, attempts: list[RetryAttempt], max_retries: int | None = None
) -> object:
    """Run ``operation``, retrying transient failures with exponential backoff.

    ``attempts`` is appended to in place (one entry per retry performed) and is
    left untouched when the failure is permanent, so callers can record or
    report exactly what happened.
    """
    limit = settings.MAX_RETRIES if max_retries is None else max_retries
    base = settings.RETRY_BASE_DELAY_SECONDS
    ceiling = settings.RETRY_MAX_DELAY_SECONDS
    retry = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            retryable, reason, status_code = classify(exc)
            if not retryable or retry >= limit:
                raise
            delay = _delay_for(exc, reason, retry, base, ceiling)
            attempts.append(
                RetryAttempt(
                    retry=retry + 1,
                    delay_seconds=delay,
                    reason=reason,
                    status_code=status_code,
                    detail=_detail(exc),
                )
            )
            _sleep(delay)
            retry += 1
