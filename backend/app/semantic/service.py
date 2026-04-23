from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import Interpretation, RetrievalResult, SqlPlan
from app.config import get_settings
from app.semantic.errors import SemanticCompilationError
from app.semantic import repository
from app.semantic.validators import (
    SemanticValidationIssue,
    SemanticValidationReport,
    validate_approved_template_definition,
    validate_dimension_definition,
    validate_example_definition,
    validate_metric_definition,
    validate_term_definition,
)

settings = get_settings()


@dataclass(frozen=True)
class GrainDefinition:
    grain_key: str
    source_table: str
    base_alias: str
    time_column: str
    time_dimension_column: str


GRAIN_REGISTRY: dict[str, GrainDefinition] = {
    "order": GrainDefinition(
        grain_key="order",
        source_table="fact.orders",
        base_alias="fo",
        time_column="order_timestamp",
        time_dimension_column="order_day",
    ),
    "tender": GrainDefinition(
        grain_key="tender",
        source_table="fact.tenders",
        base_alias="ft",
        time_column="tender_timestamp",
        time_dimension_column="tender_day",
    ),
}


@dataclass(frozen=True)
class SemanticMetricDefinition:
    metric_key: str
    business_name: str
    description: str
    sql_expression_template: str
    grain: str
    allowed_dimensions: list[str]
    allowed_filters: list[str]
    default_chart: str
    safety_tags: list[str]


@dataclass(frozen=True)
class SemanticDimensionDefinition:
    dimension_key: str
    business_name: str
    table_name: str
    column_name: str
    join_path: str
    data_type: str


@dataclass(frozen=True)
class SemanticTermDefinition:
    term: str
    aliases: list[str]
    mapped_entity_type: str
    mapped_entity_key: str


@dataclass(frozen=True)
class SemanticExampleDefinition:
    title: str
    natural_text: str
    metric_key: str
    dimension_keys: list[str]
    filter_keys: list[str]
    canonical_intent_json: dict[str, Any]
    sql_example: str
    domain_tag: str


@dataclass(frozen=True)
class SemanticTemplateDefinition:
    template_key: str
    title: str
    description: str
    natural_text: str
    metric_key: str
    dimension_keys: list[str]
    filter_keys: list[str]
    canonical_intent_json: dict[str, Any]
    chart_type: str
    category: str


@dataclass(frozen=True)
class SemanticCatalog:
    metrics: dict[str, SemanticMetricDefinition]
    dimensions: dict[str, SemanticDimensionDefinition]
    filters: dict[str, SemanticDimensionDefinition]

    def get_metric(self, metric_key: str | None) -> SemanticMetricDefinition | None:
        if not metric_key:
            return None
        return self.metrics.get(metric_key)

    def get_dimension(self, dimension_key: str | None) -> SemanticDimensionDefinition | None:
        if not dimension_key:
            return None
        return self.dimensions.get(dimension_key)

    def get_filter(self, filter_key: str | None) -> SemanticDimensionDefinition | None:
        if not filter_key:
            return None
        return self.filters.get(filter_key)

    def prompt_summary(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "metrics": [
                {
                    "metric_key": metric.metric_key,
                    "business_name": metric.business_name,
                    "description": metric.description,
                    "grain": metric.grain,
                    "allowed_dimensions": metric.allowed_dimensions,
                    "allowed_filters": metric.allowed_filters,
                    "default_chart": metric.default_chart,
                    "safety_tags": metric.safety_tags,
                }
                for metric in self.metrics.values()
            ],
            "dimensions": [
                {
                    "dimension_key": dimension.dimension_key,
                    "business_name": dimension.business_name,
                    "table_name": dimension.table_name,
                    "column_name": dimension.column_name,
                    "data_type": dimension.data_type,
                }
                for dimension in self.dimensions.values()
            ],
            "filters": [
                {
                    "dimension_key": dimension.dimension_key,
                    "business_name": dimension.business_name,
                    "data_type": dimension.data_type,
                    "allowed_operators": _allowed_operators(dimension.data_type),
                }
                for dimension in self.filters.values()
            ],
        }

def build_semantic_catalog(
    metric_rows: list[Any],
    dimension_rows: list[Any],
) -> SemanticCatalog:
    metrics = {
        row.metric_key: SemanticMetricDefinition(
            metric_key=row.metric_key,
            business_name=row.business_name,
            description=row.description,
            sql_expression_template=row.sql_expression_template,
            grain=row.grain,
            allowed_dimensions=list(row.allowed_dimensions_json or []),
            allowed_filters=list(row.allowed_filters_json or []),
            default_chart=row.default_chart,
            safety_tags=list(row.safety_tags_json or []),
        )
        for row in metric_rows
        if row.is_active
    }
    dimensions = {
        row.dimension_key: SemanticDimensionDefinition(
            dimension_key=row.dimension_key,
            business_name=row.business_name,
            table_name=row.table_name,
            column_name=row.column_name,
            join_path=row.join_path or "",
            data_type=row.data_type,
        )
        for row in dimension_rows
        if row.is_active
    }
    return SemanticCatalog(metrics=metrics, dimensions=dimensions, filters=dict(dimensions))


async def load_semantic_catalog(db: AsyncSession) -> SemanticCatalog:
    metric_rows = await repository.list_metric_catalog_entries(db, active_only=True)
    dimension_rows = await repository.list_dimension_catalog_entries(db, active_only=True)
    return build_semantic_catalog(metric_rows, dimension_rows)


def _render_template(template: str, *, grain: GrainDefinition, dimension_alias: str = "dim_value") -> str:
    return template.format(
        base_alias=grain.base_alias,
        dimension_alias=dimension_alias,
        time_column=grain.time_column,
        time_dimension_column=grain.time_dimension_column,
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _compile_period(date_range: dict[str, Any], *, time_column: str, base_alias: str) -> list[str]:
    field = f"{base_alias}.{time_column}"
    kind = date_range.get("kind")
    if kind == "rolling_days":
        return [f"{field} >= CURRENT_DATE - INTERVAL '{int(date_range['days'])} days'"]
    if kind == "since_date":
        return [f"{field} >= DATE '{date_range['start']}'"]
    if kind == "until_date":
        return [f"{field} < DATE '{date_range['end']}' + INTERVAL '1 day'"]
    if kind == "exact_date":
        return [f"DATE({field}) = DATE '{date_range['date']}'"]
    if kind == "between_dates":
        return [
            f"{field} >= DATE '{date_range['start']}'",
            f"{field} < DATE '{date_range['end']}' + INTERVAL '1 day'",
        ]
    return []


def _allowed_operators(data_type: str) -> list[str]:
    if data_type in {"date", "timestamp", "integer", "numeric"}:
        return ["eq", "in", "between"]
    return ["eq", "in"]


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
            f"Dimension {dimension.dimension_key} requires join_path because it is not on the base grain table."
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
            f"Operator {operator} is not allowed for filter {dimension.dimension_key} ({dimension.data_type})."
        )
    if not values:
        raise SemanticCompilationError(f"Filter {dimension.dimension_key} does not have values.")
    expression, join_sql = _resolve_dimension_sql(dimension, grain=grain)
    if operator == "eq":
        return f"{expression} = {_sql_literal(values[0])}", join_sql
    if operator == "in":
        return f"{expression} IN ({', '.join(_sql_literal(value) for value in values)})", join_sql
    if operator == "between" and len(values) >= 2:
        return f"{expression} BETWEEN {_sql_literal(values[0])} AND {_sql_literal(values[1])}", join_sql
    raise SemanticCompilationError(f"Operator {operator} is not supported for filter {dimension.dimension_key}.")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def compile_interpretation_to_sql(
    interpretation: Interpretation,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> tuple[SqlPlan, str]:
    from app.semantic.compiler import compile_interpretation_to_sql as compile_with_ast

    return compile_with_ast(interpretation, retrieval, catalog)


async def validate_semantic_layer(db: AsyncSession) -> SemanticValidationReport:
    metrics = await repository.list_metric_catalog_entries(db)
    dimensions = await repository.list_dimension_catalog_entries(db)
    terms = await repository.list_semantic_terms(db)
    examples = await repository.list_semantic_examples(db)
    templates = await repository.list_approved_templates(db)

    metric_keys = {item.metric_key for item in metrics if item.is_active}
    dimension_keys = {item.dimension_key for item in dimensions if item.is_active}
    issues: list[SemanticValidationIssue] = []

    for item in metrics:
        issues.extend(
            validate_metric_definition(
                {
                    "metric_key": item.metric_key,
                    "business_name": item.business_name,
                    "description": item.description,
                    "sql_expression_template": item.sql_expression_template,
                    "grain": item.grain,
                    "allowed_dimensions": item.allowed_dimensions_json,
                    "allowed_filters": item.allowed_filters_json,
                    "default_chart": item.default_chart,
                    "safety_tags": item.safety_tags_json,
                },
                dimension_keys=dimension_keys,
                supported_grains=set(GRAIN_REGISTRY),
            ).issues
        )
    for item in dimensions:
        issues.extend(
            validate_dimension_definition(
                {
                    "dimension_key": item.dimension_key,
                    "business_name": item.business_name,
                    "table_name": item.table_name,
                    "column_name": item.column_name,
                    "join_path": item.join_path,
                    "data_type": item.data_type,
                },
                allowed_tables=settings.allowed_analytics_tables,
            ).issues
        )
    for item in terms:
        issues.extend(
            validate_term_definition(
                {
                    "term": item.term,
                    "aliases": item.aliases,
                    "mapped_entity_type": item.mapped_entity_type,
                    "mapped_entity_key": item.mapped_entity_key,
                },
                metric_keys=metric_keys,
                dimension_keys=dimension_keys,
            ).issues
        )
    for item in examples:
        issues.extend(
            validate_example_definition(
                {
                    "title": item.title,
                    "metric_key": item.metric_key,
                    "dimension_keys": item.dimension_keys_json,
                    "filter_keys": item.filter_keys_json,
                    "sql_example": item.sql_example,
                },
                metric_keys=metric_keys,
                dimension_keys=dimension_keys,
            ).issues
        )
    for item in templates:
        issues.extend(
            validate_approved_template_definition(
                {
                    "template_key": item.template_key,
                    "metric_key": item.metric_key,
                    "dimension_keys": item.dimension_keys_json,
                    "filter_keys": item.filter_keys_json,
                    "chart_type": item.chart_type,
                },
                metric_keys=metric_keys,
                dimension_keys=dimension_keys,
            ).issues
        )
    return SemanticValidationReport(issues)


async def _ensure_metric_can_be_deleted(db: AsyncSession, metric_key: str) -> None:
    if await repository.list_examples_for_metric(db, metric_key):
        raise HTTPException(status_code=409, detail="Metric is referenced by semantic_examples.")
    if await repository.list_templates_for_metric(db, metric_key):
        raise HTTPException(status_code=409, detail="Metric is referenced by approved_templates.")
    if await repository.list_terms_for_entity(db, mapped_entity_type="metric", mapped_entity_key=metric_key):
        raise HTTPException(status_code=409, detail="Metric is referenced by semantic_terms.")


async def _ensure_dimension_can_be_deleted(db: AsyncSession, dimension_key: str) -> None:
    metrics = await repository.list_metric_catalog_entries(db)
    for metric in metrics:
        if dimension_key in (metric.allowed_dimensions_json or []) or dimension_key in (metric.allowed_filters_json or []):
            raise HTTPException(status_code=409, detail="Dimension is referenced by metric_catalog.")
    if await repository.list_terms_for_entity(db, mapped_entity_type="dimension", mapped_entity_key=dimension_key):
        raise HTTPException(status_code=409, detail="Dimension is referenced by semantic_terms.")
    for item in await repository.list_semantic_examples(db):
        if dimension_key in (item.dimension_keys_json or []) or dimension_key in (item.filter_keys_json or []):
            raise HTTPException(status_code=409, detail="Dimension is referenced by semantic_examples.")
    for item in await repository.list_approved_templates(db):
        if dimension_key in (item.dimension_keys_json or []) or dimension_key in (item.filter_keys_json or []):
            raise HTTPException(status_code=409, detail="Dimension is referenced by approved_templates.")


async def create_metric_catalog_entry(db: AsyncSession, payload: dict[str, Any], *, updated_by: Any) -> Any:
    report = validate_metric_definition(
        payload,
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
        supported_grains=set(GRAIN_REGISTRY),
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    if await repository.get_metric_catalog_entry(db, payload["metric_key"]):
        raise HTTPException(status_code=409, detail="Metric already exists.")
    instance = repository.build_metric_catalog_entry(payload)
    instance.updated_by = updated_by
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    return instance


async def update_metric_catalog_entry(db: AsyncSession, metric_key: str, payload: dict[str, Any], *, updated_by: Any) -> Any:
    instance = await repository.get_metric_catalog_entry(db, metric_key)
    if not instance:
        raise HTTPException(status_code=404, detail="Metric not found.")
    merged = {
        "metric_key": instance.metric_key,
        "business_name": payload.get("business_name", instance.business_name),
        "description": payload.get("description", instance.description),
        "sql_expression_template": payload.get("sql_expression_template", instance.sql_expression_template),
        "grain": payload.get("grain", instance.grain),
        "allowed_dimensions": payload.get("allowed_dimensions", list(instance.allowed_dimensions_json or [])),
        "allowed_filters": payload.get("allowed_filters", list(instance.allowed_filters_json or [])),
        "default_chart": payload.get("default_chart", instance.default_chart),
        "safety_tags": payload.get("safety_tags", list(instance.safety_tags_json or [])),
        "is_active": payload.get("is_active", instance.is_active),
    }
    report = validate_metric_definition(
        merged,
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
        supported_grains=set(GRAIN_REGISTRY),
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    repository.apply_model_updates(
        instance,
        {
            "business_name": merged["business_name"],
            "description": merged["description"],
            "sql_expression_template": merged["sql_expression_template"],
            "grain": merged["grain"],
            "allowed_dimensions_json": merged["allowed_dimensions"],
            "allowed_filters_json": merged["allowed_filters"],
            "default_chart": merged["default_chart"],
            "safety_tags_json": merged["safety_tags"],
            "is_active": merged["is_active"],
            "updated_by": updated_by,
        },
    )
    await db.commit()
    await db.refresh(instance)
    return instance


async def delete_metric_catalog_entry(db: AsyncSession, metric_key: str) -> None:
    instance = await repository.get_metric_catalog_entry(db, metric_key)
    if not instance:
        raise HTTPException(status_code=404, detail="Metric not found.")
    await _ensure_metric_can_be_deleted(db, metric_key)
    await repository.delete_model_instance(db, instance)
    await db.commit()


async def create_dimension_catalog_entry(db: AsyncSession, payload: dict[str, Any], *, updated_by: Any) -> Any:
    report = validate_dimension_definition(payload, allowed_tables=settings.allowed_analytics_tables)
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    if await repository.get_dimension_catalog_entry(db, payload["dimension_key"]):
        raise HTTPException(status_code=409, detail="Dimension already exists.")
    instance = repository.build_dimension_catalog_entry(payload)
    instance.updated_by = updated_by
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    return instance


async def update_dimension_catalog_entry(
    db: AsyncSession,
    dimension_key: str,
    payload: dict[str, Any],
    *,
    updated_by: Any,
) -> Any:
    instance = await repository.get_dimension_catalog_entry(db, dimension_key)
    if not instance:
        raise HTTPException(status_code=404, detail="Dimension not found.")
    merged = {
        "dimension_key": instance.dimension_key,
        "business_name": payload.get("business_name", instance.business_name),
        "table_name": payload.get("table_name", instance.table_name),
        "column_name": payload.get("column_name", instance.column_name),
        "join_path": payload.get("join_path", instance.join_path),
        "data_type": payload.get("data_type", instance.data_type),
        "is_active": payload.get("is_active", instance.is_active),
    }
    report = validate_dimension_definition(merged, allowed_tables=settings.allowed_analytics_tables)
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    repository.apply_model_updates(
        instance,
        {
            "business_name": merged["business_name"],
            "table_name": merged["table_name"],
            "column_name": merged["column_name"],
            "join_path": merged["join_path"],
            "data_type": merged["data_type"],
            "is_active": merged["is_active"],
            "updated_by": updated_by,
        },
    )
    await db.commit()
    await db.refresh(instance)
    return instance


async def delete_dimension_catalog_entry(db: AsyncSession, dimension_key: str) -> None:
    instance = await repository.get_dimension_catalog_entry(db, dimension_key)
    if not instance:
        raise HTTPException(status_code=404, detail="Dimension not found.")
    await _ensure_dimension_can_be_deleted(db, dimension_key)
    await repository.delete_model_instance(db, instance)
    await db.commit()


async def create_semantic_term_entry(db: AsyncSession, payload: dict[str, Any], *, updated_by: Any) -> Any:
    report = validate_term_definition(
        payload,
        metric_keys={row.metric_key for row in await repository.list_metric_catalog_entries(db, active_only=True)},
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    if await repository.get_semantic_term(db, payload["term"].strip().lower()):
        raise HTTPException(status_code=409, detail="Semantic term already exists.")
    instance = repository.build_semantic_term(payload)
    instance.updated_by = updated_by
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    return instance


async def update_semantic_term_entry(db: AsyncSession, term: str, payload: dict[str, Any], *, updated_by: Any) -> Any:
    instance = await repository.get_semantic_term(db, term.strip().lower())
    if not instance:
        raise HTTPException(status_code=404, detail="Semantic term not found.")
    merged = {
        "term": payload.get("term", instance.term),
        "aliases": payload.get("aliases", list(instance.aliases or [])),
        "mapped_entity_type": payload.get("mapped_entity_type", instance.mapped_entity_type),
        "mapped_entity_key": payload.get("mapped_entity_key", instance.mapped_entity_key),
        "is_active": payload.get("is_active", instance.is_active),
    }
    report = validate_term_definition(
        merged,
        metric_keys={row.metric_key for row in await repository.list_metric_catalog_entries(db, active_only=True)},
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    repository.apply_model_updates(
        instance,
        {
            "term": str(merged["term"]).strip().lower(),
            "aliases": merged["aliases"],
            "mapped_entity_type": merged["mapped_entity_type"],
            "mapped_entity_key": merged["mapped_entity_key"],
            "is_active": merged["is_active"],
            "updated_by": updated_by,
        },
    )
    await db.commit()
    await db.refresh(instance)
    return instance


async def delete_semantic_term_entry(db: AsyncSession, term: str) -> None:
    instance = await repository.get_semantic_term(db, term.strip().lower())
    if not instance:
        raise HTTPException(status_code=404, detail="Semantic term not found.")
    await repository.delete_model_instance(db, instance)
    await db.commit()


async def create_semantic_example_entry(db: AsyncSession, payload: dict[str, Any], *, updated_by: Any) -> Any:
    report = validate_example_definition(
        payload,
        metric_keys={row.metric_key for row in await repository.list_metric_catalog_entries(db, active_only=True)},
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    instance = repository.build_semantic_example(payload)
    instance.updated_by = updated_by
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    return instance


async def update_semantic_example_entry(db: AsyncSession, example_id: Any, payload: dict[str, Any], *, updated_by: Any) -> Any:
    instance = await repository.get_semantic_example(db, example_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Semantic example not found.")
    merged = {
        "title": payload.get("title", instance.title),
        "natural_text": payload.get("natural_text", instance.natural_text),
        "metric_key": payload.get("metric_key", instance.metric_key),
        "dimension_keys": payload.get("dimension_keys", list(instance.dimension_keys_json or [])),
        "filter_keys": payload.get("filter_keys", list(instance.filter_keys_json or [])),
        "canonical_intent_json": payload.get("canonical_intent_json", dict(instance.canonical_intent_json or {})),
        "sql_example": payload.get("sql_example", instance.sql_example),
        "domain_tag": payload.get("domain_tag", instance.domain_tag),
        "is_active": payload.get("is_active", instance.is_active),
    }
    report = validate_example_definition(
        merged,
        metric_keys={row.metric_key for row in await repository.list_metric_catalog_entries(db, active_only=True)},
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    repository.apply_model_updates(
        instance,
        {
            "title": merged["title"],
            "natural_text": merged["natural_text"],
            "metric_key": merged["metric_key"],
            "dimension_keys_json": merged["dimension_keys"],
            "filter_keys_json": merged["filter_keys"],
            "canonical_intent_json": merged["canonical_intent_json"],
            "sql_example": merged["sql_example"],
            "domain_tag": merged["domain_tag"],
            "is_active": merged["is_active"],
            "updated_by": updated_by,
        },
    )
    await db.commit()
    await db.refresh(instance)
    return instance


async def delete_semantic_example_entry(db: AsyncSession, example_id: Any) -> None:
    instance = await repository.get_semantic_example(db, example_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Semantic example not found.")
    await repository.delete_model_instance(db, instance)
    await db.commit()


async def create_approved_template_entry(db: AsyncSession, payload: dict[str, Any], *, updated_by: Any) -> Any:
    report = validate_approved_template_definition(
        payload,
        metric_keys={row.metric_key for row in await repository.list_metric_catalog_entries(db, active_only=True)},
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    if await repository.get_approved_template(db, payload["template_key"]):
        raise HTTPException(status_code=409, detail="Approved template already exists.")
    instance = repository.build_approved_template(payload)
    instance.approved_by = updated_by
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    return instance


async def update_approved_template_entry(
    db: AsyncSession,
    template_key: str,
    payload: dict[str, Any],
    *,
    updated_by: Any,
) -> Any:
    instance = await repository.get_approved_template(db, template_key)
    if not instance:
        raise HTTPException(status_code=404, detail="Approved template not found.")
    merged = {
        "template_key": instance.template_key,
        "title": payload.get("title", instance.title),
        "description": payload.get("description", instance.description),
        "natural_text": payload.get("natural_text", instance.natural_text),
        "metric_key": payload.get("metric_key", instance.metric_key),
        "dimension_keys": payload.get("dimension_keys", list(instance.dimension_keys_json or [])),
        "filter_keys": payload.get("filter_keys", list(instance.filter_keys_json or [])),
        "canonical_intent_json": payload.get("canonical_intent_json", dict(instance.canonical_intent_json or {})),
        "chart_type": payload.get("chart_type", instance.chart_type),
        "category": payload.get("category", instance.category),
        "is_active": payload.get("is_active", instance.is_active),
    }
    report = validate_approved_template_definition(
        merged,
        metric_keys={row.metric_key for row in await repository.list_metric_catalog_entries(db, active_only=True)},
        dimension_keys={row.dimension_key for row in await repository.list_dimension_catalog_entries(db, active_only=True)},
    )
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.as_dict())
    repository.apply_model_updates(
        instance,
        {
            "title": merged["title"],
            "description": merged["description"],
            "natural_text": merged["natural_text"],
            "metric_key": merged["metric_key"],
            "dimension_keys_json": merged["dimension_keys"],
            "filter_keys_json": merged["filter_keys"],
            "canonical_intent_json": merged["canonical_intent_json"],
            "chart_type": merged["chart_type"],
            "category": merged["category"],
            "is_active": merged["is_active"],
            "approved_by": updated_by,
        },
    )
    await db.commit()
    await db.refresh(instance)
    return instance


async def delete_approved_template_entry(db: AsyncSession, template_key: str) -> None:
    instance = await repository.get_approved_template(db, template_key)
    if not instance:
        raise HTTPException(status_code=404, detail="Approved template not found.")
    await repository.delete_model_instance(db, instance)
    await db.commit()
