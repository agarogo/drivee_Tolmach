from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Literal

import sqlglot
from sqlglot import expressions as exp
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.answer_classifier import AnswerTypeDecision
from app.ai.semantic_compiler import SemanticCompilationError, compile_sql_query_bundle
from app.ai.types import Interpretation, RetrievalResult, SqlPlan
from app.config import get_settings
from app.semantic.planner import (
    _compile_filter_clause,
    _compile_period,
    _dedupe,
    _normalize_limit,
    _resolve_dimension_sql,
)
from app.semantic.service import GRAIN_REGISTRY, SemanticCatalog, SemanticMetricDefinition
from app.services.guardrails import GuardrailDecision, validate_sql
from app.services.query_runner import execute_validated_query

settings = get_settings()

AnswerQueryMode = Literal["aggregate", "record"]


@dataclass(frozen=True)
class AnswerQuerySpec:
    block_key: str
    title: str
    mode: AnswerQueryMode
    interpretation: Interpretation
    reason: str
    optional: bool = False
    config: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "block_key": self.block_key,
            "title": self.title,
            "mode": self.mode,
            "reason": self.reason,
            "optional": self.optional,
            "config": self.config,
            "interpretation": self.interpretation.as_dict(),
        }


@dataclass(frozen=True)
class AnswerPlan:
    decision: AnswerTypeDecision
    primary_spec: AnswerQuerySpec | None
    secondary_specs: list[AnswerQuerySpec]
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.model_dump(mode="json"),
            "primary_spec": self.primary_spec.as_dict() if self.primary_spec else None,
            "secondary_specs": [item.as_dict() for item in self.secondary_specs],
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CompiledAnswerQuery:
    sql_plan: SqlPlan
    rendered_sql: str
    planner_payload: dict[str, Any]
    source_tables: set[str]
    column_references: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sql_plan": self.sql_plan.as_dict(),
            "rendered_sql": self.rendered_sql,
            "planner_payload": self.planner_payload,
            "source_tables": sorted(self.source_tables),
            "column_references": self.column_references,
        }


@dataclass(frozen=True)
class AnswerBlockFailure:
    block_key: str
    title: str
    reason: str
    optional: bool
    stage: str
    block_reasons: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "block_key": self.block_key,
            "title": self.title,
            "reason": self.reason,
            "optional": self.optional,
            "stage": self.stage,
            "block_reasons": self.block_reasons,
            "logs": self.logs,
        }


@dataclass(frozen=True)
class ExecutedAnswerBlock:
    spec: AnswerQuerySpec
    compiled: CompiledAnswerQuery
    validation: GuardrailDecision
    rows: list[dict[str, Any]]
    execution_ms: int
    cached: bool
    execution_mode: str
    fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.as_dict(),
            "compiled": self.compiled.as_dict(),
            "validated_sql": self.validation.validated_sql.sql if self.validation.validated_sql else "",
            "rows_returned": len(self.rows),
            "execution_ms": self.execution_ms,
            "cached": self.cached,
            "execution_mode": self.execution_mode,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class ExecutedAnswerPlan:
    decision: AnswerTypeDecision
    primary_block: ExecutedAnswerBlock | None
    blocks: dict[str, ExecutedAnswerBlock]
    failures: dict[str, AnswerBlockFailure]
    total_execution_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.model_dump(mode="json"),
            "primary_block": self.primary_block.as_dict() if self.primary_block else None,
            "blocks": {key: value.as_dict() for key, value in self.blocks.items()},
            "failures": {key: value.as_dict() for key, value in self.failures.items()},
            "total_execution_ms": self.total_execution_ms,
        }


@dataclass(frozen=True)
class RecordColumnDefinition:
    key: str
    label: str
    expression_template: str
    data_type: str


ROW_LEVEL_COLUMN_PROFILES: dict[str, list[RecordColumnDefinition]] = {
    "order": [
        RecordColumnDefinition("order_id", "Order ID", "{base_alias}.order_id", "string"),
        RecordColumnDefinition("order_day", "Order Day", "{base_alias}.{time_dimension_column}", "date"),
        RecordColumnDefinition("status_order", "Order Status", "{base_alias}.status_order", "string"),
        RecordColumnDefinition("status_tender", "Tender Status", "{base_alias}.status_tender", "string"),
        RecordColumnDefinition("driver_id", "Driver", "{base_alias}.driver_id", "string"),
        RecordColumnDefinition("user_id", "Client", "{base_alias}.user_id", "string"),
        RecordColumnDefinition("price_order_local", "Order Price", "{base_alias}.price_order_local", "number"),
        RecordColumnDefinition("distance_in_meters", "Distance (m)", "{base_alias}.distance_in_meters", "number"),
        RecordColumnDefinition("duration_in_seconds", "Duration (s)", "{base_alias}.duration_in_seconds", "number"),
    ],
    "tender": [
        RecordColumnDefinition("tender_id", "Tender ID", "{base_alias}.tender_id", "string"),
        RecordColumnDefinition("tender_day", "Tender Day", "{base_alias}.{time_dimension_column}", "date"),
        RecordColumnDefinition("status_tender", "Tender Status", "{base_alias}.status_tender", "string"),
        RecordColumnDefinition("driver_id", "Driver", "{base_alias}.driver_id", "string"),
        RecordColumnDefinition("user_id", "Client", "{base_alias}.user_id", "string"),
        RecordColumnDefinition("price_tender_local", "Tender Price", "{base_alias}.price_tender_local", "number"),
        RecordColumnDefinition("price_start_local", "Start Price", "{base_alias}.price_start_local", "number"),
    ],
}


def _is_time_dimension(key: str, catalog: SemanticCatalog) -> bool:
    if key in {"day", "week", "month", "quarter", "year", "hour"}:
        return True
    definition = catalog.get_dimension(key)
    if not definition:
        return False
    return definition.data_type in {"date", "timestamp"}


def _metric_definition(
    interpretation: Interpretation,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> SemanticMetricDefinition:
    metric_key = interpretation.metric or decision.preferred_metric_key
    metric = catalog.get_metric(metric_key)
    if not metric:
        raise SemanticCompilationError(
            f"Answer strategy requires a governed metric, but none was resolved for answer_type={decision.answer_type_key}."
        )
    return metric


def _candidate_dimensions(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    decision: AnswerTypeDecision,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for source in (interpretation.dimensions, decision.preferred_dimension_keys, metric.allowed_dimensions):
        for key in source:
            if key and key not in seen:
                ordered.append(key)
                seen.add(key)
    return ordered


def _choose_time_dimension(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> str:
    if decision.preferred_time_dimension and decision.preferred_time_dimension in metric.allowed_dimensions:
        return decision.preferred_time_dimension
    for key in _candidate_dimensions(interpretation, metric, decision):
        if key in metric.allowed_dimensions and _is_time_dimension(key, catalog):
            return key
    return ""


def _choose_category_dimension(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> str:
    for key in _candidate_dimensions(interpretation, metric, decision):
        if key in metric.allowed_dimensions and not _is_time_dimension(key, catalog):
            return key
    return ""


def _shape_interpretation(
    interpretation: Interpretation,
    *,
    dimensions: list[str],
    limit: int,
    sort_by: str,
    direction: str,
) -> Interpretation:
    return replace(
        interpretation,
        dimensions=dimensions,
        grouping=list(dimensions),
        limit=limit,
        top=limit if dimensions else None,
        sorting={"by": sort_by, "direction": direction},
    )


def _previous_period(date_range: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(date_range.get("kind") or "missing")
    if kind == "rolling_days":
        days = int(date_range.get("days") or 0)
        if days <= 0:
            return None
        return {
            "kind": "between_dates",
            "start": (date.today() - timedelta(days=days * 2)).isoformat(),
            "end": (date.today() - timedelta(days=days + 1)).isoformat(),
            "label": f"previous {days} days",
        }
    if kind == "between_dates":
        start = _parse_date(str(date_range.get("start") or ""))
        end = _parse_date(str(date_range.get("end") or ""))
        if not start or not end or end < start:
            return None
        span = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        return {
            "kind": "between_dates",
            "start": prev_start.isoformat(),
            "end": prev_end.isoformat(),
            "label": f"{prev_start.isoformat()}..{prev_end.isoformat()}",
        }
    if kind == "exact_date":
        current = _parse_date(str(date_range.get("date") or ""))
        if not current:
            return None
        prev = current - timedelta(days=1)
        return {"kind": "exact_date", "date": prev.isoformat(), "label": prev.isoformat()}
    return None


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _build_single_value_specs(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    decision: AnswerTypeDecision,
) -> tuple[AnswerQuerySpec, list[AnswerQuerySpec], list[str]]:
    notes: list[str] = []
    primary = AnswerQuerySpec(
        block_key="primary_kpi",
        title="Headline KPI",
        mode="aggregate",
        interpretation=_shape_interpretation(
            interpretation,
            dimensions=[],
            limit=1,
            sort_by=metric.metric_key,
            direction="desc",
        ),
        reason="Single KPI mode requires one aggregate without a categorical or time breakdown.",
    )
    secondary: list[AnswerQuerySpec] = []
    previous_period = _previous_period(interpretation.date_range or {})
    if previous_period:
        baseline = replace(primary.interpretation, date_range=previous_period)
        secondary.append(
            AnswerQuerySpec(
                block_key="previous_period",
                title="Previous Period Baseline",
                mode="aggregate",
                interpretation=baseline,
                reason="Single KPI mode adds a baseline query for delta calculation.",
                optional=True,
            )
        )
    else:
        notes.append("Previous-period baseline is unavailable because the current period cannot be shifted safely.")
    return primary, secondary, notes


def _build_comparison_specs(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> tuple[AnswerQuerySpec, list[AnswerQuerySpec], list[str]]:
    category = _choose_category_dimension(interpretation, metric, catalog, decision)
    if not category:
        category = next((key for key in metric.allowed_dimensions if not _is_time_dimension(key, catalog)), "")
    if not category:
        raise SemanticCompilationError(f"Comparison mode requires a categorical dimension for metric {metric.metric_key}.")
    limit = min(max(int(interpretation.top or interpretation.limit or 10), 5), 15)
    primary = AnswerQuerySpec(
        block_key="comparison",
        title="Comparison",
        mode="aggregate",
        interpretation=_shape_interpretation(
            interpretation,
            dimensions=[category],
            limit=limit,
            sort_by=metric.metric_key,
            direction="desc",
        ),
        reason="Comparison mode groups the governed metric by one category, ranks values, and limits the result set.",
        config={"dimension_key": category},
    )
    return primary, [], []


def _build_trend_specs(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> tuple[AnswerQuerySpec, list[AnswerQuerySpec], list[str]]:
    time_dimension = _choose_time_dimension(interpretation, metric, catalog, decision)
    if not time_dimension and "day" in metric.allowed_dimensions:
        time_dimension = "day"
    if not time_dimension:
        raise SemanticCompilationError(f"Trend mode requires a time dimension for metric {metric.metric_key}.")
    primary = AnswerQuerySpec(
        block_key="trend",
        title="Trend",
        mode="aggregate",
        interpretation=_shape_interpretation(
            interpretation,
            dimensions=[time_dimension],
            limit=min(max(int(interpretation.limit or 30), 14), 120),
            sort_by=time_dimension,
            direction="asc",
        ),
        reason="Trend mode groups the governed metric by a time grain and orders points chronologically.",
        config={"time_dimension": time_dimension},
    )
    return primary, [], []


def _build_distribution_specs(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> tuple[AnswerQuerySpec, list[AnswerQuerySpec], list[str]]:
    category = _choose_category_dimension(interpretation, metric, catalog, decision)
    if not category:
        category = next((key for key in metric.allowed_dimensions if not _is_time_dimension(key, catalog)), "")
    if not category:
        raise SemanticCompilationError(f"Distribution mode requires a categorical dimension for metric {metric.metric_key}.")
    primary = AnswerQuerySpec(
        block_key="distribution",
        title="Distribution",
        mode="aggregate",
        interpretation=_shape_interpretation(
            interpretation,
            dimensions=[category],
            limit=min(max(int(interpretation.limit or 25), 10), 50),
            sort_by=metric.metric_key,
            direction="desc",
        ),
        reason="Distribution mode aggregates categories so the renderer can compute percentages and collapse the long tail into Other.",
        config={"dimension_key": category, "visible_item_limit": 6},
    )
    return primary, [], []


def _build_table_specs(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> tuple[AnswerQuerySpec, list[AnswerQuerySpec], list[str]]:
    del catalog, decision
    page_size = 25
    primary = AnswerQuerySpec(
        block_key="records",
        title="Record Table",
        mode="record",
        interpretation=replace(interpretation, limit=page_size + 1, top=None),
        reason="Table mode compiles a row-level governed SELECT with server-ready pagination semantics.",
        config={"page_size": page_size, "page_offset": 0, "grain": metric.grain},
    )
    return primary, [], []


def _build_full_report_specs(
    interpretation: Interpretation,
    metric: SemanticMetricDefinition,
    catalog: SemanticCatalog,
    decision: AnswerTypeDecision,
) -> tuple[AnswerQuerySpec, list[AnswerQuerySpec], list[str]]:
    primary, secondary, notes = _build_single_value_specs(interpretation, metric, decision)
    primary = replace(primary, block_key="headline_kpi", title="Headline KPI")
    time_dimension = _choose_time_dimension(interpretation, metric, catalog, decision)
    category = _choose_category_dimension(interpretation, metric, catalog, decision)

    if time_dimension or "day" in metric.allowed_dimensions:
        trend_key = time_dimension or "day"
        secondary.append(
            AnswerQuerySpec(
                block_key="report_trend",
                title="Trend Section",
                mode="aggregate",
                interpretation=_shape_interpretation(
                    interpretation,
                    dimensions=[trend_key],
                    limit=min(max(int(interpretation.limit or 30), 14), 90),
                    sort_by=trend_key,
                    direction="asc",
                ),
                reason="Full report includes a trend block when the metric supports a time dimension.",
                optional=True,
                config={"time_dimension": trend_key},
            )
        )
    else:
        notes.append("Trend section is unavailable because the metric does not expose a governed time dimension.")

    if category:
        secondary.append(
            AnswerQuerySpec(
                block_key="report_comparison",
                title="Comparison Section",
                mode="aggregate",
                interpretation=_shape_interpretation(
                    interpretation,
                    dimensions=[category],
                    limit=min(max(int(interpretation.top or interpretation.limit or 8), 5), 12),
                    sort_by=metric.metric_key,
                    direction="desc",
                ),
                reason="Full report includes a ranked comparison section when a categorical dimension is available.",
                optional=True,
                config={"dimension_key": category},
            )
        )
    else:
        notes.append("Comparison section is unavailable because the metric does not expose a governed category dimension.")

    secondary.append(
        AnswerQuerySpec(
            block_key="report_records",
            title="Record Preview",
            mode="record",
            interpretation=replace(interpretation, limit=9, top=None),
            reason="Full report includes a short record preview so the layout stays auditable.",
            optional=True,
            config={"page_size": 8, "page_offset": 0, "grain": metric.grain},
        )
    )
    return primary, secondary, notes


def build_answer_plan(
    *,
    decision: AnswerTypeDecision,
    interpretation: Interpretation,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> AnswerPlan:
    del retrieval
    metric = _metric_definition(interpretation, catalog, decision)

    if decision.answer_type_key == "single_value":
        primary, secondary, notes = _build_single_value_specs(interpretation, metric, decision)
    elif decision.answer_type_key == "comparison_top":
        primary, secondary, notes = _build_comparison_specs(interpretation, metric, catalog, decision)
    elif decision.answer_type_key == "trend":
        primary, secondary, notes = _build_trend_specs(interpretation, metric, catalog, decision)
    elif decision.answer_type_key == "distribution":
        primary, secondary, notes = _build_distribution_specs(interpretation, metric, catalog, decision)
    elif decision.answer_type_key == "table":
        primary, secondary, notes = _build_table_specs(interpretation, metric, catalog, decision)
    elif decision.answer_type_key == "full_report":
        primary, secondary, notes = _build_full_report_specs(interpretation, metric, catalog, decision)
    else:
        raise SemanticCompilationError(
            f"Answer type {decision.answer_type_key} does not require SQL planning."
        )
    return AnswerPlan(decision=decision, primary_spec=primary, secondary_specs=secondary, notes=notes)


def _column_references(expression: exp.Expression) -> list[dict[str, str]]:
    return [
        {
            "table_alias": str(column.table or "").strip().lower(),
            "column_name": column.name.lower(),
        }
        for column in expression.find_all(exp.Column)
    ]


def _source_tables(expression: exp.Expression) -> set[str]:
    tables: set[str] = set()
    for table in expression.find_all(exp.Table):
        schema = str(table.db or "").strip().lower()
        name = str(table.name or "").strip().lower()
        tables.add(f"{schema}.{name}" if schema else name)
    return tables


def _compile_record_query(spec: AnswerQuerySpec, catalog: SemanticCatalog) -> CompiledAnswerQuery:
    metric = catalog.get_metric(spec.interpretation.metric)
    if not metric:
        raise SemanticCompilationError("Row-level table mode requires a governed metric to determine grain.")
    grain = GRAIN_REGISTRY[metric.grain]
    profile = ROW_LEVEL_COLUMN_PROFILES.get(metric.grain, [])
    interpretation = spec.interpretation
    joins: list[str] = []
    filters_sql: list[str] = []
    planner_notes: list[dict[str, Any]] = [
        {
            "stage": "record_select",
            "metric_key": metric.metric_key,
            "grain": metric.grain,
            "reason": spec.reason,
        }
    ]

    select_parts: list[str] = []
    visible_dimension_labels: dict[str, str] = {}
    selected_dimension_keys: list[str] = []

    for dimension_key in interpretation.dimensions:
        if dimension_key not in metric.allowed_dimensions:
            continue
        dimension = catalog.get_dimension(dimension_key)
        if not dimension:
            continue
        expression, join_sql = _resolve_dimension_sql(dimension, grain=grain)
        if join_sql:
            joins.append(join_sql)
        select_parts.append(f"{expression} AS {dimension.dimension_key}")
        visible_dimension_labels[dimension.dimension_key] = dimension.business_name
        selected_dimension_keys.append(dimension.dimension_key)

    selected_keys = set(selected_dimension_keys)
    for column in profile:
        if column.key in selected_keys:
            continue
        expression = column.expression_template.format(
            base_alias=grain.base_alias,
            time_dimension_column=grain.time_dimension_column,
        )
        select_parts.append(f"{expression} AS {column.key}")

    for filter_key, filter_value in interpretation.filters.items():
        if filter_key not in metric.allowed_filters:
            continue
        definition = catalog.get_filter(filter_key)
        if not definition:
            continue
        clause, join_sql = _compile_filter_clause(
            definition,
            grain=grain,
            operator=str(filter_value.get("operator", "eq")),
            values=[str(item) for item in filter_value.get("values", []) if item not in {None, ""}],
        )
        if join_sql:
            joins.append(join_sql)
        filters_sql.append(clause)
        planner_notes.append(
            {
                "stage": "filter",
                "filter_key": filter_key,
                "operator": str(filter_value.get("operator", "eq")),
                "values": [str(item) for item in filter_value.get("values", []) if item not in {None, ""}],
            }
        )

    period_clauses = _compile_period(interpretation.date_range, time_column=grain.time_column, base_alias=grain.base_alias)
    all_where = [*filters_sql, *period_clauses]
    joins_sql = "\n".join(_dedupe(joins))
    where_sql = f"WHERE {' AND '.join(all_where)}" if all_where else ""
    order_by_sql = f"{grain.base_alias}.{grain.time_column} DESC"
    limit = _normalize_limit(spec.interpretation.limit)
    rendered_sql = f"""
SELECT
  {', '.join(select_parts)}
FROM {grain.source_table} {grain.base_alias}
{joins_sql}
{where_sql}
ORDER BY {order_by_sql}
LIMIT {limit}
""".strip()
    ast = sqlglot.parse_one(rendered_sql, read="postgres")
    sql_plan = SqlPlan(
        metric=metric.metric_key,
        metric_label=metric.business_name,
        metric_expression="row_level_select",
        source_table=f"{grain.source_table} {grain.base_alias}",
        dimensions=selected_dimension_keys,
        dimension_labels=visible_dimension_labels,
        joins=_dedupe(joins),
        filters=[*filters_sql, *period_clauses],
        group_by=[],
        order_by=order_by_sql,
        limit=limit,
        chart_type="table_only",
        explanation=[
            f"Row-level record query compiled on governed grain {grain.grain_key}.",
            "The planner selected explicit approved columns only; no chart heuristic was used.",
        ],
        ast_json=ast.dump() if hasattr(ast, "dump") else {"sql": rendered_sql},
        planner_notes=planner_notes,
        clarification_reasons=[],
    )
    return CompiledAnswerQuery(
        sql_plan=sql_plan,
        rendered_sql=rendered_sql,
        planner_payload={
            "strategy_mode": "record",
            "selected_dimension_keys": selected_dimension_keys,
            "selected_profile_columns": [column.key for column in profile],
            "period_clauses": period_clauses,
        },
        source_tables=_source_tables(ast),
        column_references=_column_references(ast),
    )


def compile_answer_query(
    spec: AnswerQuerySpec,
    *,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> CompiledAnswerQuery:
    if spec.mode == "aggregate":
        compiled = compile_sql_query_bundle(spec.interpretation, retrieval, catalog)
        return CompiledAnswerQuery(
            sql_plan=compiled.sql_plan,
            rendered_sql=compiled.rendered_sql,
            planner_payload={
                "strategy_mode": "aggregate",
                "planner_result": compiled.planner_result.as_dict(),
            },
            source_tables=set(compiled.source_tables),
            column_references=list(compiled.column_references),
        )
    return _compile_record_query(spec, catalog)


async def _execute_spec(
    db: AsyncSession,
    *,
    query_id,
    role: str,
    spec: AnswerQuerySpec,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> tuple[ExecutedAnswerBlock | None, AnswerBlockFailure | None]:
    compiled = compile_answer_query(spec, retrieval=retrieval, catalog=catalog)
    validation = await validate_sql(
        db,
        compiled.rendered_sql,
        role=role,
        query_id=query_id,
        compiled_query=SimpleNamespace(column_references=compiled.column_references),
    )
    if not validation.ok or validation.validated_sql is None:
        failure = AnswerBlockFailure(
            block_key=spec.block_key,
            title=spec.title,
            reason=validation.message,
            optional=spec.optional,
            stage="guardrails",
            block_reasons=list(validation.block_reasons),
            logs=list(validation.logs),
        )
        return None, failure

    try:
        result = await execute_validated_query(
            validation.validated_sql,
            role=role,
            db=db,
            query_id=query_id,
            use_cache=True,
        )
    except Exception as exc:
        failure = AnswerBlockFailure(
            block_key=spec.block_key,
            title=spec.title,
            reason=str(exc),
            optional=spec.optional,
            stage="execution",
            block_reasons=[],
            logs=[],
        )
        return None, failure
    block = ExecutedAnswerBlock(
        spec=spec,
        compiled=CompiledAnswerQuery(
            sql_plan=compiled.sql_plan,
            rendered_sql=validation.validated_sql.sql,
            planner_payload=compiled.planner_payload,
            source_tables=compiled.source_tables,
            column_references=compiled.column_references,
        ),
        validation=validation,
        rows=result.rows,
        execution_ms=result.execution_ms,
        cached=result.cached,
        execution_mode=result.execution_mode,
        fingerprint=result.fingerprint,
    )
    return block, None


async def execute_answer_plan(
    db: AsyncSession,
    *,
    query_id,
    role: str,
    plan: AnswerPlan,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> ExecutedAnswerPlan:
    blocks: dict[str, ExecutedAnswerBlock] = {}
    failures: dict[str, AnswerBlockFailure] = {}
    total_execution_ms = 0
    primary_block: ExecutedAnswerBlock | None = None

    specs: list[AnswerQuerySpec] = []
    if plan.primary_spec is not None:
        specs.append(plan.primary_spec)
    specs.extend(plan.secondary_specs)

    for spec in specs:
        block, failure = await _execute_spec(
            db,
            query_id=query_id,
            role=role,
            spec=spec,
            retrieval=retrieval,
            catalog=catalog,
        )
        if failure is not None:
            failures[spec.block_key] = failure
            if not spec.optional:
                return ExecutedAnswerPlan(
                    decision=plan.decision,
                    primary_block=primary_block,
                    blocks=blocks,
                    failures=failures,
                    total_execution_ms=total_execution_ms,
                )
            continue
        if block is None:
            continue
        if primary_block is None and plan.primary_spec and spec.block_key == plan.primary_spec.block_key:
            primary_block = block
        blocks[spec.block_key] = block
        total_execution_ms += block.execution_ms

    return ExecutedAnswerPlan(
        decision=plan.decision,
        primary_block=primary_block,
        blocks=blocks,
        failures=failures,
        total_execution_ms=total_execution_ms,
    )


__all__ = [
    "AnswerBlockFailure",
    "AnswerPlan",
    "AnswerQuerySpec",
    "CompiledAnswerQuery",
    "ExecutedAnswerBlock",
    "ExecutedAnswerPlan",
    "build_answer_plan",
    "compile_answer_query",
    "execute_answer_plan",
]
