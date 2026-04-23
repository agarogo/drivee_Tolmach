from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.ai.types import Interpretation, RetrievalResult
from app.config import get_settings
from app.semantic.errors import (
    ClarificationCode,
    ClarificationReason,
    SemanticCompilationError,
    SemanticErrorCode,
    build_block_reason,
    build_clarification_reason,
)
from app.semantic.service import (
    GRAIN_REGISTRY,
    GrainDefinition,
    SemanticCatalog,
    SemanticDimensionDefinition,
    SemanticMetricDefinition,
)

settings = get_settings()


@dataclass(frozen=True)
class PlannedDimension:
    definition: SemanticDimensionDefinition
    select_sql: str
    group_by_sql: str
    join_sql: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension_key": self.definition.dimension_key,
            "business_name": self.definition.business_name,
            "table_name": self.definition.table_name,
            "select_sql": self.select_sql,
            "group_by_sql": self.group_by_sql,
            "join_sql": self.join_sql or "",
        }


@dataclass(frozen=True)
class PlannedFilter:
    definition: SemanticDimensionDefinition
    operator: str
    values: list[str]
    clause_sql: str
    join_sql: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension_key": self.definition.dimension_key,
            "business_name": self.definition.business_name,
            "operator": self.operator,
            "values": self.values,
            "clause_sql": self.clause_sql,
            "join_sql": self.join_sql or "",
        }


@dataclass(frozen=True)
class QueryPlannerResult:
    metric: SemanticMetricDefinition
    grain: GrainDefinition
    metric_expression_sql: str
    dimensions: list[PlannedDimension]
    filters: list[PlannedFilter]
    period_clauses: list[str]
    joins: list[str]
    order_by_sql: str
    limit: int
    chart_type: str
    explanation: list[str]
    clarification_reasons: list[ClarificationReason] = field(default_factory=list)
    planner_notes: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric_key": self.metric.metric_key,
            "metric_business_name": self.metric.business_name,
            "grain": self.grain.grain_key,
            "metric_expression_sql": self.metric_expression_sql,
            "dimensions": [item.as_dict() for item in self.dimensions],
            "filters": [item.as_dict() for item in self.filters],
            "period_clauses": self.period_clauses,
            "joins": self.joins,
            "order_by_sql": self.order_by_sql,
            "limit": self.limit,
            "chart_type": self.chart_type,
            "explanation": self.explanation,
            "clarification_reasons": [item.as_dict() for item in self.clarification_reasons],
            "planner_notes": self.planner_notes,
        }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _render_template(template: str, *, grain: GrainDefinition, dimension_alias: str = "dim_value") -> str:
    return template.format(
        base_alias=grain.base_alias,
        dimension_alias=dimension_alias,
        time_column=grain.time_column,
        time_dimension_column=grain.time_dimension_column,
    )


def _normalize_limit(limit: int | None) -> int:
    raw_value = int(limit or 20)
    if raw_value <= 0:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.INVALID_LIMIT,
                "Requested LIMIT must be greater than zero.",
                details={"requested_limit": raw_value},
            )
        )
    return min(raw_value, settings.max_result_rows)


def _parse_temporal_value(data_type: str, value: str) -> str:
    text = value.strip()
    if data_type == "date":
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.INVALID_FILTER_VALUE,
                    "Date filter value must use YYYY-MM-DD format.",
                    details={"value": text, "data_type": data_type},
                )
            ) from exc
        return f"DATE '{text}'"
    if data_type == "timestamp":
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.INVALID_FILTER_VALUE,
                    "Timestamp filter value must use ISO-like datetime format.",
                    details={"value": text, "data_type": data_type},
                )
            )
        normalized = parsed.strftime("%Y-%m-%d %H:%M:%S")
        return f"TIMESTAMP '{normalized}'"
    return ""


def _sql_literal(data_type: str, value: str) -> str:
    if data_type in {"integer", "numeric"}:
        text = value.strip()
        try:
            if data_type == "integer":
                return str(int(text))
            return str(float(text))
        except ValueError as exc:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.INVALID_FILTER_VALUE,
                    f"Filter value {value!r} is not valid for {data_type}.",
                    details={"value": value, "data_type": data_type},
                )
            ) from exc

    temporal_literal = _parse_temporal_value(data_type, value)
    if temporal_literal:
        return temporal_literal

    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _allowed_operators(data_type: str) -> list[str]:
    if data_type in {"date", "timestamp", "integer", "numeric"}:
        return ["eq", "in", "between"]
    return ["eq", "in"]


def _compile_period(date_range: dict[str, Any], *, time_column: str, base_alias: str) -> list[str]:
    field = f"{base_alias}.{time_column}"
    kind = str(date_range.get("kind", "missing"))
    if kind == "rolling_days":
        days = int(date_range.get("days") or 0)
        if days <= 0:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.INVALID_PERIOD,
                    "Rolling period must specify a positive number of days.",
                    details={"date_range": date_range},
                )
            )
        return [f"{field} >= CURRENT_DATE - INTERVAL '{days} days'"]
    if kind == "since_date":
        start = str(date_range.get("start") or "").strip()
        return [f"{field} >= DATE '{start}'"] if start else []
    if kind == "until_date":
        end = str(date_range.get("end") or "").strip()
        return [f"{field} < DATE '{end}' + INTERVAL '1 day'"] if end else []
    if kind == "exact_date":
        exact = str(date_range.get("date") or "").strip()
        return [f"DATE({field}) = DATE '{exact}'"] if exact else []
    if kind == "between_dates":
        start = str(date_range.get("start") or "").strip()
        end = str(date_range.get("end") or "").strip()
        if not start or not end:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.INVALID_PERIOD,
                    "Between period must include start and end dates.",
                    details={"date_range": date_range},
                )
            )
        return [
            f"{field} >= DATE '{start}'",
            f"{field} < DATE '{end}' + INTERVAL '1 day'",
        ]
    if kind == "missing":
        return []
    raise SemanticCompilationError(
        build_block_reason(
            SemanticErrorCode.INVALID_PERIOD,
            f"Unsupported period kind: {kind}.",
            details={"date_range": date_range},
        )
    )


def _resolve_dimension_sql(
    dimension: SemanticDimensionDefinition,
    *,
    grain: GrainDefinition,
) -> tuple[str, str | None]:
    dimension_alias = f"dim_{dimension.dimension_key}"
    column_expression = _render_template(dimension.column_name, grain=grain, dimension_alias=dimension_alias)
    if dimension.table_name == "__grain__":
        return f"{grain.base_alias}.{column_expression}", None
    join_sql = _render_template(dimension.join_path, grain=grain, dimension_alias=dimension_alias).strip()
    if not join_sql:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.INVALID_JOIN_PATH,
                f"Dimension {dimension.dimension_key} requires a join_path.",
                details={"dimension_key": dimension.dimension_key},
            )
        )
    return f"{dimension_alias}.{column_expression}", join_sql


def _compile_filter_clause(
    dimension: SemanticDimensionDefinition,
    *,
    grain: GrainDefinition,
    operator: str,
    values: list[str],
) -> tuple[str, str | None]:
    allowed_operators = _allowed_operators(dimension.data_type)
    if operator not in allowed_operators:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.INVALID_FILTER_OPERATOR,
                f"Operator {operator} is not allowed for filter {dimension.dimension_key}.",
                details={
                    "filter_key": dimension.dimension_key,
                    "operator": operator,
                    "allowed_operators": allowed_operators,
                },
            )
        )
    if not values:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.MISSING_FILTER_VALUES,
                f"Filter {dimension.dimension_key} does not include values.",
                details={"filter_key": dimension.dimension_key},
            )
        )
    expression, join_sql = _resolve_dimension_sql(dimension, grain=grain)
    if operator == "eq":
        return f"{expression} = {_sql_literal(dimension.data_type, values[0])}", join_sql
    if operator == "in":
        joined_values = ", ".join(_sql_literal(dimension.data_type, value) for value in values)
        return f"{expression} IN ({joined_values})", join_sql
    if operator == "between" and len(values) >= 2:
        return (
            f"{expression} BETWEEN {_sql_literal(dimension.data_type, values[0])} "
            f"AND {_sql_literal(dimension.data_type, values[1])}",
            join_sql,
        )
    raise SemanticCompilationError(
        build_block_reason(
            SemanticErrorCode.INVALID_FILTER_OPERATOR,
            f"Operator {operator} is not supported for filter {dimension.dimension_key}.",
            details={"filter_key": dimension.dimension_key, "operator": operator, "values": values},
        )
    )


def _build_clarification_reasons(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition | None,
    catalog: SemanticCatalog,
) -> list[ClarificationReason]:
    reasons: list[ClarificationReason] = []
    if not interpretation.metric:
        reasons.append(
            build_clarification_reason(
                ClarificationCode.METRIC_REQUIRED,
                "The request does not resolve to a governed metric yet.",
            )
        )
    elif metric is None:
        reasons.append(
            build_clarification_reason(
                ClarificationCode.METRIC_NOT_IN_CATALOG,
                f"Metric {interpretation.metric} is not present in the semantic catalog.",
                details={"metric_key": interpretation.metric},
            )
        )
    for dimension_key in interpretation.dimensions:
        if dimension_key not in catalog.dimensions:
            reasons.append(
                build_clarification_reason(
                    ClarificationCode.DIMENSION_NOT_IN_CATALOG,
                    f"Dimension {dimension_key} is not present in the semantic catalog.",
                    details={"dimension_key": dimension_key},
                )
            )
    for filter_key in interpretation.filters:
        if filter_key not in catalog.filters:
            reasons.append(
                build_clarification_reason(
                    ClarificationCode.FILTER_NOT_IN_CATALOG,
                    f"Filter {filter_key} is not present in the semantic catalog.",
                    details={"filter_key": filter_key},
                )
            )
    for ambiguity in interpretation.ambiguity_flags:
        reasons.append(
            build_clarification_reason(
                ClarificationCode.AMBIGUOUS_REQUEST,
                ambiguity,
                details={"ambiguity": ambiguity},
            )
        )
    if interpretation.date_range.get("kind") == "missing":
        reasons.append(
            build_clarification_reason(
                ClarificationCode.PERIOD_REQUIRED,
                "The request does not specify a period; the system can still compile it, but the result may be broad.",
            )
        )
    return reasons


def plan_sql_query(
    interpretation: Interpretation,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> QueryPlannerResult:
    metric = catalog.get_metric(interpretation.metric)
    clarification_reasons = _build_clarification_reasons(interpretation, metric, catalog)
    if not metric:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.UNKNOWN_METRIC if interpretation.metric else SemanticErrorCode.METRIC_REQUIRED,
                "Metric not found in metric_catalog.",
                details={"metric_key": interpretation.metric, "clarification_reasons": [item.as_dict() for item in clarification_reasons]},
            )
        )

    grain = GRAIN_REGISTRY.get(metric.grain)
    if not grain:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.UNSUPPORTED_GRAIN,
                f"Unsupported grain {metric.grain} in metric_catalog.",
                details={"metric_key": metric.metric_key, "grain": metric.grain},
            )
        )

    metric_expression_sql = _render_template(metric.sql_expression_template, grain=grain)
    dimensions: list[PlannedDimension] = []
    filters: list[PlannedFilter] = []
    joins: list[str] = []
    planner_notes: list[dict[str, Any]] = [
        {
            "stage": "metric",
            "metric_key": metric.metric_key,
            "grain": grain.grain_key,
            "source_table": grain.source_table,
        }
    ]

    for dimension_key in interpretation.dimensions:
        if metric.allowed_dimensions and dimension_key not in metric.allowed_dimensions:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.DISALLOWED_DIMENSION,
                    f"Dimension {dimension_key} is not allowed for metric {metric.metric_key}.",
                    details={
                        "metric_key": metric.metric_key,
                        "dimension_key": dimension_key,
                        "allowed_dimensions": metric.allowed_dimensions,
                    },
                )
            )
        dimension = catalog.get_dimension(dimension_key)
        if not dimension:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.UNKNOWN_DIMENSION,
                    f"Dimension {dimension_key} not found in dimension_catalog.",
                    details={"dimension_key": dimension_key},
                )
            )
        expression, join_sql = _resolve_dimension_sql(dimension, grain=grain)
        if join_sql:
            joins.append(join_sql)
        dimensions.append(
            PlannedDimension(
                definition=dimension,
                select_sql=expression,
                group_by_sql=expression,
                join_sql=join_sql,
            )
        )
        planner_notes.append(
            {
                "stage": "dimension",
                "dimension_key": dimension_key,
                "table_name": dimension.table_name,
                "join_sql": join_sql or "",
            }
        )

    for filter_key, filter_value in interpretation.filters.items():
        if metric.allowed_filters and filter_key not in metric.allowed_filters:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.DISALLOWED_FILTER,
                    f"Filter {filter_key} is not allowed for metric {metric.metric_key}.",
                    details={
                        "metric_key": metric.metric_key,
                        "filter_key": filter_key,
                        "allowed_filters": metric.allowed_filters,
                    },
                )
            )
        dimension = catalog.get_filter(filter_key)
        if not dimension:
            raise SemanticCompilationError(
                build_block_reason(
                    SemanticErrorCode.UNKNOWN_FILTER,
                    f"Filter {filter_key} not found in dimension_catalog.",
                    details={"filter_key": filter_key},
                )
            )
        clause, join_sql = _compile_filter_clause(
            dimension,
            grain=grain,
            operator=str(filter_value.get("operator", "eq")),
            values=[str(value) for value in filter_value.get("values", []) if value not in {None, ""}],
        )
        if join_sql:
            joins.append(join_sql)
        filters.append(
            PlannedFilter(
                definition=dimension,
                operator=str(filter_value.get("operator", "eq")),
                values=[str(value) for value in filter_value.get("values", []) if value not in {None, ""}],
                clause_sql=clause,
                join_sql=join_sql,
            )
        )
        planner_notes.append(
            {
                "stage": "filter",
                "filter_key": filter_key,
                "operator": str(filter_value.get("operator", "eq")),
                "values": [str(value) for value in filter_value.get("values", []) if value not in {None, ""}],
            }
        )

    period_clauses = _compile_period(
        interpretation.date_range,
        time_column=grain.time_column,
        base_alias=grain.base_alias,
    )
    joins = _dedupe(joins)
    group_by = _dedupe([item.group_by_sql for item in dimensions])
    limit = _normalize_limit(interpretation.limit)
    sort_direction = str((interpretation.sorting or {}).get("direction", "desc")).lower()
    if sort_direction not in {"asc", "desc"}:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.INVALID_SORT,
                f"Unsupported sort direction: {sort_direction}.",
                details={"sort_direction": sort_direction},
            )
        )

    metric_alias = metric.metric_key
    order_by_sql = "day ASC" if "day" in interpretation.dimensions else f"{metric_alias} {sort_direction.upper()}"
    chart_type = "line" if "day" in interpretation.dimensions else metric.default_chart
    explanation = [
        f"Metric {metric.business_name} compiled from metric_catalog key {metric.metric_key}.",
        f"SQL uses only approved grain {grain.grain_key} and source table {grain.source_table}.",
        f"Dimensions allowed by catalog: {', '.join(metric.allowed_dimensions) or 'none'}.",
        f"Filters allowed by catalog: {', '.join(metric.allowed_filters) or 'none'}.",
    ]
    if retrieval.semantic_terms:
        explanation.append(
            "Matched semantic terms: " + ", ".join(item["term"] for item in retrieval.semantic_terms[:6]) + "."
        )
    if retrieval.planner_candidates:
        explanation.append(
            "Planner candidates considered: "
            + ", ".join(str(item.get("entity_key", "")) for item in retrieval.planner_candidates[:6] if item.get("entity_key"))
            + "."
        )
    if period_clauses:
        explanation.append(f"Period applied on {grain.base_alias}.{grain.time_column}.")
    planner_notes.append({"stage": "limit", "requested_limit": interpretation.limit, "applied_limit": limit})
    planner_notes.append({"stage": "order_by", "order_by_sql": order_by_sql})
    planner_notes.append({"stage": "group_by", "group_by": group_by})

    return QueryPlannerResult(
        metric=metric,
        grain=grain,
        metric_expression_sql=metric_expression_sql,
        dimensions=dimensions,
        filters=filters,
        period_clauses=period_clauses,
        joins=joins,
        order_by_sql=order_by_sql,
        limit=limit,
        chart_type=chart_type,
        explanation=explanation,
        clarification_reasons=clarification_reasons,
        planner_notes=planner_notes,
    )
