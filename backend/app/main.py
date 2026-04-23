import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.services.bootstrap import bootstrap_demo_data
from app.services.observability import setup_observability

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
setup_observability(settings.otel_exporter_otlp_endpoint)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        try:
            await bootstrap_demo_data(db)
            logger.info("demo data is ready")
        except Exception:
            logger.exception("demo data bootstrap failed")
            await db.rollback()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Self-service AI-аналитика: чат, Text-to-SQL, guardrails, админ-логи.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"message": "Толмач работает", "docs": "/docs"}
