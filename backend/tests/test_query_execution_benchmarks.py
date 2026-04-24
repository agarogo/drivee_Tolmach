import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.query_execution.benchmarks import BENCHMARK_PRESETS, run_benchmark_suite


class QueryExecutionBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_benchmark_suite_covers_required_presets(self) -> None:
        preset_keys = {item.key for item in BENCHMARK_PRESETS}
        self.assertEqual(
            preset_keys,
            {
                "top_10_cities_revenue_30d",
                "daily_kpi_7d",
                "cancellations_by_city",
                "active_drivers_by_city",
                "tender_decline_rate",
            },
        )

    async def test_benchmark_suite_returns_case_payloads(self) -> None:
        fake_compiled = SimpleNamespace(rendered_sql="SELECT 1", planner_result=None, sql_plan=None)
        fake_validation = SimpleNamespace(
            ok=True,
            message="ok",
            validated_sql=SimpleNamespace(
                sql="SELECT 1 LIMIT 1",
                explain_cost=1.0,
                explain_plan={"Plan": {"Node Type": "Limit", "Total Cost": 1.0}},
                validator_summary={"logs": []},
            ),
        )
        fake_result = SimpleNamespace(
            rows=[{"value": 1}],
            row_count=1,
            execution_ms=10,
            cached=False,
            fingerprint="abc123",
            explain_plan={"Plan": {"Node Type": "Limit", "Total Cost": 1.0}},
            explain_cost=1.0,
            execution_mode="database",
        )
        fake_cached_result = SimpleNamespace(
            rows=[{"value": 1}],
            row_count=1,
            execution_ms=0,
            cached=True,
            fingerprint="abc123",
            explain_plan={"Plan": {"Node Type": "Limit", "Total Cost": 1.0}},
            explain_cost=1.0,
            execution_mode="cache",
        )
        with patch("app.query_execution.benchmarks.load_semantic_catalog", new=AsyncMock(return_value=SimpleNamespace())):
            with patch("app.query_execution.benchmarks.compile_sql_query_bundle", return_value=fake_compiled):
                with patch("app.query_execution.benchmarks.validate_sql", new=AsyncMock(return_value=fake_validation)):
                    with patch(
                        "app.query_execution.benchmarks.execute_safe_query",
                        new=AsyncMock(side_effect=[fake_result, fake_cached_result] * len(BENCHMARK_PRESETS)),
                    ):
                        payload = await run_benchmark_suite(AsyncMock(), iterations=2, role="admin")

        self.assertEqual(payload["iterations"], 2)
        self.assertEqual(len(payload["cases"]), len(BENCHMARK_PRESETS))
        self.assertEqual(payload["cases"][0]["fingerprint"], "abc123")


if __name__ == "__main__":
    unittest.main()
