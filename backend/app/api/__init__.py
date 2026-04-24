from fastapi import APIRouter

from .routes import admin, admin_semantic, auth, chats, health, queries, reports, schedules, templates


router = APIRouter()

for route_module in (
    health,
    auth,
    queries,
    templates,
    admin_semantic,
    reports,
    schedules,
    chats,
    admin,
):
    router.include_router(route_module.router)


__all__ = ["router"]
