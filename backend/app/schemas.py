from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    role: Literal["user", "admin"] = "user"


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: str
    content: str
    payload: dict
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


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str


class TemplateCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    content: str = Field(min_length=2, max_length=2000)


class ReportCreate(BaseModel):
    chat_id: int | None = None
    title: str = Field(min_length=2, max_length=180)
    question: str
    sql_text: str
    result: list[dict] = Field(default_factory=list)
    chart_spec: dict = Field(default_factory=dict)


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    question: str
    sql_text: str
    result: list
    chart_spec: dict
    schedule: dict
    created_at: datetime


class ScheduleRequest(BaseModel):
    frequency: Literal["daily", "weekly"]
    email: str


class LogOut(BaseModel):
    id: int
    created_at: datetime
    user_email: str | None
    question: str
    generated_sql: str
    status: str
    duration_ms: int
    prompt: str
    raw_response: str
    error: str
