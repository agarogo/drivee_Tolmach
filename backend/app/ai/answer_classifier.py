from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.answer_contracts import AnswerTypeCode, AnswerTypeKey, ViewMode
from app.ai.types import RetrievalResult


ANSWER_TYPE_LABELS: dict[AnswerTypeCode, str] = {
    AnswerTypeCode.CHAT_HELP: "Chat Help",
    AnswerTypeCode.SINGLE_VALUE: "Single KPI",
    AnswerTypeCode.COMPARISON_TOP: "Comparison / Top",
    AnswerTypeCode.TREND: "Trend",
    AnswerTypeCode.DISTRIBUTION: "Distribution",
    AnswerTypeCode.TABLE: "Table",
    AnswerTypeCode.FULL_REPORT: "Full Report",
}

ANSWER_TYPE_KEYS: dict[AnswerTypeCode, AnswerTypeKey] = {
    AnswerTypeCode.CHAT_HELP: AnswerTypeKey.CHAT_HELP,
    AnswerTypeCode.SINGLE_VALUE: AnswerTypeKey.SINGLE_VALUE,
    AnswerTypeCode.COMPARISON_TOP: AnswerTypeKey.COMPARISON_TOP,
    AnswerTypeCode.TREND: AnswerTypeKey.TREND,
    AnswerTypeCode.DISTRIBUTION: AnswerTypeKey.DISTRIBUTION,
    AnswerTypeCode.TABLE: AnswerTypeKey.TABLE,
    AnswerTypeCode.FULL_REPORT: AnswerTypeKey.FULL_REPORT,
}

PRIMARY_VIEW_BY_TYPE: dict[AnswerTypeCode, ViewMode] = {
    AnswerTypeCode.CHAT_HELP: ViewMode.CHAT,
    AnswerTypeCode.SINGLE_VALUE: ViewMode.NUMBER,
    AnswerTypeCode.COMPARISON_TOP: ViewMode.CHART,
    AnswerTypeCode.TREND: ViewMode.CHART,
    AnswerTypeCode.DISTRIBUTION: ViewMode.CHART,
    AnswerTypeCode.TABLE: ViewMode.TABLE,
    AnswerTypeCode.FULL_REPORT: ViewMode.REPORT,
}

HELP_KEYWORDS = (
    "help",
    "faq",
    "glossary",
    "semantic layer",
    "semantic catalog",
    "what is",
    "what does",
    "what means",
    "how does",
    "which tables",
    "which columns",
    "which metrics",
    "что такое",
    "что значит",
    "как работает",
    "какие таблицы",
    "какие колонки",
    "какие метрики",
    "справка",
    "глоссар",
    "семантическ",
    "status_tender",
    "status_order",
    "confidence",
    "guardrail",
)
REPORT_KEYWORDS = (
    "full report",
    "executive summary",
    "report",
    "analytics for",
    "summary report",
    "полный отчет",
    "полный отчёт",
    "сводка",
    "сводный",
    "аналитика за",
    "executive",
    "итог за",
)
TABLE_KEYWORDS = (
    "show list",
    "show records",
    "export",
    "download",
    "latest",
    "list",
    "records",
    "table",
    "покажи список",
    "покажи записи",
    "список",
    "выгрузи",
    "выгрузка",
    "последние",
    "все записи",
    "таблица",
)
DISTRIBUTION_KEYWORDS = (
    "distribution",
    "share",
    "mix",
    "structure",
    "breakdown share",
    "composition",
    "доля",
    "структура",
    "распредел",
    "из чего состоит",
)
TREND_KEYWORDS = (
    "trend",
    "over time",
    "by day",
    "by week",
    "by month",
    "time series",
    "динамик",
    "тренд",
    "по дням",
    "по недел",
    "по месяц",
    "как менял",
    "за период",
)
COMPARISON_KEYWORDS = (
    "top",
    "compare",
    "comparison",
    "ranking",
    "by city",
    "by driver",
    "by category",
    "by segment",
    "топ",
    "сравни",
    "больше всего",
    "по город",
    "по водител",
    "по категор",
    "по сегмент",
)
SINGLE_VALUE_KEYWORDS = (
    "how many",
    "what is the value",
    "what percent",
    "average",
    "avg",
    "median",
    "minimum",
    "maximum",
    "max",
    "min",
    "сколько",
    "какой процент",
    "среднее",
    "медиана",
    "минимум",
    "максимум",
)
TIME_DIMENSION_KEYS = {"day", "week", "month", "quarter", "year", "hour"}
CATEGORY_DIMENSION_KEYS = {"city", "driver", "client", "segment", "status", "category"}


class AnswerTypeDecision(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    answer_type: AnswerTypeCode
    answer_type_key: AnswerTypeKey
    answer_type_label: str
    reason: str
    explanation: str
    requires_sql: bool
    primary_view_mode: ViewMode
    confidence_score: int = 0
    matched_keywords: list[str] = Field(default_factory=list)
    matched_semantic_terms: list[str] = Field(default_factory=list)
    retrieval_template_keys: list[str] = Field(default_factory=list)
    inherited_from_chat: str = ""
    preferred_metric_key: str = ""
    preferred_dimension_keys: list[str] = Field(default_factory=list)
    preferred_time_dimension: str = ""


def _normalized(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _matched_keywords(question: str, keywords: tuple[str, ...]) -> list[str]:
    lowered = _normalized(question)
    return [keyword for keyword in keywords if keyword in lowered]


def _semantic_terms(retrieval: RetrievalResult) -> list[str]:
    return [
        str(item.get("term") or item.get("mapped_entity_key") or "").strip()
        for item in retrieval.semantic_terms
        if str(item.get("term") or item.get("mapped_entity_key") or "").strip()
    ]


def _template_keys(retrieval: RetrievalResult) -> list[str]:
    return [
        str(item.get("template_key") or item.get("title") or "").strip()
        for item in retrieval.templates
        if str(item.get("template_key") or item.get("title") or "").strip()
    ]


def _hint_metric(retrieval: RetrievalResult) -> str:
    for collection in (retrieval.templates, retrieval.examples, retrieval.semantic_terms):
        for item in collection:
            metric_key = str(item.get("metric_key") or item.get("mapped_entity_key") or "").strip()
            mapped_type = str(item.get("mapped_entity_type") or "").strip()
            if metric_key and (not mapped_type or mapped_type == "metric"):
                return metric_key
    return ""


def _hint_dimensions(retrieval: RetrievalResult) -> list[str]:
    dimensions: list[str] = []
    seen: set[str] = set()
    for collection in (retrieval.templates, retrieval.examples):
        for item in collection:
            for value in item.get("dimension_keys") or item.get("dimension_keys_json") or []:
                key = str(value).strip()
                if key and key not in seen:
                    dimensions.append(key)
                    seen.add(key)
    for item in retrieval.semantic_terms:
        if str(item.get("mapped_entity_type") or "") == "dimension":
            key = str(item.get("mapped_entity_key") or "").strip()
            if key and key not in seen:
                dimensions.append(key)
                seen.add(key)
    return dimensions


def _hint_time_dimension(retrieval: RetrievalResult) -> str:
    for key in _hint_dimensions(retrieval):
        if key in TIME_DIMENSION_KEYS:
            return key
    return ""


def _build_decision(
    answer_type: AnswerTypeCode,
    *,
    reason: str,
    explanation: str,
    confidence_score: int,
    matched_keywords: list[str],
    matched_semantic_terms: list[str],
    retrieval_template_keys: list[str],
    inherited_from_chat: str = "",
    preferred_metric_key: str = "",
    preferred_dimension_keys: list[str] | None = None,
    preferred_time_dimension: str = "",
) -> AnswerTypeDecision:
    return AnswerTypeDecision(
        answer_type=answer_type,
        answer_type_key=ANSWER_TYPE_KEYS[answer_type],
        answer_type_label=ANSWER_TYPE_LABELS[answer_type],
        reason=reason,
        explanation=explanation,
        requires_sql=answer_type != AnswerTypeCode.CHAT_HELP,
        primary_view_mode=PRIMARY_VIEW_BY_TYPE[answer_type],
        confidence_score=confidence_score,
        matched_keywords=matched_keywords,
        matched_semantic_terms=matched_semantic_terms,
        retrieval_template_keys=retrieval_template_keys,
        inherited_from_chat=inherited_from_chat,
        preferred_metric_key=preferred_metric_key,
        preferred_dimension_keys=list(preferred_dimension_keys or []),
        preferred_time_dimension=preferred_time_dimension,
    )


def classify_answer_type(
    *,
    question: str,
    chat_context: dict[str, Any] | None,
    retrieval: RetrievalResult,
) -> AnswerTypeDecision:
    normalized_question = _normalized(question)
    chat_context = chat_context or {}
    matched_terms = _semantic_terms(retrieval)[:8]
    template_keys = _template_keys(retrieval)[:4]
    preferred_metric_key = _hint_metric(retrieval)
    preferred_dimension_keys = _hint_dimensions(retrieval)
    preferred_time_dimension = _hint_time_dimension(retrieval)
    inherited_from_chat = str(chat_context.get("anchor_answer_type") or "").strip()
    follow_up_applied = bool(chat_context.get("follow_up_applied"))

    help_matches = _matched_keywords(normalized_question, HELP_KEYWORDS)
    if help_matches:
        return _build_decision(
            AnswerTypeCode.CHAT_HELP,
            reason="The request asks for product help, terminology, schema guidance, or semantic glossary context.",
            explanation="Classifier routed the question into the non-SQL help path before intent extraction and SQL planning.",
            confidence_score=99,
            matched_keywords=help_matches,
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    report_matches = _matched_keywords(normalized_question, REPORT_KEYWORDS)
    if report_matches:
        return _build_decision(
            AnswerTypeCode.FULL_REPORT,
            reason="The request explicitly asks for a report, summary, or executive-style multi-block output.",
            explanation="Classifier selected report mode so planner can build KPI plus supporting sections instead of a single chart/table query.",
            confidence_score=96,
            matched_keywords=report_matches,
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            inherited_from_chat=inherited_from_chat,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    table_matches = _matched_keywords(normalized_question, TABLE_KEYWORDS)
    if table_matches:
        return _build_decision(
            AnswerTypeCode.TABLE,
            reason="The request is list-oriented and should return row-level records rather than an aggregate chart.",
            explanation="Classifier selected table mode before SQL so planner can compile a governed record query with pagination semantics.",
            confidence_score=95,
            matched_keywords=table_matches,
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            inherited_from_chat=inherited_from_chat,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    distribution_matches = _matched_keywords(normalized_question, DISTRIBUTION_KEYWORDS)
    if distribution_matches:
        return _build_decision(
            AnswerTypeCode.DISTRIBUTION,
            reason="The request asks for shares or composition across categories.",
            explanation="Classifier selected distribution mode so planner can aggregate categories and compute share percentages with an honest other-bucket rule.",
            confidence_score=94,
            matched_keywords=distribution_matches,
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            inherited_from_chat=inherited_from_chat,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    trend_matches = _matched_keywords(normalized_question, TREND_KEYWORDS)
    if trend_matches or preferred_time_dimension:
        return _build_decision(
            AnswerTypeCode.TREND,
            reason="The request or retrieval hints imply a time-grain answer.",
            explanation="Classifier selected trend mode so planner can group by time and keep ordering aligned with the time axis.",
            confidence_score=93 if trend_matches else 88,
            matched_keywords=trend_matches or ([preferred_time_dimension] if preferred_time_dimension else []),
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            inherited_from_chat=inherited_from_chat,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    comparison_matches = _matched_keywords(normalized_question, COMPARISON_KEYWORDS)
    category_hint = next((key for key in preferred_dimension_keys if key in CATEGORY_DIMENSION_KEYS), "")
    if comparison_matches or category_hint:
        return _build_decision(
            AnswerTypeCode.COMPARISON_TOP,
            reason="The request compares categories or asks for a ranked top breakdown.",
            explanation="Classifier selected comparison mode so planner can group by category, sort by metric, and apply a bounded top-N limit.",
            confidence_score=92 if comparison_matches else 86,
            matched_keywords=comparison_matches or ([category_hint] if category_hint else []),
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            inherited_from_chat=inherited_from_chat,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    single_value_matches = _matched_keywords(normalized_question, SINGLE_VALUE_KEYWORDS)
    if single_value_matches:
        return _build_decision(
            AnswerTypeCode.SINGLE_VALUE,
            reason="The request asks for one KPI and does not require a category or time breakdown.",
            explanation="Classifier selected single-value mode so planner can compile one aggregate and, when possible, a previous-period baseline query.",
            confidence_score=90,
            matched_keywords=single_value_matches,
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            inherited_from_chat=inherited_from_chat,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    if follow_up_applied and inherited_from_chat in {item.value for item in AnswerTypeKey}:
        inherited_type = AnswerTypeCode(
            next(code for code, key in ANSWER_TYPE_KEYS.items() if key.value == inherited_from_chat)
        )
        return _build_decision(
            inherited_type,
            reason="The question is a short follow-up inside the same chat, so the classifier inherited the prior answer shape.",
            explanation="Classifier reused the anchor answer type from the current chat because the follow-up did not introduce a stronger competing shape signal.",
            confidence_score=82,
            matched_keywords=[],
            matched_semantic_terms=matched_terms,
            retrieval_template_keys=template_keys,
            inherited_from_chat=inherited_from_chat,
            preferred_metric_key=preferred_metric_key,
            preferred_dimension_keys=preferred_dimension_keys,
            preferred_time_dimension=preferred_time_dimension,
        )

    if retrieval.templates:
        chart_type = str(retrieval.templates[0].get("chart_type") or "").strip().lower()
        if chart_type == "line":
            return _build_decision(
                AnswerTypeCode.TREND,
                reason="The best semantic template maps to a time-series chart.",
                explanation="Classifier used retrieval template hints to choose trend mode before SQL planning.",
                confidence_score=84,
                matched_keywords=[chart_type],
                matched_semantic_terms=matched_terms,
                retrieval_template_keys=template_keys,
                inherited_from_chat=inherited_from_chat,
                preferred_metric_key=preferred_metric_key,
                preferred_dimension_keys=preferred_dimension_keys,
                preferred_time_dimension=preferred_time_dimension,
            )
        if chart_type in {"bar", "grouped_bar"}:
            return _build_decision(
                AnswerTypeCode.COMPARISON_TOP,
                reason="The best semantic template maps to a ranked category comparison.",
                explanation="Classifier used retrieval template hints to choose comparison mode before SQL planning.",
                confidence_score=83,
                matched_keywords=[chart_type],
                matched_semantic_terms=matched_terms,
                retrieval_template_keys=template_keys,
                inherited_from_chat=inherited_from_chat,
                preferred_metric_key=preferred_metric_key,
                preferred_dimension_keys=preferred_dimension_keys,
                preferred_time_dimension=preferred_time_dimension,
            )

    return _build_decision(
        AnswerTypeCode.SINGLE_VALUE,
        reason="No stronger comparison, trend, distribution, table, or report signal was present, so the safest default is a single KPI.",
        explanation="Classifier defaulted to single-value mode and will let the planner add a previous-period baseline when the time range supports it.",
        confidence_score=75,
        matched_keywords=[],
        matched_semantic_terms=matched_terms,
        retrieval_template_keys=template_keys,
        inherited_from_chat=inherited_from_chat,
        preferred_metric_key=preferred_metric_key,
        preferred_dimension_keys=preferred_dimension_keys,
        preferred_time_dimension=preferred_time_dimension,
    )


__all__ = [
    "ANSWER_TYPE_KEYS",
    "ANSWER_TYPE_LABELS",
    "PRIMARY_VIEW_BY_TYPE",
    "AnswerTypeDecision",
    "classify_answer_type",
]
