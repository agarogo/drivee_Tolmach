from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PLATFORM_SCHEMA, PlatformBase, utcnow, uuid_pk


class Query(PlatformBase, Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), index=True)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app.chats.id"),
        nullable=True,
        index=True,
    )
    natural_text: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str] = mapped_column(Text, default="")
    corrected_sql: Mapped[str] = mapped_column(Text, default="")
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    confidence_band: Mapped[str] = mapped_column(String(20), default="low", index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    block_reason: Mapped[str] = mapped_column(Text, default="")
    interpretation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    resolved_request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    semantic_terms_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    sql_plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sql_explain_plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sql_explain_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    confidence_reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    ambiguity_flags_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rows_returned: Mapped[int] = mapped_column(Integer, default=0)
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    answer_type_code: Mapped[int] = mapped_column(Integer, default=5, index=True)
    answer_type_key: Mapped[str] = mapped_column(String(32), default="table", index=True)
    primary_view_mode: Mapped[str] = mapped_column(String(32), default="table")
    answer_envelope_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    result_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    chart_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ai_answer: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    auto_fix_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="queries")
    events: Mapped[list["QueryEvent"]] = relationship("QueryEvent", back_populates="query", cascade="all, delete-orphan")
    guardrail_logs: Mapped[list["SqlGuardrailLog"]] = relationship("SqlGuardrailLog", back_populates="query", cascade="all, delete-orphan")
    clarifications: Mapped[list["QueryClarification"]] = relationship("QueryClarification", back_populates="query", cascade="all, delete-orphan")

class QueryClarification(PlatformBase, Base):
    __tablename__ = "query_clarifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.queries.id"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    chosen_option: Mapped[str] = mapped_column(Text, default="")
    freeform_answer: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    query: Mapped["Query"] = relationship("Query", back_populates="clarifications")

class QueryEvent(PlatformBase, Base):
    __tablename__ = "query_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.queries.id"), index=True)
    step_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    query: Mapped["Query"] = relationship("Query", back_populates="events")

class SqlGuardrailLog(PlatformBase, Base):
    __tablename__ = "sql_guardrail_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.queries.id"), index=True)
    check_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped["Query"] = relationship("Query", back_populates="guardrail_logs")

class QueryResultCache(PlatformBase, Base):
    __tablename__ = "query_result_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    sql_text: Mapped[str] = mapped_column(Text)
    row_limit: Mapped[int] = mapped_column(Integer, default=0)
    explain_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    explain_plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_rows_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class QueryExecutionAudit(PlatformBase, Base):
    __tablename__ = "query_execution_audit"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.queries.id"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    sql_text: Mapped[str] = mapped_column(Text)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    execution_mode: Mapped[str] = mapped_column(String(20), default="database", index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    explain_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    explain_plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# Backward-compatible name for old admin logs views.
QueryLog = Query

