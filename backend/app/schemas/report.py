from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


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

    question: str = ""
    sql_text: str = ""
    result: list[dict[str, Any]] = Field(default_factory=list)
    schedule: dict[str, Any] = Field(default_factory=dict)
