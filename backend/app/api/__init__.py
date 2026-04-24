from fastapi import APIRouter

from app.query_execution.service import get_query_cache_stats, get_query_execution_summary, list_query_execution_audits
from app.semantic import repository as semantic_repository

from .routes.admin_observability import router as admin_observability_router
from .routes.admin_semantic import router as admin_semantic_router
from .routes.auth import router as auth_router
from .routes.chats import router as chats_router
from .routes.monitoring import router as monitoring_router
from .routes.queries import router as queries_router
from .routes.reports import router as reports_router
from .routes.schedules import router as schedules_router
from .routes.templates import router as templates_router

router = APIRouter()
for child in (
    monitoring_router,
    auth_router,
    queries_router,
    templates_router,
    admin_semantic_router,
    reports_router,
    schedules_router,
    chats_router,
    admin_observability_router,
):
    router.include_router(child)

__all__ = [
    "router",
    "semantic_repository",
    "get_query_cache_stats",
    "get_query_execution_summary",
    "list_query_execution_audits",
]
