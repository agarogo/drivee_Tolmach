import re
from dataclasses import dataclass
from uuid import UUID

import sqlglot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import expressions as exp

from app.config import get_settings
from app.models import AccessPolicy

settings = get_settings()

FORBIDDEN_SQL = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate|create|grant|revoke|copy|merge|call|execute)\b",
    re.IGNORECASE,
)


class GuardrailError(Exception):
    pass


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    tables: set[str]
    row_limit: int


@dataclass
class GuardrailDecision:
    ok: bool
    sql: str
    message: str
    logs: list[dict]
    validated_sql: ValidatedSQL | None = None


def _log(check_name: str, status: str, severity: str, message: str | dict, details: dict | None = None) -> dict:
    allowed_severities = {"info", "warning", "critical"}
    if severity not in allowed_severities:
        details = message if isinstance(message, dict) else details
        message = severity
        severity = "warning" if status == "warning" else "info"
    if not isinstance(message, str):
        details = message if details is None and isinstance(message, dict) else details
        message = ""
    if details is not None and not isinstance(details, dict):
        details = {"value": details}
    return {
        "check_name": check_name,
        "status": status,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _fail(logs: list[dict], check_name: str, message: str, details: dict | None = None) -> GuardrailDecision:
    logs.append(_log(check_name, "failed", "critical", message, details))
    return GuardrailDecision(ok=False, sql="", message=message, logs=logs)


def _extract_limit(sql: str) -> int | None:
    match = re.search(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


async def _load_policies(db: AsyncSession, role: str, tables: set[str]) -> dict[str, AccessPolicy]:
    result = await db.scalars(
        select(AccessPolicy).where(
            AccessPolicy.role == role,
            AccessPolicy.table_name.in_(tables),
            AccessPolicy.is_active.is_(True),
        )
    )
    return {policy.table_name: policy for policy in result.all()}


async def validate_sql(
    db: AsyncSession,
    sql: str,
    role: str,
    query_id: UUID | None = None,
) -> GuardrailDecision:
    logs: list[dict] = []
    cleaned = sql.strip().rstrip(";")

    if not cleaned:
        return _fail(logs, "non_empty_sql", "SQL пустой.")
    logs.append(_log("non_empty_sql", "passed", "info", "SQL не пустой."))

    if FORBIDDEN_SQL.search(cleaned):
        return _fail(
            logs,
            "keyword_denylist",
            "Запрос заблокирован: разрешены только безопасные SELECT/WITH запросы.",
            {"sql": cleaned},
        )
    logs.append(_log("keyword_denylist", "passed", "info", "Запрещённые write/DDL ключевые слова не найдены."))

    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        return _fail(logs, "readonly_statement", "Запрос заблокирован: SQL должен начинаться с SELECT или WITH.")
    logs.append(_log("readonly_statement", "passed", "info", "Запрос начинается с SELECT/WITH."))

    try:
        statements = sqlglot.parse(cleaned, read="postgres")
    except Exception as exc:
        return _fail(logs, "parse_tree", f"SQL не прошёл проверку синтаксиса: {exc}")
    if len(statements) != 1:
        return _fail(logs, "single_statement", "Запрос заблокирован: несколько SQL-операторов в одном запросе.")
    parsed = statements[0]
    logs.append(_log("parse_tree", "passed", "info", "SQL parse tree построен успешно."))

    table_names = {table.name.lower() for table in parsed.find_all(exp.Table)}
    if not table_names:
        return _fail(logs, "table_presence", "Запрос должен обращаться к аналитическим таблицам.")

    illegal_tables = sorted(table_names - settings.allowed_analytics_tables)
    if illegal_tables:
        return _fail(
            logs,
            "table_whitelist",
            "Запрос обращается к запрещённым таблицам: " + ", ".join(illegal_tables),
            {"tables": sorted(table_names)},
        )
    logs.append(_log("table_whitelist", "passed", "info", "Все таблицы входят в whitelist.", {"tables": sorted(table_names)}))

    policies = await _load_policies(db, role, table_names)
    missing_policies = sorted(table_names - set(policies))
    if missing_policies:
        return _fail(
            logs,
            "access_policy",
            "Нет активной access policy для таблиц: " + ", ".join(missing_policies),
        )
    logs.append(_log("access_policy", "passed", "info", "Ролевые политики найдены."))

    if re.search(r"select\s+\*|,\s*\*", cleaned, flags=re.IGNORECASE):
        return _fail(logs, "select_star", "SELECT * запрещён: выберите конкретные безопасные колонки.")
    logs.append(_log("select_star", "passed", "info", "SELECT * не используется."))

    allowed_columns = set().union(*(set(policy.allowed_columns_json) for policy in policies.values()))
    forbidden_columns = []
    unknown_columns = []
    for column in parsed.find_all(exp.Column):
        name = column.name.lower()
        if name in settings.forbidden_columns:
            forbidden_columns.append(name)
        if name != "*" and allowed_columns and name not in allowed_columns:
            unknown_columns.append(name)
    if forbidden_columns:
        return _fail(
            logs,
            "forbidden_columns",
            "Запрос обращается к запрещённым колонкам: " + ", ".join(sorted(set(forbidden_columns))),
        )
    logs.append(_log("forbidden_columns", "passed", "info", "Чувствительные колонки не используются."))

    # Expressions such as DATE(order_timestamp) are valid, but aliases can confuse parsers.
    safe_aliases = {
        "day",
        "city",
        "revenue",
        "avg_check",
        "orders_count",
        "completed_trips",
        "client_cancellations",
        "driver_cancellations",
        "active_drivers",
        "tender_decline_rate",
    }
    suspicious_unknown = sorted(set(unknown_columns) - safe_aliases)
    if suspicious_unknown:
        logs.append(
            _log(
                "column_whitelist",
                "warning",
                "warning",
                "Некоторые колонки не найдены в policy, но могут быть алиасами выражений.",
                {"columns": suspicious_unknown},
            )
        )
    else:
        logs.append(_log("column_whitelist", "passed", "info", "Колонки соответствуют whitelist."))

    limit = _extract_limit(cleaned)
    max_policy_limit = min(policy.row_limit for policy in policies.values()) if policies else settings.max_result_rows
    row_limit = min(max_policy_limit, settings.max_result_rows)
    if limit is None:
        cleaned = f"{cleaned}\nLIMIT {row_limit}"
        logs.append(_log("limit_injection", "warning", "warning", "Автоматически добавлен LIMIT.", {"limit": row_limit}))
    elif limit > row_limit:
        cleaned = re.sub(r"\blimit\s+\d+\b", f"LIMIT {row_limit}", cleaned, flags=re.IGNORECASE)
        logs.append(_log("limit_cap", "warning", "warning", "LIMIT уменьшен согласно policy.", {"requested": limit, "applied": row_limit}))
    else:
        row_limit = limit
        logs.append(_log("limit_present", "passed", "info", "LIMIT задан явно.", {"limit": limit}))

    if "where" not in cleaned.lower() and row_limit > 500:
        logs.append(
            _log(
                "cost_heuristic",
                "warning",
                "warning",
                "Запрос без WHERE ограничен LIMIT; для тяжёлых срезов рекомендуем период.",
                {"limit": row_limit},
            )
        )
    else:
        logs.append(_log("cost_heuristic", "passed", "info", "Эвристика стоимости в пределах MVP-лимитов."))

    return GuardrailDecision(
        ok=True,
        sql=cleaned,
        message="SQL прошёл guardrails.",
        logs=logs,
        validated_sql=ValidatedSQL(sql=cleaned, tables=table_names, row_limit=row_limit),
    )


def ensure_safe_sql(sql: str) -> tuple[str, list[str]]:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        raise GuardrailError("SQL пустой.")
    if FORBIDDEN_SQL.search(cleaned):
        raise GuardrailError("Запрос заблокирован: разрешены только безопасные SELECT-запросы.")
    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        raise GuardrailError("Запрос заблокирован: разрешены только SELECT-запросы.")
    if not re.search(r"\blimit\b", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned}\nLIMIT {settings.max_result_rows}"
        return cleaned, [f"Автоматически добавлен LIMIT {settings.max_result_rows}."]
    return cleaned, []
