from app.api.common import *


router = APIRouter(tags=["Queries"])


@router.post("/queries/run", response_model=QueryOut)
async def run_query(
    payload: QueryRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    question = payload.question.strip()
    chat = await ensure_query_chat(db, user, payload.chat_id, question)
    prior_count = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id))
    if prior_count == 0:
        chat.title = make_chat_title(question)
    user_message = Message(chat_id=chat.id, role="user", content=question, payload={})
    db.add(user_message)
    await db.flush()

    item = await _run_query_workflow_or_503(db, user, question, chat.id)
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


@router.post("/queries/{query_id}/clarify", response_model=QueryOut)
async def clarify_query(
    query_id: UUID,
    payload: QueryClarifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    item = await _run_query_workflow_or_503(db, user, clarified_question, original.chat_id)
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


@router.get("/queries/history", response_model=list[QueryOut])
async def query_history(
    limit: int = ApiQuery(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[QueryOut]:
    rows = list(
        (
            await db.scalars(
                select(Query).where(Query.user_id == user.id).order_by(Query.created_at.desc()).limit(limit)
            )
        ).all()
    )
    return [await query_to_out(db, row) for row in rows]


@router.get("/queries/{query_id}", response_model=QueryOut)
async def get_query(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    return await query_to_out(db, await require_owned_query(db, query_id, user))
