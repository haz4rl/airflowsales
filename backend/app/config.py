from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the repo root so uvicorn works from any CWD.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Airflow Sales"
    API_V1_STR: str = "/v1"
    DATABASE_URL: str | None = None
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "airflow_sales"
    TAVILY_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # Token cost accounting. Defaults follow Groq's published per-million-token
    # pricing for the configured model; override via env if pricing changes.
    # Cost is estimated from reported token usage, never invented.
    GROQ_PRICE_PER_M_INPUT_TOKENS: float = 0.15
    GROQ_PRICE_PER_M_OUTPUT_TOKENS: float = 0.66
    SEARCH_TIMEOUT_SECONDS: float = 15.0
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_TOKENS: int = 2048
    # One-shot escalation budget for token-exhausted json_validate_failed 400s.
    LLM_MAX_TOKENS_ESCALATED: int = 4096
    MAX_RETRIES: int = 2
    RETRY_BASE_DELAY_SECONDS: float = 0.5
    RETRY_MAX_DELAY_SECONDS: float = 8.0
    # Bounded critic-driven revision of outreach drafts (see run_sales_intelligence).
    OUTREACH_MAX_REVISIONS: int = 2
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD, safe="")
        return (
            f"postgresql://{user}:{password}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

    model_config = SettingsConfigDict(case_sensitive=True, env_file=str(_ENV_FILE), extra="ignore")


settings = Settings()
