import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


PLATFORM_SCHEMA = "tolmach"


def utcnow() -> datetime:
    return datetime.utcnow()


def uuid_pk() -> uuid.UUID:
    return uuid.uuid4()


class PlatformBase:
    __table_args__ = {"schema": PLATFORM_SCHEMA}


class User(PlatformBase, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    notification_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    chats: Mapped[list["Chat"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    queries: Mapped[list["Query"]] = relationship(back_populates="user")
    reports: Mapped[list["Report"]] = relationship(back_populates="user")


class Invite(PlatformBase, Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tolmach.users.id"),
        nullable=True,
    )
    used_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tolmach.users.id"),
        nullable=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class RefreshToken(PlatformBase, Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255))
    device_hint: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Chat(PlatformBase, Base):
    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tolmach.users.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), default="Новый запрос")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="chats")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(PlatformBase, Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tolmach.chats.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    chat: Mapped[Chat] = relationship(back_populates="messages")


class Query(PlatformBase, Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.users.id"), index=True)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tolmach.chats.id"),
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
    semantic_terms_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    sql_plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    confidence_reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    ambiguity_flags_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rows_returned: Mapped[int] = mapped_column(Integer, default=0)
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    result_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    chart_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ai_answer: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    auto_fix_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="queries")
    events: Mapped[list["QueryEvent"]] = relationship(back_populates="query", cascade="all, delete-orphan")
    guardrail_logs: Mapped[list["SqlGuardrailLog"]] = relationship(back_populates="query", cascade="all, delete-orphan")
    clarifications: Mapped[list["QueryClarification"]] = relationship(back_populates="query", cascade="all, delete-orphan")


class QueryClarification(PlatformBase, Base):
    __tablename__ = "query_clarifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.queries.id"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    chosen_option: Mapped[str] = mapped_column(Text, default="")
    freeform_answer: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    query: Mapped[Query] = relationship(back_populates="clarifications")


class QueryEvent(PlatformBase, Base):
    __tablename__ = "query_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.queries.id"), index=True)
    step_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    query: Mapped[Query] = relationship(back_populates="events")


class SqlGuardrailLog(PlatformBase, Base):
    __tablename__ = "sql_guardrail_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.queries.id"), index=True)
    check_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped[Query] = relationship(back_populates="guardrail_logs")


class Report(PlatformBase, Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.users.id"), index=True)
    query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.queries.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    natural_text: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str] = mapped_column(Text)
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    chart_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="reports")
    versions: Mapped[list["ReportVersion"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    recipients: Mapped[list["ReportRecipient"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportVersion(PlatformBase, Base):
    __tablename__ = "report_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.reports.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    generated_sql: Mapped[str] = mapped_column(Text)
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.users.id"), nullable=True)

    report: Mapped[Report] = relationship(back_populates="versions")


class Schedule(PlatformBase, Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.reports.id"), index=True)
    frequency: Mapped[str] = mapped_column(String(20), default="weekly", index=True)
    run_at_time: Mapped[Any | None] = mapped_column(Time(), nullable=True)
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    report: Mapped[Report] = relationship(back_populates="schedules")
    runs: Mapped[list["ScheduleRun"]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class ScheduleRun(PlatformBase, Base):
    __tablename__ = "schedule_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.schedules.id"), index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.reports.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ok", index=True)
    rows_returned: Mapped[int] = mapped_column(Integer, default=0)
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    schedule: Mapped[Schedule] = relationship(back_populates="runs")


class ReportRecipient(PlatformBase, Base):
    __tablename__ = "report_recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.reports.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report: Mapped[Report] = relationship(back_populates="recipients")


class Template(PlatformBase, Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    natural_text: Mapped[str] = mapped_column(Text)
    canonical_intent_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    chart_type: Mapped[str] = mapped_column(String(32), default="bar")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SemanticLayer(PlatformBase, Base):
    __tablename__ = "semantic_layer"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    term: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sql_expression: Mapped[str] = mapped_column(Text)
    table_name: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    metric_type: Mapped[str] = mapped_column(String(64), default="metric")
    dimension_type: Mapped[str] = mapped_column(String(64), default="")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tolmach.users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SemanticExample(PlatformBase, Base):
    __tablename__ = "semantic_examples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    title: Mapped[str] = mapped_column(String(255))
    natural_text: Mapped[str] = mapped_column(Text)
    canonical_intent_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sql_example: Mapped[str] = mapped_column(Text)
    domain_tag: Mapped[str] = mapped_column(String(64), default="general", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AccessPolicy(PlatformBase, Base):
    __tablename__ = "access_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    role: Mapped[str] = mapped_column(String(20), index=True)
    table_name: Mapped[str] = mapped_column(String(128), index=True)
    allowed_columns_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    row_limit: Mapped[int] = mapped_column(Integer, default=1000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChartPreference(PlatformBase, Base):
    __tablename__ = "chart_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    metric_type: Mapped[str] = mapped_column(String(64), index=True)
    dimension_type: Mapped[str] = mapped_column(String(64), index=True)
    chart_type: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    notes: Mapped[str] = mapped_column(Text, default="")


class City(Base):
    __tablename__ = "cities"

    city_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    country: Mapped[str] = mapped_column(String(64), default="RU", index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Driver(Base):
    __tablename__ = "drivers"

    driver_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.city_id"), index=True)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=5)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    total_trips: Mapped[int] = mapped_column(Integer, default=0)

    city: Mapped[City] = relationship()


class Client(Base):
    __tablename__ = "clients"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.city_id"), index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    city: Mapped[City] = relationship()


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tender_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.city_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("clients.user_id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.driver_id"), index=True)
    offset_hours: Mapped[int] = mapped_column(Integer, default=3)
    status_order: Mapped[str] = mapped_column(String(32), index=True)
    status_tender: Mapped[str] = mapped_column(String(32), index=True)
    order_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tender_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    driverdone_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clientcancel_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    drivercancel_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_modified_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_before_accept_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    distance_in_meters: Mapped[int] = mapped_column(Integer, default=0)
    duration_in_seconds: Mapped[int] = mapped_column(Integer, default=0)
    price_order_local: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    price_tender_local: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    price_start_local: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    city: Mapped[City] = relationship()
    driver: Mapped[Driver] = relationship()
    client: Mapped[Client] = relationship()


# Backward-compatible name for old admin logs views.
QueryLog = Query
