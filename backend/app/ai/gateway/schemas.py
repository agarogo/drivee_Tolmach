from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PeriodSelection(StrictSchema):
    kind: Literal["rolling_days", "since_date", "until_date", "between_dates", "exact_date", "missing"] = "missing"
    days: int | None = None
    start: str | None = None
    end: str | None = None
    date: str | None = None
    label: str = ""


class FilterSelection(StrictSchema):
    dimension_key: str = Field(min_length=1)
    operator: Literal["eq", "in", "between"] = "eq"
    values: list[str] = Field(default_factory=list)


class ClarificationOption(StrictSchema):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    description: str = ""


class IntentExtractionResult(StrictSchema):
    metric_key: str | None = None
    dimension_keys: list[str] = Field(default_factory=list)
    filters: list[FilterSelection] = Field(default_factory=list)
    period: PeriodSelection = Field(default_factory=PeriodSelection)
    limit: int | None = None
    sort_direction: Literal["asc", "desc"] = "desc"
    ambiguities: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""


class ClarificationNeedResult(StrictSchema):
    needs_clarification: bool = False
    question: str = ""
    options: list[ClarificationOption] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""


class SQLPlanDraft(StrictSchema):
    metric_key: str
    dimension_keys: list[str] = Field(default_factory=list)
    filters: list[FilterSelection] = Field(default_factory=list)
    period: PeriodSelection = Field(default_factory=PeriodSelection)
    limit: int | None = None
    sort_direction: Literal["asc", "desc"] = "desc"
    chart_preference: str = "table_only"
    grain: str | None = None
    safety_notes: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""


class AnswerSummaryDraft(StrictSchema):
    headline: str = ""
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
