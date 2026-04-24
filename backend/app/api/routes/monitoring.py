from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
@router.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": "Толмач by Drivee",
        "database": "postgresql",
        "database_name": settings.analytics_database_name,
        "mode": "read-only analytics executor",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
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
