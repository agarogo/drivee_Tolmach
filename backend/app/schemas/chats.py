from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.answer_contracts import AnswerEnvelope


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    role: str
    content: str
    payload: dict[str, Any]
    created_at: datetime

class MessagesPage(BaseModel):
    items: list[MessageOut]
    has_more: bool
    next_offset: int

class SendMessageRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)

class AssistantMessageResponse(BaseModel):
    chat: ChatOut
    user_message: MessageOut
    assistant_message: MessageOut

class ChatDeleteOut(BaseModel):
    id: UUID
    deleted: bool = True
    deleted_related_counts: dict[str, int] = Field(default_factory=dict)
