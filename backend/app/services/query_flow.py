from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import assistant_payload_from_query, chat_out, query_to_out, run_query_workflow_or_503
from app.models import Chat, Message, QueryClarification, User
from app.repositories.chats import ensure_query_chat, make_chat_title, require_owned_chat
from app.repositories.queries import require_owned_query
from app.schemas import AssistantMessageResponse, MessageOut, QueryClarifyRequest, QueryOut, QueryRunRequest, SendMessageRequest


async def run_query_for_user(
    db: AsyncSession,
    user: User,
    payload: QueryRunRequest,
) -> QueryOut:
    question = payload.question.strip()
    chat = await ensure_query_chat(db, user, payload.chat_id, question)
    prior_count = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id))
    if prior_count == 0:
        chat.title = make_chat_title(question)
    user_message = Message(chat_id=chat.id, role="user", content=question, payload={})
    db.add(user_message)
    await db.flush()

    item = await run_query_workflow_or_503(db, user, question, chat.id)
    output = await query_to_out(db, item)
    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=item.ai_answer or "Готово.",
        payload=assistant_payload_from_query(output, item),
    )
    chat.updated_at = datetime.utcnow()
    db.add(assistant_message)
    await db.commit()
    return output


async def clarify_query_for_user(
    db: AsyncSession,
    user: User,
    query_id: UUID,
    payload: QueryClarifyRequest,
) -> QueryOut:
    original = await require_owned_query(db, query_id, user)
    clarification = await db.scalar(
        select(QueryClarification)
        .where(QueryClarification.query_id == query_id)
        .order_by(QueryClarification.created_at.desc())
    )
    answer = payload.freeform_answer or payload.chosen_option
    if not answer:
        raise HTTPException(status_code=400, detail="Нужно выбрать вариант или написать уточнение")
    if clarification:
        clarification.chosen_option = payload.chosen_option
        clarification.freeform_answer = payload.freeform_answer
        clarification.answered_at = datetime.utcnow()
    original.status = "clarified"
    await db.flush()
    clarified_question = f"{original.natural_text}. Уточнение: {answer}"
    chat: Chat | None = None
    if original.chat_id:
        chat = await require_owned_chat(db, original.chat_id, user)
        db.add(Message(chat_id=chat.id, role="user", content=answer, payload={"clarifies_query_id": str(original.id)}))
        await db.flush()
    item = await run_query_workflow_or_503(db, user, clarified_question, original.chat_id)
    output = await query_to_out(db, item)
    if chat:
        db.add(
            Message(
                chat_id=chat.id,
                role="assistant",
                content=item.ai_answer or "Готово.",
                payload=assistant_payload_from_query(output, item),
            )
        )
        chat.updated_at = datetime.utcnow()
        await db.commit()
    return output


async def send_message_to_chat(
    db: AsyncSession,
    user: User,
    chat_id: UUID,
    payload: SendMessageRequest,
) -> AssistantMessageResponse:
    chat = await require_owned_chat(db, chat_id, user)
    question = payload.question.strip()
    prior_count = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id))
    if prior_count == 0:
        chat.title = make_chat_title(question)
    user_message = Message(chat_id=chat.id, role="user", content=question, payload={})
    db.add(user_message)
    await db.flush()
    query = await run_query_workflow_or_503(db, user, question, chat_id)
    output = await query_to_out(db, query)
    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=query.ai_answer,
        payload=assistant_payload_from_query(output, query),
    )
    chat.updated_at = datetime.utcnow()
    db.add(assistant_message)
    await db.commit()
    await db.refresh(chat)
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    return AssistantMessageResponse(
        chat=await chat_out(db, chat),
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
    )
