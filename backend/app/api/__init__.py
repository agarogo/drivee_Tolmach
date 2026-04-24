from __future__ import annotations

from fastapi import APIRouter

from .routes import admin, admin_semantic, auth, chats, health, queries, reports, schedules, templates

_ROUTE_MODULES = (
    health,
    auth,
    queries,
    templates,
    admin_semantic,
    reports,
    schedules,
    chats,
    admin,
)


def _include_modules(target: APIRouter, *, include_in_schema: bool = True) -> None:
    for route_module in _ROUTE_MODULES:
        target.include_router(route_module.router, include_in_schema=include_in_schema)


router = APIRouter()

# Canonical API shown in Swagger/OpenAPI.
v1_router = APIRouter(prefix="/api/v1")
_include_modules(v1_router, include_in_schema=True)
router.include_router(v1_router)

# Backward-compatible endpoints used by the current frontend and older demos.
legacy_router = APIRouter()
_include_modules(legacy_router, include_in_schema=False)
router.include_router(legacy_router)

api_compat_router = APIRouter(prefix="/api")
_include_modules(api_compat_router, include_in_schema=False)
router.include_router(api_compat_router)

__all__ = ["router", "v1_router"]
