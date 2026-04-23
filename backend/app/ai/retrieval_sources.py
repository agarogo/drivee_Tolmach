from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.semantic import repository as semantic_repository


@dataclass(frozen=True)
class RetrievalSource:
    entity_type: str
    entity_key: str
    source_table: str
    title: str
    search_text: str
    metadata: dict[str, Any]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.search_text.encode("utf-8")).hexdigest()


def _normalize_whitespace(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def build_semantic_term_source(row: Any) -> RetrievalSource:
    aliases = [str(item).strip() for item in (row.aliases or []) if str(item).strip()]
    search_text = _normalize_whitespace(
        " ".join(
            [
                row.term,
                row.mapped_entity_type,
                row.mapped_entity_key,
                " ".join(aliases),
            ]
        )
    )
    return RetrievalSource(
        entity_type="semantic_term",
        entity_key=row.term,
        source_table="app.semantic_terms",
        title=row.term,
        search_text=search_text,
        metadata={
            "term": row.term,
            "aliases": aliases,
            "mapped_entity_type": row.mapped_entity_type,
            "mapped_entity_key": row.mapped_entity_key,
        },
    )


def build_approved_template_source(row: Any) -> RetrievalSource:
    search_text = _normalize_whitespace(
        " ".join(
            [
                row.template_key,
                row.title,
                row.description or "",
                row.natural_text,
                row.metric_key,
                row.category,
                " ".join(row.dimension_keys_json or []),
                " ".join(row.filter_keys_json or []),
            ]
        )
    )
    return RetrievalSource(
        entity_type="approved_template",
        entity_key=row.template_key,
        source_table="app.approved_templates",
        title=row.title,
        search_text=search_text,
        metadata={
            "template_key": row.template_key,
            "title": row.title,
            "description": row.description or "",
            "natural_text": row.natural_text,
            "metric_key": row.metric_key,
            "dimension_keys": list(row.dimension_keys_json or []),
            "filter_keys": list(row.filter_keys_json or []),
            "chart_type": row.chart_type,
            "category": row.category,
        },
    )


def build_semantic_example_source(row: Any) -> RetrievalSource:
    search_text = _normalize_whitespace(
        " ".join(
            [
                row.title,
                row.natural_text,
                row.metric_key,
                row.domain_tag,
                " ".join(row.dimension_keys_json or []),
                " ".join(row.filter_keys_json or []),
            ]
        )
    )
    return RetrievalSource(
        entity_type="semantic_example",
        entity_key=str(row.id),
        source_table="app.semantic_examples",
        title=row.title,
        search_text=search_text,
        metadata={
            "id": str(row.id),
            "title": row.title,
            "natural_text": row.natural_text,
            "metric_key": row.metric_key,
            "dimension_keys": list(row.dimension_keys_json or []),
            "filter_keys": list(row.filter_keys_json or []),
            "sql_example": row.sql_example,
            "domain_tag": row.domain_tag,
        },
    )


async def collect_retrieval_sources(db: AsyncSession) -> list[RetrievalSource]:
    sources: list[RetrievalSource] = []
    for row in await semantic_repository.list_semantic_terms(db, active_only=True):
        sources.append(build_semantic_term_source(row))
    for row in await semantic_repository.list_approved_templates(db, active_only=True):
        sources.append(build_approved_template_source(row))
    for row in await semantic_repository.list_semantic_examples(db, active_only=True):
        sources.append(build_semantic_example_source(row))
    return sources
