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


class ChatDeleteOut(BaseModel):
    id: UUID
    deleted: bool = True
    deleted_related_counts: dict[str, int] = Field(default_factory=dict)


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


class SemanticLayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    term: str
    semantic_key: str
    item_kind: str
    aliases: list[str]
    sql_expression: str
    table_name: str
    description: str
    metric_type: str
    dimension_type: str
    semantic_config_json: dict[str, Any]
    updated_at: datetime


class SemanticLayerCreate(BaseModel):
    term: str = Field(min_length=2, max_length=128)
    semantic_key: str = Field(min_length=2, max_length=128)
    item_kind: Literal["metric", "dimension", "filter", "legacy"] = "legacy"
    aliases: list[str] = Field(default_factory=list)
    sql_expression: str
    table_name: str
    description: str = ""
    metric_type: str = "metric"
    dimension_type: str = ""
    semantic_config_json: dict[str, Any] = Field(default_factory=dict)


class MetricCatalogBase(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    description: str = ""
    sql_expression_template: str = Field(min_length=2)
    grain: str = Field(min_length=2, max_length=64)
    allowed_dimensions: list[str] = Field(default_factory=list)
    allowed_filters: list[str] = Field(default_factory=list)
    default_chart: str = "table_only"
    safety_tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class MetricCatalogCreate(MetricCatalogBase):
    metric_key: str = Field(min_length=2, max_length=128)


class MetricCatalogPatch(BaseModel):
    business_name: str | None = None
    description: str | None = None
    sql_expression_template: str | None = None
    grain: str | None = None
    allowed_dimensions: list[str] | None = None
    allowed_filters: list[str] | None = None
    default_chart: str | None = None
    safety_tags: list[str] | None = None
    is_active: bool | None = None


class MetricCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    metric_key: str
    business_name: str
    description: str
    sql_expression_template: str
    grain: str
    allowed_dimensions: list[str] = Field(validation_alias="allowed_dimensions_json")
    allowed_filters: list[str] = Field(validation_alias="allowed_filters_json")
    default_chart: str
    safety_tags: list[str] = Field(validation_alias="safety_tags_json")
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DimensionCatalogBase(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    table_name: str = Field(min_length=2, max_length=128)
    column_name: str = Field(min_length=1)
    join_path: str = ""
    data_type: str = Field(min_length=2, max_length=32)
    is_active: bool = True


class DimensionCatalogCreate(DimensionCatalogBase):
    dimension_key: str = Field(min_length=2, max_length=128)


class DimensionCatalogPatch(BaseModel):
    business_name: str | None = None
    table_name: str | None = None
    column_name: str | None = None
    join_path: str | None = None
    data_type: str | None = None
    is_active: bool | None = None


class DimensionCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dimension_key: str
    business_name: str
    table_name: str
    column_name: str
    join_path: str
    data_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SemanticTermBase(BaseModel):
    aliases: list[str] = Field(default_factory=list)
    mapped_entity_type: Literal["metric", "dimension", "filter"]
    mapped_entity_key: str = Field(min_length=2, max_length=128)
    is_active: bool = True


class SemanticTermCreate(SemanticTermBase):
    term: str = Field(min_length=2, max_length=128)


class SemanticTermPatch(BaseModel):
    term: str | None = None
    aliases: list[str] | None = None
    mapped_entity_type: Literal["metric", "dimension", "filter"] | None = None
    mapped_entity_key: str | None = None
    is_active: bool | None = None


class SemanticTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    term: str
    aliases: list[str]
    mapped_entity_type: str
    mapped_entity_key: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SemanticExampleBase(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    natural_text: str = Field(min_length=2)
    metric_key: str = Field(min_length=2, max_length=128)
    dimension_keys: list[str] = Field(default_factory=list)
    filter_keys: list[str] = Field(default_factory=list)
    canonical_intent_json: dict[str, Any] = Field(default_factory=dict)
    sql_example: str = Field(min_length=2)
    domain_tag: str = "general"
    is_active: bool = True


class SemanticExampleCreate(SemanticExampleBase):
    pass


class SemanticExamplePatch(BaseModel):
    title: str | None = None
    natural_text: str | None = None
    metric_key: str | None = None
    dimension_keys: list[str] | None = None
    filter_keys: list[str] | None = None
    canonical_intent_json: dict[str, Any] | None = None
    sql_example: str | None = None
    domain_tag: str | None = None
    is_active: bool | None = None


class SemanticExampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    natural_text: str
    metric_key: str
    dimension_keys: list[str] = Field(validation_alias="dimension_keys_json")
    filter_keys: list[str] = Field(validation_alias="filter_keys_json")
    canonical_intent_json: dict[str, Any]
    sql_example: str
    domain_tag: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApprovedTemplateBase(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str = ""
    natural_text: str = Field(min_length=2)
    metric_key: str = Field(min_length=2, max_length=128)
    dimension_keys: list[str] = Field(default_factory=list)
    filter_keys: list[str] = Field(default_factory=list)
    canonical_intent_json: dict[str, Any] = Field(default_factory=dict)
    chart_type: str = "table_only"
    category: str = "general"
    is_active: bool = True


class ApprovedTemplateCreate(ApprovedTemplateBase):
    template_key: str = Field(min_length=2, max_length=128)


class ApprovedTemplatePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    natural_text: str | None = None
    metric_key: str | None = None
    dimension_keys: list[str] | None = None
    filter_keys: list[str] | None = None
    canonical_intent_json: dict[str, Any] | None = None
    chart_type: str | None = None
    category: str | None = None
    is_active: bool | None = None


class ApprovedTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_key: str
    title: str
    description: str
    natural_text: str
    metric_key: str
    dimension_keys: list[str] = Field(validation_alias="dimension_keys_json")
    filter_keys: list[str] = Field(validation_alias="filter_keys_json")
    canonical_intent_json: dict[str, Any]
    chart_type: str
    category: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SemanticValidationIssueOut(BaseModel):
    level: str
    code: str
    entity_type: str
    entity_key: str
    message: str


class SemanticValidationReportOut(BaseModel):
    ok: bool
    issues: list[SemanticValidationIssueOut] = Field(default_factory=list)


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


class SchedulerSummaryOut(BaseModel):
    worker_enabled: bool
    queued_runs: int
    running_runs: int
    failed_runs: int
    succeeded_runs_24h: int
    due_schedules: int
    retrying_runs: int


ReportCreate.model_rebuild()
ScheduleCreate.model_rebuild()
SchedulePatch.model_rebuild()
