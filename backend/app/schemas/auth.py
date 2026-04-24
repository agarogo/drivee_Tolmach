from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.answer_contracts import AnswerEnvelope


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    full_name: str = ""

class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    role: Literal["user"] = "user"
    full_name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    user: UserOut

class LogoutResponse(BaseModel):
    ok: bool = True
