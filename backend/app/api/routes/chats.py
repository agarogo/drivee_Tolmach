from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query as ApiQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.utils import chat_out
from app.models import Chat, Message, User
from app.repositories.chats import delete_chat_with_related_data, require_owned_chat
from app.schemas import AssistantMessageResponse, ChatDeleteOut, ChatOut, MessageOut, MessagesPage, SendMessageRequest
from app.services.query_flow import send_message_to_chat

router = APIRouter(prefix="/chats", tags=["Chats"])


@router.get("", response_model=list[ChatOut])
async def list_chats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[ChatOut]:
    rows = list(
        (
            await db.scalars(
                select(Chat).where(Chat.user_id == user.id).order_by(Chat.updated_at.desc(), Chat.id.desc())
            )
        ).all()
    )
    return [await chat_out(db, row) for row in rows]


@router.post("", response_model=ChatOut)
async def create_chat(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ChatOut:
    chat = Chat(user_id=user.id, title="Новый запрос")
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return await chat_out(db, chat)


@router.delete("/{chat_id}", response_model=ChatDeleteOut)
async def delete_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDeleteOut:
    chat = await require_owned_chat(db, chat_id, user)
    counts = await delete_chat_with_related_data(db, chat)
    await db.commit()
    return ChatDeleteOut(id=chat_id, deleted=True, deleted_related_counts=counts)


@router.get("/{chat_id}/messages", response_model=MessagesPage)
async def list_messages(
    chat_id: UUID,
    limit: int = ApiQuery(default=50, ge=1, le=100),
    offset: int = ApiQuery(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessagesPage:
    await require_owned_chat(db, chat_id, user)
    total = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat_id))
    rows = list(
        (
            await db.scalars(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    items = list(reversed(rows))
    return MessagesPage(
        items=[MessageOut.model_validate(item) for item in items],
        has_more=(total or 0) > offset + len(rows),
        next_offset=offset + len(rows),
    )


@router.post("/{chat_id}/messages", response_model=AssistantMessageResponse)
async def send_message(
    chat_id: UUID,
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantMessageResponse:
    return await send_message_to_chat(db, user, chat_id, payload)
