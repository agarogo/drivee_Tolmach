from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


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


class QueryExecutionCacheEntryOut(BaseModel):
    fingerprint: str
    role: str
    row_count: int
    hit_count: int
    expires_at: str
    updated_at: str
    sample_explain: dict[str, Any]


class QueryExecutionCacheStatsOut(BaseModel):
    cache_enabled: bool
    ttl_seconds: int
    total_entries: int
    active_entries: int
    expired_entries: int
    total_hit_count: int
    avg_row_count: float
    recent_entries: list[QueryExecutionCacheEntryOut] = Field(default_factory=list)


class QueryExecutionAuditOut(BaseModel):
    id: UUID
    query_id: UUID | None = None
    fingerprint: str
    role: str
    cache_hit: bool
    execution_mode: str
    row_count: int
    execution_ms: int
    explain_cost: float
    status: str
    error_message: str
    details: dict[str, Any] = Field(default_factory=dict)
    sample_explain: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class QueryExecutionSummaryOut(BaseModel):
    sample_size: int
    cache_hit_rate: float
    avg_execution_ms: float
    p95_target_ms: int


class BenchmarkPresetOut(BaseModel):
    key: str
    title: str
    question: str
