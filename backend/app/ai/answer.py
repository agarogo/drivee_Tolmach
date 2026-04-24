from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from numbers import Number
from typing import Any, Iterable
from uuid import UUID

from app.answer_contracts import (
    AnswerEnvelope,
    AnswerExplainability,
    AnswerMetadata,
    ChatHelpResponse,
    ComparisonItem,
    ComparisonResponse,
    CompatibilityInfo,
    DataType,
    DistributionResponse,
    FullReportActionability,
    FullReportChartSection,
    FullReportInsightSection,
    FullReportKpi,
    FullReportResponse,
    FullReportTableSection,
    HelpCard,
    ResultGrain,
    RerenderPolicy,
    SingleValueResponse,
    SqlVisibility,
    TableColumn,
    TableResponse,
    TableSortSpec,
    TrendExtrema,
    TrendPoint,
    TrendResponse,
    ViewMode,
    ViewSwitchOption,
)
from app.ai.answer_classifier import AnswerTypeDecision
from app.ai.answer_classifier import classify_answer_type
from app.ai.answer_strategy import (
    AnswerBlockFailure,
    AnswerQuerySpec,
    CompiledAnswerQuery,
    ExecutedAnswerBlock,
    ExecutedAnswerPlan,
)
from app.ai.types import ConfidenceResult, Interpretation, RetrievalResult, SqlPlan
from app.semantic.service import SemanticCatalog
from app.services.guardrails import GuardrailDecision, ValidatedSQL


TIME_COLUMN_HINTS = ("date", "day", "week", "month", "year", "time", "hour")

FAQ_HELP_CARDS: dict[str, HelpCard] = {
    "confidence": HelpCard(
        title="Confidence",
        body="Confidence reflects how well the semantic layer and the governed interpretation align. Low confidence triggers clarification before SQL.",
        category="faq",
    ),
    "status_tender": HelpCard(
        title="status_tender",
        body="Tender lifecycle status on tender grain. Common values include decline, timeout, and done depending on the accepted tender state.",
        category="glossary",
    ),
    "status_order": HelpCard(
        title="status_order",
        body="Order lifecycle status on order grain. In the demo dataset the important values are done and cancelled.",
        category="glossary",
    ),
    "decline": HelpCard(
        title="decline",
        body="A decline tender means a tender was offered but not accepted by a driver.",
        category="glossary",
    ),
    "guardrail": HelpCard(
        title="Guardrails",
        body="Guardrails validate read-only SQL, enforce approved tables and columns, and cap cost before execution.",
        category="faq",
    ),
}


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        number = float(value)
        if number.is_integer():
            return int(number)
        return number
    return value


def serialize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: serialize_value(value) for key, value in row.items()} for row in rows]


def _column_order(rows: list[dict[str, Any]], preferred: Iterable[str] | None = None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for key in preferred or []:
        normalized = str(key)
        if normalized and normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    for row in rows:
        for key in row.keys():
            normalized = str(key)
            if normalized not in seen:
                ordered.append(normalized)
                seen.add(normalized)
    return ordered


def _values_for_key(rows: list[dict[str, Any]], key: str) -> list[Any]:
    return [row[key] for row in rows if key in row and row[key] is not None]


def _is_numeric_value(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _is_numeric_column(rows: list[dict[str, Any]], key: str) -> bool:
    values = _values_for_key(rows, key)
    return bool(values) and all(_is_numeric_value(value) for value in values)


def _is_time_value(value: Any) -> bool:
    if isinstance(value, (datetime, date)):
        return True
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return False


def _is_time_column(rows: list[dict[str, Any]], key: str) -> bool:
    lowered = key.lower()
    if any(token in lowered for token in TIME_COLUMN_HINTS):
        return True
    values = _values_for_key(rows, key)
    return bool(values) and all(_is_time_value(value) for value in values)


def _infer_data_type(rows: list[dict[str, Any]], key: str) -> DataType:
    values = _values_for_key(rows, key)
    if not values:
        return DataType.UNKNOWN
    if all(isinstance(value, bool) for value in values):
        return DataType.BOOLEAN
    if all(_is_numeric_value(value) for value in values):
        return DataType.NUMBER
    if all(isinstance(value, datetime) for value in values):
        return DataType.DATETIME
    if all(isinstance(value, date) for value in values):
        return DataType.DATE
    if _is_time_column(rows, key):
        return DataType.DATETIME
    if all(isinstance(value, dict) for value in values):
        return DataType.JSON
    return DataType.STRING


def _table_columns(rows: list[dict[str, Any]], preferred: Iterable[str] | None = None) -> list[TableColumn]:
    return [
        TableColumn(
            key=column,
            label=column.replace("_", " ").title(),
            data_type=_infer_data_type(rows, column),
        )
        for column in _column_order(rows, preferred)
    ]


def _first_non_null(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _float_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Number):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_if_whole(value: float | None) -> float | int | None:
    if value is None:
        return None
    return int(value) if float(value).is_integer() else round(float(value), 4)


def _result_grain(answer_type_key: str) -> ResultGrain:
    mapping = {
        "chat_help": ResultGrain.CHAT,
        "single_value": ResultGrain.KPI,
        "comparison_top": ResultGrain.CATEGORY,
        "trend": ResultGrain.TIME_SERIES,
        "distribution": ResultGrain.DISTRIBUTION,
        "table": ResultGrain.RECORD,
        "full_report": ResultGrain.REPORT,
    }
    return mapping.get(answer_type_key, ResultGrain.UNKNOWN)


def _format_period(interpretation: Interpretation | None) -> str:
    if not interpretation:
        return "Period not specified"
    label = str((interpretation.date_range or {}).get("label") or "").strip()
    return label or "Period not specified"


def _single_metric_key(block: ExecutedAnswerBlock | None) -> str:
    if block is None:
        return ""
    return block.compiled.sql_plan.metric


def _single_metric_label(block: ExecutedAnswerBlock | None) -> str:
    if block is None:
        return ""
    return block.compiled.sql_plan.metric_label or block.compiled.sql_plan.metric


def _dimension_key(block: ExecutedAnswerBlock | None) -> str:
    if block is None or not block.compiled.sql_plan.dimensions:
        return ""
    return block.compiled.sql_plan.dimensions[0]


def _distribution_items(
    rows: list[dict[str, Any]],
    *,
    dimension_key: str,
    metric_key: str,
    visible_item_limit: int,
) -> tuple[list[ComparisonItem], float, bool]:
    items: list[tuple[str, float]] = []
    for row in rows:
        label = str(row.get(dimension_key) or "Unknown")
        value = _float_value(row.get(metric_key))
        if value is None:
            continue
        items.append((label, value))
    items.sort(key=lambda item: item[1], reverse=True)
    total = sum(value for _, value in items)
    if total <= 0:
        return (
            [
                ComparisonItem(rank=index + 1, label=label, value=_int_if_whole(value), share_pct=None)
                for index, (label, value) in enumerate(items[:visible_item_limit])
            ],
            0.0,
            False,
        )
    visible = items[:visible_item_limit]
    tail = items[visible_item_limit:]
    other_bucket_applied = bool(tail)
    if tail:
        visible.append(("Other", sum(value for _, value in tail)))
    comparison_items = [
        ComparisonItem(
            rank=index + 1,
            label=label,
            value=_int_if_whole(value),
            share_pct=round((value / total) * 100, 2),
            is_other=label == "Other",
        )
        for index, (label, value) in enumerate(visible)
    ]
    return comparison_items, total, other_bucket_applied


def _help_cards(question: str, *, catalog: SemanticCatalog, semantic_terms: list[dict[str, Any]]) -> list[HelpCard]:
    normalized = question.lower()
    cards: list[HelpCard] = []
    seen: set[tuple[str, str]] = set()

    def add_card(card: HelpCard) -> None:
        key = (card.title.lower(), card.category.lower())
        if key in seen:
            return
        cards.append(card)
        seen.add(key)

    for item in semantic_terms[:8]:
        mapped_type = str(item.get("mapped_entity_type") or "").strip()
        mapped_key = str(item.get("mapped_entity_key") or "").strip()
        if mapped_type == "metric":
            metric = catalog.get_metric(mapped_key)
            if metric:
                add_card(
                    HelpCard(
                        title=metric.business_name or metric.metric_key,
                        body=(
                            f"{metric.description} Grain: {metric.grain}. "
                            f"Breakdowns: {', '.join(metric.allowed_dimensions) or 'none'}. "
                            f"Filters: {', '.join(metric.allowed_filters) or 'none'}."
                        ),
                        category="metric",
                    )
                )
        elif mapped_type in {"dimension", "filter"}:
            dimension = catalog.get_dimension(mapped_key) or catalog.get_filter(mapped_key)
            if dimension:
                add_card(
                    HelpCard(
                        title=dimension.business_name or dimension.dimension_key,
                        body=(
                            f"Governed key `{dimension.dimension_key}` from {dimension.table_name}. "
                            f"Column: {dimension.column_name}. Data type: {dimension.data_type}."
                        ),
                        category=mapped_type or "dimension",
                    )
                )

    if "какие таблицы" in normalized or "which tables" in normalized:
        add_card(
            HelpCard(
                title="Approved Tables",
                body="Analytics runs only against governed sources: fact.orders, fact.tenders, dim.cities, dim.drivers, dim.clients, and approved marts.",
                category="schema",
            )
        )
    if "какие колонки" in normalized or "which columns" in normalized:
        add_card(
            HelpCard(
                title="Governed Dimensions",
                body=", ".join(sorted(catalog.dimensions.keys())) or "No governed dimensions are active.",
                category="schema",
            )
        )
    if "какие метрики" in normalized or "which metrics" in normalized:
        add_card(
            HelpCard(
                title="Governed Metrics",
                body=", ".join(sorted(catalog.metrics.keys())) or "No governed metrics are active.",
                category="schema",
            )
        )
    for key, card in FAQ_HELP_CARDS.items():
        if key in normalized:
            add_card(card)
    if not cards:
        add_card(
            HelpCard(
                title="Semantic Catalog",
                body="Ask about governed metrics, dimensions, statuses, tables, columns, or how confidence and guardrails work.",
                category="reference",
            )
        )
    return cards[:6]


def build_chat_help_envelope(
    *,
    question: str,
    decision: AnswerTypeDecision,
    catalog: SemanticCatalog,
    semantic_terms: list[dict[str, Any]],
    query_id: UUID | None,
    chat_id: UUID | None,
    created_at: datetime | None,
    updated_at: datetime | None,
) -> AnswerEnvelope:
    help_cards = _help_cards(question, catalog=catalog, semantic_terms=semantic_terms)
    payload = ChatHelpResponse(
        message="This request is routed to semantic help, so no SQL was generated or executed.",
        help_cards=help_cards,
        suggested_questions=[
            "What does status_tender mean?",
            "Which metrics are available in the semantic layer?",
            "How does confidence affect clarification?",
        ],
    )
    return AnswerEnvelope(
        answer_type=decision.answer_type,
        answer_type_key=decision.answer_type_key,
        answer_type_label=decision.answer_type_label,
        answer_type_reason=decision.reason,
        primary_view_mode=decision.primary_view_mode,
        available_view_modes=[ViewMode.CHAT],
        rerender_policy=RerenderPolicy.LOCKED,
        requires_sql=False,
        result_grain=ResultGrain.CHAT,
        can_switch_without_requery=False,
        explanation_why_this_type=decision.explanation,
        metadata=AnswerMetadata(
            query_id=query_id,
            chat_id=chat_id,
            status="success",
            rows_returned=0,
            execution_ms=0,
            created_at=created_at,
            updated_at=updated_at,
        ),
        explainability=AnswerExplainability(
            metric="",
            dimensions=[],
            dimension_labels={},
            period="No SQL period required",
            filters={},
            grouping=[],
            sorting="",
            limit=0,
            source="answer_type_classifier",
            provider_confidence=float(decision.confidence_score) / 100.0,
            fallback_used=False,
            semantic_terms=[str(item.get("term") or item.get("mapped_entity_key") or "") for item in semantic_terms[:8]],
            sql_reasoning=[],
            answer_type_reasoning=decision.reason,
            view_reasoning="Chat help uses a messenger-style text view because SQL is intentionally bypassed.",
        ),
        sql_visibility=SqlVisibility(
            show_sql_panel=False,
            sql="",
            explain_cost=0.0,
            explain_plan_available=False,
        ),
        render_payload=payload,
        switch_options=[
            ViewSwitchOption(
                view_mode=ViewMode.CHAT,
                label="Chat",
                can_switch_without_requery=False,
                requery_required=False,
                reason="Semantic help answers stay in chat mode.",
            )
        ],
        compatibility_info=CompatibilityInfo(
            compatible_view_modes=[ViewMode.CHAT],
            can_switch_without_requery=False,
            requery_required_for_views=[ViewMode.NUMBER, ViewMode.CHART, ViewMode.TABLE, ViewMode.REPORT],
        ),
    )


def _view_contract(
    answer_type_key: str,
    *,
    render_payload: Any | None,
) -> tuple[ViewMode, list[ViewMode], RerenderPolicy, bool, list[ViewSwitchOption], CompatibilityInfo]:
    has_renderable_data = render_payload is not None

    if answer_type_key == "chat_help":
        primary = ViewMode.CHAT
        available = [ViewMode.CHAT]
    elif answer_type_key == "single_value":
        primary = ViewMode.NUMBER
        available = [ViewMode.NUMBER, ViewMode.TABLE]
    elif answer_type_key in {"comparison_top", "trend", "distribution"}:
        primary = ViewMode.CHART
        available = [ViewMode.CHART, ViewMode.TABLE]
    elif answer_type_key == "full_report":
        primary = ViewMode.REPORT
        available = [ViewMode.REPORT]
        if render_payload is not None:
            if getattr(render_payload, "kpis", None):
                available.append(ViewMode.NUMBER)
            section_kinds = {getattr(section, "kind", "") for section in getattr(render_payload, "sections", [])}
            if "chart" in section_kinds:
                available.append(ViewMode.CHART)
            if "table" in section_kinds:
                available.append(ViewMode.TABLE)
    else:
        primary = ViewMode.TABLE
        available = [ViewMode.TABLE]

    deduped_available: list[ViewMode] = []
    seen_available: set[ViewMode] = set()
    for mode in available:
        if mode not in seen_available:
            deduped_available.append(mode)
            seen_available.add(mode)

    can_switch_without_requery = has_renderable_data and len(deduped_available) > 1
    rerender_policy = (
        RerenderPolicy.CLIENT_SAFE_ONLY if can_switch_without_requery else RerenderPolicy.REQUERY_FOR_INCOMPATIBLE
    )
    switch_space = [ViewMode.CHAT, ViewMode.NUMBER, ViewMode.CHART, ViewMode.TABLE, ViewMode.REPORT]
    requery_required_for_views = [mode for mode in switch_space if mode not in deduped_available]
    switch_options = [
        ViewSwitchOption(
            view_mode=mode,
            label=mode.value.title(),
            can_switch_without_requery=mode in deduped_available and has_renderable_data,
            requery_required=mode not in deduped_available,
            reason=(
                "Compatible with the current result grain."
                if mode in deduped_available and has_renderable_data
                else "Requires a different answer type or SQL strategy."
                if mode not in deduped_available
                else "The answer shape is known, but the renderer has no factual payload yet."
            ),
        )
        for mode in switch_space
    ]
    return (
        primary,
        deduped_available,
        rerender_policy,
        can_switch_without_requery,
        switch_options,
        CompatibilityInfo(
            compatible_view_modes=deduped_available,
            can_switch_without_requery=can_switch_without_requery,
            requery_required_for_views=requery_required_for_views,
        ),
    )


def _failure_note(failures: dict[str, AnswerBlockFailure], block_key: str, fallback: str) -> str:
    failure = failures.get(block_key)
    return failure.reason if failure else fallback


def _build_single_value_payload(
    *,
    primary_block: ExecutedAnswerBlock,
    failures: dict[str, AnswerBlockFailure],
    notes: list[str],
    interpretation: Interpretation | None,
) -> SingleValueResponse:
    rows = primary_block.rows
    metric_key = _single_metric_key(primary_block)
    metric_label = _single_metric_label(primary_block)
    current_value = serialize_value(_first_non_null(rows, metric_key))
    supporting_rows = serialize_rows(rows[:10])
    return SingleValueResponse(
        metric_key=metric_key,
        metric_label=metric_label,
        current_value=current_value,
        previous_value=None,
        delta_abs=None,
        delta_pct=None,
        freshness_timestamp=datetime.utcnow(),
        unit_label="",
        context=f"{metric_label} for {_format_period(interpretation)}.",
        availability_note=_failure_note(
            failures,
            "previous_period",
            notes[0] if notes else "Previous-period baseline was not requested.",
        ),
        columns=_table_columns(rows, [metric_key] if metric_key else None),
        supporting_rows=supporting_rows,
    )


def _build_single_value_payload_with_baseline(
    *,
    primary_block: ExecutedAnswerBlock,
    previous_block: ExecutedAnswerBlock | None,
    failures: dict[str, AnswerBlockFailure],
    notes: list[str],
    interpretation: Interpretation | None,
) -> SingleValueResponse:
    payload = _build_single_value_payload(
        primary_block=primary_block,
        failures=failures,
        notes=notes,
        interpretation=interpretation,
    )
    if previous_block is None:
        return payload
    metric_key = _single_metric_key(primary_block)
    current_value = _float_value(_first_non_null(primary_block.rows, metric_key))
    previous_value = _float_value(_first_non_null(previous_block.rows, metric_key))
    if current_value is None or previous_value is None:
        payload.availability_note = "Previous-period baseline ran, but the value was not numeric."
        return payload
    delta_abs = current_value - previous_value
    delta_pct = None if previous_value == 0 else round((delta_abs / previous_value) * 100, 2)
    payload.previous_value = _int_if_whole(previous_value)
    payload.delta_abs = round(delta_abs, 4)
    payload.delta_pct = delta_pct
    payload.availability_note = ""
    return payload


def _build_comparison_payload(primary_block: ExecutedAnswerBlock) -> ComparisonResponse:
    rows = serialize_rows(primary_block.rows)
    metric_key = _single_metric_key(primary_block)
    metric_label = _single_metric_label(primary_block)
    dimension_key = _dimension_key(primary_block)
    ordered_rows = sorted(rows, key=lambda row: _float_value(row.get(metric_key)) or float("-inf"), reverse=True)
    items = [
        ComparisonItem(
            rank=index + 1,
            label=str(row.get(dimension_key) or f"Row {index + 1}"),
            value=_int_if_whole(_float_value(row.get(metric_key))),
        )
        for index, row in enumerate(ordered_rows)
    ]
    top_item = items[0] if items else None
    return ComparisonResponse(
        metric_key=metric_key,
        metric_label=metric_label,
        dimension_key=dimension_key,
        dimension_label=primary_block.compiled.sql_plan.dimension_labels.get(dimension_key, dimension_key),
        items=items,
        columns=_table_columns(rows, [dimension_key, metric_key]),
        rows=ordered_rows,
        insight=(
            f"{top_item.label} leads the ranking."
            if top_item and top_item.value is not None
            else "Comparison is ready across governed categories."
        ),
    )


def _build_trend_payload(primary_block: ExecutedAnswerBlock) -> TrendResponse:
    rows = serialize_rows(primary_block.rows)
    metric_key = _single_metric_key(primary_block)
    metric_label = _single_metric_label(primary_block)
    time_key = _dimension_key(primary_block)
    points = [
        TrendPoint(
            label=str(row.get(time_key) or ""),
            value=_int_if_whole(_float_value(row.get(metric_key))),
        )
        for row in rows
    ]
    numeric_points = [point for point in points if point.value is not None]
    peak = max(numeric_points, key=lambda point: float(point.value), default=TrendPoint(label="", value=None))
    low = min(numeric_points, key=lambda point: float(point.value), default=TrendPoint(label="", value=None))
    return TrendResponse(
        metric_key=metric_key,
        metric_label=metric_label,
        time_key=time_key,
        points=points,
        peak=TrendExtrema(label=peak.label, value=peak.value),
        low=TrendExtrema(label=low.label, value=low.value),
        columns=_table_columns(rows, [time_key, metric_key]),
        rows=rows,
        insight=(
            f"Peak at {peak.label} and low at {low.label}."
            if peak.value is not None and low.value is not None
            else "Trend points are ready for the selected period."
        ),
    )


def _build_distribution_payload(
    primary_block: ExecutedAnswerBlock,
    *,
    visible_item_limit: int,
) -> DistributionResponse:
    rows = serialize_rows(primary_block.rows)
    metric_key = _single_metric_key(primary_block)
    metric_label = _single_metric_label(primary_block)
    dimension_key = _dimension_key(primary_block)
    items, total, other_bucket_applied = _distribution_items(
        rows,
        dimension_key=dimension_key,
        metric_key=metric_key,
        visible_item_limit=visible_item_limit,
    )
    integrity_pct = round(sum(item.share_pct or 0.0 for item in items), 2) if items else 100.0
    return DistributionResponse(
        metric_key=metric_key,
        metric_label=metric_label,
        dimension_key=dimension_key,
        dimension_label=primary_block.compiled.sql_plan.dimension_labels.get(dimension_key, dimension_key),
        items=items,
        total_value=round(total, 4),
        integrity_pct=integrity_pct,
        other_bucket_applied=other_bucket_applied,
        columns=_table_columns(rows, [dimension_key, metric_key]),
        rows=rows,
        insight=(
            f"{items[0].label} is the largest share."
            if items and items[0].share_pct is not None
            else "Distribution is ready across governed categories."
        ),
    )


def _build_table_payload(primary_block: ExecutedAnswerBlock) -> TableResponse:
    page_size = int(primary_block.spec.config.get("page_size") or 25)
    page_offset = int(primary_block.spec.config.get("page_offset") or 0)
    has_more = len(primary_block.rows) > page_size
    visible_rows = serialize_rows(primary_block.rows[:page_size])
    return TableResponse(
        columns=_table_columns(visible_rows),
        rows=visible_rows,
        snapshot_row_count=len(visible_rows),
        total_row_count=None,
        pagination_mode="server_ready",
        page_size=page_size,
        page_offset=page_offset,
        has_more=has_more,
        sort=TableSortSpec(
            key=primary_block.compiled.sql_plan.order_by.split()[0] if primary_block.compiled.sql_plan.order_by else "",
            direction="desc" if "DESC" in primary_block.compiled.sql_plan.order_by.upper() else "asc",
        ),
        export_formats=["csv"],
    )


def _report_kpis(
    *,
    headline_payload: SingleValueResponse | None,
    comparison_payload: ComparisonResponse | None,
    trend_payload: TrendResponse | None,
) -> list[FullReportKpi]:
    kpis: list[FullReportKpi] = []
    if headline_payload:
        kpis.append(
            FullReportKpi(
                key=headline_payload.metric_key,
                label=headline_payload.metric_label or headline_payload.metric_key,
                value=headline_payload.current_value,
                unit_label=headline_payload.unit_label,
            )
        )
        if headline_payload.previous_value is not None:
            kpis.append(
                FullReportKpi(
                    key=f"{headline_payload.metric_key}_previous_period",
                    label="Previous Period",
                    value=headline_payload.previous_value,
                )
            )
    if comparison_payload and comparison_payload.items:
        leader = comparison_payload.items[0]
        kpis.append(
            FullReportKpi(
                key=f"{comparison_payload.dimension_key}_leader",
                label=f"Top {comparison_payload.dimension_label}",
                value=f"{leader.label}: {leader.value}",
            )
        )
    if trend_payload and trend_payload.peak.value is not None:
        kpis.append(
            FullReportKpi(
                key=f"{trend_payload.metric_key}_peak",
                label="Peak",
                value=f"{trend_payload.peak.label}: {trend_payload.peak.value}",
            )
        )
    return kpis[:4]


def _build_full_report_payload(
    *,
    question: str,
    blocks: dict[str, ExecutedAnswerBlock],
    failures: dict[str, AnswerBlockFailure],
    notes: list[str],
    interpretation: Interpretation | None,
) -> FullReportResponse:
    headline_block = blocks.get("headline_kpi")
    previous_block = blocks.get("previous_period")
    trend_block = blocks.get("report_trend")
    comparison_block = blocks.get("report_comparison")
    record_block = blocks.get("report_records")

    headline_payload = (
        _build_single_value_payload_with_baseline(
            primary_block=headline_block,
            previous_block=previous_block,
            failures=failures,
            notes=notes,
            interpretation=interpretation,
        )
        if headline_block
        else None
    )
    trend_payload = _build_trend_payload(trend_block) if trend_block else None
    comparison_payload = _build_comparison_payload(comparison_block) if comparison_block else None
    record_payload = _build_table_payload(record_block) if record_block else None

    insights: list[str] = []
    if headline_payload:
        insights.append(f"{headline_payload.metric_label or headline_payload.metric_key}: {headline_payload.current_value}.")
    if trend_payload and trend_payload.peak.value is not None and trend_payload.low.value is not None:
        insights.append(f"Peak {trend_payload.peak.label} / low {trend_payload.low.label}.")
    if comparison_payload and comparison_payload.items:
        insights.append(f"Top segment: {comparison_payload.items[0].label}.")
    for note in notes:
        if note:
            insights.append(note)
    for failure in failures.values():
        if failure.optional:
            insights.append(f"{failure.title} was skipped: {failure.reason}")

    sections: list[Any] = []
    sections.append(
        FullReportInsightSection(
            title="Executive Summary",
            body=" ".join(insights[:3]) or "Report completed from governed semantic blocks.",
        )
    )
    if trend_payload:
        sections.append(
            FullReportChartSection(
                title="Trend",
                chart_type="line",
                metric_key=trend_payload.metric_key,
                metric_label=trend_payload.metric_label,
                x_key=trend_payload.time_key,
                columns=trend_payload.columns,
                rows=trend_payload.rows,
            )
        )
    if comparison_payload:
        sections.append(
            FullReportChartSection(
                title="Comparison",
                chart_type="bar",
                metric_key=comparison_payload.metric_key,
                metric_label=comparison_payload.metric_label,
                x_key=comparison_payload.dimension_key,
                columns=comparison_payload.columns,
                rows=comparison_payload.rows,
            )
        )
    if record_payload:
        sections.append(
            FullReportTableSection(
                title="Record Preview",
                columns=record_payload.columns,
                rows=record_payload.rows,
            )
        )

    return FullReportResponse(
        title=question.strip() or "Analytics report",
        summary=f"Report assembled for {_format_period(interpretation)} using governed semantic blocks.",
        kpis=_report_kpis(
            headline_payload=headline_payload,
            comparison_payload=comparison_payload,
            trend_payload=trend_payload,
        ),
        sections=sections,
        insights=insights[:6],
        actionability=FullReportActionability(
            rerun_supported=True,
            save_supported=True,
            schedule_supported=True,
            export_formats=["csv"],
        ),
        rerun_supported=True,
        save_supported=True,
    )


def build_answer_envelope(
    *,
    question: str,
    decision: AnswerTypeDecision,
    interpretation: Interpretation | None = None,
    confidence: ConfidenceResult | None = None,
    executed_plan: ExecutedAnswerPlan | None = None,
    status: str = "success",
    query_id: UUID | None = None,
    chat_id: UUID | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    execution_ms: int = 0,
    sql_text: str = "",
    sql_explain_cost: float = 0.0,
    semantic_terms: list[dict[str, Any]] | None = None,
    catalog: SemanticCatalog | None = None,
    notes: list[str] | None = None,
) -> AnswerEnvelope:
    semantic_terms = semantic_terms or []
    notes = notes or []
    render_payload = None
    primary_block = executed_plan.primary_block if executed_plan else None
    blocks = executed_plan.blocks if executed_plan else {}
    failures = executed_plan.failures if executed_plan else {}

    if decision.answer_type_key == "single_value" and primary_block is not None:
        render_payload = _build_single_value_payload_with_baseline(
            primary_block=primary_block,
            previous_block=blocks.get("previous_period"),
            failures=failures,
            notes=notes,
            interpretation=interpretation,
        )
    elif decision.answer_type_key == "comparison_top" and primary_block is not None:
        render_payload = _build_comparison_payload(primary_block)
    elif decision.answer_type_key == "trend" and primary_block is not None:
        render_payload = _build_trend_payload(primary_block)
    elif decision.answer_type_key == "distribution" and primary_block is not None:
        visible_limit = int(primary_block.spec.config.get("visible_item_limit") or 6)
        render_payload = _build_distribution_payload(primary_block, visible_item_limit=visible_limit)
    elif decision.answer_type_key == "table" and primary_block is not None:
        render_payload = _build_table_payload(primary_block)
    elif decision.answer_type_key == "full_report" and primary_block is not None:
        render_payload = _build_full_report_payload(
            question=question,
            blocks=blocks,
            failures=failures,
            notes=notes,
            interpretation=interpretation,
        )
    elif decision.answer_type_key == "chat_help" and catalog is not None:
        return build_chat_help_envelope(
            question=question,
            decision=decision,
            catalog=catalog,
            semantic_terms=semantic_terms,
            query_id=query_id,
            chat_id=chat_id,
            created_at=created_at,
            updated_at=updated_at,
        )

    primary_view_mode, available_view_modes, rerender_policy, can_switch_without_requery, switch_options, compatibility = _view_contract(
        decision.answer_type_key,
        render_payload=render_payload,
    )
    primary_plan = primary_block.compiled.sql_plan if primary_block is not None else None
    metric = primary_plan.metric if primary_plan else (interpretation.metric if interpretation else "")
    dimensions = primary_plan.dimensions if primary_plan else (interpretation.dimensions if interpretation else [])
    total_rows = (
        sum(len(block.rows) for block in blocks.values())
        if executed_plan is not None
        else 0
    )
    total_execution_ms = executed_plan.total_execution_ms if executed_plan is not None else execution_ms
    reasoning_notes = list(primary_plan.explanation if primary_plan else [])
    reasoning_notes.extend(notes)
    if failures:
        reasoning_notes.extend(f"{failure.title}: {failure.reason}" for failure in failures.values())

    return AnswerEnvelope(
        answer_type=decision.answer_type,
        answer_type_key=decision.answer_type_key,
        answer_type_label=decision.answer_type_label,
        answer_type_reason=decision.reason,
        primary_view_mode=primary_view_mode,
        available_view_modes=available_view_modes,
        rerender_policy=rerender_policy,
        requires_sql=decision.requires_sql,
        result_grain=_result_grain(decision.answer_type_key),
        can_switch_without_requery=can_switch_without_requery,
        explanation_why_this_type=decision.explanation,
        metadata=AnswerMetadata(
            query_id=query_id,
            chat_id=chat_id,
            status=status,
            rows_returned=total_rows,
            execution_ms=total_execution_ms,
            created_at=created_at,
            updated_at=updated_at,
        ),
        explainability=AnswerExplainability(
            metric=metric or "",
            dimensions=list(dimensions or []),
            dimension_labels=dict(primary_plan.dimension_labels if primary_plan else {}),
            period=_format_period(interpretation),
            filters=dict(interpretation.filters if interpretation else {}),
            grouping=list(primary_plan.group_by if primary_plan else (interpretation.grouping if interpretation else [])),
            sorting=str(primary_plan.order_by if primary_plan else (interpretation.sorting if interpretation else "")),
            limit=int(primary_plan.limit if primary_plan else (interpretation.limit if interpretation else 0)),
            source=str(interpretation.source if interpretation else "answer_type_classifier"),
            provider_confidence=float(
                interpretation.provider_confidence if interpretation and interpretation.provider_confidence else (confidence.score / 100 if confidence else decision.confidence_score / 100)
            ),
            fallback_used=bool(interpretation.fallback_used if interpretation else False),
            semantic_terms=[str(item.get("term") or item.get("mapped_entity_key") or "") for item in semantic_terms[:8]],
            sql_reasoning=reasoning_notes,
            answer_type_reasoning=decision.reason,
            view_reasoning="View mode is selected from the server-side answer type and the factual result grain, not from legacy chart heuristics.",
        ),
        sql_visibility=SqlVisibility(
            show_sql_panel=decision.requires_sql and bool(sql_text),
            sql=sql_text,
            explain_cost=float(sql_explain_cost or 0.0),
            explain_plan_available=decision.requires_sql and bool(sql_text),
        ),
        render_payload=render_payload,
        switch_options=switch_options,
        compatibility_info=compatibility,
    )


def render_answer_text(envelope: AnswerEnvelope) -> str:
    payload = envelope.render_payload
    if payload is None:
        return envelope.answer_type_reason
    if payload.kind == "chat_help":
        return payload.message
    if payload.kind == "single_value":
        delta = (
            f" ({payload.delta_pct:+.2f}% vs previous period)"
            if payload.delta_pct is not None
            else f" ({payload.availability_note})"
            if payload.availability_note
            else ""
        )
        return f"{payload.metric_label or payload.metric_key}: {payload.current_value}. {payload.context}{delta}"
    if payload.kind == "comparison_top":
        if not payload.items:
            return f"{payload.metric_label or payload.metric_key}: comparison returned no visible values."
        return (
            f"{payload.metric_label or payload.metric_key}: {payload.items[0].label} leads with "
            f"{payload.items[0].value}."
        )
    if payload.kind == "trend":
        if payload.peak.value is not None and payload.low.value is not None:
            return (
                f"{payload.metric_label or payload.metric_key}: {len(payload.points)} points. "
                f"Peak {payload.peak.label}, low {payload.low.label}."
            )
        return f"{payload.metric_label or payload.metric_key}: {len(payload.points)} time points."
    if payload.kind == "distribution":
        if not payload.items:
            return f"{payload.metric_label or payload.metric_key}: distribution is empty."
        lead_share = (
            f" ({payload.items[0].share_pct:.2f}%)"
            if payload.items[0].share_pct is not None
            else ""
        )
        return f"{payload.metric_label or payload.metric_key}: largest share is {payload.items[0].label}{lead_share}."
    if payload.kind == "table":
        return f"Returned {payload.snapshot_row_count} rows in table mode."
    if payload.kind == "full_report":
        return payload.summary or payload.title or "Report is ready."
    return envelope.answer_type_reason


def legacy_chart_spec_from_answer(envelope: AnswerEnvelope) -> dict[str, Any]:
    payload = envelope.render_payload
    if payload is None:
        return {"type": "table_only"}
    if payload.kind == "trend":
        return {
            "type": "line",
            "x": payload.time_key,
            "series": [{"key": payload.metric_key, "name": payload.metric_label or payload.metric_key}],
        }
    if payload.kind in {"comparison_top", "distribution"}:
        return {
            "type": "bar",
            "x": payload.dimension_key,
            "series": [{"key": payload.metric_key, "name": payload.metric_label or payload.metric_key}],
        }
    return {"type": "table_only"}


def explain_interpretation(
    *,
    decision: AnswerTypeDecision,
    interpretation: Interpretation | None,
    envelope: AnswerEnvelope,
) -> dict[str, Any]:
    return {
        "metric": interpretation.metric if interpretation else "",
        "dimensions": list(interpretation.dimensions) if interpretation else [],
        "filters": dict(interpretation.filters) if interpretation else {},
        "period": _format_period(interpretation),
        "grouping": list(interpretation.grouping) if interpretation else [],
        "sorting": interpretation.sorting if interpretation else {},
        "limit": interpretation.limit if interpretation else 0,
        "answer_type": decision.answer_type_key,
        "answer_type_label": decision.answer_type_label,
        "answer_type_reason": decision.reason,
        "primary_view_mode": envelope.primary_view_mode,
        "available_view_modes": list(envelope.available_view_modes),
        "view_reasoning": envelope.explainability.view_reasoning,
    }


def _legacy_period_phrase(interpretation: Interpretation | None) -> str:
    if interpretation is None:
        return "за период"
    date_range = interpretation.date_range or {}
    label = str(date_range.get("label") or "").strip()
    if label:
        return f"за период {label}"
    return "за период"


def _legacy_breakdown_phrase(interpretation: Interpretation | None, plan: SqlPlan) -> str:
    dimensions = list(plan.dimensions or (interpretation.dimensions if interpretation else []))
    if not dimensions:
        return "без разреза"
    labels = [plan.dimension_labels.get(key, key) for key in dimensions]
    return ", ".join(labels)


def compose_answer(
    question: str,
    interpretation: Interpretation,
    confidence: ConfidenceResult,
    plan: SqlPlan,
    rows: list[dict[str, Any]],
) -> str:
    retrieval = RetrievalResult(
        semantic_terms=[
            {
                "term": interpretation.metric or plan.metric,
                "mapped_entity_type": "metric",
                "mapped_entity_key": interpretation.metric or plan.metric,
            }
        ],
        templates=[],
        examples=[],
        planner_candidates=[],
    )
    decision = classify_answer_type(question=question, chat_context={}, retrieval=retrieval)
    spec = AnswerQuerySpec(
        block_key="primary",
        title="Primary",
        mode="aggregate",
        interpretation=interpretation,
        reason="Legacy compose_answer compatibility helper.",
        config={},
    )
    compiled = CompiledAnswerQuery(
        sql_plan=plan,
        rendered_sql="SELECT 1",
        planner_payload={"compatibility": True},
        source_tables={plan.source_table},
        column_references=[],
    )
    validation = GuardrailDecision(
        ok=True,
        sql="SELECT 1",
        message="ok",
        logs=[],
        validated_sql=ValidatedSQL(
            sql="SELECT 1",
            tables={plan.source_table},
            row_limit=plan.limit,
            explain_plan={},
            explain_cost=0.0,
        ),
    )
    block = ExecutedAnswerBlock(
        spec=spec,
        compiled=compiled,
        validation=validation,
        rows=rows,
        execution_ms=0,
        cached=False,
        execution_mode="compatibility",
        fingerprint="compose_answer",
    )
    executed_plan = ExecutedAnswerPlan(
        decision=decision,
        primary_block=block,
        blocks={"primary": block},
        failures={},
        total_execution_ms=0,
    )
    envelope = build_answer_envelope(
        question=question,
        decision=decision,
        interpretation=interpretation,
        confidence=confidence,
        executed_plan=executed_plan,
        status="success",
    )
    payload = envelope.render_payload
    if payload is not None and getattr(payload, "kind", "") == "single_value":
        metric_label = payload.metric_label or plan.metric_label or plan.metric
        breakdown = _legacy_breakdown_phrase(interpretation, plan)
        return (
            f"{metric_label} {_legacy_period_phrase(interpretation)}: {payload.current_value}. "
            f"разрез = {breakdown}"
        )
    return render_answer_text(envelope)


__all__ = [
    "build_answer_envelope",
    "build_chat_help_envelope",
    "compose_answer",
    "explain_interpretation",
    "legacy_chart_spec_from_answer",
    "render_answer_text",
    "serialize_rows",
    "serialize_value",
]
