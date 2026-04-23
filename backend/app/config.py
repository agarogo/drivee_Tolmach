from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Толмач"
    database_url: str
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
    otel_exporter_otlp_endpoint: str = ""
    analytics_database_name: str = "drivee_prod"

    @property
    def allowed_analytics_tables(self) -> set[str]:
        return {
            "orders",
            "train",
            "cities",
            "drivers",
            "clients",
            "mart_orders",
            "mart_tenders",
            "mart_city_daily",
            "mart_driver_daily",
            "mart_client_daily",
        }

    @property
    def forbidden_columns(self) -> set[str]:
        return {"password", "password_hash", "credit_card", "ssn"}

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        database_url = value.strip()
        if not database_url:
            raise ValueError("DATABASE_URL must be set")

        lowered = database_url.lower()
        if lowered.startswith("sqlite"):
            raise ValueError("DATABASE_URL must point to PostgreSQL, SQLite is not supported")

        if lowered.startswith("postgres://"):
            return f"postgresql+asyncpg://{database_url.split('://', 1)[1]}"
        if lowered.startswith("postgresql://"):
            return f"postgresql+asyncpg://{database_url.split('://', 1)[1]}"
        if lowered.startswith("postgresql+"):
            return f"postgresql+asyncpg://{database_url.split('://', 1)[1]}"

        raise ValueError("DATABASE_URL must use a PostgreSQL DSN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
