import unittest
from unittest.mock import AsyncMock, patch

from app.ai.gateway.providers import LLMCallTelemetry, LLMStructuredResponse
from app.ai.gateway.schemas import IntentExtractionResult, PeriodSelection
from app.ai.gateway.service import GatewayStageResult
from app.ai.llm_interpreter import interpret_with_ai
from app.ai.semantic_compiler import compile_sql_query
from app.ai.types import Interpretation, RetrievalResult
from app.models import AccessPolicy
from app.semantic.service import SemanticCatalog, SemanticDimensionDefinition, SemanticMetricDefinition
from app.services.guardrails import validate_sql


def build_catalog() -> SemanticCatalog:
    revenue = SemanticMetricDefinition(
        metric_key="revenue",
        business_name="Выручка",
        description="Сумма price_order_local по завершенным заказам.",
        sql_expression_template="SUM({base_alias}.price_order_local) FILTER (WHERE {base_alias}.status_order = 'done')",
        grain="order",
        allowed_dimensions=["city", "day"],
        allowed_filters=["city", "day"],
        default_chart="bar",
        safety_tags=["finance"],
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
    return SemanticCatalog(metrics={"revenue": revenue}, dimensions=dimensions, filters=dict(dimensions))


def build_intent_stage(*, fallback_used: bool = False) -> GatewayStageResult[IntentExtractionResult]:
    result = IntentExtractionResult(
        metric_key="revenue",
        dimension_keys=["city"],
        filters=[],
        period=PeriodSelection(kind="rolling_days", days=30, label="последние 30 дней"),
        limit=10,
        sort_direction="desc",
        ambiguities=[],
        confidence=0.93,
        reasoning="Question clearly asks for revenue by city.",
    )
    return GatewayStageResult(
        structured=result,
        response=LLMStructuredResponse(
            result=result,
            raw_text=result.model_dump_json(),
            provider="fallback" if fallback_used else "ollama",
            model="deterministic-v1" if fallback_used else "qwen",
            telemetry=LLMCallTelemetry(
                provider="fallback" if fallback_used else "ollama",
                model="deterministic-v1" if fallback_used else "qwen",
                prompt_key="intent_extraction",
                prompt_version="v1",
                duration_ms=14,
                attempts=1,
                timeout_seconds=60,
                fallback_used=fallback_used,
                initial_provider="ollama" if fallback_used else "",
                fallback_reason="provider unavailable" if fallback_used else "",
            ),
        ),
    )


class SemanticCompilerTests(unittest.TestCase):
    def test_compiler_generates_controlled_sql_from_catalog(self) -> None:
        interpretation = Interpretation(
            intent="analytics",
            metric="revenue",
            dimensions=["city"],
            date_range={"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
            limit=10,
            source="llm_structured",
            provider_confidence=0.95,
        )
        plan, sql = compile_sql_query(interpretation, RetrievalResult([], [], []), build_catalog())
        lowered = sql.lower()
        self.assertEqual(plan.metric, "revenue")
        self.assertEqual(plan.metric_label, "Выручка")
        self.assertTrue(plan.ast_json)
        self.assertIn("from fact.orders as fo", lowered)
        self.assertIn("join dim.cities as dim_city on dim_city.city_id = fo.city_id", lowered)
        self.assertIn("sum(fo.price_order_local)", lowered)
        self.assertIn("limit 10", lowered)
        self.assertNotIn("select *", lowered)

    def test_compiler_escapes_filter_values(self) -> None:
        interpretation = Interpretation(
            intent="analytics",
            metric="revenue",
            dimensions=["city"],
            filters={"city": {"operator": "eq", "values": ["O'Reilly"]}},
            date_range={"kind": "rolling_days", "days": 7, "label": "последние 7 дней"},
            limit=5,
            source="llm_structured",
            provider_confidence=0.9,
        )
        _, sql = compile_sql_query(interpretation, RetrievalResult([], [], []), build_catalog())
        self.assertIn("O''Reilly", sql)


class LLMInterpreterTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.ai.llm_interpreter.extract_intent_with_ai", new_callable=AsyncMock)
    async def test_interpret_with_ai_uses_structured_llm_output(self, mocked_extract: AsyncMock) -> None:
        mocked_extract.return_value = build_intent_stage()
        interpretation = await interpret_with_ai(
            "Покажи выручку по городам за последние 30 дней",
            RetrievalResult([], [], []),
            build_catalog(),
        )
        self.assertTrue(interpretation.source.startswith("llm_gateway:intent_extraction@"))
        self.assertFalse(interpretation.fallback_used)
        self.assertEqual(interpretation.metric, "revenue")
        self.assertEqual(interpretation.dimensions, ["city"])

    @patch("app.ai.llm_interpreter.extract_intent_with_ai", new_callable=AsyncMock)
    async def test_interpret_with_ai_marks_fallback_when_provider_fails(self, mocked_extract: AsyncMock) -> None:
        mocked_extract.return_value = build_intent_stage(fallback_used=True)
        interpretation = await interpret_with_ai(
            "Покажи выручку по городам за последние 30 дней",
            RetrievalResult([], [], []),
            build_catalog(),
        )
        self.assertTrue(interpretation.fallback_used)
        self.assertTrue(interpretation.source.startswith("llm_gateway:intent_extraction@"))
        self.assertEqual(interpretation.metric, "revenue")


class GuardrailExplainTests(unittest.IsolatedAsyncioTestCase):
    async def test_validate_sql_keeps_explain_metadata(self) -> None:
        policy = AccessPolicy(
            role="user",
            table_name="fact.orders",
            allowed_columns_json=["order_id", "city_id", "order_timestamp", "price_order_local", "status_order"],
            row_limit=1000,
            is_active=True,
        )
        with patch("app.services.guardrails._load_policies", new=AsyncMock(return_value={"fact.orders": policy})):
            with patch(
                "app.services.guardrails._run_explain_plan",
                new=AsyncMock(return_value=({"Plan": {"Total Cost": 123.45}}, 123.45)),
            ):
                decision = await validate_sql(
                    AsyncMock(),
                    "SELECT fo.order_id AS order_id FROM fact.orders fo LIMIT 10",
                    role="user",
                )
        self.assertTrue(decision.ok)
        self.assertAlmostEqual(decision.validated_sql.explain_cost, 123.45)
        self.assertEqual(decision.validated_sql.explain_plan["Plan"]["Total Cost"], 123.45)
        self.assertTrue(decision.validated_sql.ast_json)

    async def test_validate_sql_blocks_high_explain_cost(self) -> None:
        policy = AccessPolicy(
            role="user",
            table_name="fact.orders",
            allowed_columns_json=["order_id", "city_id", "order_timestamp", "price_order_local", "status_order"],
            row_limit=1000,
            is_active=True,
        )
        with patch("app.services.guardrails._load_policies", new=AsyncMock(return_value={"fact.orders": policy})):
            with patch(
                "app.services.guardrails._run_explain_plan",
                new=AsyncMock(return_value=({"Plan": {"Total Cost": 9999999.0}}, 9999999.0)),
            ):
                decision = await validate_sql(
                    AsyncMock(),
                    "SELECT fo.order_id AS order_id FROM fact.orders fo LIMIT 10",
                    role="user",
                )
        self.assertFalse(decision.ok)
        self.assertEqual(decision.block_reasons[0]["code"], "explain_cost_exceeded")


if __name__ == "__main__":
    unittest.main()
