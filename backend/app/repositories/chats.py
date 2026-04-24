from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chat, Message, Query, QueryClarification, QueryExecutionAudit, QueryEvent, Report, SqlGuardrailLog, User


def make_chat_title(question: str) -> str:
    compact = " ".join(question.strip().split())
    if len(compact) <= 30:
        return compact
    return compact[:29].rstrip() + "..."


async def require_owned_chat(db: AsyncSession, chat_id: UUID, user: User) -> Chat:
    chat = await db.get(Chat, chat_id)
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Чат не найден")
    return chat


async def ensure_query_chat(db: AsyncSession, user: User, chat_id: UUID | None, question: str) -> Chat:
    if chat_id:
        return await require_owned_chat(db, chat_id, user)
    chat = Chat(user_id=user.id, title=make_chat_title(question))
    db.add(chat)
    await db.flush()
    return chat


async def delete_chat_with_related_data(db: AsyncSession, chat: Chat) -> dict[str, int]:
    query_ids = list((await db.scalars(select(Query.id).where(Query.chat_id == chat.id))).all())
    counts = {
        "messages": int(await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id)) or 0),
        "queries": len(query_ids),
        "clarifications": 0,
        "events": 0,
        "guardrail_logs": 0,
        "reports_detached": 0,
        "query_audits_detached": 0,
    }
    if query_ids:
        counts["clarifications"] = int(
            await db.scalar(select(func.count(QueryClarification.id)).where(QueryClarification.query_id.in_(query_ids))) or 0
        )
        counts["events"] = int(
            await db.scalar(select(func.count(QueryEvent.id)).where(QueryEvent.query_id.in_(query_ids))) or 0
        )
        counts["guardrail_logs"] = int(
            await db.scalar(select(func.count(SqlGuardrailLog.id)).where(SqlGuardrailLog.query_id.in_(query_ids))) or 0
        )
        counts["reports_detached"] = int(
            await db.scalar(select(func.count(Report.id)).where(Report.query_id.in_(query_ids))) or 0
        )
        counts["query_audits_detached"] = int(
            await db.scalar(select(func.count(QueryExecutionAudit.id)).where(QueryExecutionAudit.query_id.in_(query_ids))) or 0
        )

        await db.execute(update(Report).where(Report.query_id.in_(query_ids)).values(query_id=None, updated_at=datetime.utcnow()))
        await db.execute(update(QueryExecutionAudit).where(QueryExecutionAudit.query_id.in_(query_ids)).values(query_id=None))
        await db.execute(delete(QueryClarification).where(QueryClarification.query_id.in_(query_ids)))
        await db.execute(delete(QueryEvent).where(QueryEvent.query_id.in_(query_ids)))
        await db.execute(delete(SqlGuardrailLog).where(SqlGuardrailLog.query_id.in_(query_ids)))
        await db.execute(delete(Query).where(Query.id.in_(query_ids)))

    await db.execute(delete(Message).where(Message.chat_id == chat.id))
    await db.delete(chat)
    await db.flush()
    return counts
