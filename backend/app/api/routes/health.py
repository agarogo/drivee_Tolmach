from app.api.common import *


router = APIRouter(tags=["System"])


@router.get("/health")
@router.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": "Толмач by Drivee",
        "database": "postgresql",
        "platform_database_name": settings.platform_database_label,
        "analytics_database_name": settings.analytics_database_label,
        "mode": "read-only analytics executor",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_strict_mode": settings.llm_strict_mode,
        "llm_rule_fallback_allowed": settings.llm_fallback_allowed,
    }


@router.get("/metrics")
async def metrics() -> dict:
    return {"status": "ok", "service": "tolmach", "otel": "optional", "queries_endpoint": "/queries/run"}


@router.get("/traces-link")
async def traces_link() -> dict:
    return {
        "phoenix_url": "http://localhost:6006",
        "otel_endpoint_env": "OTEL_EXPORTER_OTLP_ENDPOINT",
        "note": "OpenTelemetry/Phoenix can subscribe to query_events; UI Trace Panel reads persisted events.",
    }
