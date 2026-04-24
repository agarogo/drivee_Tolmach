from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


logger = logging.getLogger(__name__)
_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,62}$")


def _split_database_url(database_url: str) -> tuple[str, str]:
    """Return (maintenance_database_url, target_database_name).

    Docker named volumes can survive from older failed runs where the default
    database was not created.  Connecting directly to /tolmach then fails with
    `database does not exist`.  We first connect to the maintenance `postgres`
    database and create the target DB when it is missing.
    """
    parsed = urlsplit(database_url)
    db_name = (parsed.path or "/").lstrip("/") or "postgres"
    if not _DB_NAME_RE.match(db_name):
        raise ValueError(f"Unsafe PostgreSQL database name in DATABASE_URL: {db_name!r}")
    maintenance = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment))
    return maintenance, db_name


def _quote_ident(identifier: str) -> str:
    if not _DB_NAME_RE.match(identifier):
        raise ValueError(f"Unsafe PostgreSQL identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


async def _ensure_database_exists(database_url: str, max_attempts: int) -> None:
    maintenance_url, db_name = _split_database_url(database_url)
    if db_name == "postgres":
        return

    engine = create_async_engine(maintenance_url, pool_pre_ping=True, isolation_level="AUTOCOMMIT")
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                async with engine.connect() as connection:
                    exists = await connection.scalar(
                        text("select 1 from pg_database where datname = :name"),
                        {"name": db_name},
                    )
                    if not exists:
                        logger.warning("database %s is missing; creating it", db_name)
                        await connection.execute(text(f"create database {_quote_ident(db_name)}"))
                    return
            except Exception as exc:
                if attempt == max_attempts:
                    logger.exception("could not ensure database %s exists after %s attempts", db_name, max_attempts)
                    raise
                logger.warning("maintenance database is not ready yet (%s/%s): %s", attempt, max_attempts, exc)
                await asyncio.sleep(min(5, attempt))
    finally:
        await engine.dispose()


async def _wait_for_single_database(label: str, database_url: str, max_attempts: int) -> None:
    await _ensure_database_exists(database_url, max_attempts=max_attempts)
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
    await _wait_for_single_database("database", settings.database_url, max_attempts)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(wait_for_database())


if __name__ == "__main__":
    main()
