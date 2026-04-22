import re

import sqlglot
from sqlglot import expressions as exp

from app.config import get_settings

settings = get_settings()

FORBIDDEN_SQL = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate|create|grant|revoke|copy|merge|call)\b",
    re.IGNORECASE,
)


class GuardrailError(Exception):
    pass


def ensure_safe_sql(sql: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    cleaned = sql.strip().rstrip(";")

    if not cleaned:
        raise GuardrailError("SQL пустой.")

    if FORBIDDEN_SQL.search(cleaned):
        raise GuardrailError("Запрос заблокирован: разрешены только безопасные SELECT-запросы.")

    try:
        statements = sqlglot.parse(cleaned, read="postgres")
    except Exception as exc:
        raise GuardrailError(f"SQL не прошёл проверку синтаксиса: {exc}") from exc

    if len(statements) != 1:
        raise GuardrailError("Запрос заблокирован: несколько SQL-операторов в одном запросе.")

    parsed = statements[0]
    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        raise GuardrailError("Запрос заблокирован: разрешены только SELECT-запросы.")

    table_names = {table.name.lower() for table in parsed.find_all(exp.Table)}
    if not table_names:
        raise GuardrailError("Запрос должен обращаться к аналитическим таблицам.")

    illegal_tables = sorted(table_names - settings.allowed_analytics_tables)
    if illegal_tables:
        raise GuardrailError(
            "Запрос обращается к запрещённым таблицам: " + ", ".join(illegal_tables)
        )

    forbidden_columns = [
        col.name
        for col in parsed.find_all(exp.Column)
        if col.name.lower() in settings.forbidden_columns
    ]
    if forbidden_columns:
        raise GuardrailError(
            "Запрос обращается к запрещённым колонкам: " + ", ".join(sorted(set(forbidden_columns)))
        )

    if not re.search(r"\blimit\b", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned}\nLIMIT {settings.max_result_rows}"
        notes.append(f"Автоматически добавлен LIMIT {settings.max_result_rows}.")

    return cleaned, notes
