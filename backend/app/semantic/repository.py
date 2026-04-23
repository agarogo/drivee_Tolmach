from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApprovedTemplate, DimensionCatalog, MetricCatalog, SemanticExample, SemanticTerm


async def list_metric_catalog_entries(db: AsyncSession, *, active_only: bool = False) -> list[MetricCatalog]:
    stmt = select(MetricCatalog).order_by(MetricCatalog.metric_key.asc())
    if active_only:
        stmt = stmt.where(MetricCatalog.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_metric_catalog_entry(db: AsyncSession, metric_key: str) -> MetricCatalog | None:
    return await db.scalar(select(MetricCatalog).where(MetricCatalog.metric_key == metric_key))


async def list_dimension_catalog_entries(db: AsyncSession, *, active_only: bool = False) -> list[DimensionCatalog]:
    stmt = select(DimensionCatalog).order_by(DimensionCatalog.dimension_key.asc())
    if active_only:
        stmt = stmt.where(DimensionCatalog.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_dimension_catalog_entry(db: AsyncSession, dimension_key: str) -> DimensionCatalog | None:
    return await db.scalar(select(DimensionCatalog).where(DimensionCatalog.dimension_key == dimension_key))


async def list_semantic_terms(db: AsyncSession, *, active_only: bool = False) -> list[SemanticTerm]:
    stmt = select(SemanticTerm).order_by(SemanticTerm.term.asc())
    if active_only:
        stmt = stmt.where(SemanticTerm.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_semantic_term(db: AsyncSession, term: str) -> SemanticTerm | None:
    return await db.scalar(select(SemanticTerm).where(SemanticTerm.term == term.lower()))


async def list_semantic_examples(db: AsyncSession, *, active_only: bool = False) -> list[SemanticExample]:
    stmt = select(SemanticExample).order_by(SemanticExample.title.asc())
    if active_only:
        stmt = stmt.where(SemanticExample.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_semantic_example(db: AsyncSession, example_id: Any) -> SemanticExample | None:
    return await db.get(SemanticExample, example_id)


async def list_approved_templates(db: AsyncSession, *, active_only: bool = False) -> list[ApprovedTemplate]:
    stmt = select(ApprovedTemplate).order_by(ApprovedTemplate.category.asc(), ApprovedTemplate.title.asc())
    if active_only:
        stmt = stmt.where(ApprovedTemplate.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_approved_template(db: AsyncSession, template_key: str) -> ApprovedTemplate | None:
    return await db.scalar(select(ApprovedTemplate).where(ApprovedTemplate.template_key == template_key))


def apply_model_updates(instance: Any, payload: dict[str, Any]) -> Any:
    for key, value in payload.items():
        setattr(instance, key, value)
    return instance


def build_metric_catalog_entry(payload: dict[str, Any]) -> MetricCatalog:
    return MetricCatalog(
        metric_key=payload["metric_key"],
        business_name=payload["business_name"],
        description=payload.get("description", ""),
        sql_expression_template=payload["sql_expression_template"],
        grain=payload["grain"],
        allowed_dimensions_json=list(payload.get("allowed_dimensions") or []),
        allowed_filters_json=list(payload.get("allowed_filters") or []),
        default_chart=payload.get("default_chart", "table_only"),
        safety_tags_json=list(payload.get("safety_tags") or []),
        is_active=bool(payload.get("is_active", True)),
    )


def build_dimension_catalog_entry(payload: dict[str, Any]) -> DimensionCatalog:
    return DimensionCatalog(
        dimension_key=payload["dimension_key"],
        business_name=payload["business_name"],
        table_name=payload["table_name"],
        column_name=payload["column_name"],
        join_path=payload.get("join_path", ""),
        data_type=payload["data_type"],
        is_active=bool(payload.get("is_active", True)),
    )


def build_semantic_term(payload: dict[str, Any]) -> SemanticTerm:
    return SemanticTerm(
        term=payload["term"].strip().lower(),
        aliases=list(payload.get("aliases") or []),
        mapped_entity_type=payload["mapped_entity_type"],
        mapped_entity_key=payload["mapped_entity_key"],
        is_active=bool(payload.get("is_active", True)),
    )


def build_semantic_example(payload: dict[str, Any]) -> SemanticExample:
    return SemanticExample(
        title=payload["title"],
        natural_text=payload["natural_text"],
        canonical_intent_json=dict(payload.get("canonical_intent_json") or {}),
        sql_example=payload["sql_example"],
        domain_tag=payload.get("domain_tag", "general"),
        metric_key=payload["metric_key"],
        dimension_keys_json=list(payload.get("dimension_keys") or []),
        filter_keys_json=list(payload.get("filter_keys") or []),
        is_active=bool(payload.get("is_active", True)),
    )


def build_approved_template(payload: dict[str, Any]) -> ApprovedTemplate:
    return ApprovedTemplate(
        template_key=payload["template_key"],
        title=payload["title"],
        description=payload.get("description", ""),
        natural_text=payload["natural_text"],
        metric_key=payload["metric_key"],
        dimension_keys_json=list(payload.get("dimension_keys") or []),
        filter_keys_json=list(payload.get("filter_keys") or []),
        canonical_intent_json=dict(payload.get("canonical_intent_json") or {}),
        chart_type=payload.get("chart_type", "table_only"),
        category=payload.get("category", "general"),
        is_active=bool(payload.get("is_active", True)),
    )


async def delete_model_instance(db: AsyncSession, instance: Any) -> None:
    await db.delete(instance)


async def delete_semantic_terms_for_mapping(
    db: AsyncSession,
    *,
    mapped_entity_type: str,
    mapped_entity_key: str,
) -> None:
    await db.execute(
        delete(SemanticTerm).where(
            SemanticTerm.mapped_entity_type == mapped_entity_type,
            SemanticTerm.mapped_entity_key == mapped_entity_key,
        )
    )


async def list_examples_for_metric(db: AsyncSession, metric_key: str) -> Sequence[SemanticExample]:
    return list((await db.scalars(select(SemanticExample).where(SemanticExample.metric_key == metric_key))).all())


async def list_templates_for_metric(db: AsyncSession, metric_key: str) -> Sequence[ApprovedTemplate]:
    return list((await db.scalars(select(ApprovedTemplate).where(ApprovedTemplate.metric_key == metric_key))).all())


async def list_terms_for_entity(
    db: AsyncSession,
    *,
    mapped_entity_type: str,
    mapped_entity_key: str,
) -> Sequence[SemanticTerm]:
    return list(
        (
            await db.scalars(
                select(SemanticTerm).where(
                    SemanticTerm.mapped_entity_type == mapped_entity_type,
                    SemanticTerm.mapped_entity_key == mapped_entity_key,
                )
            )
        ).all()
    )
