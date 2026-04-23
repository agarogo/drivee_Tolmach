from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.semantic.compiler import CompiledSemanticQuery
from app.semantic.sql_validator import (
    FORBIDDEN_SQL,
    GuardrailDecision,
    GuardrailError,
    ValidatedSQL,
    _load_policies as _validator_load_policies,
    _log as _validator_log,
    _run_explain_plan as _validator_run_explain_plan,
    _table_identifier as _validator_table_identifier,
    ensure_safe_sql,
)
from app.semantic.sql_validator import validate_sql as _validate_sql


def _log(check_name: str, status: str, severity: str, message: str, details: dict | None = None) -> dict[str, Any]:
    return _validator_log(check_name, status, severity, message, details=details)


async def _load_policies(db: AsyncSession, role: str, tables: set[str]):
    return await _validator_load_policies(db, role, tables)


async def _run_explain_plan(sql: str):
    return await _validator_run_explain_plan(sql)


def _table_identifier(table) -> str:
    return _validator_table_identifier(table)


async def validate_sql(
    db: AsyncSession,
    sql: str,
    role: str,
    query_id: UUID | None = None,
    *,
    compiled_query: CompiledSemanticQuery | None = None,
) -> GuardrailDecision:
    return await _validate_sql(
        db,
        sql,
        role,
        query_id,
        compiled_query=compiled_query,
        policy_loader=_load_policies,
        explain_runner=_run_explain_plan,
    )


__all__ = [
    "FORBIDDEN_SQL",
    "GuardrailDecision",
    "GuardrailError",
    "ValidatedSQL",
    "_load_policies",
    "_log",
    "_run_explain_plan",
    "_table_identifier",
    "ensure_safe_sql",
    "validate_sql",
]
