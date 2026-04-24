from app.api.common import *


router = APIRouter(tags=["Chats"])


# Compatibility chat API for previous app shell.
@router.get("/api/chats", response_model=list[ChatOut])
async def list_chats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[ChatOut]:
    rows = list(
        (
            await db.scalars(
                select(Chat).where(Chat.user_id == user.id).order_by(Chat.updated_at.desc(), Chat.id.desc())
            )
        ).all()
    )
    return [await chat_out(db, row) for row in rows]


@router.post("/api/chats", response_model=ChatOut)
async def create_chat(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ChatOut:
    chat = Chat(user_id=user.id, title="Новый запрос")
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return await chat_out(db, chat)


@router.delete("/api/chats/{chat_id}", response_model=ChatDeleteOut)
async def delete_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDeleteOut:
    chat = await require_owned_chat(db, chat_id, user)
    counts = await delete_chat_with_related_data(db, chat)
    await db.commit()
    return ChatDeleteOut(id=chat_id, deleted=True, deleted_related_counts=counts)


@router.get("/api/chats/{chat_id}/messages", response_model=MessagesPage)
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


@router.post("/api/chats/{chat_id}/messages", response_model=AssistantMessageResponse)
async def send_message(
    chat_id: UUID,
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantMessageResponse:
    chat = await require_owned_chat(db, chat_id, user)
    question = payload.question.strip()
    prior_count = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id))
    if prior_count == 0:
        chat.title = make_chat_title(question)
    user_message = Message(chat_id=chat.id, role="user", content=question, payload={})
    db.add(user_message)
    await db.flush()
    query = await _run_query_workflow_or_503(db, user, question, chat_id)
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
