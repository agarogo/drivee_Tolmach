from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.api.exception_handlers import register_exception_handlers
from app.api.middleware.request_id import RequestIDMiddleware
from app.config import get_settings
from app.services.observability import setup_logging, setup_observability

settings = get_settings()
setup_logging(settings.json_logs)
setup_observability(settings.otel_exporter_otlp_endpoint)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    description=(
        "Self-service AI-аналитика: чат, Text-to-SQL, guardrails, "
        "семантический слой, отчёты и расписания. Каноничный API: /api/v1."
    ),
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", settings.csrf_header_name, "X-Request-ID"],
)
register_exception_handlers(app)

app.include_router(router)


@app.get("/", tags=["System"])
def root() -> dict:
    return {"message": "Толмач работает", "docs": "/docs", "api": "/api/v1"}
