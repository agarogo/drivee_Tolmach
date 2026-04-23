from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Толмач"
    app_env: str = "development"
    database_url: str
    frontend_origin: str = "http://localhost:5173"

    jwt_secret: str = "change-me-in-production"
    jwt_ttl_minutes: int = 60 * 24 * 7

    llm_provider: str = "ollama"
    llm_model: str = "qwen3:4b"
    ollama_base_url: str = "http://localhost:11434"
    production_llm_base_url: str = ""
    production_llm_api_key: str = ""
    production_llm_model: str = ""
    embedding_provider: str = "disabled"
    embedding_model: str = ""
    embedding_timeout_seconds: int = 30
    embedding_max_retries: int = 2
    llm_temperature: float = 0.1
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2
    llm_retry_backoff_ms: int = 250
    llm_prompt_intent_version: str = "v1"
    llm_prompt_clarification_version: str = "v1"
    llm_prompt_plan_version: str = "v1"
    llm_prompt_summary_version: str = "v1"
    retrieval_enable_vectors: bool = True
    retrieval_top_k_terms: int = 8
    retrieval_top_k_templates: int = 4
    retrieval_top_k_examples: int = 4
    retrieval_planner_top_k: int = 12
    retrieval_lexical_candidate_pool: int = 24
    retrieval_vector_candidate_pool: int = 16
    retrieval_term_threshold: float = 0.08
    retrieval_template_threshold: float = 0.06
    retrieval_example_threshold: float = 0.06

    max_result_rows: int = 1000
    query_timeout_ms: int = 5000
    sql_lock_timeout_ms: int = 1000
    sql_idle_in_transaction_timeout_ms: int = 10000
    sql_explain_max_cost: float = 200000
    cache_ttl_seconds: int = 300
    query_cache_enabled: bool = True
    query_cache_ttl_seconds: int = 300
    query_cache_max_rows: int = 500
    query_cache_namespace: str = "v1"
    query_observability_limit: int = 200
    benchmark_default_iterations: int = 7
    benchmark_p95_target_ms: int = 1200
    otel_exporter_otlp_endpoint: str = ""
    analytics_database_name: str = "drivee_prod"
    demo_bootstrap_allow_nonlocal: bool = False

    @property
    def allowed_analytics_tables(self) -> set[str]:
        return {
            "dim.cities",
            "dim.drivers",
            "dim.clients",
            "fact.orders",
            "fact.tenders",
            "mart.city_daily",
            "mart.driver_daily",
            "mart.client_daily",
            "mart.orders_kpi_daily",
        }

    @property
    def forbidden_columns(self) -> set[str]:
        return {"password", "password_hash", "credit_card", "ssn"}

    @property
    def is_production(self) -> bool:
        return self.app_env in {"prod", "production"}

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("APP_ENV must be set")
        return normalized

    @field_validator(
        "llm_provider",
        "embedding_provider",
        "llm_prompt_intent_version",
        "llm_prompt_clarification_version",
        "llm_prompt_plan_version",
        "llm_prompt_summary_version",
    )
    @classmethod
    def normalize_string_setting(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Setting must not be empty")
        return normalized

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
