from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import sqlglot


SAFE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SAFE_ENTITY_TYPES = {"metric", "dimension", "filter"}
SAFE_DATA_TYPES = {"string", "integer", "numeric", "date", "timestamp", "boolean"}
SAFE_CHART_TYPES = {"table_only", "bar", "line", "grouped_bar", "area", "pie"}
BLOCKED_SQL_RE = re.compile(
    r"\b(select|from|insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|merge|call|execute)\b",
    re.IGNORECASE,
)
PLACEHOLDER_VALUES = {
    "base_alias": "src",
    "dimension_alias": "dim_alias",
    "time_column": "order_timestamp",
    "time_dimension_column": "order_day",
}


class SemanticValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SemanticValidationIssue:
    level: str
    code: str
    entity_type: str
    entity_key: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "entity_type": self.entity_type,
            "entity_key": self.entity_key,
            "message": self.message,
        }


@dataclass(frozen=True)
class SemanticValidationReport:
    issues: list[SemanticValidationIssue]

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [issue.as_dict() for issue in self.issues]}


def _issue(level: str, code: str, entity_type: str, entity_key: str, message: str) -> SemanticValidationIssue:
    return SemanticValidationIssue(
        level=level,
        code=code,
        entity_type=entity_type,
        entity_key=entity_key,
        message=message,
    )


def _render_template(value: str, **overrides: str) -> str:
    context = {**PLACEHOLDER_VALUES, **overrides}
    try:
        return value.format(**context)
    except KeyError as exc:
        raise SemanticValidationError(f"Unknown placeholder {exc.args[0]} in semantic template.") from exc


def _validate_key(entity_type: str, key: str) -> list[SemanticValidationIssue]:
    if SAFE_KEY_RE.match(key):
        return []
    return [_issue("error", "invalid_key", entity_type, key, "Key must match ^[a-z][a-z0-9_]*$.")]


def _validate_expression_fragment(entity_type: str, entity_key: str, expression: str) -> list[SemanticValidationIssue]:
    issues: list[SemanticValidationIssue] = []
    if not expression.strip():
        return [_issue("error", "blank_expression", entity_type, entity_key, "SQL template must not be empty.")]
    if ";" in expression:
        issues.append(_issue("error", "semicolon", entity_type, entity_key, "SQL template must not contain semicolons."))
    if BLOCKED_SQL_RE.search(expression):
        issues.append(
            _issue(
                "error",
                "forbidden_sql_keyword",
                entity_type,
                entity_key,
                "Expression templates must be fragments, not full SQL statements.",
            )
        )
    if issues:
        return issues
    rendered = _render_template(expression)
    try:
        sqlglot.parse_one(f"SELECT {rendered} AS semantic_value FROM fact.orders src", read="postgres")
    except Exception as exc:
        issues.append(
            _issue(
                "error",
                "invalid_sql_expression",
                entity_type,
                entity_key,
                f"SQL template failed to parse: {exc}",
            )
        )
    return issues


def _validate_join_path(entity_type: str, entity_key: str, join_path: str) -> list[SemanticValidationIssue]:
    if not join_path.strip():
        return []
    lowered = join_path.strip().lower()
    if ";" in join_path:
        return [_issue("error", "semicolon", entity_type, entity_key, "Join path must not contain semicolons.")]
    if not (lowered.startswith("join ") or lowered.startswith("left join ")):
        return [_issue("error", "join_prefix", entity_type, entity_key, "Join path must start with JOIN or LEFT JOIN.")]
    if re.search(r"\b(delete|update|insert|drop|alter|truncate|create|merge|call|execute)\b", lowered):
        return [_issue("error", "forbidden_join_keyword", entity_type, entity_key, "Join path contains forbidden SQL.")]
    rendered = _render_template(join_path)
    try:
        sqlglot.parse_one(f"SELECT 1 FROM fact.orders src {rendered}", read="postgres")
    except Exception as exc:
        return [
            _issue(
                "error",
                "invalid_join_path",
                entity_type,
                entity_key,
                f"Join path failed to parse: {exc}",
            )
        ]
    return []


def validate_metric_definition(
    payload: dict[str, Any],
    *,
    dimension_keys: set[str],
    supported_grains: set[str],
) -> SemanticValidationReport:
    key = str(payload.get("metric_key") or "")
    issues = _validate_key("metric", key)
    description = str(payload.get("description") or "").strip()
    if not description:
        issues.append(_issue("error", "missing_description", "metric", key, "Description is required."))
    grain = str(payload.get("grain") or "")
    if grain not in supported_grains:
        issues.append(_issue("error", "unsupported_grain", "metric", key, f"Unsupported grain: {grain}."))
    default_chart = str(payload.get("default_chart") or "table_only")
    if default_chart not in SAFE_CHART_TYPES:
        issues.append(_issue("error", "unsupported_chart", "metric", key, f"Unsupported chart type: {default_chart}."))
    issues.extend(_validate_expression_fragment("metric", key, str(payload.get("sql_expression_template") or "")))
    for field_name in ("allowed_dimensions", "allowed_filters"):
        values = list(payload.get(field_name) or [])
        for value in values:
            if value not in dimension_keys:
                issues.append(
                    _issue(
                        "error",
                        f"unknown_{field_name[:-1]}",
                        "metric",
                        key,
                        f"{field_name} references unknown dimension/filter key {value}.",
                    )
                )
    return SemanticValidationReport(issues)


def validate_dimension_definition(payload: dict[str, Any], *, allowed_tables: set[str]) -> SemanticValidationReport:
    key = str(payload.get("dimension_key") or "")
    issues = _validate_key("dimension", key)
    table_name = str(payload.get("table_name") or "").strip()
    if table_name not in {"__grain__"} and table_name not in allowed_tables:
        issues.append(
            _issue(
                "error",
                "unknown_table",
                "dimension",
                key,
                f"Dimension table_name must be one of allowed analytics tables or __grain__: {table_name}",
            )
        )
    data_type = str(payload.get("data_type") or "").strip().lower()
    if data_type not in SAFE_DATA_TYPES:
        issues.append(_issue("error", "unsupported_data_type", "dimension", key, f"Unsupported data_type: {data_type}."))
    issues.extend(_validate_expression_fragment("dimension", key, str(payload.get("column_name") or "")))
    issues.extend(_validate_join_path("dimension", key, str(payload.get("join_path") or "")))
    return SemanticValidationReport(issues)


def validate_term_definition(
    payload: dict[str, Any],
    *,
    metric_keys: set[str],
    dimension_keys: set[str],
) -> SemanticValidationReport:
    key = str(payload.get("term") or "").strip().lower()
    issues: list[SemanticValidationIssue] = []
    if not key:
        issues.append(_issue("error", "blank_term", "term", key, "Term must not be empty."))
    mapped_entity_type = str(payload.get("mapped_entity_type") or "").strip().lower()
    mapped_entity_key = str(payload.get("mapped_entity_key") or "").strip()
    if mapped_entity_type not in SAFE_ENTITY_TYPES:
        issues.append(
            _issue(
                "error",
                "unsupported_entity_type",
                "term",
                key or mapped_entity_key,
                f"Unsupported mapped_entity_type: {mapped_entity_type}.",
            )
        )
    expected_pool = metric_keys if mapped_entity_type == "metric" else dimension_keys
    if mapped_entity_type in SAFE_ENTITY_TYPES and mapped_entity_key not in expected_pool:
        issues.append(
            _issue(
                "error",
                "unknown_mapped_entity",
                "term",
                key or mapped_entity_key,
                f"mapped_entity_key {mapped_entity_key} does not exist for entity type {mapped_entity_type}.",
            )
        )
    return SemanticValidationReport(issues)


def validate_example_definition(
    payload: dict[str, Any],
    *,
    metric_keys: set[str],
    dimension_keys: set[str],
) -> SemanticValidationReport:
    key = str(payload.get("title") or "")
    issues: list[SemanticValidationIssue] = []
    metric_key = str(payload.get("metric_key") or "")
    if metric_key not in metric_keys:
        issues.append(_issue("error", "unknown_metric", "example", key, f"Unknown metric_key {metric_key}."))
    for value in list(payload.get("dimension_keys") or []):
        if value not in dimension_keys:
            issues.append(_issue("error", "unknown_dimension", "example", key, f"Unknown dimension key {value}."))
    for value in list(payload.get("filter_keys") or []):
        if value not in dimension_keys:
            issues.append(_issue("error", "unknown_filter", "example", key, f"Unknown filter key {value}."))
    sql_example = str(payload.get("sql_example") or "").strip()
    if not sql_example:
        issues.append(_issue("error", "blank_sql_example", "example", key, "sql_example is required."))
    elif ";" in sql_example.rstrip(";"):
        issues.append(_issue("warning", "semicolon_sql_example", "example", key, "sql_example contains semicolons."))
    return SemanticValidationReport(issues)


def validate_approved_template_definition(
    payload: dict[str, Any],
    *,
    metric_keys: set[str],
    dimension_keys: set[str],
) -> SemanticValidationReport:
    key = str(payload.get("template_key") or "")
    issues = _validate_key("approved_template", key)
    metric_key = str(payload.get("metric_key") or "")
    if metric_key not in metric_keys:
        issues.append(_issue("error", "unknown_metric", "approved_template", key, f"Unknown metric_key {metric_key}."))
    for value in list(payload.get("dimension_keys") or []):
        if value not in dimension_keys:
            issues.append(
                _issue("error", "unknown_dimension", "approved_template", key, f"Unknown dimension key {value}.")
            )
    for value in list(payload.get("filter_keys") or []):
        if value not in dimension_keys:
            issues.append(_issue("error", "unknown_filter", "approved_template", key, f"Unknown filter key {value}."))
    chart_type = str(payload.get("chart_type") or "table_only")
    if chart_type not in SAFE_CHART_TYPES:
        issues.append(
            _issue("error", "unsupported_chart", "approved_template", key, f"Unsupported chart type {chart_type}.")
        )
    return SemanticValidationReport(issues)
