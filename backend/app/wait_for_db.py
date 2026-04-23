import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


logger = logging.getLogger(__name__)


async def wait_for_database(max_attempts: int = 60) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("select 1"))
                logger.info("database connection is ready")
                return
            except Exception as exc:
                if attempt == max_attempts:
                    logger.exception("database connection failed after %s attempts", max_attempts)
                    raise
                logger.warning("database is not ready yet (%s/%s): %s", attempt, max_attempts, exc)
                await asyncio.sleep(min(5, attempt))
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(wait_for_database())


if __name__ == "__main__":
    main()
