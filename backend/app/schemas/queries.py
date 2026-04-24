from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.answer_contracts import AnswerEnvelope


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
    block_reasons: list[dict[str, Any]] = Field(default_factory=list)
    interpretation: dict[str, Any]
    resolved_request: dict[str, Any]
    semantic_terms: list[dict[str, Any]]
    sql_plan: dict[str, Any]
    sql_explain_plan: dict[str, Any]
    sql_explain_cost: float
    confidence_reasons: list[str]
    ambiguity_flags: list[str]
    rows_returned: int
    execution_ms: int
    provider: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    llm_used: bool = False
    fallback_used: bool = False
    retrieval_used: bool = False
    answer_type_code: int = 5
    answer_type_key: str = "table"
    primary_view_mode: str = "table"
    answer: AnswerEnvelope | None = None
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
