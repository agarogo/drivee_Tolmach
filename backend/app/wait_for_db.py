from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


logger = logging.getLogger(__name__)


async def _wait_for_single_database(label: str, database_url: str, max_attempts: int) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("select 1"))
                logger.info("%s database connection is ready", label)
                return
            except Exception as exc:
                if attempt == max_attempts:
                    logger.exception("%s database connection failed after %s attempts", label, max_attempts)
                    raise
                logger.warning("%s database is not ready yet (%s/%s): %s", label, attempt, max_attempts, exc)
                await asyncio.sleep(min(5, attempt))
    finally:
        await engine.dispose()


async def wait_for_database(max_attempts: int = 60) -> None:
    settings = get_settings()
    seen: set[str] = set()
    for label, database_url in (
        ("platform", settings.platform_database_url),
        ("analytics", settings.analytics_database_url),
    ):
        if database_url in seen:
            logger.info("%s database uses the same DSN as a previously checked engine; skipping duplicate probe", label)
            continue
        seen.add(database_url)
        await _wait_for_single_database(label, database_url, max_attempts)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(wait_for_database())


if __name__ == "__main__":
    main()
