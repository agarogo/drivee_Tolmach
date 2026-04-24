from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PLATFORM_SCHEMA, PlatformBase, utcnow, uuid_pk


class Report(PlatformBase, Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), index=True)
    query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.queries.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    natural_text: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str] = mapped_column(Text)
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    chart_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    semantic_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    latest_version_number: Mapped[int] = mapped_column(Integer, default=1)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(32), default="never", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="reports")
    versions: Mapped[list["ReportVersion"]] = relationship("ReportVersion", back_populates="report", cascade="all, delete-orphan")
    schedules: Mapped[list["Schedule"]] = relationship("Schedule", back_populates="report", cascade="all, delete-orphan")
    recipients: Mapped[list["ReportRecipient"]] = relationship("ReportRecipient", back_populates="report", cascade="all, delete-orphan")
    runs: Mapped[list["ScheduleRun"]] = relationship("ScheduleRun", back_populates="report", cascade="all, delete-orphan")
    artifacts: Mapped[list["ReportArtifact"]] = relationship("ReportArtifact", back_populates="report", cascade="all, delete-orphan")
    deliveries: Mapped[list["ReportDelivery"]] = relationship("ReportDelivery", back_populates="report", cascade="all, delete-orphan")

class ReportVersion(PlatformBase, Base):
    __tablename__ = "report_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.reports.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    generated_sql: Mapped[str] = mapped_column(Text)
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    chart_spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    semantic_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True)

    report: Mapped["Report"] = relationship("Report", back_populates="versions")
    runs: Mapped[list["ScheduleRun"]] = relationship("ScheduleRun", back_populates="report_version")

class Schedule(PlatformBase, Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.reports.id"), index=True)
    frequency: Mapped[str] = mapped_column(String(20), default="weekly", index=True)
    run_at_time: Mapped[Any | None] = mapped_column(Time(), nullable=True)
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    retry_backoff_seconds: Mapped[int] = mapped_column(Integer, default=300)
    last_error_message: Mapped[str] = mapped_column(Text, default="")
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    report: Mapped["Report"] = relationship("Report", back_populates="schedules")
    runs: Mapped[list["ScheduleRun"]] = relationship("ScheduleRun", back_populates="schedule", cascade="all, delete-orphan")

class ScheduleRun(PlatformBase, Base):
    __tablename__ = "schedule_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app.schedules.id"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.reports.id"), index=True)
    report_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app.report_versions.id"),
        nullable=True,
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app.users.id"),
        nullable=True,
        index=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual", index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    retry_backoff_seconds: Mapped[int] = mapped_column(Integer, default=0)
    final_sql: Mapped[str] = mapped_column(Text, default="")
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    chart_spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    semantic_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    execution_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    explain_plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    explain_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    validator_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    structured_error_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    stack_trace: Mapped[str] = mapped_column(Text, default="")
    attempts_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    artifact_summary_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    delivery_summary_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    rows_returned: Mapped[int] = mapped_column(Integer, default=0)
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    schedule: Mapped["Schedule"] = relationship("Schedule", back_populates="runs")
    report: Mapped["Report"] = relationship("Report", back_populates="runs")
    report_version: Mapped["ReportVersion | None"] = relationship("ReportVersion", back_populates="runs")
    artifacts: Mapped[list["ReportArtifact"]] = relationship("ReportArtifact", back_populates="run", cascade="all, delete-orphan")
    deliveries: Mapped[list["ReportDelivery"]] = relationship("ReportDelivery", back_populates="run", cascade="all, delete-orphan")

class ReportRecipient(PlatformBase, Base):
    __tablename__ = "report_recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.reports.id"), index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="email", index=True)
    destination: Mapped[str] = mapped_column(String(255), default="", index=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report: Mapped["Report"] = relationship("Report", back_populates="recipients")
    deliveries: Mapped[list["ReportDelivery"]] = relationship("ReportDelivery", back_populates="recipient")

class ReportArtifact(PlatformBase, Base):
    __tablename__ = "report_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.reports.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.schedule_runs.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(32), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    report: Mapped["Report"] = relationship("Report", back_populates="artifacts")
    run: Mapped["ScheduleRun"] = relationship("ScheduleRun", back_populates="artifacts")

class ReportDelivery(PlatformBase, Base):
    __tablename__ = "report_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.reports.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app.schedule_runs.id"), index=True)
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app.report_recipients.id"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(20), index=True)
    destination: Mapped[str] = mapped_column(String(255), index=True)
    adapter_key: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    external_message_id: Mapped[str] = mapped_column(String(255), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    structured_error_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    stack_trace: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    report: Mapped["Report"] = relationship("Report", back_populates="deliveries")
    run: Mapped["ScheduleRun"] = relationship("ScheduleRun", back_populates="deliveries")
    recipient: Mapped["ReportRecipient | None"] = relationship("ReportRecipient", back_populates="deliveries")
