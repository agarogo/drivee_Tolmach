from dataclasses import dataclass, field
from typing import Any, Literal


Status = Literal[
    "idle",
    "running",
    "clarification_required",
    "blocked",
    "success",
    "sql_error",
    "autofix_running",
    "autofix_failed",
]


@dataclass
class Interpretation:
    intent: str
    metric: str | None = None
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    date_range: dict[str, Any] = field(default_factory=dict)
    grouping: list[str] = field(default_factory=list)
    sorting: dict[str, Any] = field(default_factory=dict)
    comparison: str | None = None
    top: int | None = None
    limit: int = 100
    ambiguity_flags: list[str] = field(default_factory=list)
    dangerous: bool = False
    dangerous_reason: str = ""
    clarification_question: str = ""
    clarification_options: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""
    source: str = "unknown"
    provider_confidence: float = 0.0
    fallback_used: bool = False
    clarification_reasons: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "metric": self.metric,
            "dimensions": self.dimensions,
            "filters": self.filters,
            "date_range": self.date_range,
            "grouping": self.grouping,
            "sorting": self.sorting,
            "comparison": self.comparison,
            "top": self.top,
            "limit": self.limit,
            "ambiguity_flags": self.ambiguity_flags,
            "dangerous": self.dangerous,
            "dangerous_reason": self.dangerous_reason,
            "clarification_question": self.clarification_question,
            "clarification_options": self.clarification_options,
            "reasoning": self.reasoning,
            "source": self.source,
            "provider_confidence": self.provider_confidence,
            "fallback_used": self.fallback_used,
            "clarification_reasons": self.clarification_reasons,
        }


@dataclass
class RetrievalResult:
    semantic_terms: list[dict[str, Any]]
    templates: list[dict[str, Any]]
    examples: list[dict[str, Any]]
    planner_candidates: list[dict[str, Any]] = field(default_factory=list)
    retrieval_mode: str = "lexical_pg_trgm"
    retrieval_explainability: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "semantic_terms": self.semantic_terms,
            "templates": self.templates,
            "examples": self.examples,
            "planner_candidates": self.planner_candidates,
            "retrieval_mode": self.retrieval_mode,
            "retrieval_explainability": self.retrieval_explainability,
        }


@dataclass
class ConfidenceResult:
    score: int
    band: Literal["high", "medium", "low"]
    reasons: list[str]
    ambiguities: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "band": self.band,
            "reasons": self.reasons,
            "ambiguities": self.ambiguities,
        }


@dataclass
class SqlPlan:
    metric: str
    metric_expression: str
    source_table: str
    dimensions: list[str]
    joins: list[str]
    filters: list[str]
    group_by: list[str]
    order_by: str
    limit: int
    chart_type: str
    explanation: list[str]
    metric_label: str = ""
    dimension_labels: dict[str, str] = field(default_factory=dict)
    ast_json: dict[str, Any] = field(default_factory=dict)
    planner_notes: list[dict[str, Any]] = field(default_factory=list)
    clarification_reasons: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "metric_label": self.metric_label,
            "metric_expression": self.metric_expression,
            "source_table": self.source_table,
            "dimensions": self.dimensions,
            "dimension_labels": self.dimension_labels,
            "joins": self.joins,
            "filters": self.filters,
            "group_by": self.group_by,
            "order_by": self.order_by,
            "limit": self.limit,
            "chart_type": self.chart_type,
            "explanation": self.explanation,
            "ast_json": self.ast_json,
            "planner_notes": self.planner_notes,
            "clarification_reasons": self.clarification_reasons,
        }
