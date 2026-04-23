import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import Interpretation, RetrievalResult
from app.models import SemanticExample, SemanticLayer, Template


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"\W+", text.lower()) if len(token) > 2}


def _score(question_tokens: set[str], text: str, aliases: list[str] | None = None) -> int:
    source = _tokens(text)
    for alias in aliases or []:
        source |= _tokens(alias)
    return len(question_tokens & source)


async def retrieve_context(db: AsyncSession, question: str, interpretation: Interpretation) -> RetrievalResult:
    question_tokens = _tokens(question)
    semantic_rows = list((await db.scalars(select(SemanticLayer))).all())
    template_rows = list(
        (
            await db.scalars(
                select(Template).where(or_(Template.is_public.is_(True), Template.created_by.is_(None)))
            )
        ).all()
    )
    example_rows = list((await db.scalars(select(SemanticExample))).all())

    semantic = sorted(
        [
            (
                _score(question_tokens, f"{row.term} {row.description}", row.aliases)
                + (4 if interpretation.metric and interpretation.metric in row.sql_expression else 0),
                row,
            )
            for row in semantic_rows
        ],
        key=lambda item: item[0],
        reverse=True,
    )
    templates = sorted(
        [
            (
                _score(question_tokens, f"{row.title} {row.description} {row.natural_text}")
                + (2 if row.category in question.lower() else 0),
                row,
            )
            for row in template_rows
        ],
        key=lambda item: item[0],
        reverse=True,
    )
    examples = sorted(
        [
            (
                _score(question_tokens, f"{row.title} {row.natural_text} {row.domain_tag}")
                + (2 if interpretation.metric and interpretation.metric in row.sql_example else 0),
                row,
            )
            for row in example_rows
        ],
        key=lambda item: item[0],
        reverse=True,
    )

    def semantic_dict(row: SemanticLayer, score: int) -> dict[str, Any]:
        return {
            "term": row.term,
            "aliases": row.aliases,
            "sql_expression": row.sql_expression,
            "table_name": row.table_name,
            "description": row.description,
            "metric_type": row.metric_type,
            "dimension_type": row.dimension_type,
            "score": score,
        }

    return RetrievalResult(
        semantic_terms=[semantic_dict(row, score) for score, row in semantic if score > 0][:8],
        templates=[
            {
                "id": str(row.id),
                "title": row.title,
                "natural_text": row.natural_text,
                "category": row.category,
                "chart_type": row.chart_type,
                "score": score,
            }
            for score, row in templates
            if score > 0
        ][:4],
        examples=[
            {
                "title": row.title,
                "natural_text": row.natural_text,
                "sql_example": row.sql_example,
                "domain_tag": row.domain_tag,
                "score": score,
            }
            for score, row in examples
            if score > 0
        ][:4],
    )
