from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# One project, one PostgreSQL URL.  Platform tables, semantic catalog, marts,
# reports, scheduler and analytics facts live in the same database/schemas.
database_engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(
    bind=database_engine,
    autoflush=False,
    expire_on_commit=False,
)

# Backward-compatible aliases for modules that still import the old split names.
# They intentionally point to the same engine/session and must not be configured
# independently anymore.
platform_engine = database_engine
analytics_engine = database_engine
PlatformSessionLocal = SessionLocal
AnalyticsSessionLocal = SessionLocal


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db:
        yield db
