from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    full_name: str = ""


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    role: Literal["user", "admin"] = "user"
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


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


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    natural_text: str
    canonical_intent_json: dict[str, Any]
    category: str
    chart_type: str
    is_public: bool
    use_count: int
    created_at: datetime


class TemplateCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    natural_text: str = Field(min_length=2, max_length=2000)
    description: str = ""
    canonical_intent_json: dict[str, Any] = Field(default_factory=dict)
    category: str = "general"
    chart_type: str = "bar"
    is_public: bool = False


class QueryEventOut(BaseModel):
    id: UUID
    step_name: str
    status: str
    payload_json: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int


class GuardrailLogOut(BaseModel):
    id: UUID
    check_name: str
    status: str
    severity: str
    message: str
    details_json: dict[str, Any]
    created_at: datetime


class ClarificationOut(BaseModel):
    id: UUID
    question_text: str
    options_json: list[dict[str, Any]]
    chosen_option: str
    freeform_answer: str
    created_at: datetime
    answered_at: datetime | None


class QueryRunRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    chat_id: UUID | None = None


class QueryClarifyRequest(BaseModel):
    chosen_option: str = ""
    freeform_answer: str = ""


class QueryOut(BaseModel):
    id: UUID
    chat_id: UUID | None = None
    natural_text: str
    generated_sql: str
    corrected_sql: str
    confidence_score: float
    confidence_band: str
    status: str
    block_reason: str
    interpretation: dict[str, Any]
    semantic_terms: list[dict[str, Any]]
    sql_plan: dict[str, Any]
    confidence_reasons: list[str]
    ambiguity_flags: list[str]
    rows_returned: int
    execution_ms: int
    chart_type: str
    chart_spec: dict[str, Any]
    result_snapshot: list[dict[str, Any]]
    ai_answer: str
    error_message: str
    auto_fix_attempts: int
    clarifications: list[ClarificationOut] = Field(default_factory=list)
    events: list[QueryEventOut] = Field(default_factory=list)
    guardrail_logs: list[GuardrailLogOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ReportCreate(BaseModel):
    query_id: UUID | None = None
    title: str = Field(min_length=2, max_length=255)
    natural_text: str = ""
    generated_sql: str = ""
    chart_type: str = "table_only"
    chart_spec: dict[str, Any] = Field(default_factory=dict)
    result_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    schedule: dict[str, Any] | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)

    # Backward-compatible fields used by the previous one-page demo.
    chat_id: UUID | None = None
    question: str = ""
    sql_text: str = ""
    result: list[dict[str, Any]] = Field(default_factory=list)


class ReportPatch(BaseModel):
    title: str | None = None
    generated_sql: str | None = None
    chart_type: str | None = None
    chart_spec: dict[str, Any] | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None


class ReportVersionOut(BaseModel):
    id: UUID
    version_number: int
    generated_sql: str
    chart_type: str
    config_json: dict[str, Any]
    created_at: datetime


class ScheduleRunOut(BaseModel):
    id: UUID
    status: str
    rows_returned: int
    execution_ms: int
    error_message: str
    ran_at: datetime


class ScheduleCreate(BaseModel):
    report_id: UUID
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    run_at_time: time | None = None
    day_of_week: int | None = None
    day_of_month: int | None = None
    recipients: list[str] = Field(default_factory=list)
    is_active: bool = True


class SchedulePatch(BaseModel):
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    run_at_time: time | None = None
    day_of_week: int | None = None
    day_of_month: int | None = None
    recipients: list[str] | None = None
    is_active: bool | None = None


class ScheduleRequest(BaseModel):
    frequency: Literal["daily", "weekly", "monthly"]
    email: str


class ScheduleOut(BaseModel):
    id: UUID
    report_id: UUID
    report_title: str
    frequency: str
    run_at_time: time | None
    day_of_week: int | None
    day_of_month: int | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    is_active: bool
    recipients: list[str]
    runs: list[ScheduleRunOut]


class ReportOut(BaseModel):
    id: UUID
    title: str
    natural_text: str
    generated_sql: str
    chart_type: str
    chart_spec: dict[str, Any]
    result_snapshot: list[dict[str, Any]]
    config_json: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    recipients: list[str] = Field(default_factory=list)
    schedules: list[ScheduleOut] = Field(default_factory=list)
    versions: list[ReportVersionOut] = Field(default_factory=list)

    # Backward-compatible aliases for the previous frontend.
    question: str = ""
    sql_text: str = ""
    result: list[dict[str, Any]] = Field(default_factory=list)
    schedule: dict[str, Any] = Field(default_factory=dict)


class SemanticLayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    term: str
    aliases: list[str]
    sql_expression: str
    table_name: str
    description: str
    metric_type: str
    dimension_type: str
    updated_at: datetime


class SemanticLayerCreate(BaseModel):
    term: str = Field(min_length=2, max_length=128)
    aliases: list[str] = Field(default_factory=list)
    sql_expression: str
    table_name: str
    description: str = ""
    metric_type: str = "metric"
    dimension_type: str = ""


class LogOut(BaseModel):
    id: UUID
    created_at: datetime
    user_email: str | None
    question: str
    generated_sql: str
    status: str
    duration_ms: int
    prompt: str
    raw_response: str
    error: str
