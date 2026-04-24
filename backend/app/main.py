import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.llm_runtime import build_health_payload
from app.services.observability import setup_observability

settings = get_settings()
logging.basicConfig(level=logging.INFO)
setup_observability(settings.otel_exporter_otlp_endpoint)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Self-service AI-аналитика: чат, Text-to-SQL, guardrails, админ-логи.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", settings.csrf_header_name],
)


@app.get("/health")
@app.get("/api/health")
async def lightweight_health() -> dict:
    return await build_health_payload(app_name=settings.app_name)


from app.api import router  # noqa: E402  # Imported after lightweight health routes are registered.

app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"message": "Толмач работает", "docs": "/docs"}
