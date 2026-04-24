import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.tests.runtime_stubs import install_runtime_stubs

install_runtime_stubs()

from app.ai.answer import build_answer_envelope
from app.ai.answer_classifier import AnswerTypeDecision, classify_answer_type
from app.ai.answer_strategy import (
    AnswerPlan,
    AnswerQuerySpec,
    CompiledAnswerQuery,
    ExecutedAnswerBlock,
    ExecutedAnswerPlan,
    build_answer_plan,
)
from app.ai.types import ConfidenceResult, Interpretation, RetrievalResult, SqlPlan
from app.answer_contracts import AnswerTypeCode, AnswerTypeKey, ViewMode
from app.semantic.service import (
    SemanticCatalog,
    SemanticDimensionDefinition,
    SemanticMetricDefinition,
)
from app.services.guardrails import GuardrailDecision, ValidatedSQL


def sample_catalog() -> SemanticCatalog:
    metrics = {
        "revenue": SemanticMetricDefinition(
            metric_key="revenue",
            business_name="Revenue",
            description="Completed order revenue.",
            sql_expression_template="SUM({base_alias}.price_order_local)",
            grain="order",
            allowed_dimensions=["city", "day"],
            allowed_filters=["city", "day"],
            default_chart="bar",
            safety_tags=["finance"],
        ),
        "completed_trips": SemanticMetricDefinition(
            metric_key="completed_trips",
            business_name="Completed Trips",
            description="Completed trips count.",
            sql_expression_template="COUNT(DISTINCT {base_alias}.order_id)",
            grain="order",
            allowed_dimensions=["city", "day", "driver", "client"],
            allowed_filters=["city", "day", "driver", "client"],
            default_chart="bar",
            safety_tags=["count"],
        ),
        "tender_decline_rate": SemanticMetricDefinition(
            metric_key="tender_decline_rate",
            business_name="Tender Decline Rate",
            description="Tender decline rate.",
            sql_expression_template="AVG(CASE WHEN {base_alias}.status_tender = 'decline' THEN 1 ELSE 0 END)",
            grain="tender",
            allowed_dimensions=["city", "day", "driver"],
            allowed_filters=["city", "day", "driver"],
            default_chart="bar",
            safety_tags=["ratio"],
        ),
    }
    dimensions = {
        "city": SemanticDimensionDefinition(
            dimension_key="city",
            business_name="City",
            table_name="dim.cities",
            column_name="city_name",
            join_path="JOIN dim.cities {dimension_alias} ON {dimension_alias}.city_id = {base_alias}.city_id",
            data_type="string",
        ),
        "day": SemanticDimensionDefinition(
            dimension_key="day",
            business_name="Day",
            table_name="__grain__",
            column_name="{time_dimension_column}",
            join_path="",
            data_type="date",
        ),
        "driver": SemanticDimensionDefinition(
            dimension_key="driver",
            business_name="Driver",
            table_name="dim.drivers",
            column_name="driver_id",
            join_path="JOIN dim.drivers {dimension_alias} ON {dimension_alias}.driver_id = {base_alias}.driver_id",
            data_type="string",
        ),
        "client": SemanticDimensionDefinition(
            dimension_key="client",
            business_name="Client",
            table_name="dim.clients",
            column_name="user_id",
            join_path="JOIN dim.clients {dimension_alias} ON {dimension_alias}.user_id = {base_alias}.user_id",
            data_type="string",
        ),
    }
    return SemanticCatalog(metrics=metrics, dimensions=dimensions, filters=dict(dimensions))


def retrieval_for(
    *,
    metric_key: str = "revenue",
    dimension_keys: list[str] | None = None,
    chart_type: str = "bar",
) -> RetrievalResult:
    dimension_keys = dimension_keys or []
    semantic_terms = [{"term": metric_key, "mapped_entity_type": "metric", "mapped_entity_key": metric_key}]
    for key in dimension_keys:
        semantic_terms.append({"term": key, "mapped_entity_type": "dimension", "mapped_entity_key": key})
    return RetrievalResult(
        semantic_terms=semantic_terms,
        templates=[
            {
                "template_key": f"{metric_key}_{chart_type}",
                "title": f"{metric_key} template",
                "metric_key": metric_key,
                "dimension_keys": dimension_keys,
                "chart_type": chart_type,
            }
        ],
        examples=[
            {
                "id": f"example_{metric_key}",
                "title": f"{metric_key} example",
                "metric_key": metric_key,
                "dimension_keys": dimension_keys,
            }
        ],
        planner_candidates=[],
    )


def decision_for(answer_type_key: str) -> AnswerTypeDecision:
    mapping = {
        "chat_help": (AnswerTypeCode.CHAT_HELP, ViewMode.CHAT),
        "single_value": (AnswerTypeCode.SINGLE_VALUE, ViewMode.NUMBER),
        "comparison_top": (AnswerTypeCode.COMPARISON_TOP, ViewMode.CHART),
        "trend": (AnswerTypeCode.TREND, ViewMode.CHART),
        "distribution": (AnswerTypeCode.DISTRIBUTION, ViewMode.CHART),
        "table": (AnswerTypeCode.TABLE, ViewMode.TABLE),
        "full_report": (AnswerTypeCode.FULL_REPORT, ViewMode.REPORT),
    }
    answer_type, view_mode = mapping[answer_type_key]
    return AnswerTypeDecision(
        answer_type=answer_type,
        answer_type_key=AnswerTypeKey(answer_type_key),
        answer_type_label=answer_type_key.replace("_", " ").title(),
        reason=f"{answer_type_key} selected",
        explanation=f"{answer_type_key} explanation",
        requires_sql=answer_type_key != "chat_help",
        primary_view_mode=view_mode,
        confidence_score=95,
        matched_keywords=[],
        matched_semantic_terms=["revenue"],
        retrieval_template_keys=["sample"],
        preferred_metric_key="revenue",
        preferred_dimension_keys=["city", "day"],
        preferred_time_dimension="day",
    )


def sample_sql_plan(
    *,
    metric: str = "revenue",
    metric_label: str = "Revenue",
    dimensions: list[str] | None = None,
    dimension_labels: dict[str, str] | None = None,
    order_by: str = "revenue DESC",
    limit: int = 10,
    chart_type: str = "bar",
) -> SqlPlan:
    dimensions = dimensions or []
    dimension_labels = dimension_labels or {key: key.title() for key in dimensions}
    return SqlPlan(
        metric=metric,
        metric_label=metric_label,
        metric_expression=f"metric_expression_for_{metric}",
        source_table="fact.orders fo",
        dimensions=dimensions,
        dimension_labels=dimension_labels,
        joins=[],
        filters=[],
        group_by=dimensions,
        order_by=order_by,
        limit=limit,
        chart_type=chart_type,
        explanation=[f"{metric_label} plan"],
        ast_json={},
        planner_notes=[],
        clarification_reasons=[],
    )


def sample_block(
    *,
    block_key: str,
    title: str,
    rows: list[dict],
    sql_plan: SqlPlan,
    mode: str = "aggregate",
    config: dict | None = None,
) -> ExecutedAnswerBlock:
    spec = AnswerQuerySpec(
        block_key=block_key,
        title=title,
        mode=mode,
        interpretation=Interpretation(intent="analytics", metric=sql_plan.metric, dimensions=list(sql_plan.dimensions), filters={}, date_range={"kind": "between_dates", "label": "2026-04-01..2026-04-07"}, limit=sql_plan.limit),
        reason=title,
        optional=block_key != "primary_kpi",
        config=config or {},
    )
    compiled = CompiledAnswerQuery(
        sql_plan=sql_plan,
        rendered_sql=f"SELECT * FROM sample_{block_key}",
        planner_payload={"block_key": block_key},
        source_tables={"fact.orders"},
        column_references=[{"table_alias": "fo", "column_name": "order_id"}],
    )
    validation = GuardrailDecision(
        ok=True,
        sql=compiled.rendered_sql,
        message="ok",
        logs=[],
        validated_sql=ValidatedSQL(
            sql=compiled.rendered_sql,
            tables={"fact.orders"},
            row_limit=sql_plan.limit,
            explain_plan={},
            explain_cost=11.0,
        ),
    )
    return ExecutedAnswerBlock(
        spec=spec,
        compiled=compiled,
        validation=validation,
        rows=rows,
        execution_ms=42,
        cached=False,
        execution_mode="database",
        fingerprint=f"{block_key}_fingerprint",
    )


class Stage3ClassifierTests(unittest.TestCase):
    def test_classifier_selects_all_answer_types(self) -> None:
        cases = [
            ("what does status_tender mean", retrieval_for(metric_key="revenue"), "chat_help"),
            ("how many completed trips last week", retrieval_for(metric_key="completed_trips"), "single_value"),
            ("top cities by revenue", retrieval_for(metric_key="revenue", dimension_keys=["city"], chart_type="bar"), "comparison_top"),
            ("show revenue by day over time", retrieval_for(metric_key="revenue", dimension_keys=["day"], chart_type="line"), "trend"),
            ("revenue share by city", retrieval_for(metric_key="revenue", dimension_keys=["city"], chart_type="bar"), "distribution"),
            ("show list of latest orders", retrieval_for(metric_key="completed_trips"), "table"),
            ("full report for revenue this month", retrieval_for(metric_key="revenue", dimension_keys=["city", "day"], chart_type="bar"), "full_report"),
        ]

        for question, retrieval, expected in cases:
            with self.subTest(question=question, expected=expected):
                decision = classify_answer_type(question=question, chat_context={}, retrieval=retrieval)
                self.assertEqual(decision.answer_type_key, expected)


class Stage3PlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = sample_catalog()

    def test_single_value_strategy_adds_previous_period_baseline(self) -> None:
        interpretation = Interpretation(
            intent="analytics",
            metric="completed_trips",
            dimensions=["city"],
            filters={},
            date_range={"kind": "between_dates", "start": "2026-04-01", "end": "2026-04-07", "label": "2026-04-01..2026-04-07"},
            limit=10,
        )
        plan = build_answer_plan(
            decision=decision_for("single_value"),
            interpretation=interpretation,
            retrieval=retrieval_for(metric_key="completed_trips"),
            catalog=self.catalog,
        )

        self.assertEqual(plan.primary_spec.mode, "aggregate")
        self.assertEqual(plan.primary_spec.interpretation.dimensions, [])
        self.assertEqual(plan.primary_spec.interpretation.limit, 1)
        self.assertIn("previous_period", [item.block_key for item in plan.secondary_specs])

    def test_type_specific_strategies_change_sql_shape(self) -> None:
        cases = [
            ("comparison_top", Interpretation(intent="analytics", metric="revenue", dimensions=[], filters={}, date_range={"kind": "between_dates", "start": "2026-04-01", "end": "2026-04-07", "label": "April"}), "aggregate", ["city"]),
            ("trend", Interpretation(intent="analytics", metric="revenue", dimensions=[], filters={}, date_range={"kind": "between_dates", "start": "2026-04-01", "end": "2026-04-07", "label": "April"}), "aggregate", ["day"]),
            ("distribution", Interpretation(intent="analytics", metric="revenue", dimensions=[], filters={}, date_range={"kind": "between_dates", "start": "2026-04-01", "end": "2026-04-07", "label": "April"}), "aggregate", ["city"]),
            ("table", Interpretation(intent="analytics", metric="completed_trips", dimensions=[], filters={}, date_range={"kind": "between_dates", "start": "2026-04-01", "end": "2026-04-07", "label": "April"}), "record", []),
        ]

        for answer_type_key, interpretation, mode, expected_dimensions in cases:
            with self.subTest(answer_type_key=answer_type_key):
                plan = build_answer_plan(
                    decision=decision_for(answer_type_key),
                    interpretation=interpretation,
                    retrieval=retrieval_for(metric_key=interpretation.metric or "revenue", dimension_keys=["city", "day"], chart_type="line" if answer_type_key == "trend" else "bar"),
                    catalog=self.catalog,
                )
                self.assertEqual(plan.primary_spec.mode, mode)
                if expected_dimensions:
                    self.assertEqual(plan.primary_spec.interpretation.dimensions, expected_dimensions)

        report_plan = build_answer_plan(
            decision=decision_for("full_report"),
            interpretation=Interpretation(intent="analytics", metric="revenue", dimensions=[], filters={}, date_range={"kind": "between_dates", "start": "2026-04-01", "end": "2026-04-07", "label": "April"}),
            retrieval=retrieval_for(metric_key="revenue", dimension_keys=["city", "day"], chart_type="bar"),
            catalog=self.catalog,
        )
        self.assertEqual(report_plan.primary_spec.block_key, "headline_kpi")
        self.assertIn("report_trend", [item.block_key for item in report_plan.secondary_specs])
        self.assertIn("report_comparison", [item.block_key for item in report_plan.secondary_specs])
        self.assertIn("report_records", [item.block_key for item in report_plan.secondary_specs])


class Stage3PayloadTests(unittest.TestCase):
    def test_successful_answer_requires_typed_render_payload(self) -> None:
        decision = decision_for("trend")

        with self.assertRaisesRegex(RuntimeError, "typed render_payload"):
            build_answer_envelope(
                question="show revenue by day",
                decision=decision,
                interpretation=Interpretation(
                    intent="analytics",
                    metric="revenue",
                    dimensions=["day"],
                    filters={},
                    date_range={"kind": "between_dates", "label": "April"},
                ),
                confidence=ConfidenceResult(score=95, band="high", reasons=[], ambiguities=[]),
                executed_plan=None,
                status="success",
            )

    def test_single_value_payload_contains_real_delta(self) -> None:
        primary = sample_block(
            block_key="primary_kpi",
            title="Headline KPI",
            rows=[{"completed_trips": 120}],
            sql_plan=sample_sql_plan(metric="completed_trips", metric_label="Completed Trips", dimensions=[], order_by="completed_trips DESC", limit=1, chart_type="table_only"),
        )
        baseline = sample_block(
            block_key="previous_period",
            title="Previous Period",
            rows=[{"completed_trips": 96}],
            sql_plan=sample_sql_plan(metric="completed_trips", metric_label="Completed Trips", dimensions=[], order_by="completed_trips DESC", limit=1, chart_type="table_only"),
        )
        decision = decision_for("single_value")
        executed = ExecutedAnswerPlan(
            decision=decision,
            primary_block=primary,
            blocks={"primary_kpi": primary, "previous_period": baseline},
            failures={},
            total_execution_ms=84,
        )

        envelope = build_answer_envelope(
            question="how many completed trips",
            decision=decision,
            interpretation=primary.spec.interpretation,
            confidence=ConfidenceResult(score=96, band="high", reasons=[], ambiguities=[]),
            executed_plan=executed,
            status="success",
        )

        self.assertEqual(envelope.render_payload.kind, "single_value")
        self.assertEqual(envelope.render_payload.current_value, 120)
        self.assertEqual(envelope.render_payload.previous_value, 96)
        self.assertEqual(envelope.render_payload.delta_abs, 24.0)
        self.assertEqual(envelope.render_payload.delta_pct, 25.0)

    def test_comparison_payload_and_switching_contract(self) -> None:
        primary = sample_block(
            block_key="comparison",
            title="Comparison",
            rows=[{"city": "Tokyo", "revenue": 300}, {"city": "Osaka", "revenue": 220}],
            sql_plan=sample_sql_plan(dimensions=["city"], dimension_labels={"city": "City"}, chart_type="bar"),
        )
        decision = decision_for("comparison_top")
        executed = ExecutedAnswerPlan(decision=decision, primary_block=primary, blocks={"comparison": primary}, failures={}, total_execution_ms=42)
        envelope = build_answer_envelope(
            question="top cities by revenue",
            decision=decision,
            interpretation=primary.spec.interpretation,
            confidence=ConfidenceResult(score=94, band="high", reasons=[], ambiguities=[]),
            executed_plan=executed,
            status="success",
        )

        self.assertEqual(envelope.render_payload.kind, "comparison_top")
        self.assertEqual(envelope.render_payload.items[0].label, "Tokyo")
        self.assertTrue(envelope.compatibility_info.can_switch_without_requery)
        self.assertIn("table", envelope.compatibility_info.compatible_view_modes)
        self.assertIn("report", envelope.compatibility_info.requery_required_for_views)

    def test_trend_payload_uses_time_series_and_honest_switch_rules(self) -> None:
        primary = sample_block(
            block_key="trend",
            title="Trend",
            rows=[{"day": "2026-04-01", "revenue": 100}, {"day": "2026-04-02", "revenue": 180}],
            sql_plan=sample_sql_plan(dimensions=["day"], dimension_labels={"day": "Day"}, order_by="day ASC", chart_type="line"),
        )
        decision = decision_for("trend")
        executed = ExecutedAnswerPlan(decision=decision, primary_block=primary, blocks={"trend": primary}, failures={}, total_execution_ms=42)
        envelope = build_answer_envelope(
            question="revenue by day",
            decision=decision,
            interpretation=primary.spec.interpretation,
            confidence=ConfidenceResult(score=95, band="high", reasons=[], ambiguities=[]),
            executed_plan=executed,
            status="success",
        )

        self.assertEqual(envelope.render_payload.kind, "trend")
        self.assertEqual(envelope.render_payload.peak.label, "2026-04-02")
        table_switch = next(item for item in envelope.switch_options if item.view_mode == "table")
        report_switch = next(item for item in envelope.switch_options if item.view_mode == "report")
        self.assertTrue(table_switch.can_switch_without_requery)
        self.assertTrue(report_switch.requery_required)

    def test_distribution_payload_collapses_tail_into_other(self) -> None:
        primary = sample_block(
            block_key="distribution",
            title="Distribution",
            rows=[
                {"city": "A", "revenue": 50},
                {"city": "B", "revenue": 30},
                {"city": "C", "revenue": 10},
                {"city": "D", "revenue": 5},
                {"city": "E", "revenue": 3},
                {"city": "F", "revenue": 1},
                {"city": "G", "revenue": 1},
            ],
            sql_plan=sample_sql_plan(dimensions=["city"], dimension_labels={"city": "City"}, chart_type="bar"),
            config={"visible_item_limit": 5},
        )
        decision = decision_for("distribution")
        executed = ExecutedAnswerPlan(decision=decision, primary_block=primary, blocks={"distribution": primary}, failures={}, total_execution_ms=42)
        envelope = build_answer_envelope(
            question="revenue share by city",
            decision=decision,
            interpretation=primary.spec.interpretation,
            confidence=ConfidenceResult(score=92, band="high", reasons=[], ambiguities=[]),
            executed_plan=executed,
            status="success",
        )

        self.assertEqual(envelope.render_payload.kind, "distribution")
        self.assertTrue(envelope.render_payload.other_bucket_applied)
        self.assertEqual(envelope.render_payload.items[-1].label, "Other")

    def test_table_payload_is_row_level_and_server_ready(self) -> None:
        primary = sample_block(
            block_key="records",
            title="Records",
            rows=[{"order_id": "ord-1", "status_order": "done"}, {"order_id": "ord-2", "status_order": "cancelled"}],
            sql_plan=sample_sql_plan(metric="completed_trips", metric_label="Completed Trips", dimensions=[], order_by="fo.order_timestamp DESC", limit=26, chart_type="table_only"),
            mode="record",
            config={"page_size": 25, "page_offset": 0},
        )
        decision = decision_for("table")
        executed = ExecutedAnswerPlan(decision=decision, primary_block=primary, blocks={"records": primary}, failures={}, total_execution_ms=42)
        envelope = build_answer_envelope(
            question="show list of latest orders",
            decision=decision,
            interpretation=primary.spec.interpretation,
            confidence=ConfidenceResult(score=91, band="high", reasons=[], ambiguities=[]),
            executed_plan=executed,
            status="success",
        )

        self.assertEqual(envelope.render_payload.kind, "table")
        self.assertEqual(envelope.render_payload.pagination_mode, "server_ready")
        self.assertEqual(envelope.render_payload.page_size, 25)
        self.assertEqual(envelope.primary_view_mode, "table")
        self.assertFalse(envelope.compatibility_info.can_switch_without_requery)

    def test_full_report_payload_contains_multi_block_sections(self) -> None:
        headline = sample_block(
            block_key="headline_kpi",
            title="Headline",
            rows=[{"revenue": 900}],
            sql_plan=sample_sql_plan(metric="revenue", metric_label="Revenue", dimensions=[], order_by="revenue DESC", limit=1, chart_type="table_only"),
        )
        previous = sample_block(
            block_key="previous_period",
            title="Previous",
            rows=[{"revenue": 750}],
            sql_plan=sample_sql_plan(metric="revenue", metric_label="Revenue", dimensions=[], order_by="revenue DESC", limit=1, chart_type="table_only"),
        )
        trend = sample_block(
            block_key="report_trend",
            title="Trend",
            rows=[{"day": "2026-04-01", "revenue": 100}, {"day": "2026-04-02", "revenue": 200}],
            sql_plan=sample_sql_plan(dimensions=["day"], dimension_labels={"day": "Day"}, order_by="day ASC", chart_type="line"),
        )
        comparison = sample_block(
            block_key="report_comparison",
            title="Comparison",
            rows=[{"city": "Tokyo", "revenue": 500}, {"city": "Osaka", "revenue": 400}],
            sql_plan=sample_sql_plan(dimensions=["city"], dimension_labels={"city": "City"}, chart_type="bar"),
        )
        records = sample_block(
            block_key="report_records",
            title="Records",
            rows=[{"order_id": "ord-1", "status_order": "done"}],
            sql_plan=sample_sql_plan(metric="revenue", metric_label="Revenue", dimensions=[], order_by="fo.order_timestamp DESC", limit=9, chart_type="table_only"),
            mode="record",
            config={"page_size": 8, "page_offset": 0},
        )
        decision = decision_for("full_report")
        executed = ExecutedAnswerPlan(
            decision=decision,
            primary_block=headline,
            blocks={
                "headline_kpi": headline,
                "previous_period": previous,
                "report_trend": trend,
                "report_comparison": comparison,
                "report_records": records,
            },
            failures={},
            total_execution_ms=210,
        )
        envelope = build_answer_envelope(
            question="full report for revenue",
            decision=decision,
            interpretation=headline.spec.interpretation,
            confidence=ConfidenceResult(score=97, band="high", reasons=[], ambiguities=[]),
            executed_plan=executed,
            status="success",
            notes=["Comparison section is included."],
        )

        self.assertEqual(envelope.render_payload.kind, "full_report")
        section_kinds = [section.kind for section in envelope.render_payload.sections]
        self.assertIn("insight", section_kinds)
        self.assertIn("chart", section_kinds)
        self.assertIn("table", section_kinds)
        self.assertEqual(envelope.primary_view_mode, "report")

        chart_switch = next(item for item in envelope.switch_options if item.view_mode == "chart")
        number_switch = next(item for item in envelope.switch_options if item.view_mode == "number")
        table_switch = next(item for item in envelope.switch_options if item.view_mode == "table")
        chat_switch = next(item for item in envelope.switch_options if item.view_mode == "chat")
        self.assertTrue(chart_switch.can_switch_without_requery)
        self.assertTrue(number_switch.can_switch_without_requery)
        self.assertTrue(table_switch.can_switch_without_requery)
        self.assertTrue(chat_switch.requery_required)


if __name__ == "__main__":
    unittest.main()
