import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.ai.semantic_compiler import compile_sql_query_bundle
from app.ai.types import Interpretation, RetrievalResult
from app.models import AccessPolicy
from app.semantic.errors import SemanticCompilationError
from app.semantic.service import SemanticCatalog, SemanticDimensionDefinition, SemanticMetricDefinition
from app.services.guardrails import ValidatedSQL, validate_sql
from app.query_execution.fingerprint import build_query_fingerprint
from app.services.query_runner import execute_validated_query, execute_validated_select


def build_catalog() -> SemanticCatalog:
    revenue = SemanticMetricDefinition(
        metric_key="revenue",
        business_name="Revenue",
        description="Sum of completed order revenue.",
        sql_expression_template="SUM({base_alias}.price_order_local) FILTER (WHERE {base_alias}.status_order = 'done')",
        grain="order",
        allowed_dimensions=["city", "day"],
        allowed_filters=["city", "day"],
        default_chart="bar",
        safety_tags=["finance"],
    )
    city = SemanticDimensionDefinition(
        dimension_key="city",
        business_name="City",
        table_name="dim.cities",
        column_name="city_name",
        join_path="JOIN dim.cities {dimension_alias} ON {dimension_alias}.city_id = {base_alias}.city_id",
        data_type="string",
    )
    day = SemanticDimensionDefinition(
        dimension_key="day",
        business_name="Day",
        table_name="__grain__",
        column_name="{time_dimension_column}",
        join_path="",
        data_type="date",
    )
    driver = SemanticDimensionDefinition(
        dimension_key="driver",
        business_name="Driver",
        table_name="dim.drivers",
        column_name="driver_id",
        join_path="JOIN dim.drivers {dimension_alias} ON {dimension_alias}.driver_id = {base_alias}.driver_id",
        data_type="string",
    )
    dimensions = {"city": city, "day": day, "driver": driver}
    return SemanticCatalog(metrics={"revenue": revenue}, dimensions=dimensions, filters=dict(dimensions))


def build_policies() -> dict[str, AccessPolicy]:
    return {
        "fact.orders": AccessPolicy(
            role="user",
            table_name="fact.orders",
            allowed_columns_json=[
                "order_id",
                "city_id",
                "driver_id",
                "order_timestamp",
                "order_day",
                "price_order_local",
                "status_order",
            ],
            row_limit=500,
            is_active=True,
        ),
        "dim.cities": AccessPolicy(
            role="user",
            table_name="dim.cities",
            allowed_columns_json=["city_id", "city_name"],
            row_limit=500,
            is_active=True,
        ),
    }


class SemanticCompilerBundleTests(unittest.TestCase):
    def test_compile_bundle_creates_ast_and_rendered_sql(self) -> None:
        interpretation = Interpretation(
            intent="analytics",
            metric="revenue",
            dimensions=["city"],
            date_range={"kind": "rolling_days", "days": 30, "label": "last 30 days"},
            limit=25,
            source="llm_structured",
            provider_confidence=0.98,
        )
        artifact = compile_sql_query_bundle(interpretation, RetrievalResult([], [], []), build_catalog())

        self.assertEqual(artifact.sql_plan.metric, "revenue")
        self.assertTrue(artifact.sql_plan.ast_json)
        self.assertIn("fact.orders", artifact.source_tables)
        self.assertIn("dim.cities", artifact.source_tables)
        self.assertIn("SUM(fo.price_order_local)", artifact.rendered_sql)
        self.assertNotIn("SELECT *", artifact.rendered_sql.upper())

    def test_compile_bundle_blocks_dimension_not_allowed_by_metric(self) -> None:
        interpretation = Interpretation(
            intent="analytics",
            metric="revenue",
            dimensions=["driver"],
            date_range={"kind": "rolling_days", "days": 7, "label": "last 7 days"},
            limit=10,
            source="llm_structured",
            provider_confidence=0.92,
        )
        with self.assertRaises(SemanticCompilationError) as context:
            compile_sql_query_bundle(interpretation, RetrievalResult([], [], []), build_catalog())

        self.assertEqual(context.exception.reason.code, "disallowed_dimension")


class SqlValidatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_validator_injects_limit_and_keeps_validator_summary(self) -> None:
        with patch("app.services.guardrails._load_policies", new=AsyncMock(return_value=build_policies())):
            with patch(
                "app.services.guardrails._run_explain_plan",
                new=AsyncMock(return_value=({"Plan": {"Total Cost": 11.5}}, 11.5)),
            ):
                decision = await validate_sql(
                    AsyncMock(),
                    "SELECT fo.order_id AS order_id FROM fact.orders fo",
                    role="user",
                )
        self.assertTrue(decision.ok)
        self.assertIn("LIMIT 500", decision.validated_sql.sql)
        self.assertTrue(decision.validated_sql.validator_summary["logs"])
        self.assertTrue(decision.validated_sql.ast_json)

    async def test_validator_blocks_unknown_column_with_structured_reason(self) -> None:
        with patch("app.services.guardrails._load_policies", new=AsyncMock(return_value=build_policies())):
            with patch(
                "app.services.guardrails._run_explain_plan",
                new=AsyncMock(return_value=({"Plan": {"Total Cost": 11.5}}, 11.5)),
            ):
                decision = await validate_sql(
                    AsyncMock(),
                    "SELECT fo.secret_margin FROM fact.orders fo LIMIT 10",
                    role="user",
                )
        self.assertFalse(decision.ok)
        self.assertEqual(decision.block_reasons[0]["code"], "unknown_column")


class _FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self):
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return self

    async def execute(self, statement):
        rendered = str(statement)
        self.executed.append(rendered)
        if rendered.strip().upper().startswith("SELECT"):
            return _FakeResult([_FakeRow({"city": "Tokyo", "revenue": 123.0})])
        return _FakeResult([])


class _FakeEngine:
    def __init__(self):
        self.connection = _FakeConnection()

    def connect(self):
        return self.connection


class SafeExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_validated_select_uses_read_only_transaction_and_timeouts(self) -> None:
        fake_engine = _FakeEngine()
        validated_sql = ValidatedSQL(
            sql="SELECT city, revenue FROM mart.city_daily LIMIT 1",
            tables={"mart.city_daily"},
            row_limit=1,
            explain_plan={"Plan": {"Total Cost": 1.0}},
            explain_cost=1.0,
        )
        with patch("app.query_execution.service.analytics_engine", fake_engine):
            rows = await execute_validated_select(validated_sql)

        self.assertEqual(rows, [{"city": "Tokyo", "revenue": 123.0}])
        joined = "\n".join(fake_engine.connection.executed)
        self.assertIn("SET TRANSACTION READ ONLY", joined)
        self.assertIn("SET LOCAL statement_timeout", joined)
        self.assertIn("SELECT city, revenue FROM mart.city_daily LIMIT 1", joined)

    async def test_execute_validated_query_reads_from_cache_when_entry_is_fresh(self) -> None:
        validated_sql = ValidatedSQL(
            sql="SELECT city, revenue FROM mart.city_daily LIMIT 1",
            tables={"mart.city_daily"},
            row_limit=1,
            explain_plan={"Plan": {"Node Type": "Limit", "Total Cost": 1.0}},
            explain_cost=1.0,
        )
        cache_entry = AsyncMock()
        cache_entry.expires_at = datetime.now(timezone.utc).replace(year=2099)
        cache_entry.row_count = 1
        cache_entry.hit_count = 0
        cache_entry.explain_cost = 1.0
        cache_entry.explain_plan_json = {"Plan": {"Node Type": "Limit", "Total Cost": 1.0}}
        cache_entry.result_rows_json = [{"city": "Tokyo", "revenue": 123.0}]
        fingerprint = build_query_fingerprint(validated_sql.sql, "user")

        with patch("app.query_execution.service._prune_expired_cache", new=AsyncMock(return_value=0)):
            with patch("app.query_execution.service._get_cache_entry", new=AsyncMock(return_value=cache_entry)) as mocked_cache:
                with patch("app.query_execution.service._record_execution_audit", new=AsyncMock()) as mocked_audit:
                    result = await execute_validated_query(validated_sql, role="user", db=AsyncMock(), use_cache=True)

        mocked_cache.assert_awaited_once()
        mocked_audit.assert_awaited_once()
        self.assertTrue(result.cached)
        self.assertEqual(result.fingerprint, fingerprint)
        self.assertEqual(result.rows, [{"city": "Tokyo", "revenue": 123.0}])


if __name__ == "__main__":
    unittest.main()
