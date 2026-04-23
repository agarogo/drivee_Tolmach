import unittest

from app.ai.gateway.prompts import PromptRegistry
from app.ai.gateway.providers import (
    FallbackRuleProvider,
    LLMProviderError,
    extract_json_payload,
    parse_structured_response,
)
from app.ai.gateway.schemas import IntentExtractionResult, PeriodSelection
from app.ai.gateway.service import AIGateway
from app.ai.types import Interpretation, RetrievalResult
from app.semantic.service import SemanticCatalog, SemanticDimensionDefinition, SemanticMetricDefinition


def build_catalog() -> SemanticCatalog:
    revenue = SemanticMetricDefinition(
        metric_key="revenue",
        business_name="Выручка",
        description="Сумма price_order_local по завершённым заказам.",
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


class BrokenProvider:
    provider_name = "broken"
    model_name = "broken-model"

    async def generate_structured(self, prompt, schema):
        raise LLMProviderError("synthetic upstream failure")


class AIGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_falls_back_and_preserves_failover_reason(self) -> None:
        gateway = AIGateway(primary_provider=BrokenProvider(), fallback_provider=FallbackRuleProvider())
        result = await gateway.extract_intent(
            "Покажи выручку по городам за последние 30 дней",
            RetrievalResult([], [], []),
            build_catalog(),
        )
        self.assertEqual(result.response.provider, "fallback_rule")
        self.assertTrue(result.response.telemetry.fallback_used)
        self.assertEqual(result.response.telemetry.initial_provider, "broken")
        self.assertIn("synthetic upstream failure", result.response.telemetry.fallback_reason)
        self.assertEqual(result.structured.metric_key, "revenue")

    async def test_fallback_plan_uses_resolved_interpretation_context(self) -> None:
        gateway = AIGateway(primary_provider=FallbackRuleProvider(), fallback_provider=FallbackRuleProvider())
        interpretation = Interpretation(
            intent="analytics",
            metric="revenue",
            dimensions=["city"],
            filters={},
            date_range={"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
            sorting={"by": "revenue", "direction": "desc"},
            limit=10,
            reasoning="resolved intent",
            provider_confidence=0.84,
        )
        result = await gateway.draft_sql_plan(
            "Покажи выручку по городам за последние 30 дней",
            RetrievalResult([], [], []),
            build_catalog(),
            interpretation,
        )
        self.assertEqual(result.structured.metric_key, "revenue")
        self.assertEqual(result.structured.dimension_keys, ["city"])
        self.assertEqual(result.structured.period.kind, "rolling_days")
        self.assertEqual(result.structured.chart_preference, "bar")


class PromptRegistryTests(unittest.TestCase):
    def test_prompt_registry_loads_latest_prompt_version(self) -> None:
        registry = PromptRegistry()
        prompt = registry.get("intent_extraction")
        system_prompt, user_prompt = prompt.render(
            {
                "question": "Покажи выручку",
                "catalog_summary_json": "{}",
                "matched_semantic_terms_json": "[]",
                "templates_json": "[]",
                "examples_json": "[]",
            }
        )
        self.assertEqual(prompt.version, "v1")
        self.assertIn("Return exactly one JSON object", system_prompt)
        self.assertIn("Покажи выручку", user_prompt)


class JsonParsingTests(unittest.TestCase):
    def test_extract_json_payload_rejects_non_object_json(self) -> None:
        with self.assertRaises(LLMProviderError):
            extract_json_payload('["not-an-object"]')

    def test_parse_structured_response_accepts_strict_valid_json(self) -> None:
        payload = parse_structured_response(
            """
            {
              "metric_key": "revenue",
              "dimension_keys": ["city"],
              "filters": [],
              "period": {"kind": "rolling_days", "days": 30, "start": null, "end": null, "date": null, "label": "последние 30 дней"},
              "limit": 10,
              "sort_direction": "desc",
              "ambiguities": [],
              "confidence": 0.91,
              "reasoning": "clear request"
            }
            """,
            IntentExtractionResult,
        )
        self.assertEqual(payload.metric_key, "revenue")
        self.assertEqual(payload.period, PeriodSelection(kind="rolling_days", days=30, label="последние 30 дней"))

    def test_parse_structured_response_rejects_invalid_schema(self) -> None:
        with self.assertRaises(LLMProviderError):
            parse_structured_response(
                '{"metric_key":"revenue","dimension_keys":["city"],"filters":[],"period":{"kind":"rolling_days","days":"30","label":"x"},"limit":10,"sort_direction":"desc","ambiguities":[],"confidence":0.9,"reasoning":"x"}',
                IntentExtractionResult,
            )


if __name__ == "__main__":
    unittest.main()
