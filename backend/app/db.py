from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

platform_engine: AsyncEngine = create_async_engine(settings.platform_database_url, pool_pre_ping=True)
analytics_engine: AsyncEngine = create_async_engine(settings.analytics_database_url, pool_pre_ping=True)

PlatformSessionLocal = async_sessionmaker(
    bind=platform_engine,
    autoflush=False,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with PlatformSessionLocal() as db:
        yield db
