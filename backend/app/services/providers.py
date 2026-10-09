from backend.app.tools.company_search import SearchProvider, TavilySearchProvider
from backend.app.tools.llm import GroqProvider, LLMProvider


def get_search_provider() -> SearchProvider:
    return TavilySearchProvider()


def get_llm_provider() -> LLMProvider:
    return GroqProvider()
