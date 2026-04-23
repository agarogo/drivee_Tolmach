from sqlalchemy import text

from app.config import get_settings
from app.db import async_engine
from app.services.charts import serialize_rows
from app.services.guardrails import GuardrailError, ValidatedSQL

settings = get_settings()


async def execute_validated_select(validated_sql: ValidatedSQL) -> list[dict]:
    async with async_engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL statement_timeout = {settings.query_timeout_ms};"))
        result = await conn.execute(text(validated_sql.sql))
        rows = [dict(row._mapping) for row in result.fetchall()]
    return serialize_rows(rows)


async def run_sql(sql: str) -> list[dict]:
    raise GuardrailError(
        "Unsafe direct SQL execution is disabled. Use validate_sql(...) and execute_validated_select(...)."
    )
