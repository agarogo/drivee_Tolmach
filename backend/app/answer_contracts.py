from __future__ import annotations

from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnswerTypeCode(IntEnum):
    CHAT_HELP = 0
    SINGLE_VALUE = 1
    COMPARISON_TOP = 2
    TREND = 3
    DISTRIBUTION = 4
    TABLE = 5
    FULL_REPORT = 6


class AnswerTypeKey(str, Enum):
    CHAT_HELP = "chat_help"
    SINGLE_VALUE = "single_value"
    COMPARISON_TOP = "comparison_top"
    TREND = "trend"
    DISTRIBUTION = "distribution"
    TABLE = "table"
    FULL_REPORT = "full_report"


class ViewMode(str, Enum):
    CHAT = "chat"
    NUMBER = "number"
    CHART = "chart"
    TABLE = "table"
    REPORT = "report"


class RerenderPolicy(str, Enum):
    LOCKED = "locked"
    CLIENT_SAFE_ONLY = "client_safe_only"
    REQUERY_FOR_INCOMPATIBLE = "requery_for_incompatible"


class ResultGrain(str, Enum):
    CHAT = "chat"
    KPI = "kpi"
    CATEGORY = "category"
    TIME_SERIES = "time_series"
    DISTRIBUTION = "distribution"
    RECORD = "record"
    REPORT = "report"
    UNKNOWN = "unknown"


class DataType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    JSON = "json"
    UNKNOWN = "unknown"


class TableColumn(BaseModel):
    key: str
    label: str
    data_type: DataType = DataType.UNKNOWN


class HelpCard(BaseModel):
    title: str
    body: str
    category: str = "reference"


class ComparisonItem(BaseModel):
    rank: int
    label: str
    value: float | int | None = None
    share_pct: float | None = None
    is_other: bool = False


class TrendPoint(BaseModel):
    label: str
    value: float | int | None = None


class TrendExtrema(BaseModel):
    label: str = ""
    value: float | int | None = None


class ChatHelpResponse(BaseModel):
    kind: Literal["chat_help"] = "chat_help"
    message: str
    help_cards: list[HelpCard] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)


class SingleValueResponse(BaseModel):
    kind: Literal["single_value"] = "single_value"
    metric_key: str = ""
    metric_label: str = ""
    current_value: float | int | str | None = None
    previous_value: float | int | None = None
    delta_abs: float | None = None
    delta_pct: float | None = None
    freshness_timestamp: datetime | None = None
    unit_label: str = ""
    context: str = ""
    availability_note: str = ""
    columns: list[TableColumn] = Field(default_factory=list)
    supporting_rows: list[dict[str, Any]] = Field(default_factory=list)


class ComparisonResponse(BaseModel):
    kind: Literal["comparison_top"] = "comparison_top"
    metric_key: str = ""
    metric_label: str = ""
    dimension_key: str = ""
    dimension_label: str = ""
    items: list[ComparisonItem] = Field(default_factory=list)
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    insight: str = ""


class TrendResponse(BaseModel):
    kind: Literal["trend"] = "trend"
    metric_key: str = ""
    metric_label: str = ""
    time_key: str = ""
    points: list[TrendPoint] = Field(default_factory=list)
    peak: TrendExtrema = Field(default_factory=TrendExtrema)
    low: TrendExtrema = Field(default_factory=TrendExtrema)
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    insight: str = ""


class DistributionResponse(BaseModel):
    kind: Literal["distribution"] = "distribution"
    metric_key: str = ""
    metric_label: str = ""
    dimension_key: str = ""
    dimension_label: str = ""
    items: list[ComparisonItem] = Field(default_factory=list)
    total_value: float = 0.0
    integrity_pct: float = 100.0
    other_bucket_applied: bool = False
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    insight: str = ""


class TableSortSpec(BaseModel):
    key: str = ""
    direction: Literal["asc", "desc"] = "desc"


class TableResponse(BaseModel):
    kind: Literal["table"] = "table"
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_row_count: int = 0
    total_row_count: int | None = None
    pagination_mode: str = "server_ready"
    page_size: int = 25
    page_offset: int = 0
    has_more: bool = False
    sort: TableSortSpec = Field(default_factory=TableSortSpec)
    export_formats: list[str] = Field(default_factory=lambda: ["csv"])


class FullReportKpi(BaseModel):
    key: str
    label: str
    value: float | int | str | None = None
    unit_label: str = ""


class FullReportInsightSection(BaseModel):
    kind: Literal["insight"] = "insight"
    title: str
    body: str


class FullReportChartSection(BaseModel):
    kind: Literal["chart"] = "chart"
    title: str
    chart_type: str
    metric_key: str = ""
    metric_label: str = ""
    x_key: str = ""
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class FullReportTableSection(BaseModel):
    kind: Literal["table"] = "table"
    title: str
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


FullReportSection = FullReportInsightSection | FullReportChartSection | FullReportTableSection


class FullReportActionability(BaseModel):
    rerun_supported: bool = True
    save_supported: bool = True
    schedule_supported: bool = True
    export_formats: list[str] = Field(default_factory=lambda: ["csv"])


class FullReportResponse(BaseModel):
    kind: Literal["full_report"] = "full_report"
    title: str = ""
    summary: str = ""
    kpis: list[FullReportKpi] = Field(default_factory=list)
    sections: list[FullReportSection] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    actionability: FullReportActionability = Field(default_factory=FullReportActionability)
    rerun_supported: bool = True
    save_supported: bool = True


AnswerRenderPayload = (
    ChatHelpResponse
    | SingleValueResponse
    | ComparisonResponse
    | TrendResponse
    | DistributionResponse
    | TableResponse
    | FullReportResponse
)


class AnswerMetadata(BaseModel):
    query_id: UUID | None = None
    chat_id: UUID | None = None
    status: str = ""
    rows_returned: int = 0
    execution_ms: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AnswerExplainability(BaseModel):
    metric: str = ""
    dimensions: list[str] = Field(default_factory=list)
    dimension_labels: dict[str, str] = Field(default_factory=dict)
    period: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    grouping: list[str] = Field(default_factory=list)
    sorting: str = ""
    limit: int = 0
    source: str = ""
    provider_confidence: float = 0.0
    fallback_used: bool = False
    semantic_terms: list[str] = Field(default_factory=list)
    sql_reasoning: list[str] = Field(default_factory=list)
    answer_type_reasoning: str = ""
    view_reasoning: str = ""


class SqlVisibility(BaseModel):
    show_sql_panel: bool = True
    sql: str = ""
    explain_cost: float = 0.0
    explain_plan_available: bool = False


class ViewSwitchOption(BaseModel):
    view_mode: ViewMode
    label: str
    can_switch_without_requery: bool
    requery_required: bool
    reason: str = ""


class CompatibilityInfo(BaseModel):
    compatible_view_modes: list[ViewMode] = Field(default_factory=list)
    can_switch_without_requery: bool = False
    requery_required_for_views: list[ViewMode] = Field(default_factory=list)


class AnswerEnvelope(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    answer_type: AnswerTypeCode
    answer_type_key: AnswerTypeKey
    answer_type_label: str
    answer_type_reason: str
    primary_view_mode: ViewMode
    available_view_modes: list[ViewMode] = Field(default_factory=list)
    rerender_policy: RerenderPolicy = RerenderPolicy.LOCKED
    requires_sql: bool = True
    result_grain: ResultGrain = ResultGrain.UNKNOWN
    can_switch_without_requery: bool = False
    explanation_why_this_type: str = ""
    metadata: AnswerMetadata = Field(default_factory=AnswerMetadata)
    explainability: AnswerExplainability = Field(default_factory=AnswerExplainability)
    sql_visibility: SqlVisibility = Field(default_factory=SqlVisibility)
    render_payload: AnswerRenderPayload | None = None
    switch_options: list[ViewSwitchOption] = Field(default_factory=list)
    compatibility_info: CompatibilityInfo = Field(default_factory=CompatibilityInfo)
