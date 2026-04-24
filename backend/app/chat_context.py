from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Query


FOLLOW_UP_PREFIXES = (
    "а ",
    "а по",
    "теперь",
    "тогда",
    "и по",
    "и еще",
    "и ещё",
    "только",
    "what about",
    "and now",
    "same",
    "same but",
    "now show",
)


@dataclass(frozen=True)
class ChatContinuationContext:
    effective_question: str
    context_json: dict[str, Any]


def _looks_like_follow_up(question: str) -> bool:
    normalized = " ".join(question.strip().lower().split())
    if not normalized:
        return False
    if len(normalized) <= 32:
        return True
    return any(normalized.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES)


def _query_summary(item: Query) -> dict[str, Any]:
    resolved = dict(item.resolved_request_json or {})
    interpretation = dict(item.interpretation_json or {})
    return {
        "query_id": str(item.id),
        "status": item.status,
        "question": item.natural_text,
        "metric": resolved.get("metric") or interpretation.get("metric") or "",
        "dimensions": list(resolved.get("dimensions") or interpretation.get("dimensions") or []),
        "filters": resolved.get("filters") or interpretation.get("filters") or {},
        "period": resolved.get("period") or interpretation.get("date_range") or {},
        "semantic_terms": [item.get("term") for item in (item.semantic_terms_json or [])[:5] if item.get("term")],
        "answer_type": item.answer_type_key,
    }


async def build_chat_continuation_context(
    db: AsyncSession,
    *,
    user_id: UUID,
    chat_id: UUID | None,
    question: str,
    window_size: int = 4,
) -> ChatContinuationContext:
    if not chat_id:
        return ChatContinuationContext(effective_question=question, context_json={})

    stmt = (
        select(Query)
        .where(Query.user_id == user_id, Query.chat_id == chat_id)
        .order_by(Query.created_at.desc())
        .limit(max(1, window_size))
    )
    rows = list((await db.scalars(stmt)).all())
    if not rows:
        return ChatContinuationContext(effective_question=question, context_json={})

    summaries = [_query_summary(item) for item in rows]
    successful = next((item for item in summaries if item["status"] == "success"), None)
    clarification = next((item for item in summaries if item["status"] == "clarification_required"), None)
    should_apply = _looks_like_follow_up(question) and (successful is not None or clarification is not None)
    if not should_apply:
        return ChatContinuationContext(
            effective_question=question,
            context_json={"recent_turns": list(reversed(summaries))},
        )

    anchor = successful or clarification or summaries[0]
    compact_context = {
        "chat_id": str(chat_id),
        "follow_up_applied": True,
        "anchor_query_id": anchor["query_id"],
        "anchor_answer_type": anchor["answer_type"],
        "anchor_metric": anchor["metric"],
        "anchor_dimensions": anchor["dimensions"],
        "anchor_filters": anchor["filters"],
        "anchor_period": anchor["period"],
        "recent_turns": list(reversed(summaries)),
    }
    context_lines = [
        "Conversation context from the current chat:",
        f"- Previous metric: {anchor['metric'] or 'not resolved'}",
        f"- Previous breakdown: {', '.join(anchor['dimensions']) if anchor['dimensions'] else 'without breakdown'}",
        f"- Previous period: {json.dumps(anchor['period'], ensure_ascii=False, default=str)}",
        f"- Previous filters: {json.dumps(anchor['filters'], ensure_ascii=False, default=str)}",
        "- Reuse this context only when the new user request does not override it explicitly.",
    ]
    effective_question = f"{question.strip()}\n\n" + "\n".join(context_lines)
    return ChatContinuationContext(effective_question=effective_question, context_json=compact_context)
