import unittest

from app.ai.answer import compose_answer
from app.ai.confidence import score_confidence
from app.ai.interpreter import interpret_query
from app.ai.semantic_compiler import compile_sql_query
from app.ai.types import ConfidenceResult, RetrievalResult
from app.semantic.service import SemanticCatalog, SemanticDimensionDefinition, SemanticMetricDefinition
from app.services.guardrails import GuardrailError, _log, ensure_safe_sql


def build_catalog() -> SemanticCatalog:
    metric = SemanticMetricDefinition(
        metric_key="completed_trips",
        business_name="Завершённые поездки",
        description="Done orders.",
        sql_expression_template="COUNT(DISTINCT {base_alias}.order_id) FILTER (WHERE {base_alias}.status_order = 'done')",
        grain="order",
        allowed_dimensions=["city", "day"],
        allowed_filters=["city", "day"],
        default_chart="bar",
        safety_tags=["count"],
    )
    city = SemanticDimensionDefinition(
        dimension_key="city",
        business_name="Город",
        table_name="dim.cities",
        column_name="city_name",
        join_path="JOIN dim.cities {dimension_alias} ON {dimension_alias}.city_id = {base_alias}.city_id",
        data_type="string",
    )
    day = SemanticDimensionDefinition(
        dimension_key="day",
        business_name="День",
        table_name="__grain__",
        column_name="{time_dimension_column}",
        join_path="",
        data_type="date",
    )
    dimensions = {"city": city, "day": day}
    return SemanticCatalog(metrics={"completed_trips": metric}, dimensions=dimensions, filters=dict(dimensions))


class AiGuardrailsTests(unittest.TestCase):
    def test_interpreter_detects_dangerous_write_intent(self) -> None:
        interpretation = interpret_query("удали всех водителей с рейтингом ниже 3.5")
        self.assertTrue(interpretation.dangerous)
        self.assertEqual(interpretation.intent, "dangerous_operation")

    def test_confidence_high_for_clear_revenue_query(self) -> None:
        interpretation = interpret_query("покажи выручку по топ-10 городам за последние 30 дней")
        retrieval = RetrievalResult(
            semantic_terms=[{"term": "выручка"}, {"term": "город"}, {"term": "день"}],
            templates=[{"title": "Отчёт по городам"}],
            examples=[{"title": "Revenue by city"}],
        )
        confidence = score_confidence(interpretation, retrieval)
        self.assertGreaterEqual(confidence.score, 85)
        self.assertEqual(confidence.band, "high")

    def test_compiler_uses_catalog_not_demo_tables(self) -> None:
        interpretation = interpret_query("сколько было всего поездок с 2025-11-18")
        interpretation.metric = "completed_trips"
        interpretation.dimensions = []
        plan, sql = compile_sql_query(interpretation, RetrievalResult([], [], []), build_catalog())
        lowered = sql.lower()
        self.assertIn("from fact.orders as fo", lowered)
        self.assertIn("count(distinct fo.order_id)", lowered)
        self.assertNotIn("mart_orders", lowered)
        self.assertEqual(plan.metric_label, "Завершённые поездки")

    def test_guardrail_warning_log_keeps_message_string_and_details_json(self) -> None:
        log = _log("column_whitelist", "warning", "warning", "Колонка может быть алиасом.", {"columns": ["active_drivers"]})
        self.assertEqual(log["message"], "Колонка может быть алиасом.")
        self.assertEqual(log["details"], {"columns": ["active_drivers"]})

    def test_total_answer_mentions_requested_metric_value(self) -> None:
        interpretation = interpret_query("сколько было всего поездок с 2025-11-18")
        interpretation.metric = "completed_trips"
        plan, _ = compile_sql_query(interpretation, RetrievalResult([], [], []), build_catalog())
        answer = compose_answer(
            "сколько было всего поездок с 2025-11-18",
            interpretation,
            ConfidenceResult(score=100, band="high", reasons=[], ambiguities=[]),
            plan,
            [{"completed_trips": 174528}],
        )
        self.assertIn("Завершённые поездки за период с 2025-11-18: 174528", answer)
        self.assertIn("разрез = без разреза", answer)

    def test_legacy_guardrail_blocks_write_sql(self) -> None:
        with self.assertRaises(GuardrailError):
            ensure_safe_sql("DELETE FROM drivers WHERE rating < 3.5")

    def test_legacy_guardrail_injects_limit(self) -> None:
        sql, notes = ensure_safe_sql("SELECT city_id FROM fact.orders")
        self.assertIn("LIMIT", sql)
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
