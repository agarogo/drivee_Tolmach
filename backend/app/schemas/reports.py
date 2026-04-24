from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.answer_contracts import AnswerEnvelope


class ReportCreate(BaseModel):
    query_id: UUID | None = None
    title: str = Field(min_length=2, max_length=255)
    natural_text: str = ""
    generated_sql: str = ""
    chart_type: str = "table_only"
    chart_spec: dict[str, Any] = Field(default_factory=dict)
    semantic_snapshot: dict[str, Any] = Field(default_factory=dict)
    result_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    delivery_targets: list["ReportRecipientIn"] = Field(default_factory=list)
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
    semantic_snapshot: dict[str, Any] | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None

class ReportRecipientIn(BaseModel):
    channel: Literal["email", "slack"] = "email"
    destination: str = Field(min_length=2, max_length=255)
    config_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

class ReportRecipientOut(BaseModel):
    id: UUID
    channel: str
    destination: str
    is_active: bool
    config_json: dict[str, Any] = Field(default_factory=dict)
    last_sent_at: datetime | None = None
    added_at: datetime

class ReportArtifactOut(BaseModel):
    id: UUID
    artifact_type: str
    file_name: str
    file_path: str
    content_type: str
    file_size_bytes: int
    checksum_sha256: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

class ReportDeliveryOut(BaseModel):
    id: UUID
    channel: str
    destination: str
    adapter_key: str
    status: str
    attempt_count: int
    external_message_id: str
    error_message: str
    structured_error_json: dict[str, Any] = Field(default_factory=dict)
    stack_trace: str
    details_json: dict[str, Any] = Field(default_factory=dict)
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

class ReportVersionOut(BaseModel):
    id: UUID
    version_number: int
    generated_sql: str
    chart_type: str
    chart_spec_json: dict[str, Any] = Field(default_factory=dict)
    semantic_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    config_json: dict[str, Any]
    created_at: datetime

class ScheduleRunOut(BaseModel):
    id: UUID
    schedule_id: UUID | None = None
    report_id: UUID
    report_version_id: UUID | None = None
    requested_by_user_id: UUID | None = None
    trigger_type: str = "manual"
    status: str
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    next_retry_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 0
    retry_backoff_seconds: int = 0
    final_sql: str = ""
    chart_type: str = "table_only"
    chart_spec_json: dict[str, Any] = Field(default_factory=dict)
    semantic_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    result_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    execution_fingerprint: str = ""
    explain_plan_json: dict[str, Any] = Field(default_factory=dict)
    explain_cost: float = 0
    validator_summary_json: dict[str, Any] = Field(default_factory=dict)
    structured_error_json: dict[str, Any] = Field(default_factory=dict)
    stack_trace: str = ""
    attempts_json: list[dict[str, Any]] = Field(default_factory=list)
    artifact_summary_json: list[dict[str, Any]] = Field(default_factory=list)
    delivery_summary_json: list[dict[str, Any]] = Field(default_factory=list)
    rows_returned: int
    execution_ms: int
    error_message: str
    ran_at: datetime
    artifacts: list[ReportArtifactOut] = Field(default_factory=list)
    deliveries: list[ReportDeliveryOut] = Field(default_factory=list)

class ScheduleCreate(BaseModel):
    report_id: UUID
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    run_at_time: time | None = None
    day_of_week: int | None = None
    day_of_month: int | None = None
    recipients: list[str] = Field(default_factory=list)
    delivery_targets: list[ReportRecipientIn] = Field(default_factory=list)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: int = Field(default=300, ge=30, le=86400)
    is_active: bool = True

class SchedulePatch(BaseModel):
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    run_at_time: time | None = None
    day_of_week: int | None = None
    day_of_month: int | None = None
    recipients: list[str] | None = None
    delivery_targets: list[ReportRecipientIn] | None = None
    max_retries: int | None = Field(default=None, ge=0, le=10)
    retry_backoff_seconds: int | None = Field(default=None, ge=30, le=86400)
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
    max_retries: int = 0
    retry_backoff_seconds: int = 0
    last_error_message: str = ""
    last_error_at: datetime | None = None
    is_active: bool
    recipients: list[str]
    delivery_targets: list[ReportRecipientOut] = Field(default_factory=list)
    runs: list[ScheduleRunOut]

class ReportOut(BaseModel):
    id: UUID
    title: str
    natural_text: str
    generated_sql: str
    chart_type: str
    chart_spec: dict[str, Any]
    semantic_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    result_snapshot: list[dict[str, Any]]
    config_json: dict[str, Any]
    is_active: bool
    latest_version_number: int = 1
    last_run_at: datetime | None = None
    last_run_status: str = "never"
    created_at: datetime
    updated_at: datetime
    recipients: list[str] = Field(default_factory=list)
    delivery_targets: list[ReportRecipientOut] = Field(default_factory=list)
    schedules: list[ScheduleOut] = Field(default_factory=list)
    versions: list[ReportVersionOut] = Field(default_factory=list)
    latest_runs: list[ScheduleRunOut] = Field(default_factory=list)

    # Backward-compatible aliases for the previous frontend.
    question: str = ""
    sql_text: str = ""
    result: list[dict[str, Any]] = Field(default_factory=list)
    schedule: dict[str, Any] = Field(default_factory=dict)



ReportCreate.model_rebuild()
ScheduleCreate.model_rebuild()
SchedulePatch.model_rebuild()
