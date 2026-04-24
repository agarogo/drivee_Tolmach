from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _normalize_postgres_dsn(value: str, field_name: str) -> str:
    dsn = value.strip()
    if not dsn:
        raise ValueError(f"{field_name} must be set")

    lowered = dsn.lower()
    if lowered.startswith("sqlite"):
        raise ValueError(f"{field_name} must point to PostgreSQL, SQLite is not supported")

    if lowered.startswith("postgres://"):
        return f"postgresql+asyncpg://{dsn.split('://', 1)[1]}"
    if lowered.startswith("postgresql://"):
        return f"postgresql+asyncpg://{dsn.split('://', 1)[1]}"
    if lowered.startswith("postgresql+"):
        return f"postgresql+asyncpg://{dsn.split('://', 1)[1]}"

    raise ValueError(f"{field_name} must use a PostgreSQL DSN")


def _database_name_from_dsn(dsn: str) -> str:
    parsed = urlparse(dsn.replace("+asyncpg", ""))
    return (parsed.path or "/").lstrip("/") or "unknown"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Tolmach"
    app_env: str = "development"

    platform_database_url: str = ""
    analytics_database_url: str = ""

    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    session_ttl_hours: int = 24 * 7
    session_cookie_name: str = "tolmach_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    csrf_cookie_name: str = "tolmach_csrf"
    csrf_header_name: str = "X-CSRF-Token"

    llm_provider: str = "ollama"
    llm_model: str = "qwen3:4b"
    llm_strict_mode: bool = False
    llm_rule_fallback_enabled: bool = True
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
    llm_prompt_classifier_version: str = "v1"
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
    scheduler_enabled: bool = True
    scheduler_poll_interval_seconds: int = 15
    scheduler_batch_size: int = 10
    scheduler_max_concurrent_runs: int = 2
    scheduler_default_max_retries: int = 2
    scheduler_default_retry_backoff_seconds: int = 300
    worker_heartbeat_ttl_seconds: int = 60
    report_artifact_dir: str = "/tmp/tolmach-report-artifacts"
    report_result_snapshot_limit: int = 200
    report_email_adapter: str = "smtp"
    report_email_from: str = "reports@tolmach.local"
    report_smtp_host: str = ""
    report_smtp_port: int = 587
    report_smtp_username: str = ""
    report_smtp_password: str = ""
    report_smtp_use_tls: bool = True
    report_smtp_use_ssl: bool = False
    report_slack_adapter: str = "webhook"
    report_slack_webhook_url: str = ""
    report_delivery_timeout_seconds: int = 20
    otel_exporter_otlp_endpoint: str = ""
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

    @property
    def is_demo(self) -> bool:
        return self.app_env == "demo"

    @property
    def frontend_origin(self) -> str:
        return self.frontend_origins[0]

    @property
    def session_cookie_secure_effective(self) -> bool:
        return self.session_cookie_secure or self.is_production

    @property
    def scheduler_worker_stale_after_seconds(self) -> int:
        return max(self.worker_heartbeat_ttl_seconds, self.scheduler_poll_interval_seconds * 3)

    @property
    def platform_database_label(self) -> str:
        return _database_name_from_dsn(self.platform_database_url)

    @property
    def analytics_database_label(self) -> str:
        return _database_name_from_dsn(self.analytics_database_url)

    @property
    def llm_fallback_allowed(self) -> bool:
        if self.llm_strict_mode or not self.llm_rule_fallback_enabled:
            return False
        if self.is_production or self.is_demo:
            return False
        if self.llm_provider == "production":
            return False
        return True

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
        "llm_prompt_classifier_version",
        "llm_prompt_intent_version",
        "llm_prompt_clarification_version",
        "llm_prompt_plan_version",
        "llm_prompt_summary_version",
        "session_cookie_samesite",
    )
    @classmethod
    def normalize_string_setting(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Setting must not be empty")
        return normalized

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_frontend_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            items = ["http://localhost:5173"]
        elif isinstance(value, list):
            items = value
        elif isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                items = json.loads(raw)
            else:
                items = [item.strip() for item in raw.split(",")]
        else:
            raise ValueError("FRONTEND_ORIGINS must be a list or comma-separated string")

        normalized: list[str] = []
        for item in items:
            origin = str(item).strip().rstrip("/")
            if not origin:
                continue
            if origin == "*":
                raise ValueError("FRONTEND_ORIGINS must not contain '*'")
            if not origin.startswith(("http://", "https://")):
                raise ValueError("Each FRONTEND_ORIGINS entry must be an explicit http/https origin")
            normalized.append(origin)

        if not normalized:
            raise ValueError("FRONTEND_ORIGINS must contain at least one explicit origin")
        return normalized

    @field_validator("csrf_header_name")
    @classmethod
    def normalize_csrf_header_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("CSRF_HEADER_NAME must not be empty")
        return normalized

    @model_validator(mode="after")
    def normalize_database_urls(self) -> "Settings":
        platform_dsn = self.platform_database_url.strip()
        analytics_dsn = self.analytics_database_url.strip() or platform_dsn

        self.platform_database_url = _normalize_postgres_dsn(platform_dsn, "PLATFORM_DATABASE_URL")
        self.analytics_database_url = _normalize_postgres_dsn(analytics_dsn, "ANALYTICS_DATABASE_URL")

        if self.session_cookie_samesite not in {"lax", "strict", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be one of: lax, strict, none")
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure_effective:
            raise ValueError("SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true")
        if self.llm_provider in {"fallback", "fallback_rule"} and not self.llm_fallback_allowed:
            raise ValueError(
                "LLM_PROVIDER=fallback is disabled when APP_ENV is demo/production or LLM_STRICT_MODE=true"
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
