from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import UUID

import sqlglot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import expressions as exp

from app.config import get_settings
from app.models import AccessPolicy
from app.semantic.compiler import CompiledSemanticQuery
from app.semantic.errors import SemanticErrorCode, build_block_reason
from app.semantic.explain import run_explain_cost_check

settings = get_settings()

FORBIDDEN_SQL = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate|create|grant|revoke|copy|merge|call|execute)\b",
    re.IGNORECASE,
)


class GuardrailError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    tables: set[str]
    row_limit: int
    explain_plan: dict[str, Any]
    explain_cost: float
    ast_json: dict[str, Any] = field(default_factory=dict)
    validator_summary: dict[str, Any] = field(default_factory=dict)
    column_references: list[dict[str, str]] = field(default_factory=list)


@dataclass
class GuardrailDecision:
    ok: bool
    sql: str
    message: str
    logs: list[dict[str, Any]]
    block_reasons: list[dict[str, Any]] = field(default_factory=list)
    validated_sql: ValidatedSQL | None = None


def _serialize_ast(expression: exp.Expression) -> dict[str, Any]:
    if hasattr(expression, "dump"):
        dumped = expression.dump()
        if isinstance(dumped, dict):
            return dumped
        return {"dump": dumped}
    try:
        return {"sql": expression.sql(dialect="postgres"), "repr": repr(expression)}
    except TypeError:
        return {"sql": expression.sql(), "repr": repr(expression)}


def _log(
    check_name: str,
    status: str,
    severity: str,
    message: str,
    *,
    code: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_code = code.value if isinstance(code, SemanticErrorCode) else str(code)
    return {
        "check_name": check_name,
        "status": status,
        "severity": severity,
        "code": normalized_code,
        "message": message,
        "details": details or {},
    }


def _fail(
    logs: list[dict[str, Any]],
    check_name: str,
    code: SemanticErrorCode | str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> GuardrailDecision:
    reason = build_block_reason(code, message, details=details)
    logs.append(
        _log(
            check_name,
            "failed",
            "critical",
            message,
            code=reason.code,
            details=reason.details,
        )
    )
    return GuardrailDecision(
        ok=False,
        sql="",
        message=message,
        logs=logs,
        block_reasons=[reason.as_dict()],
    )


def _extract_limit(sql: str) -> int | None:
    match = re.search(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _apply_limit(sql: str, row_limit: int) -> str:
    if _extract_limit(sql) is None:
        return f"{sql}\nLIMIT {row_limit}"
    return re.sub(r"\blimit\s+\d+\b", f"LIMIT {row_limit}", sql, flags=re.IGNORECASE)


def _table_identifier(table: exp.Table) -> str:
    schema = str(table.db or "").strip().lower()
    name = str(table.name or "").strip().lower()
    return f"{schema}.{name}" if schema else name


def _table_alias_name(table: exp.Table) -> str:
    alias_or_name = getattr(table, "alias_or_name", "")
    if alias_or_name:
        return str(alias_or_name).strip().lower()
    alias = getattr(table, "alias", None)
    alias_value = getattr(getattr(alias, "this", None), "name", "") or getattr(alias, "this", None)
    if alias_value:
        return str(alias_value).strip().lower()
    return str(table.name or "").strip().lower()


def _output_aliases(parsed: exp.Expression) -> set[str]:
    aliases: set[str] = set()
    select_items = getattr(parsed, "expressions", []) or []
    for item in select_items:
        if isinstance(item, exp.Alias):
            aliases.add(item.alias.lower())
    return aliases


def _alias_map(parsed: exp.Expression) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for table in parsed.find_all(exp.Table):
        table_id = _table_identifier(table)
        alias = _table_alias_name(table)
        if alias:
            mapping[alias] = table_id
        table_name = str(table.name or "").strip().lower()
        if table_name:
            mapping[table_name] = table_id
    return mapping


def _collect_column_references(parsed: exp.Expression) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for column in parsed.find_all(exp.Column):
        references.append(
            {
                "table_alias": str(column.table or "").strip().lower(),
                "column_name": column.name.lower(),
            }
        )
    return references


async def _load_policies(db: AsyncSession, role: str, tables: set[str]) -> dict[str, AccessPolicy]:
    result = await db.scalars(
        select(AccessPolicy).where(
            AccessPolicy.role == role,
            AccessPolicy.table_name.in_(tables),
            AccessPolicy.is_active.is_(True),
        )
    )
    return {policy.table_name: policy for policy in result.all()}


async def _run_explain_plan(sql: str) -> tuple[dict[str, Any], float]:
    result = await run_explain_cost_check(sql)
    return result.plan, result.total_cost


async def validate_sql(
    db: AsyncSession,
    sql: str,
    role: str,
    query_id: UUID | None = None,
    *,
    compiled_query: CompiledSemanticQuery | None = None,
    policy_loader: Callable[[AsyncSession, str, set[str]], Awaitable[dict[str, AccessPolicy]]] | None = None,
    explain_runner: Callable[[str], Awaitable[tuple[dict[str, Any], float]]] | None = None,
) -> GuardrailDecision:
    del query_id
    logs: list[dict[str, Any]] = []
    cleaned = sql.strip().rstrip(";")
    policy_loader = policy_loader or _load_policies
    explain_runner = explain_runner or _run_explain_plan

    if not cleaned:
        return _fail(logs, "non_empty_sql", SemanticErrorCode.SQL_PARSE_ERROR, "SQL is empty.")
    logs.append(_log("non_empty_sql", "passed", "info", "SQL is not empty."))

    if FORBIDDEN_SQL.search(cleaned):
        return _fail(
            logs,
            "keyword_denylist",
            SemanticErrorCode.WRITE_OPERATION,
            "Request blocked: only read-only SELECT/WITH queries are allowed.",
            details={"sql": cleaned},
        )
    logs.append(_log("keyword_denylist", "passed", "info", "No write/DDL keywords found."))

    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        return _fail(
            logs,
            "readonly_statement",
            SemanticErrorCode.NON_READONLY_STATEMENT,
            "Request blocked: SQL must begin with SELECT or WITH.",
        )
    logs.append(_log("readonly_statement", "passed", "info", "SQL starts with SELECT/WITH."))

    try:
        statements = sqlglot.parse(cleaned, read="postgres")
    except Exception as exc:
        return _fail(
            logs,
            "parse_tree",
            SemanticErrorCode.SQL_PARSE_ERROR,
            f"SQL failed syntax validation: {exc}",
        )
    if len(statements) != 1:
        return _fail(
            logs,
            "single_statement",
            SemanticErrorCode.MULTI_STATEMENT,
            "Request blocked: multiple SQL statements are not allowed.",
        )
    parsed = statements[0]
    logs.append(_log("parse_tree", "passed", "info", "SQL parse tree built successfully."))

    if any(True for _ in parsed.find_all(exp.Star)):
        return _fail(
            logs,
            "select_star",
            SemanticErrorCode.SELECT_STAR,
            "SELECT * is forbidden. Use explicit approved columns only.",
        )
    logs.append(_log("select_star", "passed", "info", "SELECT * is not used."))

    table_names = {_table_identifier(table) for table in parsed.find_all(exp.Table)}
    if not table_names:
        return _fail(
            logs,
            "table_presence",
            SemanticErrorCode.UNKNOWN_TABLE,
            "Query must target approved analytics tables.",
        )

    illegal_tables = sorted(table_names - settings.allowed_analytics_tables)
    if illegal_tables:
        return _fail(
            logs,
            "table_whitelist",
            SemanticErrorCode.UNKNOWN_TABLE,
            "Request references forbidden tables: " + ", ".join(illegal_tables),
            details={"tables": sorted(table_names)},
        )
    logs.append(
        _log(
            "table_whitelist",
            "passed",
            "info",
            "All referenced tables are in the approved analytics whitelist.",
            details={"tables": sorted(table_names)},
        )
    )

    policies = await policy_loader(db, role, table_names)
    missing_policies = sorted(table_names - set(policies))
    if missing_policies:
        return _fail(
            logs,
            "access_policy",
            SemanticErrorCode.ACCESS_POLICY_MISSING,
            "No active access policy for tables: " + ", ".join(missing_policies),
            details={"tables": missing_policies, "role": role},
        )
    logs.append(
        _log(
            "access_policy",
            "passed",
            "info",
            "Role-based access policies were found for all referenced tables.",
            details={"role": role},
        )
    )

    alias_map = _alias_map(parsed)
    output_aliases = _output_aliases(parsed)
    allowed_columns_by_table = {
        table_name: {column.lower() for column in policy.allowed_columns_json}
        for table_name, policy in policies.items()
    }
    column_references = compiled_query.column_references if compiled_query is not None else _collect_column_references(parsed)
    unknown_columns: list[dict[str, str]] = []
    forbidden_columns: list[str] = []
    for column in column_references:
        column_name = column.get("column_name", "").lower()
        if not column_name or column_name in output_aliases:
            continue
        if column_name in settings.forbidden_columns:
            forbidden_columns.append(column_name)
            continue
        table_alias = column.get("table_alias", "").lower()
        resolved_table = alias_map.get(table_alias, "")
        if not resolved_table:
            if len(table_names) == 1:
                resolved_table = next(iter(table_names))
            else:
                unknown_columns.append({"table_alias": table_alias, "column_name": column_name})
                continue
        allowed_columns = allowed_columns_by_table.get(resolved_table, set())
        if allowed_columns and column_name not in allowed_columns:
            unknown_columns.append({"table_alias": table_alias, "column_name": column_name, "table_name": resolved_table})

    if forbidden_columns:
        return _fail(
            logs,
            "forbidden_columns",
            SemanticErrorCode.FORBIDDEN_COLUMN,
            "Request references forbidden columns: " + ", ".join(sorted(set(forbidden_columns))),
            details={"columns": sorted(set(forbidden_columns))},
        )
    logs.append(_log("forbidden_columns", "passed", "info", "No sensitive columns are referenced."))

    if unknown_columns:
        return _fail(
            logs,
            "column_whitelist",
            SemanticErrorCode.UNKNOWN_COLUMN,
            "Request references columns outside approved access policies.",
            details={"columns": unknown_columns},
        )
    logs.append(_log("column_whitelist", "passed", "info", "All column references are approved by policy."))

    max_policy_limit = min(policy.row_limit for policy in policies.values()) if policies else settings.max_result_rows
    row_limit = min(max_policy_limit, settings.max_result_rows)
    requested_limit = _extract_limit(cleaned)
    if requested_limit is None:
        cleaned = _apply_limit(cleaned, row_limit)
        logs.append(
            _log(
                "limit_injection",
                "warning",
                "warning",
                "LIMIT was injected automatically.",
                code=SemanticErrorCode.LIMIT_INJECTED,
                details={"applied_limit": row_limit},
            )
        )
    elif requested_limit > row_limit:
        cleaned = _apply_limit(cleaned, row_limit)
        logs.append(
            _log(
                "limit_cap",
                "warning",
                "warning",
                "LIMIT was capped by policy.",
                code=SemanticErrorCode.LIMIT_CAPPED,
                details={"requested_limit": requested_limit, "applied_limit": row_limit},
            )
        )
    else:
        row_limit = requested_limit
        logs.append(
            _log(
                "limit_present",
                "passed",
                "info",
                "LIMIT is present and within policy.",
                details={"limit": requested_limit},
            )
        )

    try:
        reparsed = sqlglot.parse_one(cleaned, read="postgres")
    except Exception as exc:
        return _fail(
            logs,
            "post_limit_parse_tree",
            SemanticErrorCode.SQL_PARSE_ERROR,
            f"SQL failed validation after LIMIT normalization: {exc}",
            details={"sql": cleaned},
        )
    logs.append(_log("post_limit_parse_tree", "passed", "info", "SQL remains valid after LIMIT normalization."))

    try:
        explain_plan, explain_cost = await explain_runner(cleaned)
    except Exception as exc:
        return _fail(
            logs,
            "explain_plan",
            SemanticErrorCode.EXPLAIN_FAILED,
            f"Query did not pass EXPLAIN preflight: {exc}",
        )
    if explain_cost > settings.sql_explain_max_cost:
        return _fail(
            logs,
            "explain_cost",
            SemanticErrorCode.EXPLAIN_COST_EXCEEDED,
            "Request blocked: estimated plan cost exceeds the safety threshold.",
            details={"estimated_cost": explain_cost, "max_allowed_cost": settings.sql_explain_max_cost},
        )
    logs.append(
        _log(
            "explain_cost",
            "passed",
            "info",
            "Explain-cost check passed.",
            details={"estimated_cost": explain_cost, "max_allowed_cost": settings.sql_explain_max_cost},
        )
    )

    validated_sql = ValidatedSQL(
        sql=cleaned,
        tables=table_names,
        row_limit=row_limit,
        explain_plan=explain_plan,
        explain_cost=explain_cost,
        ast_json=_serialize_ast(reparsed),
        validator_summary={
            "role": role,
            "tables": sorted(table_names),
            "row_limit": row_limit,
            "logs": logs,
        },
        column_references=_collect_column_references(reparsed),
    )
    return GuardrailDecision(
        ok=True,
        sql=cleaned,
        message="SQL passed guardrails.",
        logs=logs,
        validated_sql=validated_sql,
    )


def ensure_safe_sql(sql: str) -> tuple[str, list[str]]:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        raise GuardrailError("SQL is empty.")
    if FORBIDDEN_SQL.search(cleaned):
        raise GuardrailError("Request blocked: only safe read-only SELECT queries are allowed.")
    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        raise GuardrailError("Request blocked: only read-only SELECT queries are allowed.")
    notes: list[str] = []
    if _extract_limit(cleaned) is None:
        cleaned = _apply_limit(cleaned, settings.max_result_rows)
        notes.append(f"Automatically added LIMIT {settings.max_result_rows}.")
    return cleaned, notes
