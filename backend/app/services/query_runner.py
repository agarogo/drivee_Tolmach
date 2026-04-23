from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.query_execution.service import QueryExecutionResult, execute_safe_query
from app.services.guardrails import GuardrailError, ValidatedSQL


async def execute_validated_query(
    validated_sql: ValidatedSQL,
    *,
    role: str,
    db: AsyncSession | None = None,
    query_id=None,
    use_cache: bool = True,
) -> QueryExecutionResult:
    return await execute_safe_query(
        validated_sql,
        role=role,
        db=db,
        query_id=query_id,
        use_cache=use_cache,
    )


async def execute_validated_select(
    validated_sql: ValidatedSQL,
    *,
    role: str = "user",
    db: AsyncSession | None = None,
    query_id=None,
    use_cache: bool = True,
) -> list[dict]:
    result = await execute_validated_query(
        validated_sql,
        role=role,
        db=db,
        query_id=query_id,
        use_cache=use_cache,
    )
    return result.rows


async def run_sql(sql: str) -> list[dict]:
    raise GuardrailError(
        "Unsafe direct SQL execution is disabled. Use validate_sql(...) and execute_validated_select(...)."
    )
