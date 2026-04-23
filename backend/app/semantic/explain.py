from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db import async_engine

settings = get_settings()


@dataclass(frozen=True)
class ExplainCostCheckResult:
    plan: dict[str, Any]
    total_cost: float


async def run_explain_cost_check(sql: str) -> ExplainCostCheckResult:
    async with async_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text(f"SET LOCAL statement_timeout = {settings.query_timeout_ms}"))
            await conn.execute(text(f"SET LOCAL lock_timeout = {settings.sql_lock_timeout_ms}"))
            await conn.execute(
                text(
                    f"SET LOCAL idle_in_transaction_session_timeout = {settings.sql_idle_in_transaction_timeout_ms}"
                )
            )
            result = await conn.execute(text(f"EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE) {sql}"))
            payload = result.scalar_one()

    if isinstance(payload, list) and payload:
        plan_root = payload[0]
    elif isinstance(payload, dict):
        plan_root = payload
    else:
        raise RuntimeError("EXPLAIN returned an unexpected payload.")
    top_plan = plan_root.get("Plan", {})
    total_cost = float(top_plan.get("Total Cost", 0) or 0)
    return ExplainCostCheckResult(plan=plan_root, total_cost=total_cost)
