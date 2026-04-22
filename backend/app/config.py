from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Толмач"
    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@db:5432/tolmach"
    )
    frontend_origin: str = "http://localhost:5173"

    jwt_secret: str = "change-me-in-production"
    jwt_ttl_minutes: int = 60 * 24 * 7

    llm_provider: str = "ollama"
    llm_model: str = "qwen3:4b"
    ollama_base_url: str = "http://localhost:11434"
    llm_temperature: float = 0.1
    llm_timeout_seconds: int = 60

    max_result_rows: int = 1000
    query_timeout_ms: int = 5000
    cache_ttl_seconds: int = 300

    @property
    def allowed_analytics_tables(self) -> set[str]:
        return {"orders", "cancellations", "cities"}

    @property
    def forbidden_columns(self) -> set[str]:
        return {"password", "password_hash", "credit_card", "ssn"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
