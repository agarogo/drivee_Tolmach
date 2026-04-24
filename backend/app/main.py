import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import get_settings
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

app.include_router(router)


@app.get("/", tags=["System"])
def root() -> dict:
    return {"message": "Толмач работает", "docs": "/docs"}
