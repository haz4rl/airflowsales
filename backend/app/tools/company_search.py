from dataclasses import dataclass

import httpx
from backend.app.config import settings
from backend.app.tools.retry import call_with_retries, describe_failure


@dataclass
class SearchResult:
    url: str
    title: str
    content: str
    score: float | None = None


class SearchProviderError(RuntimeError):
    pass


class SearchProvider:
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class TavilySearchProvider(SearchProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.TAVILY_API_KEY
        self.retry_attempts: list = []

    def _post(self, query: str, max_results: int) -> httpx.Response:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=settings.SEARCH_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        return r

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        self.retry_attempts = []
        if not self.api_key:
            raise SearchProviderError("TAVILY_API_KEY is not configured")
        try:
            r = call_with_retries(
                lambda: self._post(query, max_results), attempts=self.retry_attempts
            )
        except Exception as exc:
            raise SearchProviderError(
                describe_failure(exc, self.retry_attempts, "Tavily", "TAVILY_API_KEY")
            ) from exc
        return [
            SearchResult(
                x.get("url", ""), x.get("title", "Untitled"), x.get("content", ""), x.get("score")
            )
            for x in r.json().get("results", [])
            if x.get("url") and x.get("content")
        ]
