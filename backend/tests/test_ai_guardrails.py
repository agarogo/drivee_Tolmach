import unittest

from app.ai.confidence import score_confidence
from app.ai.answer import compose_answer
from app.ai.generator import generate_sql
from app.ai.interpreter import interpret_query
from app.ai.planner import build_plan
from app.ai.types import ConfidenceResult, RetrievalResult
from app.services.guardrails import GuardrailError, _log, ensure_safe_sql


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

    def test_sql_generator_uses_readonly_marts_and_limit(self) -> None:
        interpretation = interpret_query("покажи выручку по топ-10 городам за последние 30 дней")
        plan = build_plan(interpretation, RetrievalResult([], [], []))
        sql = generate_sql(plan, interpretation).lower()
        self.assertIn("from mart_orders", sql)
        self.assertIn("join cities", sql)
        self.assertIn("limit 10", sql)
        self.assertNotIn("delete", sql)

    def test_total_trips_since_absolute_date_is_accepted(self) -> None:
        interpretation = interpret_query("сколько было всего поездок с 2025-11-18")
        self.assertEqual(interpretation.metric, "completed_trips")
        self.assertEqual(interpretation.dimensions, [])
        self.assertEqual(interpretation.date_range["kind"], "since_date")
        self.assertEqual(interpretation.date_range["start"], "2025-11-18")
        confidence = score_confidence(interpretation, RetrievalResult([], [], []))
        self.assertEqual(confidence.band, "high")
        plan = build_plan(interpretation, RetrievalResult([], [], []))
        sql = generate_sql(plan, interpretation).lower()
        self.assertIn("from mart_orders", sql)
        self.assertIn("date '2025-11-18'", sql)
        self.assertIn("count(distinct mo.order_id)", sql)
        self.assertNotIn("join cities", sql)
        self.assertNotIn("group by", sql)

    def test_guardrail_warning_log_keeps_message_string_and_details_json(self) -> None:
        log = _log("column_whitelist", "warning", "warning", "Колонка может быть алиасом.", {"columns": ["active_drivers"]})
        self.assertEqual(log["message"], "Колонка может быть алиасом.")
        self.assertEqual(log["details"], {"columns": ["active_drivers"]})

    def test_total_answer_mentions_requested_metric_value(self) -> None:
        interpretation = interpret_query("сколько было всего поездок с 2025-11-18")
        plan = build_plan(interpretation, RetrievalResult([], [], []))
        answer = compose_answer(
            "сколько было всего поездок с 2025-11-18",
            interpretation,
            ConfidenceResult(score=100, band="high", reasons=[], ambiguities=[]),
            plan,
            [{"completed_trips": 174528}],
        )
        self.assertIn("поездки за период с 2025-11-18: 174528", answer)
        self.assertIn("разрез = без разреза", answer)

    def test_active_drivers_use_fact_mart_not_demo_driver_directory(self) -> None:
        interpretation = interpret_query("сколько активных водителей по городам")
        plan = build_plan(interpretation, RetrievalResult([], [], []))
        sql = generate_sql(plan, interpretation).lower()
        self.assertIn("from mart_orders", sql)
        self.assertIn("count(distinct mo.driver_id)", sql)
        self.assertNotIn("from drivers", sql)

    def test_legacy_guardrail_blocks_write_sql(self) -> None:
        with self.assertRaises(GuardrailError):
            ensure_safe_sql("DELETE FROM drivers WHERE rating < 3.5")

    def test_legacy_guardrail_injects_limit(self) -> None:
        sql, notes = ensure_safe_sql("SELECT city_id FROM orders")
        self.assertIn("LIMIT", sql)
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
